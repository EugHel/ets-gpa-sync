from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        def __str__(self) -> str:
            return self.value


class SyncStatus(StrEnum):
    """Alle gültigen Zustände eines Sync-Kandidaten."""
    AENDERUNG    = "Änderung"
    LEERZEICHEN  = "Leerzeichen"
    MEHRDEUTIG   = "Mehrdeutig"
    ADRESSKONFLIKT = "Adress-Konflikt"
    NICHT_IN_ETS = "Nicht in ETS"
    NUR_GPA      = "Nur GPA"
    NUR_ETS      = "Nur ETS"
    OK           = "OK"
    KEINE_ETS_GA = "Keine ETS-GA"


@dataclass
class EtsGroupAddress:
    address: str
    value: int
    name: str


@dataclass
class GpaDatapoint:
    zip_path: str
    entity_name: str
    read_group_address: Optional[int]
    write_group_address: Optional[int]
    listener_group_addresses: Tuple[int, ...]

    @property
    def candidate_group_addresses(self) -> Tuple[int, ...]:
        """Alle sinnvollen GA-Werte für die Namenszuordnung, ohne 0 und ohne Duplikate.

        Reihenfolge bewusst wie im GPA: zuerst Senden/Write, dann Status/Read, dann Hören/Listener.
        """
        values: List[int] = []
        for value in (self.write_group_address, self.read_group_address, *self.listener_group_addresses):
            if value is None or value == 0:
                continue
            if value not in values:
                values.append(value)
        return tuple(values)


@dataclass
class SyncCandidate:
    selected: bool
    status: SyncStatus
    zip_path: str
    current_name: str
    new_name: str
    group_address: str
    group_address_value: int
    source_field: str
