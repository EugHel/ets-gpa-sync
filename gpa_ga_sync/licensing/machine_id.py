from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
import uuid
from typing import Optional

from ..log import get_logger

_log = get_logger("licensing.machine_id")

_WIN = sys.platform == "win32"
_CREATION_FLAGS: dict = {"creationflags": 0x08000000} if _WIN else {}  # CREATE_NO_WINDOW


def _run_silent(args: list[str]) -> Optional[str]:
    """Führt einen Subprocess still aus und gibt stdout zurück, None bei Fehler."""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=4, **_CREATION_FLAGS
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _wmic_serial(wmic_class: str) -> str:
    """Liest SerialNumber via WMIC (Windows 7-10)."""
    out = _run_silent(["wmic", wmic_class, "get", "SerialNumber", "/value"])
    if out:
        for line in out.splitlines():
            if "=" in line:
                val = line.split("=", 1)[1].strip()
                if val:
                    return val
    return ""


def _ps_query(script: str) -> str:
    """Führt ein PowerShell-Snippet aus und gibt stdout zurück (Fallback für WMIC)."""
    out = _run_silent([
        "powershell", "-NoProfile", "-NonInteractive", "-Command", script,
    ])
    return out or ""


def _get_cpu_serial() -> str:
    val = _wmic_serial("cpu")
    if not val:
        val = _ps_query("(Get-WmiObject Win32_Processor).ProcessorId")
    return val


def _get_disk_serial() -> str:
    val = _wmic_serial("diskdrive")
    if not val:
        val = _ps_query(
            "(Get-WmiObject Win32_DiskDrive | Select-Object -First 1).SerialNumber"
        )
    return val


def get_machine_id() -> str:
    """Generiert eine stabile, hardware-gebundene Maschinen-ID (SHA-256, hex).

    Komponenten: MAC-Adresse, Hostname, CPU-Serial, Disk-Serial.
    Fehlt eine Komponente (VM, WMI deaktiviert), wird sie als Leerstring einbezogen.
    Die ID ändert sich nur bei echtem Hardware-Wechsel.
    """
    parts = [
        str(uuid.getnode()),      # MAC-Adresse (uuid.getnode() gibt MAC als int)
        platform.node().lower(),  # Hostname
        _get_cpu_serial(),
        _get_disk_serial(),
    ]
    raw = "|".join(parts)
    mid = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
    _log.debug("Machine-ID: %s...", mid[:12])
    return mid
