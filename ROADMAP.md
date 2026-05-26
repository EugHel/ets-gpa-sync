# Roadmap

Übersicht über bereits umgesetzte und geplante Features.

## ✅ Bereits umgesetzt (v0.x — interne Versionen)

- ✅ **Stabilität**: Threading für reaktionsfähige GUI während Analyse
- ✅ **Code-Qualität**: 103 Unit-Tests mit pytest
- ✅ **Architektur**: Modulare Package-Struktur (gpa_ga_sync/)
- ✅ **Typsicherheit**: SyncStatus-Enum statt Magic Strings
- ✅ **GUI**: Migration zu CustomTkinter mit Dark/Light Mode
- ✅ **Logging**: Strukturiertes Logging mit Rotation
- ✅ **Lizenz-Subsystem**: Vorbereitet für mögliche zukünftige Features
  (aktuell deaktiviert via Feature-Flag — siehe `gpa_ga_sync/config.py`)

## 🚧 In Arbeit (auf dem Weg zu v1.0.0)

- 🚧 GUI-Politur (Lesbarkeit Light Mode, einheitliche Schriftgrößen)
- 🚧 Eigenes App-Icon
- 🚧 Packaging als signierte Windows .exe
- 🚧 Auto-Update-Mechanismus
- 🚧 Erweiterte Dokumentation (Benutzerhandbuch)
- 🚧 Demo-Video

## 🔮 Geplant (v1.x)

- Erweiterte Filter- und Suchoptionen in der Tabelle
- Batch-Verarbeitung mehrerer Projekte
- Verbesserte Konflikt-Auflösung bei Sync-Problemen
- Anpassbare CSV-Export-Formate

## 💭 Ideen (ungewiss)

- macOS- und Linux-Unterstützung
- Plugin-System für weitere KNX-Tools
- Erweiterte Reporting-Funktionen

## 📝 Feedback und Vorschläge

Hast du Ideen oder Wünsche? Eröffne gern ein 
[Feature-Request-Issue](https://github.com/EugHel/ets-gpa-sync/issues/new).
