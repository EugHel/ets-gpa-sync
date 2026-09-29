from .ga import ga_to_int, int_to_ga
from .models import (
    DatapointReferences,
    EtsGroupAddress,
    GpaDatapoint,
    LogicReference,
    SyncCandidate,
    SyncStatus,
    TimerReference,
    VisuReference,
)
from .parser_ets import (
    EtsProjectPasswordRequired,
    EtsProjectReadError,
    # Hinweis: Dieser private Import bleibt absichtlich hier —
    # 7 Tests greifen über das core-Modul darauf zu. Bei zukünftigem
    # Refactoring: Tests auf direkten Import aus parser_ets.py umstellen.
    _extract_group_addresses_from_xml_text,
    parse_ets_ga_export,
)
from .parser_gpa import (
    GpaCrossRefIndex,
    build_reference_map,
    datapoint_uid,
    parse_gpa_datapoints,
    resolve_cross_reference_views,
    resolve_datapoint_references,
)
from .sync import (
    REFERENCE_FILTERS,
    SyncImpact,
    build_partial_candidates,
    build_sync_candidates,
    format_ga_roles,
    make_unique_name,
    matches_reference_filter,
    most_common_users,
    source_label,
    summarize_sync_impact,
)
from .utils import detect_encoding, normalize_name_for_compare, replace_entity_name_preserve_xml
from .writer import export_candidates_csv, write_updated_gpa

__all__ = [
    "ga_to_int", "int_to_ga",
    "EtsGroupAddress", "GpaDatapoint", "SyncCandidate", "SyncStatus",
    "DatapointReferences", "VisuReference", "LogicReference", "TimerReference",
    "EtsProjectPasswordRequired", "EtsProjectReadError", "parse_ets_ga_export",
    "parse_gpa_datapoints", "resolve_cross_reference_views", "GpaCrossRefIndex",
    "resolve_datapoint_references", "build_reference_map", "datapoint_uid",
    "build_partial_candidates", "build_sync_candidates",
    "REFERENCE_FILTERS", "matches_reference_filter", "SyncImpact", "summarize_sync_impact",
    "format_ga_roles", "most_common_users", "source_label",
    "export_candidates_csv", "write_updated_gpa",
]
