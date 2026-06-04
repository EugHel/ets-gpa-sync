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
        "large":          ctk.CTkFont(size=_scaled(config.FONT_SIZE_TITLE),          weight="bold"),
        # Sektion-Header ("Datenquellen importieren", "Datenpunkte – Änderungen")
        "normal":         ctk.CTkFont(size=_scaled(config.FONT_SIZE_HEADER),         weight="bold"),
        # Karten-Titel ("GPA-Projekt"), "Eigenschaften", "Ausgewählter Datenpunkt"
        "subheader":      ctk.CTkFont(size=_scaled(config.FONT_SIZE_SUBHEADER),      weight="bold"),
        # Standard-Text: Drop-Zones, Eingabefelder, allgemeine Labels
        "body":           ctk.CTkFont(size=_scaled(config.FONT_SIZE_BODY)),
        # Fett-Standard: Datei-Buttons, wichtige Labels
        "body_bold":      ctk.CTkFont(size=_scaled(config.FONT_SIZE_BODY),           weight="bold"),
        # Statusleiste, Pfad-Anzeige, Captions
        "small":          ctk.CTkFont(size=_scaled(config.FONT_SIZE_SMALL)),
        # Große KPI-Zahlen im Dashboard
        "kpi":            ctk.CTkFont(size=_scaled(config.FONT_SIZE_KPI),            weight="bold"),
        # Tabellen-Spaltenköpfe
        "table_header":   ctk.CTkFont(size=_scaled(config.FONT_SIZE_TABLE_HEADER),   weight="bold"),
        # Tabellen-Datenzeilen
        "table_body":     ctk.CTkFont(size=_scaled(config.FONT_SIZE_TABLE_BODY)),
        # Info-Box rechts
        "infobox":        ctk.CTkFont(size=_scaled(config.FONT_SIZE_INFOBOX)),
        # Eigenschaften-Feld-Labels
        "property_label": ctk.CTkFont(size=_scaled(config.FONT_SIZE_PROPERTY_LABEL)),
    }


# Für ttk.Style und tk.Label/Entry: native Tk-Font-Tupel (in Punkten → DPI-skaliert).
# ttk/tk-Widgets unterstützen kein CTkFont, aber Punkt-Größen skalieren korrekt
# sobald SetProcessDpiAwareness(2) gesetzt ist.
TTK_BODY         = ("Segoe UI", _scaled(config.FONT_SIZE_BODY))
TTK_BODY_BOLD    = ("Segoe UI", _scaled(config.FONT_SIZE_BODY),         "bold")
TTK_SMALL        = ("Segoe UI", _scaled(config.FONT_SIZE_SMALL))
TTK_TABLE_HEADER = ("Segoe UI", _scaled(config.FONT_SIZE_TABLE_HEADER), "bold")
TTK_TABLE_BODY   = ("Segoe UI", _scaled(config.FONT_SIZE_TABLE_BODY))
TTK_INFOBOX      = ("Segoe UI", _scaled(config.FONT_SIZE_INFOBOX))
