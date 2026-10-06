"""Unit-Tests für die Update-Prüfung (ohne echten Netzzugriff)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gpa_ga_sync.core.update import check_for_update, is_newer, parse_version  # noqa: E402


def _rel(tag, draft=False, prerelease=True):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease,
            "html_url": f"https://github.com/EugHel/ets-gpa-sync/releases/tag/{tag}"}


class TestVersionCompare(unittest.TestCase):

    def test_parse(self):
        self.assertEqual(parse_version("v0.10.1-beta"), (0, 10, 1, 0, "beta"))
        self.assertEqual(parse_version("1.0.0"), (1, 0, 0, 1, ""))
        self.assertIsNone(parse_version("sicherung-vor-x"))
        self.assertIsNone(parse_version(""))

    def test_numeric_not_lexical(self):
        self.assertTrue(is_newer("v0.10.0-beta", "v0.9.1-beta"))
        self.assertFalse(is_newer("v0.9.1-beta", "v0.10.0-beta"))

    def test_final_beats_prerelease(self):
        self.assertTrue(is_newer("v1.0.0", "v1.0.0-beta"))
        self.assertFalse(is_newer("v1.0.0-beta", "v1.0.0"))

    def test_equal_is_not_newer(self):
        self.assertFalse(is_newer("v0.10.1-beta", "v0.10.1-beta"))

    def test_invalid_never_newer(self):
        self.assertFalse(is_newer("kaputt", "v0.1.0"))
        self.assertFalse(is_newer("v9.9.9", "kaputt"))


class TestCheckForUpdate(unittest.TestCase):

    def test_newer_release_found(self):
        info = check_for_update("v0.10.1-beta", fetch=lambda: [
            _rel("v0.10.1-beta"), _rel("v0.10.2-beta"), _rel("v0.9.1-beta")])
        self.assertEqual(info.version, "v0.10.2-beta")
        self.assertTrue(info.url.endswith("/v0.10.2-beta"))

    def test_up_to_date(self):
        self.assertIsNone(check_for_update("v0.10.1-beta", fetch=lambda: [
            _rel("v0.10.1-beta"), _rel("v0.9.1-beta")]))

    def test_drafts_and_odd_tags_ignored(self):
        self.assertIsNone(check_for_update("v0.10.1-beta", fetch=lambda: [
            _rel("v0.11.0-beta", draft=True), _rel("sicherung"), {"foo": 1}, "x"]))

    def test_network_error_is_silent(self):
        def boom():
            raise OSError("offline")
        self.assertIsNone(check_for_update("v0.10.1-beta", fetch=boom))

    def test_unexpected_payload_is_silent(self):
        self.assertIsNone(check_for_update("v0.10.1-beta",
                                           fetch=lambda: {"message": "rate limit"}))


if __name__ == "__main__":
    unittest.main()
