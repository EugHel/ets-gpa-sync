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
APP_VERSION = "v0.10.1-beta"

# Lizenz-Subsystem (Trial, Provider-basierte Aktivierung)
# Aktuell DEAKTIVIERT — das Tool ist Open Source unter MIT-Lizenz.
# Kann später reaktiviert werden für optionale "Pro Support"-Modelle.
# Zur Aktivierung: diesen Wert auf True setzen.
LICENSING_ENABLED = False

# Update-Hinweis: beim Start einmal bei GitHub nach einer neueren Version fragen
# (nur die öffentliche Release-Liste, keine Projektdaten). Nutzer können ihn
# zusätzlich mit "update_check": false in %APPDATA%\GPA-GA-Sync\config.json abschalten.
UPDATE_CHECK_ENABLED = True

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
# Hinweis: CTk-Schriften sind Pixel, die Tabelle (ttk) nutzt Punkt –
# 10 pt in der Tabelle entsprechen etwa 13 px bei den übrigen Elementen.
FONT_SIZE_TITLE    = 22   # Toolbar-Titel "ETS GPA Sync"
FONT_SIZE_HEADER   = 15   # Sektion-Header ("Datenquellen importieren")
FONT_SIZE_SUBHEADER = 13  # Karten-Titel ("GPA-Projekt"), "Eigenschaften"
FONT_SIZE_BODY     = 13   # Standard-Text, Buttons, Drop-Zones
FONT_SIZE_SMALL    = 10   # Statusleiste, Pfad-Anzeige, Captions
FONT_SIZE_KPI      = 19   # Große KPI-Zahlen

# --- Einzeln einstellbare Spezial-Elemente ---
FONT_SIZE_TABLE_HEADER   = 10   # Tabellen-Spaltenköpfe (Sync, Status, GA, ...)
FONT_SIZE_TABLE_BODY     = 10   # Tabellen-Datenzeilen
FONT_SIZE_INFOBOX        = 10   # Info-Box rechts ("Der neue Name kann ...")
FONT_SIZE_PROPERTY_LABEL = 13   # Eigenschaften-Feld-Labels (Status, GA, ...)

# ═══════════════════════════════════════════════════════════
# CHANNEL-TYPE-ANZEIGENAMEN (Verweise-Popup)
# ═══════════════════════════════════════════════════════════
# Übersetzung eines Kanals in seinen deutschen GPA-Anzeigenamen. Die
# GPA-Projektdatei selbst enthält KEINE solche Zuordnung (nur englische
# FullName-Felder) – die deutschen Namen stammen aus der offiziellen Gira
# GPA-Projektschnittstelle-Dokumentation ("Funktionsbeschreibungen Gira X1
# v2.5") und sind für diese Firmware-Version vollständig.
#
# Schlüssel ist das PAAR (Function.Type, ChannelType), NICHT der ChannelType
# allein: mehrere Funktionen teilen sich denselben ChannelType (z. B. Integer,
# DWord, Float, Trigger sind mehrdeutig). Function.Type = <conf:Urn>,
# ChannelType = <conf:ChannelTypeId> der Channelview.
CHANNEL_TYPE_NAMES = {
    ("de.gira.schema.functions.SignedValue", "de.gira.schema.channels.Integer"): "32-Bit Wertgeber mit Vorzeichen",
    ("de.gira.schema.functions.UnsignedValue", "de.gira.schema.channels.DWord"): "32-Bit Wertgeber ohne Vorzeichen",
    ("de.gira.schema.functions.Unsigned8BitValue", "de.gira.schema.channels.Byte"): "8-Bit Wertgeber 0...255",
    ("de.gira.schema.functions.Signed8BitValue", "de.gira.schema.channels.Integer"): "8-Bit Wertgeber -128...127",
    ("de.gira.schema.functions.Audio", "de.gira.schema.channels.AudioWithPlaylist"): "Audiosteuerung",
    ("de.gira.schema.functions.Sonos.Audio", "de.gira.schema.channels.Sonos.Audio"): "Audiosteuerung (Sonos)",
    ("de.gira.schema.functions.Audio", "de.gira.schema.channels.AudioWithCover"): "Audiosteuerung mit Titelbild",
    ("de.gira.schema.functions.DecimalValue", "de.gira.schema.channels.Float"): "Dezimalwertgeber",
    ("de.gira.schema.functions.KNX.Light", "de.gira.schema.channels.KNX.Dimmer"): "Dimmer",
    ("de.gira.schema.functions.ColoredLight", "de.gira.schema.channels.DimmerRGBW"): "Dimmer (RGB / RGBW)",
    ("de.gira.schema.functions.TunableLight", "de.gira.schema.channels.DimmerWhite"): "Dimmer (Tunable White)",
    ("de.gira.schema.functions.KNX.HeatingCooling", "de.gira.schema.channels.KNX.HeatingCoolingSwitchable"): "Heizen und Kühlen",
    ("de.gira.schema.functions.Camera", "de.gira.schema.channels.Camera"): "IP Kamera",
    ("de.gira.schema.functions.KNX.FanCoil", "de.gira.schema.channels.KNX.FanCoil"): "Klimaanlage",
    ("de.gira.schema.functions.PercentValue", "de.gira.schema.channels.Percent"): "Prozentwertgeber",
    ("de.gira.schema.functions.Covering", "de.gira.schema.channels.BlindWithPos"): "Rollladen / Jalousie",
    ("de.gira.schema.functions.SaunaHeating", "de.gira.schema.channels.RoomTemperatureSwitchable"): "Saunatemperatur",
    ("de.gira.schema.functions.Switch", "de.gira.schema.channels.Switch"): "Schalter",
    ("de.gira.schema.functions.BinaryStatus", "de.gira.schema.channels.Binary"): "Statusanzeige Binär",
    ("de.gira.schema.functions.NumericFloatStatus", "de.gira.schema.channels.Float"): "Statusanzeige Dezimal",
    ("de.gira.schema.functions.NumericSignedStatus", "de.gira.schema.channels.Integer"): "Statusanzeige mit Vorzeichen",
    ("de.gira.schema.functions.NumericUnsignedStatus", "de.gira.schema.channels.DWord"): "Statusanzeige ohne Vorzeichen",
    ("de.gira.schema.functions.TextStatus", "de.gira.schema.channels.String"): "Statusanzeige Text",
    ("de.gira.schema.functions.Scene", "de.gira.schema.channels.SceneControl"): "Szenennebenstelle",
    ("de.gira.schema.functions.Scene", "de.gira.schema.channels.SceneSet"): "Szenenset",
    ("de.gira.schema.functions.PressAndHold", "de.gira.schema.channels.Trigger"): "Taster (Drücken/Loslassen)",
    ("de.gira.schema.functions.Trigger", "de.gira.schema.channels.Trigger"): "Taster (Ein/Aus)",
    ("de.gira.schema.functions.TemperatureValue", "de.gira.schema.channels.Temperature"): "Temperaturwertgeber",
    ("de.gira.schema.functions.Link", "de.gira.schema.channels.Link"): "URL-Aufruf",
}

# Fallback A: ChannelType → Name, aber NUR für ChannelTypes, die in der Tabelle
# eindeutig sind (genau ein Eintrag). Mehrdeutige (Integer/DWord/Float/Trigger)
# fehlen hier bewusst und lösen ohne Function.Type keinen Namen aus.
_CHANNEL_TYPE_COUNTS: dict = {}
for _func, _chan in CHANNEL_TYPE_NAMES:
    _CHANNEL_TYPE_COUNTS[_chan] = _CHANNEL_TYPE_COUNTS.get(_chan, 0) + 1
_UNIQUE_CHANNEL_TYPE_NAMES = {
    _chan: _name
    for (_func, _chan), _name in CHANNEL_TYPE_NAMES.items()
    if _CHANNEL_TYPE_COUNTS[_chan] == 1
}


def channel_type_display_name(function_type: str, channel_type: str):
    """Deutscher Anzeigename für einen Kanal, oder None wenn kein sicherer Treffer.

    - Primär: exakter Lookup über das Paar (Function.Type, ChannelType).
    - Fallback A: fehlt der Function.Type, aber der ChannelType ist eindeutig
      (nur ein Tabelleneintrag) → dessen Name.
    - Fallback B: mehrdeutig ohne Function.Type oder komplett unbekannt → None
      (der Aufrufer zeigt dann nur die technische ChannelTypeId).
    """
    name = CHANNEL_TYPE_NAMES.get((function_type, channel_type))
    if name:
        return name
    return _UNIQUE_CHANNEL_TYPE_NAMES.get(channel_type)
