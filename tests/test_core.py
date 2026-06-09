"""
Unit-Tests für die Kernlogik des ETS GPA Sync Tools.
Getestet werden ausschließlich reine Funktionen ohne GUI oder Datei-I/O.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gpa_ga_sync import core as tool


# ---------------------------------------------------------------------------
# KNX-Adresskonvertierung
# ---------------------------------------------------------------------------

class TestGaToInt(unittest.TestCase):

    def test_standard_addresses(self):
        self.assertEqual(tool.ga_to_int("0/0/0"), 0)
        self.assertEqual(tool.ga_to_int("0/0/1"), 1)
        self.assertEqual(tool.ga_to_int("0/1/0"), 256)
        self.assertEqual(tool.ga_to_int("1/0/0"), 2048)
        self.assertEqual(tool.ga_to_int("1/2/3"), 2048 + 512 + 3)
        self.assertEqual(tool.ga_to_int("31/7/255"), 65535)

    def test_integer_form(self):
        self.assertEqual(tool.ga_to_int("0"), 0)
        self.assertEqual(tool.ga_to_int("1"), 1)
        self.assertEqual(tool.ga_to_int("258"), 258)
        self.assertEqual(tool.ga_to_int("65535"), 65535)

    def test_whitespace_ignored(self):
        self.assertEqual(tool.ga_to_int("  1/2/3  "), tool.ga_to_int("1/2/3"))

    def test_invalid_part_count(self):
        with self.assertRaises(ValueError):
            tool.ga_to_int("1/2")
        with self.assertRaises(ValueError):
            tool.ga_to_int("1/2/3/4")

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            tool.ga_to_int("32/0/0")   # main > 31
        with self.assertRaises(ValueError):
            tool.ga_to_int("0/8/0")    # middle > 7
        with self.assertRaises(ValueError):
            tool.ga_to_int("0/0/256")  # sub > 255

    def test_integer_out_of_range(self):
        with self.assertRaises(ValueError):
            tool.ga_to_int("65536")
        with self.assertRaises(ValueError):
            tool.ga_to_int("-1")


class TestIntToGa(unittest.TestCase):

    def test_standard_values(self):
        self.assertEqual(tool.int_to_ga(0), "0/0/0")
        self.assertEqual(tool.int_to_ga(1), "0/0/1")
        self.assertEqual(tool.int_to_ga(256), "0/1/0")
        self.assertEqual(tool.int_to_ga(2048), "1/0/0")
        self.assertEqual(tool.int_to_ga(65535), "31/7/255")

    def test_roundtrip(self):
        for address in ("0/0/1", "1/2/3", "5/3/12", "31/7/255", "0/0/0"):
            self.assertEqual(tool.int_to_ga(tool.ga_to_int(address)), address)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            tool.int_to_ga(-1)
        with self.assertRaises(ValueError):
            tool.int_to_ga(65536)


# ---------------------------------------------------------------------------
# Eindeutige Namen
# ---------------------------------------------------------------------------

class TestMakeUniqueName(unittest.TestCase):

    def test_no_conflict(self):
        self.assertEqual(tool.make_unique_name("Licht EG", set()), "Licht EG")

    def test_first_conflict(self):
        self.assertEqual(tool.make_unique_name("Licht EG", {"Licht EG"}), "Licht EG (2)")

    def test_multiple_conflicts(self):
        used = {"Licht EG", "Licht EG (2)", "Licht EG (3)"}
        self.assertEqual(tool.make_unique_name("Licht EG", used), "Licht EG (4)")

    def test_gap_in_sequence_is_filled(self):
        # (2) fehlt → soll trotzdem (2) vergeben werden, nicht (4)
        used = {"Licht EG", "Licht EG (3)"}
        self.assertEqual(tool.make_unique_name("Licht EG", used), "Licht EG (2)")

    def test_empty_name(self):
        self.assertEqual(tool.make_unique_name("", set()), "")

    def test_unrelated_names_not_affected(self):
        self.assertEqual(tool.make_unique_name("Heizung", {"Licht EG"}), "Heizung")


# ---------------------------------------------------------------------------
# Whitespace-Normalisierung
# ---------------------------------------------------------------------------

class TestNormalizeNameForCompare(unittest.TestCase):

    def test_leading_trailing_whitespace(self):
        self.assertEqual(tool.normalize_name_for_compare("  foo  "), "foo")

    def test_multiple_inner_spaces(self):
        self.assertEqual(tool.normalize_name_for_compare("foo  bar"), "foo bar")

    def test_tabs_and_newlines(self):
        self.assertEqual(tool.normalize_name_for_compare("foo\tbar\nbaz"), "foo bar baz")

    def test_already_normalized(self):
        self.assertEqual(tool.normalize_name_for_compare("Licht EG"), "Licht EG")

    def test_empty_string(self):
        self.assertEqual(tool.normalize_name_for_compare(""), "")

    def test_only_whitespace(self):
        self.assertEqual(tool.normalize_name_for_compare("   "), "")


# ---------------------------------------------------------------------------
# XML EntityName ersetzen
# ---------------------------------------------------------------------------

class TestReplaceEntityName(unittest.TestCase):

    def test_basic_replacement(self):
        xml = "<root><conf:EntityName>AltNamen</conf:EntityName></root>"
        result = tool.replace_entity_name_preserve_xml(xml, "NeuNamen")
        self.assertIn("NeuNamen", result)
        self.assertNotIn("AltNamen", result)

    def test_preserves_surrounding_xml(self):
        xml = '<root attr="x"><conf:EntityName>Alt</conf:EntityName><other>data</other></root>'
        result = tool.replace_entity_name_preserve_xml(xml, "Neu")
        self.assertIn('attr="x"', result)
        self.assertIn("<other>data</other>", result)

    def test_html_escaping_ampersand(self):
        xml = "<root><conf:EntityName>Alt</conf:EntityName></root>"
        result = tool.replace_entity_name_preserve_xml(xml, "A & B")
        self.assertIn("A &amp; B", result)

    def test_html_escaping_less_than(self):
        xml = "<root><conf:EntityName>Alt</conf:EntityName></root>"
        result = tool.replace_entity_name_preserve_xml(xml, "A < B")
        self.assertIn("A &lt; B", result)

    def test_unprefixed_tag(self):
        xml = "<root><EntityName>Alt</EntityName></root>"
        result = tool.replace_entity_name_preserve_xml(xml, "Neu")
        self.assertIn("Neu", result)
        self.assertNotIn("Alt", result)

    def test_missing_entity_name_raises(self):
        xml = "<root><OtherTag>value</OtherTag></root>"
        with self.assertRaises(ValueError):
            tool.replace_entity_name_preserve_xml(xml, "Neu")

    def test_unicode_name(self):
        xml = "<root><conf:EntityName>Alt</conf:EntityName></root>"
        result = tool.replace_entity_name_preserve_xml(xml, "Licht Ärger öüß")
        self.assertIn("Licht Ärger öüß", result)


# ---------------------------------------------------------------------------
# Encoding-Erkennung
# ---------------------------------------------------------------------------

class TestDetectEncoding(unittest.TestCase):

    def test_utf8_bom(self):
        self.assertEqual(tool.detect_encoding(b"\xef\xbb\xbfHello"), "utf-8-sig")

    def test_xml_declaration_utf16(self):
        data = b'<?xml version="1.0" encoding="utf-16"?><root/>'
        self.assertEqual(tool.detect_encoding(data), "utf-16")

    def test_xml_declaration_iso(self):
        data = b"<?xml version='1.0' encoding='ISO-8859-1'?><root/>"
        self.assertEqual(tool.detect_encoding(data), "ISO-8859-1")

    def test_default_utf8(self):
        self.assertEqual(tool.detect_encoding(b"<root/>"), "utf-8")

    def test_empty(self):
        self.assertEqual(tool.detect_encoding(b""), "utf-8")


# ---------------------------------------------------------------------------
# ETS-XML-Parser
# ---------------------------------------------------------------------------

GA_XML_SAMPLE = """\
<?xml version="1.0" encoding="utf-8"?>
<GroupAddress-Export xmlns="http://knx.org/xml/ga-export/01">
  <GroupRange Name="EG" RangeStart="0" RangeEnd="2047">
    <GroupRange Name="Licht" RangeStart="0" RangeEnd="255">
      <GroupAddress Name="Licht EG Ein" Address="0/0/1" />
      <GroupAddress Name="Licht EG Aus" Address="0/0/2" />
    </GroupRange>
  </GroupRange>
  <GroupRange Name="OG" RangeStart="2048" RangeEnd="4095">
    <GroupRange Name="Heizung" RangeStart="2048" RangeEnd="2303">
      <GroupAddress Name="Heizung Soll" Address="1/0/0" />
    </GroupRange>
  </GroupRange>
</GroupAddress-Export>"""


class TestExtractGroupAddresses(unittest.TestCase):

    def test_parses_all_addresses(self):
        result = tool._extract_group_addresses_from_xml_text(GA_XML_SAMPLE)
        self.assertEqual(len(result), 3)

    def test_correct_names(self):
        result = tool._extract_group_addresses_from_xml_text(GA_XML_SAMPLE)
        self.assertEqual(result[tool.ga_to_int("0/0/1")].name, "Licht EG Ein")
        self.assertEqual(result[tool.ga_to_int("0/0/2")].name, "Licht EG Aus")
        self.assertEqual(result[tool.ga_to_int("1/0/0")].name, "Heizung Soll")

    def test_correct_address_strings(self):
        result = tool._extract_group_addresses_from_xml_text(GA_XML_SAMPLE)
        self.assertEqual(result[tool.ga_to_int("0/0/1")].address, "0/0/1")

    def test_empty_xml(self):
        self.assertEqual(tool._extract_group_addresses_from_xml_text("<root/>"), {})

    def test_invalid_xml_returns_empty(self):
        self.assertEqual(tool._extract_group_addresses_from_xml_text("kein xml"), {})

    def test_entry_without_name_skipped(self):
        xml = """\
<GroupAddress-Export xmlns="http://knx.org/xml/ga-export/01">
  <GroupRange Name="HG" RangeStart="0" RangeEnd="2047">
    <GroupRange Name="MG" RangeStart="0" RangeEnd="255">
      <GroupAddress Address="0/0/1" />
    </GroupRange>
  </GroupRange>
</GroupAddress-Export>"""
        result = tool._extract_group_addresses_from_xml_text(xml)
        self.assertEqual(result, {})

    def test_unicode_name(self):
        xml = """\
<GroupAddress-Export xmlns="http://knx.org/xml/ga-export/01">
  <GroupRange Name="HG" RangeStart="0" RangeEnd="2047">
    <GroupRange Name="MG" RangeStart="0" RangeEnd="255">
      <GroupAddress Name="Lüftung Küche" Address="0/0/5" />
    </GroupRange>
  </GroupRange>
</GroupAddress-Export>"""
        result = tool._extract_group_addresses_from_xml_text(xml)
        self.assertEqual(result[tool.ga_to_int("0/0/5")].name, "Lüftung Küche")


# ---------------------------------------------------------------------------
# Sync-Kandidaten-Logik (Kernfunktion)
# ---------------------------------------------------------------------------

def _dp(zip_path, entity_name, write_ga=None, read_ga=None, listeners=()):
    return tool.GpaDatapoint(
        zip_path=zip_path,
        entity_name=entity_name,
        write_group_address=write_ga,
        read_group_address=read_ga,
        listener_group_addresses=listeners,
    )

def _ets(address, name):
    value = tool.ga_to_int(address)
    return tool.EtsGroupAddress(address=address, value=value, name=name)


class TestBuildSyncCandidates(unittest.TestCase):

    def test_match_by_write_address(self):
        val = tool.ga_to_int("0/0/1")
        candidates = tool.build_sync_candidates(
            [_dp("f.xml", "Alt", write_ga=val)],
            {val: _ets("0/0/1", "Neu")},
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].new_name, "Neu")
        self.assertEqual(candidates[0].status, "Änderung")
        self.assertTrue(candidates[0].selected)

    def test_no_candidate_when_names_equal(self):
        val = tool.ga_to_int("0/0/1")
        candidates = tool.build_sync_candidates(
            [_dp("f.xml", "Gleich", write_ga=val)],
            {val: _ets("0/0/1", "Gleich")},
        )
        self.assertEqual(len(candidates), 0)

    def test_whitespace_only_difference(self):
        val = tool.ga_to_int("0/0/1")
        candidates = tool.build_sync_candidates(
            [_dp("f.xml", "Licht  EG", write_ga=val)],
            {val: _ets("0/0/1", "Licht EG")},
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].status, "Leerzeichen")

    def test_no_ets_match(self):
        candidates = tool.build_sync_candidates(
            [_dp("f.xml", "Alt", write_ga=tool.ga_to_int("0/0/99"))],
            {tool.ga_to_int("0/0/1"): _ets("0/0/1", "Neu")},
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].status, "Nicht in ETS")
        self.assertFalse(candidates[0].selected)

    def test_write_address_wins_over_read(self):
        write_val = tool.ga_to_int("0/0/1")
        read_val = tool.ga_to_int("0/0/2")
        candidates = tool.build_sync_candidates(
            [_dp("f.xml", "Alt", write_ga=write_val, read_ga=read_val)],
            {
                write_val: _ets("0/0/1", "Write-Name"),
                read_val:  _ets("0/0/2", "Read-Name"),
            },
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].new_name, "Write-Name")
        self.assertEqual(candidates[0].source_field, "WriteGroupAddress")

    def test_match_by_read_when_no_write(self):
        read_val = tool.ga_to_int("0/0/2")
        candidates = tool.build_sync_candidates(
            [_dp("f.xml", "Alt", read_ga=read_val)],
            {read_val: _ets("0/0/2", "Read-Name")},
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].new_name, "Read-Name")

    def test_ambiguous_different_names(self):
        write_val = tool.ga_to_int("0/0/1")
        read_val = tool.ga_to_int("0/0/2")
        candidates = tool.build_sync_candidates(
            [_dp("f.xml", "Alt", write_ga=write_val, read_ga=read_val)],
            {
                write_val: _ets("0/0/1", "Name A"),
                read_val:  _ets("0/0/2", "Name B"),
            },
        )
        # Write-Adresse hat Priorität → kein Mehrdeutig, sondern direkter Treffer
        self.assertEqual(candidates[0].new_name, "Name A")

    def test_deduplication_across_datapoints(self):
        val1 = tool.ga_to_int("0/0/1")
        val2 = tool.ga_to_int("0/0/2")
        candidates = tool.build_sync_candidates(
            [
                _dp("a.xml", "Alt A", write_ga=val1),
                _dp("b.xml", "Alt B", write_ga=val2),
            ],
            {
                val1: _ets("0/0/1", "Gleicher Name"),
                val2: _ets("0/0/2", "Gleicher Name"),
            },
        )
        new_names = {c.new_name for c in candidates if c.status == "Änderung"}
        self.assertIn("Gleicher Name", new_names)
        self.assertIn("Gleicher Name (2)", new_names)

    def test_duplicate_write_address_marked_as_conflict(self):
        # Adress-Konflikt – bitte prüfen: zwei Datenpunkte tragen dieselbe Write-GA 2/6/4.
        # Beide würden auf denselben ETS-Namen umbenannt → Adress-Konflikt statt "(N)".
        val = tool.ga_to_int("2/6/4")
        candidates = tool.build_sync_candidates(
            [
                _dp("rgb.xml", "Alt RGB", write_ga=val),
                _dp("hsv.xml", "Alt HSV", write_ga=val),
            ],
            {val: _ets("2/6/4", "Kochinsel HSV")},
        )
        self.assertEqual(len(candidates), 2)
        statuses = {c.status for c in candidates}
        self.assertEqual(statuses, {tool.SyncStatus.ADRESSKONFLIKT})
        # Kein "(N)" und keine Änderung wird erzeugt.
        new_names = {c.new_name for c in candidates}
        self.assertNotIn("Kochinsel HSV (2)", new_names)
        self.assertFalse(any(c.status == tool.SyncStatus.AENDERUNG for c in candidates))

    def test_duplicate_address_conflict_not_selected(self):
        # Konflikt-Zeilen dürfen nicht auswählbar/schreibbar sein.
        val = tool.ga_to_int("2/6/4")
        candidates = tool.build_sync_candidates(
            [
                _dp("a.xml", "Alt A", write_ga=val),
                _dp("b.xml", "Alt B", write_ga=val),
            ],
            {val: _ets("2/6/4", "Doppelte GA")},
        )
        self.assertTrue(all(not c.selected for c in candidates))

    def test_same_name_different_address_still_deduplicates(self):
        # Regressionsschutz: gleicher Name bei VERSCHIEDENEN Adressen bleibt
        # ein legitimer Dedup-Fall mit "(2)" – kein Adress-Konflikt.
        val1 = tool.ga_to_int("0/0/1")
        val2 = tool.ga_to_int("0/0/2")
        candidates = tool.build_sync_candidates(
            [
                _dp("a.xml", "Alt A", write_ga=val1),
                _dp("b.xml", "Alt B", write_ga=val2),
            ],
            {
                val1: _ets("0/0/1", "Gleicher Name"),
                val2: _ets("0/0/2", "Gleicher Name"),
            },
        )
        self.assertFalse(any(c.status == tool.SyncStatus.ADRESSKONFLIKT for c in candidates))
        new_names = {c.new_name for c in candidates if c.status == tool.SyncStatus.AENDERUNG}
        self.assertIn("Gleicher Name (2)", new_names)

    def test_empty_inputs(self):
        self.assertEqual(tool.build_sync_candidates([], {}), [])

    def test_multiple_matches_all_different(self):
        results = tool.build_sync_candidates(
            [
                _dp("a.xml", "Alt A", write_ga=tool.ga_to_int("0/0/1")),
                _dp("b.xml", "Alt B", write_ga=tool.ga_to_int("0/0/2")),
                _dp("c.xml", "Alt C", write_ga=tool.ga_to_int("0/0/3")),
            ],
            {
                tool.ga_to_int("0/0/1"): _ets("0/0/1", "Neu A"),
                tool.ga_to_int("0/0/2"): _ets("0/0/2", "Neu B"),
                tool.ga_to_int("0/0/3"): _ets("0/0/3", "Neu C"),
            },
        )
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.status == "Änderung" for r in results))


if __name__ == "__main__":
    unittest.main(verbosity=2)
