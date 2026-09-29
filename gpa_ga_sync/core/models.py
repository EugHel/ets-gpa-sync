from __future__ import annotations

from dataclasses import dataclass, field
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
    cross_reference_count: int = 0   # Visu-Ansichten
    logic_reference_count: int = 0   # Logikbausteine
    timer_reference_count: int = 0   # Zeitschaltuhren

    @property
    def total_reference_count(self) -> int:
        return self.cross_reference_count + self.logic_reference_count + self.timer_reference_count

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


@dataclass(frozen=True)
class VisuReference:
    """Verwendung eines Datenpunkts in einer Visu-Ansicht (Channelview)."""
    view_name: str
    channel_type: str = ""
    function_type: str = ""
    location: str = ""
    users: Tuple[str, ...] = ()
    orphan: bool = False  # .assoc zeigt auf keine auffindbare Ansicht


@dataclass(frozen=True)
class LogicReference:
    """Verwendung eines Datenpunkts als Baustein im GPA-Logikeditor."""
    page_name: str
    node_name: str = ""
    role: str = ""  # "Eingang" (Logik reagiert), "Ausgang" (Logik sendet) oder "Baustein"
    page_active: bool = True


@dataclass(frozen=True)
class TimerReference:
    """Verwendung eines Datenpunkts durch eine Zeitschaltuhr (FunctionTimer-Kanal)."""
    view_name: str
    schedules: Tuple[str, ...] = ()  # z. B. "08:00 täglich", "20:00 Mo–Fr (inaktiv)"
    active_count: int = 0


@dataclass
class DatapointReferences:
    """Alle GPA-internen Verwendungen eines Datenpunkts."""
    visu: List[VisuReference] = field(default_factory=list)
    logic: List[LogicReference] = field(default_factory=list)
    timers: List[TimerReference] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.visu) + len(self.logic) + len(self.timers)

    @property
    def is_unused(self) -> bool:
        return self.total == 0

    def summary_text(self) -> str:
        """Einzeilige Kurzfassung für CSV/Suche, z. B. 'Visu: EG → Küche → Licht | Logik: Seite A'."""
        parts: List[str] = []
        for v in self.visu:
            parts.append(f"Visu: {v.location + ' → ' if v.location else ''}{v.view_name}")
        for lg in self.logic:
            parts.append(f"Logik: {lg.page_name}{' (' + lg.role + ')' if lg.role else ''}")
        for t in self.timers:
            parts.append(f"Zeitschaltuhr: {t.view_name}")
        return " | ".join(parts)


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
