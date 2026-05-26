"""Zentrale Schrift-Definitionen für ETS GPA GA-Sync.

Drei nutzbare Stufen plus eine Bold-Variante – bewusst minimalistisch.
CustomTkinter skaliert alle Punktgrößen automatisch mit der Windows-DPI.

WICHTIG: get_fonts() muss NACH super().__init__() aufgerufen werden,
da CTkFont ein laufendes Tk-Root voraussetzt.
"""
from __future__ import annotations
import customtkinter as ctk


def get_fonts() -> dict:
    """Gibt die vier Schrift-Stufen zurück.

    Gibt Skalierungsfreiheit an CustomTkinter ab – keine manuellen
    DPI-Korrekturen, keine Pixelwerte.
    """
    return {
        # Größte Stufe: Toolbar-Titel, KPI-Zahlen, prominente Symbole
        "large":     ctk.CTkFont(size=16, weight="bold"),
        # Mittlere Stufe: Sektion-Header, Sub-Header
        "normal":    ctk.CTkFont(size=13, weight="bold"),
        # Standard-Text: Labels, Drop-Zones, Eingabefelder, Body
        "body":      ctk.CTkFont(size=12),
        # Fett-Standard: Datei-Buttons, Tabellen-Header, wichtige Labels
        "body_bold": ctk.CTkFont(size=12, weight="bold"),
    }


# Für ttk.Style und tk.Label/Entry: native Tk-Font-Tupel (in Punkten → DPI-skaliert).
# ttk/tk-Widgets unterstützen kein CTkFont, aber Punkt-Größen skalieren korrekt
# sobald SetProcessDpiAwareness(2) gesetzt ist.
TTK_BODY      = ("Segoe UI", 12)
TTK_BODY_BOLD = ("Segoe UI", 12, "bold")
