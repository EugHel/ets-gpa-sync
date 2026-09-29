# Changelog

Alle nennenswerten Änderungen werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

## [0.10.0-beta] - 2026-09-29

### Hinzugefügt
- **GPA-Verweise**: Für jeden Datenpunkt zeigt das Tool, wo er im GPA-Projekt verwendet
  wird – die GPA selbst bietet diese Übersicht nicht.
  - Spalten **Visu**, **Logik** und **Uhr** in der Tabelle (klickbar, sortierbar).
  - **Visu-Ansichten** mit vollem Standort (Gebäude → Etage → Raum → Kachel), deutschem
    Kanaltyp und den Benutzern, für die die Ansicht sichtbar ist.
  - **Logik**: Verwendung als Baustein im Logikeditor, mit Logikseite, Rolle
    (Eingang/Ausgang) und Hinweis auf deaktivierte Logikseiten.
  - **Zeitschaltuhren**: Datenpunkte, die von einer Zeitschaltuhr geschaltet werden, samt
    Schaltzeiten (z. B. „08:00 täglich“) und Aktiv-Status.
- **Verweise-Filter**: Alle / Verwendet / Ungenutzt / In Logik / Mit Zeitschaltuhr, jeweils
  mit Trefferzahl. „Ungenutzt“ findet Aufräumkandidaten.
- **Suche** findet Datenpunkte auch über Raum-, Ansichts- und Logikseitennamen.
- **Auswirkung vor dem Synchronisieren**: Übersicht, welche Visu-Ansichten, Logikseiten und
  Zeitschaltuhren von den Umbenennungen betroffen sind.
- **Verwendungen-Popup** mit Knopf „In Zwischenablage kopieren“.
- **CSV-Export** und Excel-Kopie enthalten die Verweise (Anzahl + Klartext).
- Adress-Konflikte werden auch ohne ETS-Datei erkannt.
- **GPA-Prüfansicht**: Wird nur ein GPA-Projekt analysiert, blendet das Tool die
  ETS-Spalten, Auswahl-Knöpfe und „Synchronisieren“ aus. Die Kennzahlen zeigen
  Verwendet / In Logik (bzw. Mit Zeitschaltuhr) / Ungenutzt und filtern per Klick.
- **Spalte „Raum“** mit dem Standort der Visu-Ansicht (sortierbar, auch in CSV/Excel).
- Eigenschaften-Panel zeigt alle Adressen nach Rolle (Senden / Status / Hören) und die
  Quelle verständlich („Senden (Write)“).

### Geändert
- Verweise werden einmal pro Analyse im Hintergrund vollständig aufgelöst; danach hält das
  Tool keine GPA-Datei mehr offen.
- Eigenschaften-Panel: Verweise gegliedert und scrollbar statt fester Obergrenze;
  Benutzer nur, wenn sie vom Projekt-Normalfall abweichen; bündige Einrückung.
- Logik- und Uhr-Spalte sowie die zugehörigen Filter erscheinen nur, wenn das Projekt
  solche Verweise enthält. Kürzere Statuszeile.

### Behoben
- Datenpunkte, die nur in der Logik verwendet werden, wurden als „0 Verweise“ angezeigt.

### Hinzugefügt
- Threading-basierte Analyse für reaktionsfähige GUI
- Modulare Package-Struktur (gpa_ga_sync/)
- 103 Unit-Tests für Core-Funktionalität
- CustomTkinter-basierte GUI mit Dark/Light Mode
- Strukturiertes Logging-System
- Lizenz-Subsystem (vorbereitet für optionale zukünftige Features)
- MIT License
- Vorbereitung für öffentliches Open-Source-Release

### Geändert
- Migration von Tkinter zu CustomTkinter
- Single-File auf modulare Package-Struktur umgestellt
- Magic Strings durch SyncStatus-Enum ersetzt

## [0.20.1] - Vorgängerversion (intern)
- Erste funktionsfähige Version (Single-File-Implementierung)
