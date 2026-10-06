# Changelog

Alle nennenswerten Änderungen werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

## [0.10.1-beta] - 2026-10-06

### Hinzugefügt
- **Update-Hinweis**: Beim Start fragt das Tool einmal bei GitHub nach, ob es eine neuere
  Version gibt, und zeigt dann oben rechts einen Hinweis mit Link zur Download-Seite.
  Es wird nur die öffentliche Release-Liste abgerufen, keine Projektdaten übertragen;
  ohne Internet bleibt es still. Abschaltbar mit `"update_check": false` in
  `%APPDATA%\GPA-GA-Sync\config.json`.

### Behoben
- Das Umschalten zwischen hellem und dunklem Design überschrieb andere gespeicherte
  Einstellungen.

## [0.10.0-beta] - 2026-10-06

### Hinzugefügt
- **GPA-Verweise**: Für jeden Datenpunkt zeigt das Tool, wo er im GPA-Projekt verwendet
  wird – eine Übersicht, die die GPA selbst nicht bietet.
  - **Visu-Ansichten** mit vollem Standort (Gebäude → Etage → Raum → Kachel), deutschem
    Kanaltyp und den Benutzern, für die die Ansicht sichtbar ist.
  - **Logik**: Verwendung als Baustein im Logikeditor, mit Logikseite, Rolle
    (Eingang/Ausgang) und Hinweis auf deaktivierte Logikseiten.
  - **Zeitschaltuhren**: Datenpunkte, die von einer Zeitschaltuhr geschaltet werden, samt
    Schaltzeiten (z. B. „08:00 täglich“) und Aktiv-Status.
- **GPA-Prüfansicht**: Wird nur ein GPA-Projekt geladen, zeigt die Tabelle alle Datenpunkte
  mit ihren Verwendungen; ETS-Spalten und „Synchronisieren“ werden ausgeblendet.
- **Spalten „Raum“, „Visu“, „Logik“ und „Uhr“** in der Tabelle (sortierbar). Logik und Uhr
  erscheinen nur, wenn das Projekt solche Verwendungen enthält.
- **Kennzahlen als Filter**: Ein Klick auf „Verwendet“, „In Logik“, „Ungenutzt“,
  „Mit Zeitschaltuhr“ oder „Konflikte“ filtert die Tabelle; „GPA-Datenpunkte“ hebt den
  Filter wieder auf. „Ungenutzt“ findet Aufräumkandidaten.
- **Verwendungen-Fenster** per Klick auf eine Zahl oder Doppelklick auf eine Zeile, mit
  Knopf „In Zwischenablage kopieren“.
- **Auswirkungsprüfung vor dem Synchronisieren**: zeigt, welche Visu-Ansichten, Logikseiten
  und Zeitschaltuhren von den Umbenennungen betroffen sind.
- **Suche** findet Datenpunkte auch über Raum-, Ansichts- und Logikseitennamen.
- Eigenschaften-Panel zeigt alle Gruppenadressen eines Datenpunkts nach Rolle
  (Senden / Status / Hören).
- **CSV-Export** und Excel-Kopie enthalten Raum und Verwendungen.
- Adress-Konflikte werden auch ohne ETS-Datei erkannt.
- Kurzanleitung in der leeren Tabelle vor der ersten Analyse.

### Geändert
- **Import-Bereich als kompakte Dateileiste**: ein Feld pro Datei (ablegen oder anklicken),
  geladene Dateien grün umrandet mit Dateiname und ✕ zum Entfernen; die ETS-Datei ist als
  optional gekennzeichnet.
- Speichern-Dialoge (Synchronisieren, CSV-Export) starten im Ordner des GPA-Projekts.
- CSV-Export speichert die aktuell angezeigten Zeilen (Filter und Suche werden berücksichtigt).
- Schriftgrößen überarbeitet und vereinheitlicht, auch für Hilfetexte (Tooltips).
- Logo im hellen Design ohne dunklen Hintergrund.

### Behoben
- Wird nach der Analyse eine andere GPA-Datei geladen, verweigert „Synchronisieren“ das
  Speichern, bis erneut analysiert wurde (vorher wären die alten Ergebnisse auf die neue
  Datei angewendet worden).

## [0.9.1-beta] - 2026-06-09

### Behoben
- Mehrere GPA-Datenpunkte mit derselben Sende-Adresse werden als „Adress-Konflikt“
  gekennzeichnet statt still umbenannt.

### Hinzugefügt
- Kennzahl „Konflikte“.

## [0.9.0-beta] - 2026-06-04

### Hinzugefügt
- Erste öffentliche Beta als Windows-`.exe`.
- Threading-basierte Analyse für reaktionsfähige GUI
- Modulare Package-Struktur (gpa_ga_sync/)
- Unit-Tests für die Kernfunktionen
- CustomTkinter-basierte GUI mit Dark/Light Mode
- Strukturiertes Logging-System
- Lizenz-Subsystem (vorbereitet für optionale zukünftige Features)
- MIT License

### Geändert
- Migration von Tkinter zu CustomTkinter
- Single-File auf modulare Package-Struktur umgestellt
- Magic Strings durch SyncStatus-Enum ersetzt

## [0.20.1] - Vorgängerversion (intern)
- Erste funktionsfähige Version (Single-File-Implementierung)
