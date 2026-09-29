"""
Unit-Tests für die Querverweis-Zählung und -Auflösung (Feature "Verweise").

Baut minimale GPA-ZIPs im Speicher/Tempfile auf, da hier – anders als in
test_core.py – echtes ZIP-I/O nötig ist.
"""
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gpa_ga_sync.core import (
    REFERENCE_FILTERS,
    DatapointReferences,
    GpaCrossRefIndex,
    LogicReference,
    SyncCandidate,
    SyncStatus,
    TimerReference,
    VisuReference,
    build_reference_map,
    datapoint_uid,
    export_candidates_csv,
    matches_reference_filter,
    parse_gpa_datapoints,
    resolve_cross_reference_views,
    resolve_datapoint_references,
    summarize_sync_impact,
)

# ── XML-Bausteine ──────────────────────────────────────────────────────────────

_NS = 'xmlns:conf="http://schemas.gira.de/GDS/conf"'


def _datapoint_xml(name: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<conf:Datapoint {_NS}>'
        f'<conf:EntityName>{name}</conf:EntityName>'
        '<conf:WriteGroupAddress>1</conf:WriteGroupAddress>'
        '</conf:Datapoint>'
    )


def _assoc_xml(channelview_uid: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Association>'
        '<End cat="datapoint" href="knxdatapoints/$dp/entity" />'
        f'<End cat="datapointview" '
        f'href="channelviews/${channelview_uid}/datapointviews/$view" />'
        '</Association>'
    )


def _channelview_xml(name: str, channel_type: str, function_type: str = "") -> str:
    urn = f'<conf:Urn>{function_type}</conf:Urn>' if function_type else ''
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<conf:Channelview {_NS}>'
        f'<conf:EntityName>{name}</conf:EntityName>'
        f'{urn}'
        f'<conf:ChannelTypeId>{channel_type}</conf:ChannelTypeId>'
        '</conf:Channelview>'
    )


def _location_assoc_xml(href: str) -> str:
    """Location-Assoc einer Channelview: zweiter <End> zeigt (cat=typedelement) auf die Standort-Kette."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Association>'
        '<End cat="location" href="channelviews/$cv1/entity" />'
        f'<End cat="typedelement" href="{href}" />'
        '</Association>'
    )


def _typedelement_xml(name: str, subtype: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<conf:TypedElement {_NS}>'
        f'<conf:EntityName>{name}</conf:EntityName>'
        f'<conf:Subtype>{subtype}</conf:Subtype>'
        '</conf:TypedElement>'
    )


def _write_gpa(entries: dict) -> Path:
    """Schreibt ein GPA-ZIP mit {pfad: text} in eine Temp-Datei und gibt den Pfad zurück."""
    fd, path = tempfile.mkstemp(suffix=".gpa")
    os.close(fd)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in entries.items():
            zf.writestr(name, text)
    return Path(path)


# ── Tests: Zählung ──────────────────────────────────────────────────────────────

class TestCrossReferenceCount(unittest.TestCase):

    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _gpa(self, entries):
        p = _write_gpa(entries)
        self._paths.append(p)
        return p

    def test_count_zero(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
        })
        dps = parse_gpa_datapoints(gpa)
        self.assertEqual(len(dps), 1)
        self.assertEqual(dps[0].cross_reference_count, 0)

    def test_count_one(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
        })
        dps = parse_gpa_datapoints(gpa)
        self.assertEqual(dps[0].cross_reference_count, 1)

    def test_count_many(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a2.assoc": _assoc_xml("cv2"),
            "prj/knxdatapoints/$dp1/datapointviews/$a3.assoc": _assoc_xml("cv3"),
        })
        dps = parse_gpa_datapoints(gpa)
        self.assertEqual(dps[0].cross_reference_count, 3)

    def test_isolation_between_datapoints(self):
        """Assocs von $dp1 dürfen nicht bei $dp2 mitzählen (Präfix-Genauigkeit)."""
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp2.xml": _datapoint_xml("DP2"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a2.assoc": _assoc_xml("cv2"),
        })
        by_name = {dp.entity_name: dp for dp in parse_gpa_datapoints(gpa)}
        self.assertEqual(by_name["DP1"].cross_reference_count, 2)
        self.assertEqual(by_name["DP2"].cross_reference_count, 0)

    def test_non_assoc_files_ignored(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/knxdatapoints/$dp1/datapointviews/readme.txt": "kein assoc",
        })
        dps = parse_gpa_datapoints(gpa)
        self.assertEqual(dps[0].cross_reference_count, 1)


# ── Tests: Namensauflösung ──────────────────────────────────────────────────────

class TestResolveCrossReferenceViews(unittest.TestCase):

    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _gpa(self, entries):
        p = _write_gpa(entries)
        self._paths.append(p)
        return p

    def test_resolve_single_view(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/channelviews/$cv1.xml": _channelview_xml(
                "Kugel Beet r.", "Switch", "de.gira.schema.functions.Switch"),
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(
            views,
            [("Kugel Beet r.", "Switch", "de.gira.schema.functions.Switch", "")])

    def test_resolve_multiple_views(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a2.assoc": _assoc_xml("cv2"),
            "prj/channelviews/$cv1.xml": _channelview_xml("Ansicht A", "Switch"),
            "prj/channelviews/$cv2.xml": _channelview_xml("Ansicht B", "Dimmer"),
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(sorted(views),
                         [("Ansicht A", "Switch", "", ""),
                          ("Ansicht B", "Dimmer", "", "")])

    def test_resolve_none(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(views, [])

    def test_resolve_with_location(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/channelviews/$cv1.xml": _channelview_xml("Kugel Beet r.", "Switch"),
            "prj/channelviews/$cv1/locations/$loc1.assoc":
                _location_assoc_xml(
                    "typedelements/$root/typedelements/$floor1/typedelements/$room1"),
            "prj/typedelements/$floor1.xml": _typedelement_xml("Erdgeschoss", "Floor"),
            "prj/typedelements/$room1.xml": _typedelement_xml("Deko", "Room"),
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(
            views,
            [("Kugel Beet r.", "Switch", "",
              "Gebäude und Geräte → Erdgeschoss → Deko (Raum)")])

    def test_resolve_location_with_project_prefix(self):
        """href mit vorangestelltem projects/$<proj>/-Präfix: Root bleibt Root, kein Extra-Level."""
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/channelviews/$cv1.xml": _channelview_xml("Kugel Beet r.", "Switch"),
            "prj/channelviews/$cv1/locations/$loc1.assoc":
                _location_assoc_xml(
                    "projects/$proj/typedelements/$root/"
                    "typedelements/$floor1/typedelements/$room1"),
            "prj/typedelements/$floor1.xml": _typedelement_xml("Erdgeschoss", "Floor"),
            "prj/typedelements/$room1.xml": _typedelement_xml("Deko", "Room"),
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(
            views,
            [("Kugel Beet r.", "Switch", "",
              "Gebäude und Geräte → Erdgeschoss → Deko (Raum)")])

    def test_resolve_location_missing_element_falls_back_to_empty(self):
        """Fehlt eine typedelement-XML, wird der Pfad weggelassen (Rest bleibt)."""
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/channelviews/$cv1.xml": _channelview_xml("Kugel Beet r.", "Switch"),
            "prj/channelviews/$cv1/locations/$loc1.assoc":
                _location_assoc_xml(
                    "typedelements/$root/typedelements/$floor1/typedelements/$room1"),
            "prj/typedelements/$floor1.xml": _typedelement_xml("Erdgeschoss", "Floor"),
            # $room1.xml fehlt bewusst
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(views, [("Kugel Beet r.", "Switch", "", "")])

    def test_orphan_assoc_counts_as_unknown(self):
        """Verweist eine .assoc auf eine nicht auffindbare Channelview → 'unbekannte Ansicht'."""
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("does_not_exist"),
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(views, [("unbekannte Ansicht", "", "", "")])

    def test_broken_assoc_counts_as_unknown(self):
        """Defekte/unlesbare .assoc → 'unbekannte Ansicht', keine Exception."""
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": "<kein gueltiges xml",
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(views, [("unbekannte Ansicht", "", "", "")])


class TestCrossRefIndex(unittest.TestCase):
    """GpaCrossRefIndex: gecachte Auflösung liefert identische Ergebnisse."""

    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _gpa(self, entries):
        p = _write_gpa(entries)
        self._paths.append(p)
        return p

    def _sample(self):
        return {
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a2.assoc": _assoc_xml("cv2"),
            "prj/channelviews/$cv1.xml": _channelview_xml(
                "Ansicht A", "Switch", "de.gira.schema.functions.Switch"),
            "prj/channelviews/$cv2.xml": _channelview_xml("Ansicht B", "Dimmer"),
        }

    def test_index_matches_fresh_resolution(self):
        gpa = self._gpa(self._sample())
        fresh = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        index = GpaCrossRefIndex(gpa)
        try:
            cached = resolve_cross_reference_views(
                gpa, "prj/knxdatapoints/$dp1.xml", index=index)
        finally:
            index.close()
        self.assertEqual(sorted(cached), sorted(fresh))

    def test_index_reusable_across_multiple_calls(self):
        gpa = self._gpa(self._sample())
        index = GpaCrossRefIndex(gpa)
        try:
            first = resolve_cross_reference_views(
                gpa, "prj/knxdatapoints/$dp1.xml", index=index)
            second = resolve_cross_reference_views(
                gpa, "prj/knxdatapoints/$dp1.xml", index=index)
        finally:
            index.close()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)

    def test_close_is_idempotent(self):
        gpa = self._gpa(self._sample())
        index = GpaCrossRefIndex(gpa)
        index.close()
        index.close()  # darf nicht werfen


# ── Erweiterte Verweise: Logik, Zeitschaltuhr, Benutzer ─────────────────────────

_CONF = 'xmlns:conf="http://service.schema.gira.de/configuration"'
_DP1 = "prj/parts/$p/devices/$d/subdevices/$s/channels/$c/knxdatapoints/$dp1.xml"
_DP2 = "prj/parts/$p/devices/$d/subdevices/$s/channels/$c/knxdatapoints/$dp2.xml"


def _logic_node_xml(node_type: str, node_name: str, dp_uids) -> str:
    params = "".join(
        f'<conf:Parameter Type="datapoint" EntityId="/projectparts/$p/devices/$d/'
        f'channels/$c/knxdatapoints/${u}" Name="datapoint" />' for u in dp_uids)
    return (f'<conf:LogicNode {_CONF}><conf:EntityId>n</conf:EntityId>'
            f'<conf:EntityName>My node</conf:EntityName>'
            f'<conf:Type>LogicModule.Nodes.{node_type}</conf:Type>'
            f'<conf:NodeName>{node_name}</conf:NodeName>'
            f'<conf:Inputs>{params}</conf:Inputs></conf:LogicNode>')


def _logic_page_xml(name: str, active: bool = True) -> str:
    flag = "True" if active else "False"
    return (f'<conf:Logicpage {_CONF}><conf:EntityName>{name}</conf:EntityName>'
            f'<conf:LogicPageName>{name}</conf:LogicPageName>'
            f'<conf:IsActive>{flag}</conf:IsActive></conf:Logicpage>')


def _timer_channel_xml(dp_uids, timers) -> str:
    sdp = "".join(
        f'<conf:SceneDataPoint EntityId="{u}" Urn="x"><conf:Scenes /></conf:SceneDataPoint>'
        for u in dp_uids)
    tms = ""
    for i, (time, rec, weekdays, enabled) in enumerate(timers, 1):
        flag = "true" if enabled else "false"
        tms += (f'<conf:Timer Index="{i}" TriggerValue="1"><conf:Name />'
                f'<conf:Enabled>{flag}</conf:Enabled>'
                f'<conf:TimerType><conf:Type>pointInTime</conf:Type>'
                f'<conf:Time>{time}</conf:Time></conf:TimerType>'
                f'<conf:Recurrence><conf:Type>{rec}</conf:Type>'
                f'<conf:WeekDays>{weekdays}</conf:WeekDays></conf:Recurrence>'
                f'</conf:Timer>')
    return (f'<conf:Channel {_CONF}><conf:EntityName>Function-Timer-7</conf:EntityName>'
            f'<conf:ChannelTypeUrn>de.gira.schema.channels.FunctionTimer</conf:ChannelTypeUrn>'
            f'<conf:Configuration><conf:SceneDataPoints>{sdp}</conf:SceneDataPoints>'
            f'<conf:Timers>{tms}</conf:Timers></conf:Configuration></conf:Channel>')


def _assoc2_xml(cat_a, uid_a, cat_b, uid_b) -> str:
    return (f'<Association xmlns="http://service.schema.gira.de/configuration">'
            f'<End href="prj/x/${uid_a}" cat="{cat_a}" uid="{uid_a}" />'
            f'<End href="prj/y/${uid_b}" cat="{cat_b}" uid="{uid_b}" /></Association>')


def _user_xml(name: str, builtin: str = "") -> str:
    return (f'<conf:User {_CONF}><conf:EntityName>{name}</conf:EntityName>'
            f'<conf:BuiltInType>{builtin}</conf:BuiltInType></conf:User>')


class _TempGpaMixin:
    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _gpa(self, entries):
        p = _write_gpa(entries)
        self._paths.append(p)
        return p


class TestLogicReferences(_TempGpaMixin, unittest.TestCase):

    def _entries(self):
        base = "prj/applications/$app/logic/$l/logicpages"
        return {
            _DP1: _datapoint_xml("DP1"),
            _DP2: _datapoint_xml("DP2"),
            f"{base}/$pg1.xml": _logic_page_xml("Ost Rollladen"),
            f"{base}/$pg1/logicnodes/$n1.xml": _logic_node_xml("DatapointEvent", "Sonne Ost", ["dp1"]),
            f"{base}/$pg1/logicnodes/$n2.xml": _logic_node_xml("DatapointAction", "Rollo fahren", ["dp1"]),
            f"{base}/$pg2.xml": _logic_page_xml("Alt", active=False),
            f"{base}/$pg2/logicnodes/$n3.xml": _logic_node_xml("DatapointEvent", "x", ["DP2"]),
            f"{base}/$pg2/logicnodes/$n4.xml": _logic_node_xml("AndGate", "UND", []),
        }

    def test_logic_counts_in_parse(self):
        by_name = {dp.entity_name: dp for dp in parse_gpa_datapoints(self._gpa(self._entries()))}
        self.assertEqual(by_name["DP1"].logic_reference_count, 2)
        self.assertEqual(by_name["DP2"].logic_reference_count, 1)  # UID case-insensitiv
        self.assertEqual(by_name["DP1"].cross_reference_count, 0)
        self.assertEqual(by_name["DP1"].total_reference_count, 2)

    def test_logic_details(self):
        refs = resolve_datapoint_references(self._gpa(self._entries()), _DP1)
        self.assertEqual(refs.visu, [])
        self.assertEqual(
            [(r.page_name, r.role, r.node_name) for r in refs.logic],
            [("Ost Rollladen", "Ausgang", "Rollo fahren"), ("Ost Rollladen", "Eingang", "Sonne Ost")])
        self.assertTrue(all(r.page_active for r in refs.logic))

    def test_inactive_page_flag(self):
        refs = resolve_datapoint_references(self._gpa(self._entries()), _DP2)
        self.assertEqual(len(refs.logic), 1)
        self.assertFalse(refs.logic[0].page_active)
        self.assertEqual(refs.logic[0].page_name, "Alt")

    def test_unknown_page_and_generic_role(self):
        gpa = self._gpa({
            _DP1: _datapoint_xml("DP1"),
            "prj/logic/$l/logicpages/$gone/logicnodes/$n.xml":
                _logic_node_xml("SomethingElse", "", ["dp1"]),
        })
        refs = resolve_datapoint_references(gpa, _DP1)
        self.assertEqual(refs.logic[0].page_name, "(unbekannte Logikseite)")
        self.assertEqual(refs.logic[0].role, "Baustein")

    def test_broken_logic_node_is_skipped(self):
        gpa = self._gpa({
            _DP1: _datapoint_xml("DP1"),
            "prj/logic/$l/logicpages/$pg/logicnodes/$n.xml": "<kaputt knxdatapoints/$dp1",
        })
        self.assertEqual(parse_gpa_datapoints(gpa)[0].logic_reference_count, 0)


class TestTimerReferences(_TempGpaMixin, unittest.TestCase):

    _CH = "prj/parts/$p/devices/$d/subdevices/$s/channels"

    def _entries(self, timers, dp_uids=("dp1",)):
        return {
            _DP1: _datapoint_xml("DP1"),
            f"{self._CH}/$t1.xml": _timer_channel_xml(dp_uids, timers),
            f"{self._CH}/$t1/channelviewtrigger/$a.assoc":
                _assoc2_xml("channel", "t1", "channelview", "cv9"),
            "prj/channelviews/$cv9.xml": _channelview_xml("Rollo Schlafen", "BlindWithPos"),
        }

    def test_timer_with_schedules(self):
        gpa = self._gpa(self._entries([
            ("08:00:00", "daily", "MTWTFSS", True),
            ("20:00:00", "weekly", "MTWTF--", False),
            ("09:15:00", "weekly", "-----SS", True),
        ]))
        self.assertEqual(parse_gpa_datapoints(gpa)[0].timer_reference_count, 1)
        refs = resolve_datapoint_references(gpa, _DP1)
        self.assertEqual(len(refs.timers), 1)
        t = refs.timers[0]
        self.assertEqual(t.view_name, "Rollo Schlafen")
        self.assertEqual(t.schedules, ("08:00 täglich", "20:00 Mo–Fr (inaktiv)", "09:15 Sa, So"))
        self.assertEqual(t.active_count, 2)

    def test_timer_without_view_falls_back_to_channel_name(self):
        entries = self._entries([("06:00:00", "daily", "MTWTFSS", True)])
        del entries[f"{self._CH}/$t1/channelviewtrigger/$a.assoc"]
        refs = resolve_datapoint_references(self._gpa(entries), _DP1)
        self.assertEqual(refs.timers[0].view_name, "Function-Timer-7")

    def test_timer_for_other_datapoint_not_counted(self):
        gpa = self._gpa(self._entries([("06:00:00", "daily", "MTWTFSS", True)], dp_uids=("other",)))
        self.assertEqual(parse_gpa_datapoints(gpa)[0].timer_reference_count, 0)


class TestVisuUsers(_TempGpaMixin, unittest.TestCase):

    def test_users_resolved_sorted_and_translated(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/channelviews/$cv1.xml": _channelview_xml("Licht", "Switch"),
            "prj/channelviews/$cv1/users/$u1.assoc": _assoc2_xml("channelview", "cv1", "user", "uk"),
            "prj/channelviews/$cv1/users/$u2.assoc": _assoc2_xml("channelview", "cv1", "user", "ua"),
            "prj/channelviews/$cv1/users/$u3.assoc": _assoc2_xml("channelview", "cv1", "user", "us"),
            "prj/channelviews/$cv1/users/$u4.assoc": _assoc2_xml("channelview", "cv1", "user", "ue"),
            "prj/users/$uk.xml": _user_xml("Kinderaccount"),
            "prj/users/$ua.xml": _user_xml("Eigentümer (Administrator)", "Admin"),
            "prj/users/$us.xml": _user_xml("System", "System"),
            "prj/users/$ue.xml": _user_xml("Everyone", "Everyone"),
        })
        refs = resolve_datapoint_references(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(refs.visu[0].users,
                         ("Alle", "Eigentümer (Administrator)", "Kinderaccount"))

    def test_orphan_flag(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("missing"),
        })
        refs = resolve_datapoint_references(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertTrue(refs.visu[0].orphan)
        self.assertFalse(refs.is_unused)


class TestBuildReferenceMap(_TempGpaMixin, unittest.TestCase):

    def test_map_covers_all_and_updates_counts(self):
        base = "prj/applications/$app/logic/$l/logicpages"
        gpa = self._gpa({
            _DP1: _datapoint_xml("DP1"),
            _DP2: _datapoint_xml("DP2"),
            _DP1[:-4] + "/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/channelviews/$cv1.xml": _channelview_xml("Ansicht A", "Switch"),
            f"{base}/$pg1.xml": _logic_page_xml("Seite"),
            f"{base}/$pg1/logicnodes/$n1.xml": _logic_node_xml("DatapointEvent", "n", ["dp1"]),
        })
        dps = parse_gpa_datapoints(gpa)
        for dp in dps:
            dp.cross_reference_count = dp.logic_reference_count = 99  # wird überschrieben
        ref_map = build_reference_map(gpa, dps)
        by_name = {dp.entity_name: dp for dp in dps}
        self.assertEqual(set(ref_map), {_DP1, _DP2})
        self.assertEqual(by_name["DP1"].cross_reference_count, 1)
        self.assertEqual(by_name["DP1"].logic_reference_count, 1)
        self.assertTrue(ref_map[_DP2].is_unused)
        self.assertEqual(ref_map[_DP1].summary_text(), "Visu: Ansicht A | Logik: Seite (Eingang)")

    def test_datapoint_uid(self):
        self.assertEqual(datapoint_uid("a\\knxdatapoints\\$AbC-1.xml"), "abc-1")
        self.assertEqual(datapoint_uid("a/knxdatapoints/$x"), "x")


class TestReferenceFilterAndImpact(unittest.TestCase):

    def _refs(self, visu=0, logic=0, timers=0):
        return DatapointReferences(
            visu=[VisuReference(view_name=f"V{i}", location="Gebäude und Geräte → EG")
                  for i in range(visu)],
            logic=[LogicReference(page_name=f"L{i}", role="Eingang") for i in range(logic)],
            timers=[TimerReference(view_name=f"T{i}") for i in range(timers)],
        )

    def test_filter_modes(self):
        rows = (self._refs(), self._refs(visu=1), self._refs(logic=1), self._refs(timers=1), None)
        self.assertEqual(REFERENCE_FILTERS[0], "Alle")
        cases = {
            "Alle":              [True, True, True, True, True],
            "Verwendet":         [False, True, True, True, False],
            "Ungenutzt":         [True, False, False, False, False],
            "In Logik":          [False, False, True, False, False],
            "Mit Zeitschaltuhr": [False, False, False, True, False],
        }
        self.assertEqual(set(cases), set(REFERENCE_FILTERS))
        for mode, expected in cases.items():
            got = [matches_reference_filter(r, mode) for r in rows]
            self.assertEqual(got, expected, mode)

    def test_sync_impact(self):
        cands = [
            SyncCandidate(True, SyncStatus.AENDERUNG, "a", "A", "A2", "1/1/1", 1, "Write"),
            SyncCandidate(True, SyncStatus.LEERZEICHEN, "b", "B ", "B", "1/1/2", 2, "Write"),
            SyncCandidate(True, SyncStatus.AENDERUNG, "c", "C", "C2", "1/1/3", 3, "Write"),
            SyncCandidate(False, SyncStatus.AENDERUNG, "d", "D", "D2", "1/1/4", 4, "Write"),
            SyncCandidate(True, SyncStatus.NICHT_IN_ETS, "e", "E", "", "1/1/5", 5, "GPA"),
        ]
        refs = {"a": self._refs(visu=2, logic=1), "b": self._refs(),
                "c": self._refs(visu=1, timers=1), "d": self._refs(logic=3)}
        impact = summarize_sync_impact(cands, refs)
        self.assertEqual(impact.renamed, 3)
        self.assertEqual((impact.in_visu, impact.in_logic, impact.in_timers, impact.unused),
                         (2, 1, 1, 1))
        self.assertEqual(impact.views,
                         ["Gebäude und Geräte → EG → V0", "Gebäude und Geräte → EG → V1"])
        self.assertEqual(impact.logic_pages, ["L0"])
        self.assertEqual([c.zip_path for c, _ in impact.rows], ["a", "b", "c"])


class TestCsvWithReferences(_TempGpaMixin, unittest.TestCase):

    def _csv_path(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self._paths.append(path)
        return Path(path)

    def test_csv_columns(self):
        cands = [
            SyncCandidate(True, SyncStatus.AENDERUNG, "a", "A", "A2", "1/1/1", 1, "Write"),
            SyncCandidate(False, SyncStatus.NUR_GPA, "b", "B", "", "1/1/2", 2, "Write"),
            SyncCandidate(False, SyncStatus.NUR_ETS, "", "", "X", "1/1/3", 3, "ETS"),
        ]
        refs = {"a": DatapointReferences(logic=[LogicReference(page_name="Seite", role="Ausgang")]),
                "b": DatapointReferences()}
        path = self._csv_path()
        export_candidates_csv(cands, path, references=refs)
        rows = [line.split(";") for line in path.read_text("utf-8-sig").splitlines()]
        self.assertEqual(rows[0][-4:], ["Visu", "Logik", "Zeitschaltuhr", "Verwendet in"])
        self.assertEqual(rows[1][-4:], ["0", "1", "0", "Logik: Seite (Ausgang)"])
        self.assertEqual(rows[2][-4:], ["0", "0", "0", "nicht verwendet"])
        self.assertEqual(rows[3][-4:], ["", "", "", ""])

    def test_csv_without_references_unchanged(self):
        path = self._csv_path()
        export_candidates_csv(
            [SyncCandidate(True, SyncStatus.AENDERUNG, "a", "A", "A2", "1/1/1", 1, "W")], path)
        header = path.read_text("utf-8-sig").splitlines()[0].split(";")
        self.assertEqual(len(header), 7)


if __name__ == "__main__":
    unittest.main()
