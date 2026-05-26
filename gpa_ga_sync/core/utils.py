from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    if ":" in tag:
        return tag.rsplit(":", 1)[1]
    return tag


def find_text_by_local_name(root: ET.Element, name: str) -> Optional[str]:
    for elem in root.iter():
        if local_name(elem.tag) == name:
            return elem.text or ""
    return None


def parse_optional_int(text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    text = text.strip()
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_listener_addresses(root: ET.Element) -> Tuple[int, ...]:
    """Liest ListenerGroupAddresses robust. Unterstützt leere Elemente, Textlisten und Kind-Elemente."""
    result: List[int] = []
    for elem in root.iter():
        if local_name(elem.tag) != "ListenerGroupAddresses":
            continue
        if elem.text and elem.text.strip():
            for token in re.split(r"[^0-9]+", elem.text.strip()):
                if token:
                    try:
                        value = int(token)
                        if value and value not in result:
                            result.append(value)
                    except ValueError:
                        pass
        for child in list(elem):
            candidates = []
            if child.text:
                candidates.append(child.text)
            candidates.extend(child.attrib.values())
            for candidate in candidates:
                for token in re.split(r"[^0-9]+", candidate.strip()):
                    if token:
                        try:
                            value = int(token)
                            if value and value not in result:
                                result.append(value)
                        except ValueError:
                            pass
    return tuple(result)


def replace_entity_name_preserve_xml(xml_text: str, new_name: str) -> str:
    """Ersetzt nur den Inhalt des EntityName-Elements und erhält den restlichen XML-Text."""
    escaped = html.escape(new_name, quote=False)
    pattern = re.compile(r"(<(?P<prefix>[A-Za-z0-9_\-.]+:)?EntityName\b[^>]*>)(.*?)(</(?P=prefix)?EntityName>)", re.DOTALL)
    new_text, count = pattern.subn(lambda m: f"{m.group(1)}{escaped}{m.group(4)}", xml_text, count=1)
    if count != 1:
        raise ValueError("EntityName-Element nicht eindeutig gefunden")
    return new_text


def detect_encoding(data: bytes) -> str:
    """Einfache Encoding-Erkennung für XML-Dateien."""
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    head = data[:200].decode("ascii", errors="ignore")
    m = re.search(r'encoding=["\']([^"\']+)["\']', head, re.IGNORECASE)
    if m:
        return m.group(1)
    return "utf-8"


def normalize_name_for_compare(name: str) -> str:
    """Trimmt und vereinheitlicht Whitespaces nur für den Vergleich."""
    return re.sub(r"\s+", " ", name.strip())
