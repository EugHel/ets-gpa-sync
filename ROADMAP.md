# Roadmap

Übersicht über bereits umgesetzte und geplante Features.

## ✅ Bereits umgesetzt (v0.x — interne Versionen)

* ✅ **Stabilität**: Threading für reaktionsfähige GUI während Analyse
* ✅ **Code-Qualität**: 103 Unit-Tests mit pytest
* ✅ **Architektur**: Modulare Package-Struktur (`gpa_ga_sync/`)
* ✅ **Typsicherheit**: `SyncStatus`-Enum statt Magic Strings
* ✅ **GUI**: Migration zu CustomTkinter mit Dark/Light Mode
* ✅ **GUI-Politur**: Einheitliche Schriftgrößen, konfigurierbar via `config.py`
* ✅ **DPI-Unterstützung**: Skalierbare Schriftgrößen für hohe Windows-DPI
* ✅ **Logging**: Strukturiertes Logging mit Rotation
* ✅ **App-Icon**: Eigenes Datenfluss-Icon (Toolbar + Windows-Symbol)
* ✅ **Lizenz-Subsystem**: Vorbereitet, aktuell deaktiviert via Feature-Flag

## 🚧 In Arbeit (auf dem Weg zu v1.0.0)

* 🚧 **Packaging**: Signierte Windows-.exe (PyInstaller + Code-Signing)
* 🚧 **Erweiterte Dokumentation**: Benutzerhandbuch
* 🚧 **Demo-Video**: Kurz-Tutorial der Hauptfunktionen

## 🔮 Geplant (v1.x)

* Auto-Update-Mechanismus
* Erweiterte Filter- und Suchoptionen in der Tabelle
* Batch-Verarbeitung mehrerer Projekte
* Verbesserte Konflikt-Auflösung bei Sync-Problemen
* Anpassbare CSV-Export-Formate

## 💭 Ideen (ungewiss)

* macOS- und Linux-Unterstützung
* Plugin-System für weitere KNX-Tools
* Erweiterte Reporting-Funktionen

## 📝 Feedback und Vorschläge

Hast du Ideen oder Wünsche? Eröffne gern ein 
[Feature-Request-Issue](https://github.com/EugHel/ets-gpa-sync/issues/new).