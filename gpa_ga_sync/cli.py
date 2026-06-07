from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from .core import (
    SyncStatus,
    build_sync_candidates,
    export_candidates_csv,
    parse_ets_ga_export,
    parse_gpa_datapoints,
    write_updated_gpa,
)
from .config import APP_VERSION
from .log import setup_logging


def run_cli(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=f"GPA-Datenpunktnamen mit ETS-Gruppenadressnamen synchronisieren ({APP_VERSION})")
    parser.add_argument("--gpa", required=True, help="Pfad zur GPA-Datei")
    parser.add_argument("--ets", required=True, help="Pfad zum ETS-Gruppenadress-Export XML")
    parser.add_argument("--out", help="Ausgabedatei .gpa")
    parser.add_argument("--password", default=None, help="ZIP-Passwort, falls GPA-Archiv verschlüsselt ist")
    parser.add_argument("--ets-password", default=None, help="ETS-Projektpasswort, falls .knxproj verschlüsselt ist")
    parser.add_argument("--csv", help="CSV-Export speichern")
    parser.add_argument("--apply-all", action="store_true", help="Alle eindeutigen Änderungen anwenden")
    args = parser.parse_args(argv)
    setup_logging(console=True)

    gpa = Path(args.gpa)
    ets = Path(args.ets)
    ets_map = parse_ets_ga_export(ets, args.ets_password)
    datapoints = parse_gpa_datapoints(gpa, args.password)
    candidates = build_sync_candidates(datapoints, ets_map)

    print(f"GPA-Datenpunkte: {len(datapoints)}")
    print(f"ETS-Gruppenadressen: {len(ets_map)}")
    print(f"Unterschiede: {len(candidates)}")
    print()
    for i, c in enumerate(candidates, 1):
        mark = "X" if c.selected else " "
        print(f"{i:3d}. [{mark}] {c.group_address:10s} {c.current_name!r} -> {c.new_name!r} ({c.status})")

    if args.csv:
        export_candidates_csv(candidates, Path(args.csv))
        print(f"\nCSV gespeichert: {args.csv}")

    if args.apply_all:
        out = Path(args.out) if args.out else gpa.with_name(gpa.stem + "_GA_SYNC.gpa")
        selected = [c for c in candidates if c.selected and c.status == SyncStatus.AENDERUNG]
        changed = write_updated_gpa(gpa, out, selected, args.password)
        print(f"\nFertig: {changed} Datenpunkte geändert. Ausgabe: {out}")

    return 0
