from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Callable, Optional

from .status import LicenseInfo, LicenseStatus
from .storage import LicenseStorage, StoredData, make_trial_hmac
from ..log import get_logger

_log = get_logger("licensing.trial")

TRIAL_DAYS = 14
_Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class TrialManager:
    """Verwaltet den konfigurierbaren Trial-Zeitraum.

    Die ``clock``-Parameter erlaubt Zeitmanipulation in Tests.
    """

    def __init__(self, days: int = TRIAL_DAYS, clock: Optional[_Clock] = None) -> None:
        self._days = days
        self._clock = clock or _utcnow

    def ensure_started(self, storage: LicenseStorage) -> None:
        """Startet den Trial beim ersten App-Start automatisch."""
        data = storage.load()
        if data.trial_start is None:
            self._start(storage, data)

    def _start(self, storage: LicenseStorage, data: StoredData) -> None:
        now = self._clock()
        data.trial_start = now.timestamp()
        data.machine_id = storage._machine_id
        data.trial_hmac = make_trial_hmac(data.trial_start, storage._machine_id)
        data = storage.write_cross_checks(data)
        storage.save(data)
        _log.info("Trial gestartet: %d Tage ab %s.", self._days, now.date())

    def get_status(self, storage: LicenseStorage) -> LicenseInfo:
        """Berechnet den aktuellen Trial-Status inkl. Tamper-Checks."""
        data = storage.load()

        if data.trial_start is None:
            return LicenseInfo(status=LicenseStatus.UNLICENSED)

        # HMAC-Eigenprüfung der gespeicherten Daten
        expected = make_trial_hmac(data.trial_start, storage._machine_id)
        if not hmac.compare_digest(data.trial_hmac.encode(), expected.encode()):
            _log.warning("Trial-HMAC-Prüfung fehlgeschlagen – manipuliert?")
            return LicenseInfo(
                status=LicenseStatus.TRIAL_EXPIRED,
                message="Manipulationsversuch erkannt.",
            )

        # Cross-Check (HKLM + ProgramData)
        if not storage.verify_cross_checks(data):
            return LicenseInfo(
                status=LicenseStatus.TRIAL_EXPIRED,
                message="Manipulationsversuch erkannt.",
            )

        # Zeitprüfung
        start = datetime.fromtimestamp(data.trial_start, tz=timezone.utc)
        now = self._clock()
        elapsed_days = (now - start).total_seconds() / 86400
        remaining = max(0, self._days - int(elapsed_days))

        if elapsed_days >= self._days:
            _log.info("Trial abgelaufen (gestartet: %s).", start.date())
            return LicenseInfo(status=LicenseStatus.TRIAL_EXPIRED, days_remaining=0)

        _log.debug("Trial aktiv: %d Tage verbleibend.", remaining)
        return LicenseInfo(status=LicenseStatus.TRIAL, days_remaining=remaining)
