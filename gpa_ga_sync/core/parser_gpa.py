from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Tuple

from .models import GpaDatapoint
from .utils import detect_encoding, find_text_by_local_name, parse_listener_addresses, parse_optional_int
from ..log import get_logger

_log = get_logger("core.parser_gpa")


def read_zip_text(zf: zipfile.ZipFile, info: zipfile.ZipInfo, password: Optional[str] = None) -> Tuple[str, str]:
    pwd = password.encode("utf-8") if password else None
    data = zf.read(info, pwd=pwd)
    enc = detect_encoding(data)
    return data.decode(enc, errors="replace"), enc


def parse_gpa_datapoints(gpa_path: Path, password: Optional[str] = None) -> List[GpaDatapoint]:
    datapoints: List[GpaDatapoint] = []
    _log.info("Lese GPA-Datei: %s", gpa_path.name)
    with zipfile.ZipFile(gpa_path, "r") as zf:
        for info in zf.infolist():
            path = info.filename.replace("\\", "/")
            if not path.lower().endswith(".xml"):
                continue
            if "/knxdatapoints/" not in path.lower():
                continue
            try:
                xml_text, _enc = read_zip_text(zf, info, password)
                root = ET.fromstring(xml_text)
            except Exception as exc:
                _log.warning("Datenpunkt-XML übersprungen (%s): %s", info.filename, exc)
                continue
            entity_name = find_text_by_local_name(root, "EntityName")
            if entity_name is None:
                _log.debug("Kein EntityName in %s – übersprungen", info.filename)
                continue
            read_ga = parse_optional_int(find_text_by_local_name(root, "ReadGroupAddress"))
            write_ga = parse_optional_int(find_text_by_local_name(root, "WriteGroupAddress"))
            listeners = parse_listener_addresses(root)
            datapoints.append(
                GpaDatapoint(
                    zip_path=info.filename,
                    entity_name=entity_name,
                    read_group_address=read_ga,
                    write_group_address=write_ga,
                    listener_group_addresses=listeners,
                )
            )
    _log.info("%d GPA-Datenpunkte gelesen", len(datapoints))
    return datapoints
