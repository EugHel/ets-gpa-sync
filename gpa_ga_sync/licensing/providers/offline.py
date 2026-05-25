from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .base import ActivationResult, LicenseProvider, LicenseValidationResult
from ..status import LicenseStatus
from ...log import get_logger

_log = get_logger("licensing.providers.offline")

# ── Produktions-Public-Key ─────────────────────────────────────────────────────
# Platzhalter – nach docs/GENERATE_KEYS.md eigenen Schlüssel generieren
# und hier als bytes-Literal eintragen:
#   _PRODUCTION_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n"""
_PRODUCTION_PUBLIC_KEY_PEM: Optional[bytes] = None

# ── Blob-Format ────────────────────────────────────────────────────────────────
_HEADER = "-----BEGIN GPA-GA-SYNC LICENSE-----"
_FOOTER = "-----END GPA-GA-SYNC LICENSE-----"
_PRODUCT = "gpa-ga-sync"


def _mask_key(key: str) -> str:
    """Maskiert eine Lizenz für sicheres Logging (nie Klartext)."""
    stripped = key.strip()[:20]
    if len(stripped) <= 4:
        return "****"
    return stripped[:4] + "-...****"


def _parse_blob(blob: str) -> Optional[tuple[bytes, bytes]]:
    """Parst einen License-Blob in (payload_bytes, signature_bytes) oder None."""
    lines = [ln.strip() for ln in blob.strip().splitlines()]
    try:
        start = lines.index(_HEADER)
        end = lines.index(_FOOTER)
    except ValueError:
        return None
    inner = "".join(lines[start + 1 : end])
    try:
        combined = base64.b64decode(inner)
        sep = combined.index(b"|SIG|")
        payload = base64.b64decode(combined[:sep])
        signature = combined[sep + 5 :]
        return payload, signature
    except Exception:
        return None


def _verify_signature(public_key_pem: bytes, payload: bytes, signature: bytes) -> bool:
    try:
        pub = serialization.load_pem_public_key(public_key_pem)
        pub.verify(
            signature,
            payload,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return True
    except InvalidSignature:
        return False
    except Exception as e:
        _log.debug("RSA-Verifikation Fehler: %s", e)
        return False


# ── Hilfsfunktion für Key-Generierung (wird vom Seller genutzt, nicht im Tool) ─

def build_license_blob(
    private_key,
    machine_id: str,
    product: str = _PRODUCT,
    expires_at: Optional[datetime] = None,
) -> str:
    """Erzeugt einen signierten Lizenz-Blob (für Schlüssel-Generierung und Tests).

    ``private_key`` ist ein cryptography-RSA-PrivateKey-Objekt.
    Der Blob wird an den Käufer per Mail / Download gesendet.
    """
    payload_dict: dict = {
        "machine_id": machine_id,
        "product": product,
        "issued_at": int(datetime.now(tz=timezone.utc).timestamp()),
        "expires_at": int(expires_at.timestamp()) if expires_at else None,
    }
    payload_bytes = json.dumps(payload_dict, sort_keys=True).encode("utf-8")
    payload_b64 = base64.b64encode(payload_bytes)

    signature = private_key.sign(
        payload_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    combined = base64.b64encode(payload_b64 + b"|SIG|" + signature).decode("ascii")
    wrapped = "\n".join(combined[i : i + 64] for i in range(0, len(combined), 64))
    return f"{_HEADER}\n{wrapped}\n{_FOOTER}"


# ── Provider-Klasse ────────────────────────────────────────────────────────────

class OfflineLicenseProvider(LicenseProvider):
    """Offline-Provider: verifiziert RSA-PSS-signierte Lizenz-Blobs.

    Der Public Key ist im Tool eingebettet; der Private Key bleibt beim Verkäufer.
    Keine Netzwerkverbindung erforderlich.
    """

    def __init__(self, public_key_pem: bytes) -> None:
        self._public_key_pem = public_key_pem

    def validate(self, license_key: str, machine_id: str) -> LicenseValidationResult:
        _log.debug("Offline-Validierung (Schlüssel: %s).", _mask_key(license_key))
        parsed = _parse_blob(license_key)
        if parsed is None:
            return LicenseValidationResult(
                valid=False, status=LicenseStatus.LICENSE_INVALID,
                message="Ungültiges Lizenz-Format.",
            )

        payload_bytes, signature = parsed
        if not _verify_signature(self._public_key_pem, payload_bytes, signature):
            _log.warning("Offline-Lizenz: Signaturprüfung fehlgeschlagen (%s).", _mask_key(license_key))
            return LicenseValidationResult(
                valid=False, status=LicenseStatus.LICENSE_INVALID,
                message="Lizenz-Signatur ungültig.",
            )

        try:
            data = json.loads(payload_bytes)
        except json.JSONDecodeError:
            return LicenseValidationResult(
                valid=False, status=LicenseStatus.LICENSE_INVALID,
                message="Lizenz-Daten unlesbar.",
            )

        if data.get("product") != _PRODUCT:
            return LicenseValidationResult(
                valid=False, status=LicenseStatus.LICENSE_INVALID,
                message="Lizenz gilt für ein anderes Produkt.",
            )

        if data.get("machine_id") != machine_id:
            _log.warning("Offline-Lizenz: Machine-ID stimmt nicht überein.")
            return LicenseValidationResult(
                valid=False, status=LicenseStatus.LICENSE_INVALID,
                message="Lizenz gilt für eine andere Maschine.",
            )

        expires_ts = data.get("expires_at")
        expires_at: Optional[datetime] = None
        if expires_ts is not None:
            expires_at = datetime.fromtimestamp(expires_ts, tz=timezone.utc)
            if datetime.now(tz=timezone.utc) > expires_at:
                return LicenseValidationResult(
                    valid=False, status=LicenseStatus.TRIAL_EXPIRED,
                    message="Lizenz abgelaufen.", expires_at=expires_at,
                )

        _log.info("Offline-Lizenz gültig (Maschine: %s...).", machine_id[:12])
        return LicenseValidationResult(
            valid=True, status=LicenseStatus.LICENSED, expires_at=expires_at,
        )

    def activate(self, license_key: str, machine_id: str) -> ActivationResult:
        result = self.validate(license_key, machine_id)
        if result.valid:
            return ActivationResult(
                success=True,
                license_data={
                    "blob": license_key,
                    "expires_at": result.expires_at.isoformat() if result.expires_at else None,
                },
            )
        return ActivationResult(success=False, message=result.message)

    def deactivate(self, license_key: str, machine_id: str) -> bool:
        # Offline-Lizenzen haben keine serverseitige Deaktivierung.
        return True


def create_offline_provider() -> OfflineLicenseProvider:
    """Erstellt den Offline-Provider mit dem eingebetteten Produktions-Public-Key.

    Wirft RuntimeError, wenn der Schlüssel noch nicht konfiguriert wurde.
    Siehe docs/GENERATE_KEYS.md.
    """
    if _PRODUCTION_PUBLIC_KEY_PEM is None:
        raise RuntimeError(
            "Offline-Provider: Kein Produktions-Public-Key konfiguriert. "
            "Siehe docs/GENERATE_KEYS.md"
        )
    return OfflineLicenseProvider(_PRODUCTION_PUBLIC_KEY_PEM)
