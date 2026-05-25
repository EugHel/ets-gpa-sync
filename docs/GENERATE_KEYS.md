# RSA-Schlüsselpaar generieren – Anleitung

Diese Anleitung beschreibt, wie du das RSA-2048-Schlüsselpaar für den
Offline-Lizenz-Provider erstellst, sicher aufbewahrst und in das Tool einbettest.

---

## 1. Voraussetzungen

OpenSSL muss installiert sein:

```bash
# Windows (winget)
winget install ShiningLight.OpenSSL

# Oder: mitgeliefertes OpenSSL aus Git for Windows nutzen
# C:\Program Files\Git\usr\bin\openssl.exe
```

---

## 2. Schlüsselpaar generieren

```bash
# Private Key (2048 Bit) – NIEMALS weitergeben!
openssl genrsa -out private_key.pem 2048

# Public Key aus Private Key ableiten
openssl rsa -in private_key.pem -pubout -out public_key.pem
```

Beide Dateien liegen jetzt im aktuellen Verzeichnis.

---

## 3. Public Key ins Tool einbetten

In `gpa_ga_sync/licensing/providers/offline.py` den Platzhalter ersetzen:

```python
# Zeile: _PRODUCTION_PUBLIC_KEY_PEM: Optional[bytes] = None
# Ersetzen durch:

_PRODUCTION_PUBLIC_KEY_PEM: Optional[bytes] = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...  ← dein echter Key
...
-----END PUBLIC KEY-----
"""
```

Den Inhalt von `public_key.pem` vollständig (inkl. Header/Footer) einfügen.

---

## 4. Lizenz-Blob für Kunden generieren

Nach dem Kauf erstellst du einen signierten Lizenz-Blob mit dem Private Key:

```python
# Einmaliges Skript: generate_license.py (NICHT ins Repo!)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pathlib import Path
from gpa_ga_sync.licensing.providers.offline import build_license_blob

# Private Key laden
pem = Path("private_key.pem").read_bytes()
from cryptography.hazmat.backends import default_backend
private_key = serialization.load_pem_private_key(pem, password=None)

machine_id = input("Machine-ID des Kunden: ").strip()
blob = build_license_blob(private_key, machine_id=machine_id)
print(blob)
# → Blob per E-Mail an Kunden senden
```

Der Kunde fügt diesen Blob in den Lizenz-Dialog (Hilfe → Lizenz verwalten) ein.

---

## 5. Sichere Aufbewahrung

| Datei | Speicherort | Backup |
|---|---|---|
| `private_key.pem` | Nur lokal, NICHT im Repo | Verschlüsselt (z.B. KeePass-Attachment) |
| `public_key.pem`  | Ins Repo OK, aber unnötig | Im Quellcode eingebettet |

**Private Key verloren?**
- Alle bereits ausgestellten Offline-Lizenzen bleiben gültig (sie prüfen nur
  die Signatur, nicht gegen einen Server).
- Du musst ein neues Schlüsselpaar generieren, den neuen Public Key einbetten
  und ein neues App-Release veröffentlichen.
- Bestehende Kunden: neue Lizenzen mit dem neuen Private Key ausstellen.

---

## 6. .gitignore-Regeln

Folgende Zeilen sicherstellen, dass der Private Key NIE ins Repo gelangt:

```gitignore
# Schlüsseldateien – NIEMALS committen
private_key.pem
*.pem
generate_license.py
```

Prüfen ob der Key bereits getrackt wird:

```bash
git ls-files "*.pem"
# Ausgabe muss leer sein!
```

Falls versehentlich eingecheckt:

```bash
git rm --cached private_key.pem
git commit -m "Sicherheit: Private Key aus Repo entfernt"
# Danach: Key als kompromittiert behandeln und neues Paar generieren!
```

---

## 7. Zusammenfassung

```
private_key.pem  →  sicher lokal aufbewahren
                     → zum Signieren von Lizenzen für Kunden verwenden

public_key.pem   →  in offline.py einbetten (_PRODUCTION_PUBLIC_KEY_PEM)
                     → wird mit dem Tool ausgeliefert
```
