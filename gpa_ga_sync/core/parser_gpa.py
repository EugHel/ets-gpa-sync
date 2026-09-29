from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .models import DatapointReferences, GpaDatapoint, LogicReference, TimerReference, VisuReference
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
        catalog = _GpaCatalog(zf, password)
        try:
            logic_refs = catalog.logic_references()
            timer_refs = catalog.timer_references()
        except Exception as exc:  # pragma: no cover - defensiv, Zählung ist Zusatzinfo
            _log.warning("Logik-/Zeitschaltuhr-Verweise nicht ermittelbar: %s", exc)
            logic_refs, timer_refs = {}, {}
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
                    logic_reference_count=len(logic_refs.get(datapoint_uid(info.filename), ())),
                    timer_reference_count=len(timer_refs.get(datapoint_uid(info.filename), ())),
                )
            )
    _log.info("%d GPA-Datenpunkte gelesen", len(datapoints))
    return datapoints


# ═══════════════════════════════════════════════════════════════════════════════
# Querverweise (Visu, Logik, Zeitschaltuhr)
# ═══════════════════════════════════════════════════════════════════════════════
#
# GPA-Struktur (relevante Ausschnitte, <p> = projects/$<projekt>):
#   Visu:   .../knxdatapoints/$<dp>/datapointviews/$<a>.assoc  → channelviews/$<cv>
#           <p>/channelviews/$<cv>.xml                         (Name, Kanaltyp)
#           <p>/channelviews/$<cv>/locations/$<a>.assoc        → typedelement-Kette
#           <p>/channelviews/$<cv>/users/$<a>.assoc            → users/$<u>
#   Logik:  .../logicpages/$<page>/logicnodes/$<node>.xml      <Parameter Type="datapoint"
#                                                               EntityId=".../knxdatapoints/$<dp>">
#   Uhr:    .../channels/$<timer>.xml (ChannelTypeUrn FunctionTimer) mit
#           <SceneDataPoint EntityId="<dp>"> und <Timers>; zugehörige Ansicht über
#           .../channels/$<timer>/channelviewtrigger/$<a>.assoc → channelviews/$<cv>

_DATAPOINT_ENTITY_RE = re.compile(r"knxdatapoints/\$([0-9A-Za-z_-]+)", re.IGNORECASE)
_BUILTIN_USER_DE = {"Everyone": "Alle"}
_HIDDEN_USERS = {"System"}
_WEEKDAYS_DE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
_TIMER_TYPE_DE = {"sunrise": "Sonnenaufgang", "sunset": "Sonnenuntergang"}
_LOGIC_ROLE_DE = {
    "DatapointEvent": "Eingang",   # Logik reagiert auf Telegramme des Datenpunkts
    "DatapointAction": "Ausgang",  # Logik sendet auf den Datenpunkt
}


def datapoint_uid(zip_path: str) -> str:
    """UID eines Datenpunkts aus seinem ZIP-Pfad (…/knxdatapoints/$<uid>.xml), klein geschrieben."""
    stem = _datapoint_stem(zip_path)
    seg = stem.rsplit("/", 1)[-1]
    return seg.lstrip("$").lower()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _end_uid(elem: ET.Element) -> str:
    """UID eines <End>-Elements: uid-Attribut, sonst letztes $-Segment des hrefs."""
    uid = elem.get("uid")
    if uid:
        return uid.lower()
    href = elem.get("href", "").replace("\\", "/").rstrip("/")
    seg = href.rsplit("/", 1)[-1]
    return seg.lstrip("$").lower() if seg.startswith("$") else ""


def _format_timer(timer: ET.Element) -> Tuple[str, bool]:
    """Kurztext einer Schaltzeit, z. B. '08:00 täglich', plus Aktiv-Flag."""
    enabled = True
    ttype = time = rec_type = weekdays = ""
    for elem in timer.iter():
        name = _local(elem.tag)
        text = (elem.text or "").strip()
        if name == "Enabled":
            enabled = text.lower() != "false"
        elif name == "Time" and not time:
            time = text
        elif name == "WeekDays":
            weekdays = text
        elif name == "Type":
            # Erstes <Type> gehört zu TimerType, das zweite zu Recurrence.
            if not ttype:
                ttype = text
            elif not rec_type:
                rec_type = text
    if ttype == "pointInTime" or (not ttype and time):
        when = time[:5] if time else "?"
    else:
        when = _TIMER_TYPE_DE.get(ttype, ttype or "?")
    active_days = [d for d, ch in zip(_WEEKDAYS_DE, weekdays) if ch.isalpha()] if weekdays else []
    if rec_type == "daily" or len(active_days) == 7:
        days = "täglich"
    elif active_days == list(_WEEKDAYS_DE[:5]):
        days = "Mo–Fr"
    elif active_days:
        days = ", ".join(active_days)
    else:
        days = {"weekly": "wöchentlich", "once": "einmalig"}.get(rec_type, rec_type)
    text = f"{when} {days}".strip()
    if not enabled:
        text += " (inaktiv)"
    return text, enabled


class _GpaCatalog:
    """Einmal pro offener GPA aufgebautes Nachschlagewerk über alle ZIP-Einträge.

    Alle Lookups laufen über Dicts (statt linearer Suche über ~15.000 Einträge):
    - xml_by_tail:   "channelviews/$<uid>.xml" → echter ZIP-Name
    - assocs_by_dir: "channelviews/$<uid>/locations" → [echte .assoc-Namen]
    XML-Dateien werden bei Bedarf gelesen und gecacht.
    """

    def __init__(self, zf: zipfile.ZipFile, password: Optional[str] = None) -> None:
        self.zf = zf
        self._pwd = password.encode("utf-8") if password else None
        self.xml_by_tail: Dict[str, str] = {}
        self.assocs_by_dir: Dict[str, List[str]] = {}
        self.logic_nodes: List[str] = []
        self.channels: List[str] = []
        for real in zf.namelist():
            low = real.replace("\\", "/").lower()
            parts = low.split("/")
            if low.endswith(".xml"):
                if len(parts) >= 2:
                    self.xml_by_tail.setdefault("/".join(parts[-2:]), real)
                if "logicnodes" in parts[:-1]:
                    self.logic_nodes.append(real)
                elif len(parts) >= 2 and parts[-2] == "channels":
                    self.channels.append(real)
            elif low.endswith(".assoc") and len(parts) >= 4:
                self.assocs_by_dir.setdefault("/".join(parts[-4:-1]), []).append(real)
        self._xml_cache: Dict[str, Optional[ET.Element]] = {}
        self._channelview_cache: Dict[str, Optional[VisuReference]] = {}
        self._location_cache: Dict[str, str] = {}
        self._user_cache: Dict[str, str] = {}
        self._logic: Optional[Dict[str, List[LogicReference]]] = None
        self._timers: Optional[Dict[str, List[TimerReference]]] = None

    # ── Low-Level ──────────────────────────────────────────────────────────────

    def read_bytes(self, real: str) -> bytes:
        return self.zf.read(real, pwd=self._pwd)

    def parse(self, real: str) -> Optional[ET.Element]:
        if real in self._xml_cache:
            return self._xml_cache[real]
        root: Optional[ET.Element]
        try:
            data = self.read_bytes(real)
            root = ET.fromstring(data.decode(detect_encoding(data), errors="replace"))
        except Exception as exc:
            _log.debug("XML nicht lesbar (%s): %s", real, exc)
            root = None
        self._xml_cache[real] = root
        return root

    def find_xml(self, folder: str, uid: str) -> Optional[ET.Element]:
        real = self.xml_by_tail.get(f"{folder}/${uid}.xml".lower())
        return self.parse(real) if real else None

    def assocs(self, folder: str, uid: str, sub: str) -> List[str]:
        return self.assocs_by_dir.get(f"{folder}/${uid}/{sub}".lower(), [])

    def assoc_end_uids(self, real: str, cat: str) -> List[str]:
        root = self.parse(real)
        if root is None:
            return []
        return [_end_uid(e) for e in root.iter() if e.get("cat") == cat]

    # ── Visu ───────────────────────────────────────────────────────────────────

    def location_path(self, cv_uid: str) -> str:
        """Voller Standort einer Channelview, z. B. 'Gebäude und Geräte → EG → Küche (Raum)'.

        Fehlt eine Ebene oder ist sie nicht lesbar, wird der Pfad weggelassen ("").
        """
        if cv_uid in self._location_cache:
            return self._location_cache[cv_uid]
        path = ""
        for real in self.assocs("channelviews", cv_uid, "locations"):
            root = self.parse(real)
            if root is None:
                continue
            href = next((e.get("href", "") for e in root.iter()
                         if e.get("cat") == "typedelement"), "")
            uids = _TYPEDELEMENT_HREF_RE.findall(href.replace("\\", "/"))
            if len(uids) < 2:  # nur Root, keine anzeigbare Ebene
                break
            names: List[str] = []
            last_subtype = ""
            for uid in uids[1:]:  # erstes Element = Root/Standortbestimmung
                te = self.find_xml("typedelements", uid)
                entity = find_text_by_local_name(te, "EntityName") if te is not None else None
                if not entity:
                    names = []
                    break
                names.append(entity)
                last_subtype = find_text_by_local_name(te, "Subtype") or ""
            if names:
                path = _LOCATION_ROOT + "".join(f" → {n}" for n in names)
                if last_subtype:
                    path += f" ({_SUBTYPE_DE.get(last_subtype, last_subtype)})"
            break
        self._location_cache[cv_uid] = path
        return path

    def user_name(self, user_uid: str) -> str:
        if user_uid not in self._user_cache:
            root = self.find_xml("users", user_uid)
            name = ""
            if root is not None:
                name = find_text_by_local_name(root, "EntityName") or ""
                builtin = find_text_by_local_name(root, "BuiltInType") or ""
                if builtin in _HIDDEN_USERS or name in _HIDDEN_USERS:
                    name = ""
                else:
                    name = _BUILTIN_USER_DE.get(builtin, _BUILTIN_USER_DE.get(name, name))
            self._user_cache[user_uid] = name
        return self._user_cache[user_uid]

    def channelview(self, cv_uid: str) -> Optional[VisuReference]:
        if cv_uid in self._channelview_cache:
            return self._channelview_cache[cv_uid]
        root = self.find_xml("channelviews", cv_uid)
        ref: Optional[VisuReference] = None
        if root is not None:
            users: List[str] = []
            for real in self.assocs("channelviews", cv_uid, "users"):
                for uid in self.assoc_end_uids(real, "user"):
                    name = self.user_name(uid)
                    if name and name not in users:
                        users.append(name)
            ref = VisuReference(
                view_name=find_text_by_local_name(root, "EntityName") or "(ohne Name)",
                channel_type=find_text_by_local_name(root, "ChannelTypeId") or "",
                function_type=find_text_by_local_name(root, "Urn") or "",
                location=self.location_path(cv_uid),
                users=tuple(sorted(users, key=str.lower)),
            )
        self._channelview_cache[cv_uid] = ref
        return ref

    def visu_references(self, dp_uid: str) -> List[VisuReference]:
        refs: List[VisuReference] = []
        for real in self.assocs("knxdatapoints", dp_uid, "datapointviews"):
            cv_uid = ""
            root = self.parse(real)
            if root is not None:
                for elem in root.iter():
                    if elem.get("cat") != "datapointview":
                        continue
                    m = _CHANNELVIEW_HREF_RE.search(elem.get("href", "").replace("\\", "/"))
                    if m:
                        cv_uid = m.group(1).lower()
                        break
            view = self.channelview(cv_uid) if cv_uid else None
            refs.append(view if view is not None
                        else VisuReference(view_name="unbekannte Ansicht", orphan=True))
        return refs

    # ── Logik ──────────────────────────────────────────────────────────────────

    def _logic_page(self, node_path: str, cache: Dict[str, Tuple[str, bool]]) -> Tuple[str, bool]:
        parts = node_path.replace("\\", "/").split("/")
        lower = [p.lower() for p in parts]
        page_uid = ""
        if "logicpages" in lower:
            idx = lower.index("logicpages")
            if idx + 1 < len(parts):
                page_uid = parts[idx + 1].lstrip("$").lower()
        if page_uid not in cache:
            page = self.find_xml("logicpages", page_uid) if page_uid else None
            if page is not None:
                name = (find_text_by_local_name(page, "LogicPageName")
                        or find_text_by_local_name(page, "EntityName") or "(ohne Name)")
                active = (find_text_by_local_name(page, "IsActive") or "True").lower() != "false"
            else:
                name, active = "(unbekannte Logikseite)", True
            cache[page_uid] = (name, active)
        return cache[page_uid]

    def logic_references(self) -> Dict[str, List[LogicReference]]:
        """Alle Logik-Verwendungen, einmalig über alle Logikbausteine ermittelt."""
        if self._logic is not None:
            return self._logic
        result: Dict[str, List[LogicReference]] = {}
        page_cache: Dict[str, Tuple[str, bool]] = {}
        for real in self.logic_nodes:
            try:
                data = self.read_bytes(real)
            except Exception as exc:
                _log.debug("Logikbaustein nicht lesbar (%s): %s", real, exc)
                continue
            if b"knxdatapoints/$" not in data.lower():
                continue
            try:
                root = ET.fromstring(data.decode(detect_encoding(data), errors="replace"))
            except Exception as exc:
                _log.debug("Logikbaustein defekt (%s): %s", real, exc)
                continue
            dp_uids: List[str] = []
            for elem in root.iter():
                entity = elem.get("EntityId")
                if entity:
                    m = _DATAPOINT_ENTITY_RE.search(entity.replace("\\", "/"))
                    if m and m.group(1).lower() not in dp_uids:
                        dp_uids.append(m.group(1).lower())
            if not dp_uids:
                continue
            node_type = (find_text_by_local_name(root, "Type") or "").rsplit(".", 1)[-1]
            page_name, page_active = self._logic_page(real, page_cache)
            ref = LogicReference(
                page_name=page_name,
                node_name=(find_text_by_local_name(root, "NodeName") or "").strip(),
                role=_LOGIC_ROLE_DE.get(node_type, "Baustein"),
                page_active=page_active)
            for uid in dp_uids:
                result.setdefault(uid, []).append(ref)
        for refs in result.values():
            refs.sort(key=lambda r: (r.page_name.lower(), r.role, r.node_name.lower()))
        self._logic = result
        return result

    # ── Zeitschaltuhr ──────────────────────────────────────────────────────────

    def _timer_view_name(self, timer_uid: str) -> str:
        for assoc in self.assocs("channels", timer_uid, "channelviewtrigger"):
            for cv_uid in self.assoc_end_uids(assoc, "channelview"):
                view = self.channelview(cv_uid)
                if view is not None:
                    return view.view_name
        return ""

    def timer_references(self) -> Dict[str, List[TimerReference]]:
        """Alle Zeitschaltuhr-Verwendungen (FunctionTimer-Kanäle mit SceneDataPoints)."""
        if self._timers is not None:
            return self._timers
        result: Dict[str, List[TimerReference]] = {}
        for real in self.channels:
            try:
                data = self.read_bytes(real)
            except Exception as exc:
                _log.debug("Kanal nicht lesbar (%s): %s", real, exc)
                continue
            if b"SceneDataPoint " not in data or b"FunctionTimer" not in data:
                continue
            root = self.parse(real)
            if root is None:
                continue
            dp_uids = [e.get("EntityId", "").lower() for e in root.iter()
                       if _local(e.tag) == "SceneDataPoint" and e.get("EntityId")]
            if not dp_uids:
                continue
            schedules: List[str] = []
            active = 0
            for elem in root.iter():
                if _local(elem.tag) == "Timer":
                    text, enabled = _format_timer(elem)
                    schedules.append(text)
                    active += 1 if enabled else 0
            timer_uid = real.replace("\\", "/").rsplit("/", 1)[-1][:-len(".xml")].lstrip("$").lower()
            view_name = (self._timer_view_name(timer_uid)
                         or find_text_by_local_name(root, "EntityName") or "Zeitschaltuhr")
            ref = TimerReference(view_name=view_name, schedules=tuple(schedules),
                                 active_count=active)
            for uid in dict.fromkeys(dp_uids):
                result.setdefault(uid, []).append(ref)
        self._timers = result
        return result

    # ── Gesamt ─────────────────────────────────────────────────────────────────

    def references(self, dp_uid: str) -> DatapointReferences:
        dp_uid = dp_uid.lower()
        return DatapointReferences(
            visu=self.visu_references(dp_uid),
            logic=list(self.logic_references().get(dp_uid, [])),
            timers=list(self.timer_references().get(dp_uid, [])),
        )


class GpaCrossRefIndex:
    """Hält eine offene GPA-ZIP samt Katalog für schnelle, wiederholte Querverweis-Auflösung.

    Das Handle wird nur lesend gehalten; vor dem Zurückschreiben (Sync in eine
    SEPARATE Datei) sollte es via close() freigegeben werden.
    """

    def __init__(self, gpa_path: Path, password: Optional[str] = None) -> None:
        self.gpa_path = Path(gpa_path)
        self.password = password
        self._zf = zipfile.ZipFile(self.gpa_path, "r")
        self.catalog = _GpaCatalog(self._zf, password)

    @property
    def zip(self) -> zipfile.ZipFile:
        return self._zf

    def references(self, datapoint_zip_path: str) -> DatapointReferences:
        return self.catalog.references(datapoint_uid(datapoint_zip_path))

    def close(self) -> None:
        try:
            self._zf.close()
        except Exception:  # pragma: no cover - defensiv
            pass


def resolve_datapoint_references(
    gpa_path: Path, datapoint_zip_path: str, password: Optional[str] = None,
    index: Optional[GpaCrossRefIndex] = None,
) -> DatapointReferences:
    """Alle Verwendungen (Visu, Logik, Zeitschaltuhr) eines einzelnen Datenpunkts."""
    if index is not None:
        return index.references(datapoint_zip_path)
    tmp = GpaCrossRefIndex(gpa_path, password)
    try:
        return tmp.references(datapoint_zip_path)
    finally:
        tmp.close()


def build_reference_map(
    gpa_path: Path, datapoints: Sequence[GpaDatapoint], password: Optional[str] = None,
) -> Dict[str, DatapointReferences]:
    """Löst die Verwendungen ALLER Datenpunkte in einem Durchgang auf (zip_path → Verweise).

    Gedacht für den Analyse-Worker: danach braucht die GUI kein offenes ZIP-Handle
    mehr (kein Datei-Lock, keine Thread-Probleme), und Filter, Export und Sync-Prüfung
    arbeiten auf fertigen Daten. Die Zähler der Datenpunkte werden mit aktualisiert.
    """
    result: Dict[str, DatapointReferences] = {}
    with zipfile.ZipFile(gpa_path, "r") as zf:
        catalog = _GpaCatalog(zf, password)
        for dp in datapoints:
            refs = catalog.references(datapoint_uid(dp.zip_path))
            dp.cross_reference_count = len(refs.visu)
            dp.logic_reference_count = len(refs.logic)
            dp.timer_reference_count = len(refs.timers)
            result[dp.zip_path] = refs
    return result


def resolve_cross_reference_views(
    gpa_path: Path, datapoint_zip_path: str, password: Optional[str] = None,
    index: Optional[GpaCrossRefIndex] = None,
) -> List[Tuple[str, str, str, str]]:
    """Nur die Visu-Verwendungen als 4-Tupel (EntityName, ChannelTypeId, FunctionType, Location).

    Kompatibilitäts-API; verwaiste/defekte Verweise erscheinen als
    ("unbekannte Ansicht", "", "", "").
    """
    refs = resolve_datapoint_references(gpa_path, datapoint_zip_path, password, index)
    return [(v.view_name, v.channel_type, v.function_type, v.location) for v in refs.visu]
