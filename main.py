#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETS GPA GA-Sync Tool – Haupteinstiegspunkt
"""
import sys

if __name__ == "__main__":
    from gpa_ga_sync.log import setup_logging
    from gpa_ga_sync.gui.app import run_gui
    from gpa_ga_sync.cli import run_cli

    cli_mode = len(sys.argv) > 1
    setup_logging(console=cli_mode)

    if cli_mode:
        sys.exit(run_cli() or 0)
    else:
        run_gui()
