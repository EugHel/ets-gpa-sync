from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

from .ga import int_to_ga
from .models import EtsGroupAddress, GpaDatapoint, SyncCandidate, SyncStatus
from .utils import normalize_name_for_compare


def make_unique_name(base_name: str, used_names: set[str]) -> str:
    """Erzeugt GPA-typische eindeutige Namen: Name, Name (2), Name (3), ..."""
    if base_name not in used_names:
        return base_name
    index = 2
    while True:
        candidate = f"{base_name} ({index})"
        if candidate not in used_names:
            return candidate
        index += 1


def resolve_ets_match(dp: GpaDatapoint, ets_map: Dict[int, EtsGroupAddress]) -> Tuple[Optional[EtsGroupAddress], str, str]:
    """
    Ordnet einen GPA-Datenpunkt einer ETS-Gruppenadresse zu.

    Priorität ab Version 0.20.1:
    - WriteGroupAddress/Senden gewinnt immer vor ReadGroupAddress/Status.
    - Wenn keine WriteGroupAddress vorhanden ist, wird wie bisher auf Eindeutigkeit geprüft.

    Rückgabe: (EtsGroupAddress oder None, Status, Quelle)
    """
    if dp.write_group_address and dp.write_group_address in ets_map:
        return ets_map[dp.write_group_address], SyncStatus.OK, "WriteGroupAddress"

    values = dp.candidate_group_addresses
    matching = [ets_map[v] for v in values if v in ets_map]
    if not matching:
        return None, SyncStatus.KEINE_ETS_GA, ""

    unique_names = sorted({ga.name for ga in matching})
    unique_values = sorted({ga.value for ga in matching})
    if len(unique_values) != 1 or len(unique_names) != 1:
        return None, SyncStatus.MEHRDEUTIG, "mehrere"

    ga = matching[0]
    if dp.read_group_address == ga.value:
        source = "ReadGroupAddress"
    elif ga.value in dp.listener_group_addresses:
        source = "ListenerGroupAddresses"
    else:
        source = "unbekannt"
    return ga, SyncStatus.OK, source


def format_ga_values(values: Sequence[int]) -> str:
    """Formatiert GA-Werte numerisch sortiert als 3-stufige KNX-Adressen."""
    out: List[str] = []
    for value in sorted({v for v in values if v}):
        try:
            out.append(int_to_ga(value))
        except ValueError:
            pass
    return ", ".join(out)


def build_sync_candidates(datapoints: Sequence[GpaDatapoint], ets_map: Dict[int, EtsGroupAddress]) -> List[SyncCandidate]:
    """Erstellt die Änderungsliste."""
    candidates: List[SyncCandidate] = []
    resolved: Dict[str, Tuple[EtsGroupAddress, str]] = {}
    ambiguous_rows: List[SyncCandidate] = []
    not_in_ets_rows: List[SyncCandidate] = []
    conflict_rows: List[SyncCandidate] = []

    # Adress-Konflikt – bitte prüfen: mehrere Datenpunkte tragen DIESELBE write_group_address,
    # die zudem im ETS existiert. Sie würden alle auf denselben ETS-Namen umbenannt.
    # Statt das still über "(N)" aufzulösen, werden sie als Adress-Konflikt markiert.
    # (Write-Duplikate sind meist ein GPA-Fehler, können aber in Randfällen gewollt sein.)
    write_counts = Counter(
        dp.write_group_address for dp in datapoints
        if dp.write_group_address and dp.write_group_address in ets_map
    )
    conflicting_writes = {value for value, count in write_counts.items() if count > 1}

    for dp in datapoints:
        if dp.write_group_address in conflicting_writes:
            ga = ets_map[dp.write_group_address]
            conflict_rows.append(SyncCandidate(
                selected=False,
                status=SyncStatus.ADRESSKONFLIKT,
                zip_path=dp.zip_path,
                current_name=dp.entity_name,
                new_name=ga.name,
                group_address=ga.address,
                group_address_value=ga.value,
                source_field="WriteGroupAddress",
            ))
            continue
        ga, status, source = resolve_ets_match(dp, ets_map)
        if ga is not None:
            resolved[dp.zip_path] = (ga, source)
            continue
        values = dp.candidate_group_addresses
        if status == SyncStatus.MEHRDEUTIG:
            matching = sorted((ets_map[v] for v in values if v in ets_map), key=lambda m: m.value)
            unique_names = sorted({m.name for m in matching})
            first = matching[0] if matching else EtsGroupAddress(address="", value=0, name="")
            ambiguous_rows.append(SyncCandidate(
                selected=False,
                status=SyncStatus.MEHRDEUTIG,
                zip_path=dp.zip_path,
                current_name=dp.entity_name,
                new_name=" / ".join(unique_names),
                group_address=", ".join(m.address for m in matching),
                group_address_value=first.value,
                source_field="mehrere",
            ))
        elif values:
            first_value = sorted(values)[0]
            not_in_ets_rows.append(SyncCandidate(False, SyncStatus.NICHT_IN_ETS, dp.zip_path, dp.entity_name, "", format_ga_values(values), first_value, "GPA"))

    used_names: set[str] = {dp.entity_name for dp in datapoints if dp.zip_path not in resolved}
    for dp in datapoints:
        if dp.zip_path not in resolved:
            continue
        ga, source = resolved[dp.zip_path]
        target_name = make_unique_name(ga.name, used_names)
        used_names.add(target_name)
        if dp.entity_name == target_name:
            continue
        cand_status = SyncStatus.LEERZEICHEN if normalize_name_for_compare(dp.entity_name) == normalize_name_for_compare(target_name) else SyncStatus.AENDERUNG
        candidates.append(SyncCandidate(True, cand_status, dp.zip_path, dp.entity_name, target_name, ga.address, ga.value, source))

    candidates.extend(conflict_rows)
    candidates.extend(ambiguous_rows)
    candidates.extend(not_in_ets_rows)
    return candidates


def build_partial_candidates(
    datapoints: Sequence[GpaDatapoint],
    ets_map: Dict[int, EtsGroupAddress],
) -> List[SyncCandidate]:
    """Erstellt eine reine Anzeigeliste, wenn nur GPA oder nur ETS geladen ist."""
    rows: List[SyncCandidate] = []

    if datapoints and not ets_map:
        for dp in datapoints:
            values = dp.candidate_group_addresses
            value = values[0] if values else 0
            try:
                ga_text = ", ".join(int_to_ga(v) for v in values) if values else ""
            except ValueError:
                ga_text = ""
            if dp.write_group_address and dp.write_group_address == value:
                source = "WriteGroupAddress"
            elif dp.read_group_address and dp.read_group_address == value:
                source = "ReadGroupAddress"
            elif value in dp.listener_group_addresses:
                source = "ListenerGroupAddresses"
            else:
                source = ""
            rows.append(
                SyncCandidate(
                    selected=False,
                    status=SyncStatus.NUR_GPA,
                    zip_path=dp.zip_path,
                    current_name=dp.entity_name,
                    new_name="",
                    group_address=ga_text,
                    group_address_value=value,
                    source_field=source,
                )
            )

    elif ets_map and not datapoints:
        for ga in sorted(ets_map.values(), key=lambda x: x.value):
            rows.append(
                SyncCandidate(
                    selected=False,
                    status=SyncStatus.NUR_ETS,
                    zip_path="",
                    current_name="",
                    new_name=ga.name,
                    group_address=ga.address,
                    group_address_value=ga.value,
                    source_field="ETS",
                )
            )

    return rows
