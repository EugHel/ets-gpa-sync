"""Zentrale Schrift-Definitionen für ETS GPA Sync.

Liest Basis-Größen und Skalierungsfaktor aus config.py.
CustomTkinter skaliert zusätzlich automatisch mit Windows-DPI.

WICHTIG: get_fonts() muss NACH super().__init__() aufgerufen werden,
da CTkFont ein laufendes Tk-Root voraussetzt.
"""
from __future__ import annotations
import customtkinter as ctk
from gpa_ga_sync import config


def _scaled(base_size: int) -> int:
    """Multipliziert eine Basisgröße mit dem globalen UI_SCALE_FACTOR.

    Mindestgröße 8pt, damit nichts unlesbar klein wird.
    """
    return max(8, round(base_size * config.UI_SCALE_FACTOR))


def get_fonts() -> dict:
    """Gibt die Schrift-Stufen zurück. Einmal beim Start aufrufen."""
    return {
        # Toolbar-Titel "ETS GPA Sync"
        "large":     ctk.CTkFont(size=_scaled(config.FONT_SIZE_TITLE),  weight="bold"),
        # Sektion-Header ("Datenquellen importieren" u.ä.)
        "normal":    ctk.CTkFont(size=_scaled(config.FONT_SIZE_HEADER), weight="bold"),
        # Standard-Text: Labels, Drop-Zones, Eingabefelder, Body
        "body":      ctk.CTkFont(size=_scaled(config.FONT_SIZE_BODY)),
        # Fett-Standard: Datei-Buttons, Tabellen-Header, wichtige Labels
        "body_bold": ctk.CTkFont(size=_scaled(config.FONT_SIZE_BODY),   weight="bold"),
        # Statusleiste, Captions, kleine Hinweise
        "small":     ctk.CTkFont(size=_scaled(config.FONT_SIZE_SMALL)),
        # Große KPI-Zahlen im Dashboard
        "kpi":       ctk.CTkFont(size=_scaled(config.FONT_SIZE_KPI),    weight="bold"),
    }


# Für ttk.Style und tk.Label/Entry: native Tk-Font-Tupel (in Punkten → DPI-skaliert).
# ttk/tk-Widgets unterstützen kein CTkFont, aber Punkt-Größen skalieren korrekt
# sobald SetProcessDpiAwareness(2) gesetzt ist.
TTK_BODY      = ("Segoe UI", _scaled(config.FONT_SIZE_BODY))
TTK_BODY_BOLD = ("Segoe UI", _scaled(config.FONT_SIZE_BODY), "bold")
TTK_SMALL     = ("Segoe UI", _scaled(config.FONT_SIZE_SMALL))
