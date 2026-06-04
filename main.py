#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETS GPA Sync Tool – Haupteinstiegspunkt
"""
import sys

# Windows: Per-Monitor-DPI-Aware aktivieren (vor jedem Tk-Init).
# Ohne diesen Aufruf skaliert Windows das Fenster als Bitmap → unscharf bei 150%/200%.
# Mit PROCESS_PER_MONITOR_DPI_AWARE=2 rendert die App nativ auf jedem Monitor.
if sys.platform == "win32":
    try:
        import ctypes
        # PROCESS_PER_MONITOR_DPI_AWARE = 2  (beste Option, Win 8.1+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        # Fallback für Windows 7/8 ohne shcore.dll
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass

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
