from __future__ import annotations

import copy
import csv
import zipfile
from pathlib import Path
from typing import Optional, Sequence

from .models import SyncCandidate, SyncStatus
from .utils import detect_encoding, replace_entity_name_preserve_xml
from ..log import get_logger

_log = get_logger("core.writer")


def write_updated_gpa(
    input_gpa: Path,
    output_gpa: Path,
    selected_candidates: Sequence[SyncCandidate],
    password: Optional[str] = None,
) -> int:
    """Erstellt eine neue GPA-Datei mit aktualisierten EntityName-Werten."""
    updates = {c.zip_path: c for c in selected_candidates if c.selected and c.status in (SyncStatus.AENDERUNG, SyncStatus.LEERZEICHEN)}
    if not updates:
        raise ValueError("Keine ausgewählten Änderungen vorhanden")

    _log.info("Schreibe neue GPA-Datei: %s (%d Änderungen)", output_gpa.name, len(updates))

    if output_gpa.exists():
        _log.debug("Ausgabedatei existiert bereits, wird überschrieben: %s", output_gpa)
        output_gpa.unlink()

    pwd = password.encode("utf-8") if password else None
    changed = 0

    with zipfile.ZipFile(input_gpa, "r") as zin, zipfile.ZipFile(output_gpa, "w") as zout:
        zout.comment = zin.comment
        for info in zin.infolist():
            data = zin.read(info, pwd=pwd)
            if info.filename in updates:
                enc = detect_encoding(data)
                text = data.decode(enc, errors="replace")
                new_name = updates[info.filename].new_name
                text = replace_entity_name_preserve_xml(text, new_name)
                data = text.encode(enc.replace("-sig", "")) if enc.lower() == "utf-8-sig" else text.encode(enc)
                _log.debug("EntityName aktualisiert: %s -> %r", info.filename, new_name)
                changed += 1

            # ZipInfo kopieren, damit Zeitstempel, Pfad, Attribute und Kompressionsart erhalten bleiben.
            out_info = copy.copy(info)
            out_info.flag_bits &= ~0x1  # keine Verschlüsselung beim Schreiben
            zout.writestr(out_info, data)

    _log.info("GPA-Datei geschrieben: %d Datenpunkte geändert", changed)
    return changed


def export_candidates_csv(candidates: Sequence[SyncCandidate], csv_path: Path) -> None:
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Ausgewählt", "Status", "GA", "Quelle", "Aktueller GPA-Name", "Neuer GPA-Name", "Datei im GPA"])
        for c in candidates:
            writer.writerow(["ja" if c.selected else "nein", c.status, c.group_address, c.source_field, c.current_name, c.new_name, c.zip_path])
