from .ga import ga_to_int, int_to_ga
from .models import EtsGroupAddress, GpaDatapoint, SyncCandidate, SyncStatus
from .parser_ets import (
    EtsProjectPasswordRequired,
    EtsProjectReadError,
    # Hinweis: Dieser private Import bleibt absichtlich hier —
    # 7 Tests greifen über das core-Modul darauf zu. Bei zukünftigem
    # Refactoring: Tests auf direkten Import aus parser_ets.py umstellen.
    _extract_group_addresses_from_xml_text,
    parse_ets_ga_export,
)
from .parser_gpa import parse_gpa_datapoints
from .sync import build_partial_candidates, build_sync_candidates, make_unique_name
from .utils import detect_encoding, normalize_name_for_compare, replace_entity_name_preserve_xml
from .writer import export_candidates_csv, write_updated_gpa

__all__ = [
    "ga_to_int", "int_to_ga",
    "EtsGroupAddress", "GpaDatapoint", "SyncCandidate", "SyncStatus",
    "EtsProjectPasswordRequired", "EtsProjectReadError", "parse_ets_ga_export",
    "parse_gpa_datapoints",
    "build_partial_candidates", "build_sync_candidates",
    "export_candidates_csv", "write_updated_gpa",
]
