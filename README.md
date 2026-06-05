# ETS GPA Sync

> Synchronisiere Gruppenadressen-Namen zwischen **KNX ETS** und **Gira GPA** — schnell, sicher, kostenlos.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Built with Python](https://img.shields.io/badge/built%20with-Python%203.14-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-103%20passing-brightgreen.svg)](#)
[![Status](https://img.shields.io/badge/status-beta-orange.svg)](#)

<div align="center">

### 💖 Unterstütze das Projekt

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/eughel)
&nbsp;&nbsp;
[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink?logo=github)](https://github.com/sponsors/EugHel)

*Dieses Tool ist kostenlos. Jede Unterstützung hilft, es aktiv weiterzuentwickeln!*

</div>

---

## 🚧 Status: Beta

Eine erste Beta-Version (**v0.9.0-beta**) ist als Windows-`.exe` verfügbar. Die erste stabile Version (**v1.0.0**) mit Code-Signing ist in Vorbereitung.

---

## ⭐ Was macht dieses Tool?

Wer KNX-Projekte mit der **ETS** plant und parallel die **Gira GPA** nutzt, kennt das Problem: Gruppenadressen-Namen müssen manuell synchron gehalten werden. Eine Änderung in der ETS bedeutet aufwendiges Nachpflegen in der GPA.

**ETS GPA Sync** automatisiert genau diesen Abgleich — du entscheidest pro Gruppenadresse, was übernommen wird. Das Original bleibt immer unverändert.

---

## ✨ Hauptfunktionen

- ✅ **Drag & Drop** für `.gpa` und ETS-Exporte (`.xml` / `.knxproj`)
- ✅ **Passwortgeschützte ETS-Projekte** werden unterstützt
- ✅ **Tabellarischer Vergleich** mit Filter- und Suchfunktion
- ✅ **Selektive Synchronisation** — pro Gruppenadresse einzeln entscheiden
- ✅ **Dark & Light Mode** mit anpassbaren Schriftgrößen
- ✅ **CSV-Export** für Dokumentation und Audit

---

## 📸 Screenshots

![Dark Mode](docs/screenshots/dark_mode.png)

---

## 📥 Download

**[⬇️ ETS GPA Sync v0.9.0-beta herunterladen](https://github.com/EugHel/ets-gpa-sync/releases/tag/v0.9.0-beta)**

ZIP entpacken → `ETS-GPA-Sync.exe` starten. Kein Python erforderlich.
Getestet auf Windows 10 und 11.

> ⚠️ Beta — bitte vor der Synchronisation Sicherheitskopien erstellen.

---

## 🚀 Quick Start

1. **Herunterladen** → ZIP entpacken → `.exe` starten
2. **GPA-Projekt** per Drag & Drop oder Button einfügen
3. **ETS-Export** (`.xml` / `.knxproj`) einfügen
4. **"Analysieren"** klicken
5. **Änderungen auswählen** → **"Synchronisieren"**

Fertig. Eine neue `.gpa`-Datei wird erzeugt — das Original bleibt unverändert.

---

## 🛠️ Für Entwickler

```bash
git clone https://github.com/EugHel/ets-gpa-sync.git
cd ets-gpa-sync
pip install -r requirements.txt
python main.py
```

```bash
pytest tests/
```

Python 3.13 oder neuer erforderlich (entwickelt mit 3.14).

---

## 📋 Weiteres

| | |
|---|---|
| 🗺️ Roadmap | [ROADMAP.md](ROADMAP.md) |
| 📜 Changelog | [CHANGELOG.md](CHANGELOG.md) |
| 🤝 Beiträge | Bitte zuerst ein [Issue](https://github.com/EugHel/ets-gpa-sync/issues/new) erstellen |
| 🔒 Sicherheit | Gemäß [SECURITY.md](SECURITY.md) melden |
| 📜 Lizenz | [MIT License](LICENSE) |

---

## ⚠️ Disclaimer

Dieses Tool wird ohne Gewährleistung bereitgestellt. Erstelle vor jeder Synchronisation eine Sicherheitskopie. Die Autoren übernehmen keine Haftung für Datenverlust.

---

*Made with ❤ for the KNX community by [@EugHel](https://github.com/EugHel)*
