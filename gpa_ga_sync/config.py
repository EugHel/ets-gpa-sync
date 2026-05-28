"""
Zentrale Feature-Flags und Konfiguration.

Diese Flags steuern optionale Subsysteme, die deaktiviert werden
können, ohne den Code zu entfernen.
"""

# Lizenz-Subsystem (Trial, Provider-basierte Aktivierung)
# Aktuell DEAKTIVIERT — das Tool ist Open Source unter MIT-Lizenz.
# Kann später reaktiviert werden für optionale "Pro Support"-Modelle.
# Zur Aktivierung: diesen Wert auf True setzen.
LICENSING_ENABLED = False

# ═══════════════════════════════════════════════════════════
# GUI-SCHRIFTGRÖSSEN
# ═══════════════════════════════════════════════════════════
#
# UI_SCALE_FACTOR multipliziert ALLE Schriftgrößen global.
#
# Anpassung je nach Windows-Skalierung / Monitor:
#   - Standard (100-125% Windows-Skalierung):  1.0
#   - Hohe Skalierung (150%):                   0.9
#   - Sehr hohe Skalierung (175-200%):          0.8
#   - Niedrige Auflösung / Wunsch größer:       1.1 - 1.3
#
# Nach Änderung: Tool neu starten.
UI_SCALE_FACTOR = 1.0

# Basis-Schriftgrößen (in pt, vor Multiplikation mit UI_SCALE_FACTOR)
FONT_SIZE_TITLE  = 16   # Toolbar-Titel "ETS GPA GA-Sync"
FONT_SIZE_HEADER = 13   # Sektion-Header ("Datenquellen importieren")
FONT_SIZE_BODY   = 12   # Standard-Text, Labels, Drop-Zones, Tabelle
FONT_SIZE_SMALL  = 10   # Statusleiste, Captions
FONT_SIZE_KPI    = 20   # Große KPI-Zahlen
