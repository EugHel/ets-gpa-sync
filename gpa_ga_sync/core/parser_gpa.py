from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import GpaDatapoint
from .utils import detect_encoding, find_text_by_local_name, parse_listener_addresses, parse_optional_int
from ..log import get_logger

_log = get_logger("core.parser_gpa")

# Ein Datenpunkt liegt unter .../knxdatapoints/$<uid>.xml; seine Verwendungen als
# Geschwister-Ordner .../knxdatapoints/$<uid>/datapointviews/$<assoc-uid>.assoc.
_ASSOC_RE = re.compile(
    r"^(?P<stem>.*/knxdatapoints/\$[^/]+)/datapointviews/[^/]+\.assoc$",
    re.IGNORECASE,
)
# href innerhalb einer .assoc, der auf die verwendende Channelview zeigt.
_CHANNELVIEW_HREF_RE = re.compile(r"channelviews/\$([^/]+)", re.IGNORECASE)

# Alle typedelement-UIDs (Root/Ebene1/Ebene2/…) eines Location-hrefs in Reihenfolge.
# Bewusst über alle Vorkommen statt String-Split, damit ein evtl. vorangestellter
# "projects/$<proj>/"-Präfix nicht fälschlich als erste Ebene gezählt wird.
_TYPEDELEMENT_HREF_RE = re.compile(r"typedelements/\$([^/]+)", re.IGNORECASE)
# Verdeutschung der Subtypes der untersten Standort-Ebene.
_SUBTYPE_DE = {"Floor": "Etage", "Room": "Raum", "Building": "Gebäude"}
_LOCATION_ROOT = "Gebäude und Geräte"


def read_zip_text(zf: zipfile.ZipFile, info: zipfile.ZipInfo, password: Optional[str] = None) -> Tuple[str, str]:
    pwd = password.encode("utf-8") if password else None
    data = zf.read(info, pwd=pwd)
    enc = detect_encoding(data)
    return data.decode(enc, errors="replace"), enc


def _datapoint_stem(zip_path: str) -> str:
    """Datenpunkt-Stamm (Pfad ohne .xml, Slashes normalisiert) als Zähl-Schlüssel."""
    path = zip_path.replace("\\", "/")
    if path.lower().endswith(".xml"):
        path = path[: -len(".xml")]
    return path


def _count_cross_references(zf: zipfile.ZipFile) -> Counter:
    """Zählt je Datenpunkt-Stamm die .assoc-Verwendungen in einem einzigen namelist()-Durchlauf."""
    counter: Counter = Counter()
    for name in zf.namelist():
        m = _ASSOC_RE.match(name.replace("\\", "/"))
        if m:
            counter[m.group("stem")] += 1
    return counter


def parse_gpa_datapoints(gpa_path: Path, password: Optional[str] = None) -> List[GpaDatapoint]:
    datapoints: List[GpaDatapoint] = []
    _log.info("Lese GPA-Datei: %s", gpa_path.name)
    with zipfile.ZipFile(gpa_path, "r") as zf:
        xref_counts = _count_cross_references(zf)
        for info in zf.infolist():
            path = info.filename.replace("\\", "/")
            if not path.lower().endswith(".xml"):
                continue
            if "/knxdatapoints/" not in path.lower():
                continue
            try:
                xml_text, _enc = read_zip_text(zf, info, password)
                root = ET.fromstring(xml_text)
            except Exception as exc:
                _log.warning("Datenpunkt-XML übersprungen (%s): %s", info.filename, exc)
                continue
            entity_name = find_text_by_local_name(root, "EntityName")
            if entity_name is None:
                _log.debug("Kein EntityName in %s – übersprungen", info.filename)
                continue
            read_ga = parse_optional_int(find_text_by_local_name(root, "ReadGroupAddress"))
            write_ga = parse_optional_int(find_text_by_local_name(root, "WriteGroupAddress"))
            listeners = parse_listener_addresses(root)
            datapoints.append(
                GpaDatapoint(
                    zip_path=info.filename,
                    entity_name=entity_name,
                    read_group_address=read_ga,
                    write_group_address=write_ga,
                    listener_group_addresses=listeners,
                    cross_reference_count=xref_counts.get(_datapoint_stem(info.filename), 0),
                )
            )
    _log.info("%d GPA-Datenpunkte gelesen", len(datapoints))
    return datapoints


def _resolve_location_path(
    zf: zipfile.ZipFile,
    name_by_normalized: Dict[str, str],
    channelview_uid: str,
    password: Optional[str] = None,
) -> str:
    """Ermittelt den vollen Gebäude-Standort einer Channelview (lazy, pro Klick).

    channelviews/$<cv>/locations/$<assoc>.assoc → zweiter <End cat="typedelement">
    liefert einen href über mehrere /typedelements/$<uid>-Ebenen. Jede Ebene (außer
    dem Root) wird zu ihrem EntityName aufgelöst, die unterste zusätzlich verdeutscht
    per Subtype. Rückgabe z. B. "Gebäude und Geräte → Erdgeschoss → Deko (Raum)".
    Bei fehlendem locations/-Ordner oder Auflösungsfehler: "" (Pfad wird weggelassen).
    """
    loc_prefix = f"channelviews/${channelview_uid}/locations/".lower()
    loc_assoc = next(
        (real for norm, real in name_by_normalized.items()
         if loc_prefix in norm and norm.endswith(".assoc")),
        None,
    )
    if loc_assoc is None:
        return ""
    try:
        info = zf.getinfo(loc_assoc)
        xml_text, _enc = read_zip_text(zf, info, password)
        root = ET.fromstring(xml_text)
    except Exception as exc:
        _log.debug("Location-Assoc nicht lesbar (%s): %s", loc_assoc, exc)
        return ""

    href = ""
    for elem in root.iter():
        if elem.get("cat") == "typedelement":
            href = elem.get("href", "")
            break
    uids = _TYPEDELEMENT_HREF_RE.findall(href.replace("\\", "/"))
    if len(uids) < 2:  # nur Root, keine anzeigbare Ebene
        return ""

    names: List[str] = []
    last_subtype = ""
    for uid in uids[1:]:  # erstes Element = Root/Standortbestimmung → überspringen
        key = f"typedelements/${uid}.xml".lower()
        real = next(
            (r for norm, r in name_by_normalized.items() if norm.endswith(key)),
            None,
        )
        if real is None:
            return ""
        try:
            te_info = zf.getinfo(real)
            te_text, _enc = read_zip_text(zf, te_info, password)
            te_root = ET.fromstring(te_text)
        except Exception as exc:
            _log.debug("Typedelement nicht lesbar (%s): %s", real, exc)
            return ""
        entity = find_text_by_local_name(te_root, "EntityName")
        if not entity:
            return ""
        names.append(entity)
        last_subtype = find_text_by_local_name(te_root, "Subtype") or ""

    if not names:
        return ""
    path = _LOCATION_ROOT + "".join(f" → {n}" for n in names)
    if last_subtype:
        path += f" ({_SUBTYPE_DE.get(last_subtype, last_subtype)})"
    return path


def resolve_cross_reference_views(
    gpa_path: Path, datapoint_zip_path: str, password: Optional[str] = None
) -> List[Tuple[str, str, str]]:
    """Löst die Verwendungen eines Datenpunkts zu Channelview-Ansichten auf (lazy, pro Klick).

    Rückgabe: Liste von (EntityName, ChannelTypeId, LocationPath). LocationPath ist
    der volle Gebäude-Standort (siehe _resolve_location_path) oder "" wenn nicht
    ermittelbar. Verwaiste .assoc-Verweise (href zeigt auf nicht auffindbare
    Channelview) werden als ("unbekannte Ansicht", "", "") mitgezählt.
    """
    results: List[Tuple[str, str, str]] = []
    prefix = _datapoint_stem(datapoint_zip_path) + "/datapointviews/"
    prefix_lower = prefix.lower()
    with zipfile.ZipFile(gpa_path, "r") as zf:
        # Name-Lookup ohne Berücksichtigung von Slash-Varianten/Case für Channelview-XML.
        name_by_normalized: Dict[str, str] = {
            n.replace("\\", "/").lower(): n for n in zf.namelist()
        }
        assoc_names = [
            n for n in zf.namelist()
            if n.replace("\\", "/").lower().startswith(prefix_lower)
            and n.lower().endswith(".assoc")
        ]
        for assoc_name in assoc_names:
            channelview_uid: Optional[str] = None
            try:
                info = zf.getinfo(assoc_name)
                xml_text, _enc = read_zip_text(zf, info, password)
                root = ET.fromstring(xml_text)
                for elem in root.iter():
                    if elem.get("cat") != "datapointview":
                        continue
                    href = elem.get("href", "")
                    m = _CHANNELVIEW_HREF_RE.search(href.replace("\\", "/"))
                    if m:
                        channelview_uid = m.group(1)
                        break
            except Exception as exc:
                _log.warning("Assoc übersprungen (%s): %s", assoc_name, exc)

            if not channelview_uid:
                results.append(("unbekannte Ansicht", "", ""))
                continue

            cv_key = f"channelviews/${channelview_uid}.xml".lower()
            cv_name = next(
                (real for norm, real in name_by_normalized.items() if norm.endswith(cv_key)),
                None,
            )
            if cv_name is None:
                results.append(("unbekannte Ansicht", "", ""))
                continue
            try:
                cv_info = zf.getinfo(cv_name)
                cv_text, _enc = read_zip_text(zf, cv_info, password)
                cv_root = ET.fromstring(cv_text)
                entity = find_text_by_local_name(cv_root, "EntityName") or "(ohne Name)"
                channel_type = find_text_by_local_name(cv_root, "ChannelTypeId") or ""
                location = _resolve_location_path(
                    zf, name_by_normalized, channelview_uid, password)
                results.append((entity, channel_type, location))
            except Exception as exc:
                _log.warning("Channelview übersprungen (%s): %s", cv_name, exc)
                results.append(("unbekannte Ansicht", "", ""))
    return results
