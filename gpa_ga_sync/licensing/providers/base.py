from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..status import LicenseStatus


@dataclass
class LicenseValidationResult:
    valid: bool
    status: LicenseStatus
    message: str = ""
    expires_at: Optional[datetime] = None


@dataclass
class ActivationResult:
    success: bool
    message: str = ""
    license_data: Optional[dict] = None


class LicenseProvider(ABC):
    """Abstrakte Basisklasse für alle Lizenz-Provider.

    Konkreter Provider kann via Konfiguration ausgetauscht werden:
    - Phase LIZENZ-1: NullProvider + OfflineLicenseProvider
    - Phase LIZENZ-3: LemonSqueezyProvider o.ä.
    """

    @abstractmethod
    def validate(self, license_key: str, machine_id: str) -> LicenseValidationResult:
        """Prüft einen Lizenzschlüssel/-blob für die gegebene Maschinen-ID."""

    @abstractmethod
    def activate(self, license_key: str, machine_id: str) -> ActivationResult:
        """Aktiviert einen Lizenzschlüssel für die gegebene Maschinen-ID."""

    @abstractmethod
    def deactivate(self, license_key: str, machine_id: str) -> bool:
        """Deaktiviert einen Lizenzschlüssel. Gibt True bei Erfolg zurück."""
