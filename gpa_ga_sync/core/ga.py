from __future__ import annotations

import re


def ga_to_int(address: str) -> int:
    """Konvertiert KNX-GA in den internen Integer-Wert.

    Unterstützt:
    - 3-stufige Schreibweise: H/M/U, z. B. 1/2/3
    - ETS-.knxproj-Integerwerte: z. B. 258
    """
    address = address.strip()
    if re.fullmatch(r"\d+", address):
        value = int(address)
        if 0 <= value <= 0xFFFF:
            return value
        raise ValueError(f"Gruppenadresse außerhalb des KNX-Bereichs: {address!r}")

    parts = address.split("/")
    if len(parts) != 3:
        raise ValueError(f"Ungültige Gruppenadresse: {address!r}")
    main, middle, sub = map(int, parts)
    if not (0 <= main <= 31 and 0 <= middle <= 7 and 0 <= sub <= 255):
        raise ValueError(f"Gruppenadresse außerhalb des 3-stufigen KNX-Bereichs: {address!r}")
    return main * 2048 + middle * 256 + sub


def int_to_ga(value: int) -> str:
    """Konvertiert internen Integer-Wert zurück in 3-stufige KNX-GA."""
    if value < 0 or value > 0xFFFF:
        raise ValueError(f"Ungültiger GA-Wert: {value}")
    main = value // 2048
    rest = value % 2048
    middle = rest // 256
    sub = rest % 256
    return f"{main}/{middle}/{sub}"
