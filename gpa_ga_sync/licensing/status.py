from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class LicenseStatus(Enum):
    UNLICENSED      = "unlicensed"       # Erstinstallation, Trial noch nicht gestartet
    TRIAL           = "trial"            # Trial läuft (x Tage übrig)
    TRIAL_EXPIRED   = "trial_expired"    # Trial abgelaufen, keine Lizenz
    LICENSED        = "licensed"         # Gültige Lizenz aktiv
    LICENSE_INVALID = "license_invalid"  # Schlüssel vorhanden, aber ungültig
    OFFLINE         = "offline"          # Lizenz gecacht, Provider nicht erreichbar


@dataclass
class LicenseInfo:
    status: LicenseStatus
    days_remaining: int = 0                  # nur relevant bei TRIAL
    license_key_masked: str = ""             # maskiert, z.B. "ETSGPA-AAAA-...****"
    activated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    message: str = ""
