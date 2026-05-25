from __future__ import annotations

from .base import ActivationResult, LicenseProvider, LicenseValidationResult
from ..status import LicenseStatus


class NullProvider(LicenseProvider):
    """Null-Provider für Trial-Only-Betrieb und Tests.

    Mit ``always_valid=True`` akzeptiert er jeden Schlüssel (Test-Modus).
    """

    def __init__(self, always_valid: bool = False) -> None:
        self._always_valid = always_valid

    def validate(self, license_key: str, machine_id: str) -> LicenseValidationResult:
        if self._always_valid:
            return LicenseValidationResult(valid=True, status=LicenseStatus.LICENSED)
        return LicenseValidationResult(
            valid=False,
            status=LicenseStatus.UNLICENSED,
            message="Kein Online-Provider konfiguriert.",
        )

    def activate(self, license_key: str, machine_id: str) -> ActivationResult:
        if self._always_valid:
            return ActivationResult(success=True, license_data={"provider": "null"})
        return ActivationResult(
            success=False, message="Kein Online-Provider konfiguriert."
        )

    def deactivate(self, license_key: str, machine_id: str) -> bool:
        return self._always_valid
