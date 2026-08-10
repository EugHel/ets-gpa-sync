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
    parse_gpa_datapoints,
    resolve_cross_reference_views,
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


def _channelview_xml(name: str, channel_type: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<conf:Channelview {_NS}>'
        f'<conf:EntityName>{name}</conf:EntityName>'
        f'<conf:ChannelTypeId>{channel_type}</conf:ChannelTypeId>'
        '</conf:Channelview>'
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
            "prj/channelviews/$cv1.xml": _channelview_xml("Kugel Beet r.", "Switch"),
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(views, [("Kugel Beet r.", "Switch")])

    def test_resolve_multiple_views(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("cv1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a2.assoc": _assoc_xml("cv2"),
            "prj/channelviews/$cv1.xml": _channelview_xml("Ansicht A", "Switch"),
            "prj/channelviews/$cv2.xml": _channelview_xml("Ansicht B", "Dimmer"),
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(sorted(views), [("Ansicht A", "Switch"), ("Ansicht B", "Dimmer")])

    def test_resolve_none(self):
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(views, [])

    def test_orphan_assoc_counts_as_unknown(self):
        """Verweist eine .assoc auf eine nicht auffindbare Channelview → 'unbekannte Ansicht'."""
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": _assoc_xml("does_not_exist"),
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(views, [("unbekannte Ansicht", "")])

    def test_broken_assoc_counts_as_unknown(self):
        """Defekte/unlesbare .assoc → 'unbekannte Ansicht', keine Exception."""
        gpa = self._gpa({
            "prj/knxdatapoints/$dp1.xml": _datapoint_xml("DP1"),
            "prj/knxdatapoints/$dp1/datapointviews/$a1.assoc": "<kein gueltiges xml",
        })
        views = resolve_cross_reference_views(gpa, "prj/knxdatapoints/$dp1.xml")
        self.assertEqual(views, [("unbekannte Ansicht", "")])


if __name__ == "__main__":
    unittest.main()
