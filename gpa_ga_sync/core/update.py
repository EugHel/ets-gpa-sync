"""Prüfung auf eine neuere Version über die öffentliche GitHub-API.

Es wird ausschließlich die Liste der Releases abgefragt (ein GET ohne Projektdaten).
Die Prüfung ist bewusst fehlertolerant: ohne Netz, bei Zeitüberschreitung oder
unerwarteten Antworten wird einfach kein Hinweis angezeigt.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from ..log import get_logger

_log = get_logger("core.update")

RELEASES_API = "https://api.github.com/repos/EugHel/ets-gpa-sync/releases?per_page=10"
RELEASES_PAGE = "https://github.com/EugHel/ets-gpa-sync/releases"

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.]+))?$")


@dataclass(frozen=True)
class UpdateInfo:
    version: str   # z. B. "v0.10.2-beta"
    url: str       # Release-Seite zum Herunterladen


def parse_version(text: str) -> Optional[Tuple[int, int, int, int, str]]:
    """'v0.10.1-beta' → (0, 10, 1, 0, 'beta'); ohne Suffix (final) → (…, 1, '').

    Das vierte Element sorgt dafür, dass eine finale Version höher gilt als jede
    Vorabversion derselben Nummer (0.10.1 > 0.10.1-beta).
    """
    m = _VERSION_RE.match((text or "").strip())
    if not m:
        return None
    major, minor, patch, pre = m.groups()
    return (int(major), int(minor), int(patch), 0 if pre else 1, pre or "")


def is_newer(candidate: str, current: str) -> bool:
    """True, wenn candidate eine höhere Version als current ist."""
    a, b = parse_version(candidate), parse_version(current)
    return a is not None and b is not None and a > b


def _fetch_releases(timeout: float = 4.0) -> List[dict]:
    req = urllib.request.Request(RELEASES_API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "ets-gpa-sync-update-check",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_for_update(current_version: str,
                     fetch: Callable[[], List[dict]] = _fetch_releases) -> Optional[UpdateInfo]:
    """Liefert die neueste veröffentlichte Version, falls sie neuer ist – sonst None.

    Berücksichtigt auch Vorabversionen (alle bisherigen Releases sind Betas),
    überspringt aber Entwürfe und Tags ohne erkennbare Versionsnummer.
    """
    try:
        releases = fetch()
    except Exception as exc:  # Netzwerk, Timeout, Proxy … → kein Hinweis
        _log.info("Update-Prüfung nicht möglich: %s", exc)
        return None
    best: Optional[UpdateInfo] = None
    for rel in releases if isinstance(releases, list) else []:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        tag = str(rel.get("tag_name") or "")
        if parse_version(tag) is None:
            continue
        if best is None or is_newer(tag, best.version):
            best = UpdateInfo(version=tag, url=str(rel.get("html_url") or RELEASES_PAGE))
    if best is not None and is_newer(best.version, current_version):
        return best
    return None
