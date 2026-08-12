"""
Zentrale Feature-Flags und Konfiguration.

Diese Flags steuern optionale Subsysteme, die deaktiviert werden
können, ohne den Code zu entfernen.
"""

# ═══════════════════════════════════════════════════════════
# VERSION
# ═══════════════════════════════════════════════════════════
# Einzige Quelle der Wahrheit für die angezeigte Versionsnummer
# (Fußleiste, CLI, ...). Inklusive "v"-Präfix.
APP_VERSION = "v0.9.1-beta"

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

# --- Allgemeine Schrift-Stufen ---
FONT_SIZE_TITLE    = 26   # Toolbar-Titel "ETS GPA Sync"
FONT_SIZE_HEADER   = 16   # Sektion-Header ("Datenquellen importieren")
FONT_SIZE_SUBHEADER = 14  # Karten-Titel ("GPA-Projekt"), "Eigenschaften"
FONT_SIZE_BODY     = 14   # Standard-Text, Buttons, Drop-Zones
FONT_SIZE_SMALL    = 10   # Statusleiste, Pfad-Anzeige, Captions
FONT_SIZE_KPI      = 20   # Große KPI-Zahlen

# --- Einzeln einstellbare Spezial-Elemente ---
FONT_SIZE_TABLE_HEADER   = 11   # Tabellen-Spaltenköpfe (Sync, Status, GA, ...)
FONT_SIZE_TABLE_BODY     = 11   # Tabellen-Datenzeilen
FONT_SIZE_INFOBOX        = 10   # Info-Box rechts ("Der neue Name kann ...")
FONT_SIZE_PROPERTY_LABEL = 14   # Eigenschaften-Feld-Labels (Status, GA, ...)

# ═══════════════════════════════════════════════════════════
# CHANNEL-TYPE-ANZEIGENAMEN (Verweise-Popup)
# ═══════════════════════════════════════════════════════════
# Übersetzung der technischen ChannelTypeId-URNs in die deutschen
# Anzeigenamen der GPA-UI. Die GPA-Projektdatei selbst enthält KEINE
# solche Zuordnung (nur englische FullName-Felder) – die deutschen Namen
# stammen aus dem GPA-Client-Produktkatalog. Daher hier fest gepflegt.
#
# Deckt aktuell die 14 ChannelTypeIds ab, die in den echten Projektdateien
# (Petermann/Niewels/Scheffer) tatsächlich vorkommen. Weiterhin potenziell
# UNVOLLSTÄNDIG: bei Bedarf erweitern, wenn in weiteren Projekten neue
# ChannelTypeIds auftauchen (Fallback ist die technische ID – kein Absturz).
CHANNEL_TYPE_NAMES = {
    "de.gira.schema.channels.Switch": "Schalten",
    "de.gira.schema.channels.KNX.Dimmer": "Dimmen",
    "de.gira.schema.channels.BlindWithPos": "Rollladen / Jalousie",
    "de.gira.schema.channels.KNX.HeatingCoolingSwitchable": "Heizen/Kühlen",
    "de.gira.schema.channels.Binary": "Binärstatus",
    "de.gira.schema.channels.Float": "Dezimalwert",
    "de.gira.schema.channels.Byte": "Wertgeber 8 Bit",
    "de.gira.schema.channels.DWord": "Wertgeber",
    "de.gira.schema.channels.Percent": "Prozentwert",
    "de.gira.schema.channels.String": "Textstatus",
    "de.gira.schema.channels.Temperature": "Temperaturwert",
    "de.gira.schema.channels.Trigger": "Tastenfunktion",
    "de.gira.schema.channels.FunctionScene": "Szene",
    "de.gira.schema.channels.Link": "IP-Link",
}
