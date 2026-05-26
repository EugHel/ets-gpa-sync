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
