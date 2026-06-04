from __future__ import annotations

import hashlib
from typing import Optional

from .status import LicenseInfo, LicenseStatus
from .storage import LicenseStorage
from .trial import TrialManager
from .providers.base import ActivationResult, LicenseProvider
from ..log import get_logger

_log = get_logger("licensing.manager")


def _hash_key(key: str) -> str:
    """SHA-256 eines Lizenzschlüssels – für sichere Speicherung (nie Klartext)."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _mask_key(key: str) -> str:
    """Maskiert einen Schlüssel für Logging: 'ETSG-...****'."""
    if not key or len(key) <= 8:
        return "****"
    return key[:4] + "-...****"


class LicenseManager:
    """Koordiniert Trial-Logik, Lizenzspeicherung und Provider.

    Reihenfolge der Status-Ermittlung:
    1. Gespeicherte Lizenz vorhanden → Provider.validate()
    2. Kein Lizenzschlüssel → TrialManager.get_status()
    """

    def __init__(
        self,
        provider: LicenseProvider,
        storage: LicenseStorage,
        trial: TrialManager,
    ) -> None:
        self._provider = provider
        self._storage = storage
        self._trial = trial
        self._cache: Optional[LicenseInfo] = None

    def ensure_trial_started(self) -> None:
        """Startet den Trial beim ersten App-Start automatisch."""
        self._trial.ensure_started(self._storage)
        self._cache = None

    def get_status(self) -> LicenseInfo:
        """Gibt den aktuellen Lizenzstatus zurück (gecacht bis Invalidierung)."""
        if self._cache is not None:
            return self._cache

        data = self._storage.load()
        if data.license_key_hash and data.license_data is not None:
            # blob kann leer sein (z.B. NullProvider) – Provider entscheidet selbst.
            blob = data.license_data.get("blob", "")
            result = self._provider.validate(blob, self._storage._machine_id)
            info = LicenseInfo(
                status=result.status,
                expires_at=result.expires_at,
                message=result.message,
            )
            self._cache = info
            return info

        info = self._trial.get_status(self._storage)
        self._cache = info
        return info

    def activate(self, license_key: str) -> ActivationResult:
        """Aktiviert einen Lizenzschlüssel und speichert die Lizenzdaten."""
        _log.info("Aktivierung angefragt (Schlüssel: %s).", _mask_key(license_key))
        result = self._provider.activate(license_key, self._storage._machine_id)
        if result.success:
            data = self._storage.load()
            data.license_key_hash = _hash_key(license_key)
            data.license_data = result.license_data
            self._storage.save(data)
            self._cache = None
            _log.info("Lizenz aktiviert (Schlüssel: %s).", _mask_key(license_key))
        else:
            _log.warning(
                "Aktivierung fehlgeschlagen (Schlüssel: %s): %s",
                _mask_key(license_key), result.message,
            )
        return result

    def deactivate(self) -> bool:
        """Deaktiviert die gespeicherte Lizenz."""
        data = self._storage.load()
        if not data.license_key_hash:
            return True
        blob = (data.license_data or {}).get("blob", "")
        ok = self._provider.deactivate(blob, self._storage._machine_id)
        if ok:
            data.license_key_hash = None
            data.license_data = None
            self._storage.save(data)
            self._cache = None
            _log.info("Lizenz deaktiviert.")
        return ok

    def invalidate_cache(self) -> None:
        """Erzwingt Neuberechnung beim nächsten get_status()-Aufruf."""
        self._cache = None
