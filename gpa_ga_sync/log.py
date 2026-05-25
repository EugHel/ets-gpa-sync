from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

LOG_FILE = Path.home() / ".gpa_ga_sync" / "gpa_ga_sync.log"
_LOGGER_NAME = "gpa_ga_sync"


def setup_logging(console: bool = False) -> None:
    """Konfiguriert den Package-Logger.

    Immer: RotatingFileHandler nach ~/.gpa_ga_sync/gpa_ga_sync.log (DEBUG+).
    Optional: StreamHandler auf stderr (INFO+), aktiviert im CLI-Modus.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return  # bereits konfiguriert

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass  # Log-Verzeichnis nicht schreibbar — kein Absturz

    if console:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    """Gibt einen benannten Child-Logger zurück, z. B. 'gpa_ga_sync.core.parser_gpa'."""
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
