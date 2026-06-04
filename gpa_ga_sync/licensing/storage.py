from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass, fields as dc_fields
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..log import get_logger

_log = get_logger("licensing.storage")

# ── Pfade ─────────────────────────────────────────────────────────────────────
_APPDATA_DIR     = Path(os.getenv("APPDATA", str(Path.home()))) / "GPA-GA-Sync"
_PROGRAMDATA_DIR = Path(os.getenv("PROGRAMDATA", "C:/ProgramData")) / "GPA-GA-Sync"
_DAT_FILE        = _APPDATA_DIR / "license.dat"
_MARKER_FILE     = _PROGRAMDATA_DIR / ".trial_marker"

# ── HKLM-Registry ─────────────────────────────────────────────────────────────
_HKLM_KEY   = r"SOFTWARE\GPA-GA-Sync"
_HKLM_VALUE = "ts"

# ── KDF-Parameter ─────────────────────────────────────────────────────────────
_KDF_SALT = b"GPA-GA-Sync-v1-2024"
_KDF_ITER = 200_000
_FORMAT_VERSION = 1


# ── Gespeicherte Daten ────────────────────────────────────────────────────────

@dataclass
class StoredData:
    version: int = _FORMAT_VERSION
    trial_start: Optional[float] = None    # Unix-Timestamp Trial-Beginn
    trial_hmac: str = ""                   # HMAC(trial_start, machine_id)
    hklm_written: bool = False             # Wurde HKLM erfolgreich beschrieben?
    programdata_written: bool = False      # Wurde ProgramData-Marker geschrieben?
    license_key_hash: Optional[str] = None # SHA-256 des Schlüssels (nie Klartext!)
    license_data: Optional[dict] = None    # Provider-spezifische Lizenz-Daten
    machine_id: str = ""


def _from_dict(d: dict) -> StoredData:
    known = {f.name for f in dc_fields(StoredData)}
    return StoredData(**{k: v for k, v in d.items() if k in known})


# ── HMAC-Hilfsfunktion ────────────────────────────────────────────────────────

def make_trial_hmac(trial_start: float, machine_id: str) -> str:
    """Erzeugt einen HMAC über trial_start + machine_id zur Tamper-Detection."""
    msg = f"{trial_start:.6f}|{machine_id}".encode("utf-8")
    return hmac.new(machine_id.encode("utf-8"), msg, hashlib.sha256).hexdigest()


# ── Fernet-Schlüssel aus Machine-ID ──────────────────────────────────────────

def _derive_fernet_key(machine_id: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_KDF_SALT,
        iterations=_KDF_ITER,
    )
    return base64.urlsafe_b64encode(kdf.derive(machine_id.encode("utf-8")))


# ── Registry-Zugriff (HKLM, best-effort) ─────────────────────────────────────

def _try_write_hklm(value: str) -> bool:
    try:
        import winreg
        key = winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE, _HKLM_KEY,
            access=winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY,
        )
        winreg.SetValueEx(key, _HKLM_VALUE, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _try_read_hklm() -> Optional[str]:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, _HKLM_KEY,
            access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        val, _ = winreg.QueryValueEx(key, _HKLM_VALUE)
        winreg.CloseKey(key)
        return str(val)
    except Exception:
        return None


def _try_delete_hklm() -> None:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, _HKLM_KEY,
            access=winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY,
        )
        winreg.DeleteValue(key, _HKLM_VALUE)
        winreg.CloseKey(key)
    except Exception:
        pass


# ── Storage-Klasse ─────────────────────────────────────────────────────────────

class LicenseStorage:
    """Verschlüsselte Persistenz für Trial- und Lizenzdaten an drei Speicherorten.

    Ort 1: %APPDATA%/GPA-GA-Sync/license.dat  (user-weit, Fernet-verschlüsselt)
    Ort 2: HKLM\\SOFTWARE\\GPA-GA-Sync (maschinen-weit, nur wenn Admin-Rechte vorhanden)
    Ort 3: %PROGRAMDATA%/GPA-GA-Sync/.trial_marker (maschinen-weit, immer versucht)

    Werden Ort 2 oder 3 nach erfolgreichem Schreiben nachträglich manipuliert oder
    gelöscht, gilt der Trial als abgelaufen.
    """

    def __init__(
        self,
        machine_id: str = "",
        dat_path: Optional[Path] = None,
        marker_path: Optional[Path] = None,
    ) -> None:
        self._machine_id = machine_id
        self._dat = dat_path or _DAT_FILE
        self._marker = marker_path or _MARKER_FILE
        self._fernet: Optional[Fernet] = None
        if machine_id:
            self._fernet = Fernet(_derive_fernet_key(machine_id))

    # ── Verschlüsselung ───────────────────────────────────────────────────────

    def _encrypt(self, data: dict) -> bytes:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        if self._fernet:
            return self._fernet.encrypt(raw)
        return raw

    def _decrypt(self, data: bytes) -> dict:
        if self._fernet:
            try:
                raw = self._fernet.decrypt(data)
            except InvalidToken:
                _log.warning("license.dat: Entschlüsselung fehlgeschlagen – manipuliert?")
                return {}
        else:
            raw = data
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    # ── Laden / Speichern ─────────────────────────────────────────────────────

    def load(self) -> StoredData:
        if not self._dat.exists():
            return StoredData()
        try:
            raw = self._dat.read_bytes()
            d = self._decrypt(raw)
            return _from_dict(d) if d else StoredData()
        except Exception:
            _log.warning("license.dat: Lesen fehlgeschlagen.")
            return StoredData()

    def save(self, data: StoredData) -> None:
        try:
            self._dat.parent.mkdir(parents=True, exist_ok=True)
            self._dat.write_bytes(self._encrypt(asdict(data)))
        except Exception as e:
            _log.error("license.dat: Schreiben fehlgeschlagen: %s", e)

    # ── Cross-Check: Schreiben ────────────────────────────────────────────────

    def write_cross_checks(self, data: StoredData) -> StoredData:
        """Schreibt den Trial-HMAC in HKLM und ProgramData. Aktualisiert data in-place."""
        val = data.trial_hmac

        # HKLM (maschinen-weit; scheitert meist ohne Admin – kein Fehler)
        data.hklm_written = _try_write_hklm(val)
        if not data.hklm_written:
            _log.debug("HKLM: kein Schreibrecht (normal ohne Admin).")

        # ProgramData (maschinen-weit; scheitert nur bei Berechtigungsproblem)
        try:
            self._marker.parent.mkdir(parents=True, exist_ok=True)
            self._marker.write_text(val, encoding="utf-8")
            data.programdata_written = True
        except Exception as e:
            _log.warning("ProgramData-Marker: Schreiben fehlgeschlagen: %s", e)
            data.programdata_written = False

        return data

    # ── Cross-Check: Prüfen ───────────────────────────────────────────────────

    def verify_cross_checks(self, data: StoredData) -> bool:
        """Vergleicht alle vorhandenen Speicherorte auf HMAC-Konsistenz.

        Gibt False zurück, wenn ein Speicherort manipuliert wurde oder fehlt,
        obwohl er beim Trial-Start erfolgreich beschrieben wurde.
        """
        expected = data.trial_hmac

        if data.hklm_written:
            hklm_val = _try_read_hklm()
            if hklm_val is None:
                _log.warning("HKLM-Eintrag fehlt – wurde entfernt (Manipulation?).")
                return False
            if not hmac.compare_digest(hklm_val, expected):
                _log.warning("HKLM-Cross-Check fehlgeschlagen.")
                return False

        if data.programdata_written:
            try:
                marker_val = self._marker.read_text(encoding="utf-8").strip()
                if not hmac.compare_digest(marker_val, expected):
                    _log.warning("ProgramData-Marker-Cross-Check fehlgeschlagen.")
                    return False
            except FileNotFoundError:
                _log.warning("ProgramData-Marker fehlt – wurde entfernt (Manipulation?).")
                return False
            except Exception:
                _log.warning("ProgramData-Marker: Lesen fehlgeschlagen.")
                return False

        return True

    # ── Bereinigung ───────────────────────────────────────────────────────────

    def clear_all(self) -> None:
        """Löscht alle Lizenzdaten (Deinstallation / Tests)."""
        try:
            self._dat.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            self._marker.unlink(missing_ok=True)
        except Exception:
            pass
        _try_delete_hklm()
