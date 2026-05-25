from __future__ import annotations

import base64
import hashlib
import hmac
import io
import re
import struct
import zipfile
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .ga import ga_to_int, int_to_ga
from .models import EtsGroupAddress
from .utils import detect_encoding, local_name
from ..log import get_logger

_log = get_logger("core.parser_ets")


class EtsProjectPasswordRequired(Exception):
    """Wird ausgelöst, wenn eine .knxproj verschlüsselte Projektbestandteile enthält."""
    pass


class EtsProjectReadError(Exception):
    """Wird ausgelöst, wenn eine .knxproj nicht gelesen werden kann."""
    pass


def _format_ets_address(address_attr: str, value: int) -> str:
    address_attr = address_attr.strip()
    if "/" in address_attr:
        return address_attr
    return int_to_ga(value)


def _extract_group_addresses_from_xml_text(xml_text: str) -> Dict[int, EtsGroupAddress]:
    result: Dict[int, EtsGroupAddress] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return result

    for elem in root.iter():
        if local_name(elem.tag) != "GroupAddress":
            continue
        name = elem.attrib.get("Name", "").strip()
        address_attr = elem.attrib.get("Address", "").strip()
        if not name or not address_attr:
            continue
        try:
            value = ga_to_int(address_attr)
            address = _format_ets_address(address_attr, value)
        except ValueError:
            continue
        result[value] = EtsGroupAddress(address=address, value=value, name=name)
    return result


def _derive_knx_project_zip_password(project_password: str) -> bytes:
    """Leitet das innere ZIP-Passwort einer passwortgeschützten .knxproj ab.

    KNX-Projektexporte verwenden für das P-XXXX.zip nicht direkt das Projektpasswort,
    sondern ein per PBKDF2-HMAC-SHA256 abgeleitetes Base64-Passwort.
    """
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        project_password.encode("utf-16le"),
        b"21.project.ets.knx.org",
        65536,
        32,
    )
    return base64.b64encode(derived)


def _zipinfo_aes_extra(info: zipfile.ZipInfo) -> Optional[Tuple[int, bytes, int, int]]:
    """Liest WinZip-AES Extra-Header 0x9901, falls vorhanden."""
    extra = info.extra
    i = 0
    while i + 4 <= len(extra):
        header_id, size = struct.unpack_from("<HH", extra, i)
        i += 4
        data = extra[i:i + size]
        i += size
        if header_id == 0x9901 and len(data) >= 7:
            version, vendor, strength, actual_compression = struct.unpack_from("<H2sBH", data, 0)
            return version, vendor, strength, actual_compression
    return None


def _raw_zip_entry_data(zip_bytes: bytes, info: zipfile.ZipInfo) -> bytes:
    """Liest die rohen verschlüsselten Daten eines ZipInfo-Eintrags."""
    bio = io.BytesIO(zip_bytes)
    bio.seek(info.header_offset)
    local = bio.read(30)
    if len(local) != 30 or local[:4] != b"PK\x03\x04":
        raise EtsProjectReadError("Ungültiger ZIP-Local-Header in ETS-Projekt.")
    fields = struct.unpack("<IHHHHHIIIHH", local)
    filename_len = fields[-2]
    extra_len = fields[-1]
    bio.seek(filename_len + extra_len, 1)
    return bio.read(info.compress_size)


def _aes_ctr_little_endian_decrypt(key: bytes, data: bytes) -> bytes:
    """WinZip-AES nutzt AES-CTR mit little-endian Counter."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as e:
        raise EtsProjectReadError(
            "Für passwortgeschützte .knxproj-Dateien wird entweder das Python-Paket "
            "'cryptography' oder 7-Zip benötigt."
        ) from e

    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    out = bytearray()
    counter = 1
    for offset in range(0, len(data), 16):
        block = data[offset:offset + 16]
        keystream = encryptor.update(counter.to_bytes(16, "little"))
        out.extend(a ^ b for a, b in zip(block, keystream))
        counter += 1
    encryptor.finalize()
    return bytes(out)


def _read_winzip_aes_member(zip_bytes: bytes, info: zipfile.ZipInfo, password: bytes) -> bytes:
    """Liest einen WinZip-AES verschlüsselten Eintrag aus einem ZIP-Archiv."""
    aes_extra = _zipinfo_aes_extra(info)
    if aes_extra is None:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            return zf.read(info, pwd=password)

    _version, _vendor, strength, actual_compression = aes_extra
    salt_len = {1: 8, 2: 12, 3: 16}.get(strength)
    key_len = {1: 16, 2: 24, 3: 32}.get(strength)
    if not salt_len or not key_len:
        raise EtsProjectReadError("Unbekannte WinZip-AES-Schlüsselstärke im ETS-Projekt.")

    raw = _raw_zip_entry_data(zip_bytes, info)
    salt = raw[:salt_len]
    password_verifier = raw[salt_len:salt_len + 2]
    encrypted_data = raw[salt_len + 2:-10]
    auth_code = raw[-10:]

    key_material = hashlib.pbkdf2_hmac("sha1", password, salt, 1000, 2 * key_len + 2)
    encryption_key = key_material[:key_len]
    authentication_key = key_material[key_len:2 * key_len]
    verifier = key_material[-2:]
    if verifier != password_verifier:
        raise EtsProjectPasswordRequired("Falsches oder fehlendes ETS-Projektpasswort.")

    expected_auth = hmac.new(authentication_key, encrypted_data, hashlib.sha1).digest()[:10]
    if expected_auth != auth_code:
        raise EtsProjectPasswordRequired("Falsches oder fehlendes ETS-Projektpasswort.")

    compressed = _aes_ctr_little_endian_decrypt(encryption_key, encrypted_data)
    if actual_compression == zipfile.ZIP_DEFLATED:
        return zlib.decompress(compressed, -15)
    if actual_compression == zipfile.ZIP_STORED:
        return compressed
    raise EtsProjectReadError(f"Nicht unterstützte Kompressionsmethode in ETS-Projekt: {actual_compression}")


def _read_nested_zip_xmls(nested_zip_bytes: bytes, project_password: Optional[str]) -> Dict[int, EtsGroupAddress]:
    """Durchsucht ein inneres P-XXXX.zip nach Gruppenadressen."""
    result: Dict[int, EtsGroupAddress] = {}

    with zipfile.ZipFile(io.BytesIO(nested_zip_bytes), "r") as zf:
        infos = [i for i in zf.infolist() if not i.is_dir() and i.filename.lower().endswith((".xml", ".knx"))]
        encrypted = any((i.flag_bits & 0x1) or _zipinfo_aes_extra(i) is not None or i.compress_type == 99 for i in infos)

        passwords: List[Optional[bytes]] = [None]
        if encrypted:
            if project_password is None:
                raise EtsProjectPasswordRequired("ETS-Projektpasswort erforderlich.")
            passwords = [_derive_knx_project_zip_password(project_password)]

        for info in infos:
            data: Optional[bytes] = None
            last_error: Optional[Exception] = None
            for pwd in passwords:
                try:
                    if _zipinfo_aes_extra(info) is not None or info.compress_type == 99:
                        if pwd is None:
                            raise EtsProjectPasswordRequired("ETS-Projektpasswort erforderlich.")
                        data = _read_winzip_aes_member(nested_zip_bytes, info, pwd)
                    else:
                        data = zf.read(info, pwd=pwd)
                    break
                except EtsProjectPasswordRequired as e:
                    last_error = e
                    continue
                except RuntimeError as e:
                    last_error = e
                    continue

            if data is None:
                if encrypted:
                    raise EtsProjectPasswordRequired("ETS-Projektpasswort erforderlich oder falsch.") from last_error
                _log.debug("Eintrag nicht lesbar, übersprungen: %s", info.filename)
                continue

            enc = detect_encoding(data)
            xml_text = data.decode(enc, errors="replace")
            found = _extract_group_addresses_from_xml_text(xml_text)
            _log.debug("%d GA(s) in %s gefunden", len(found), info.filename)
            result.update(found)

    return result


def parse_ets_ga_export(xml_path: Path, project_password: Optional[str] = None) -> Dict[int, EtsGroupAddress]:  # noqa: C901
    """Liest Gruppenadressen aus ETS-XML oder direkt aus einer .knxproj-Datei.

    Bei .knxproj wird das äußere Projektarchiv durchsucht. Enthält es ein
    verschlüsseltes P-XXXX.zip, wird das ETS-Projektpasswort benötigt.
    """
    _log.info("Lese ETS-Datei: %s", xml_path.name)
    suffix = xml_path.suffix.lower()

    if suffix == ".knxproj":
        result: Dict[int, EtsGroupAddress] = {}
        if not zipfile.is_zipfile(xml_path):
            raise EtsProjectReadError("Die .knxproj-Datei ist kein gültiges ZIP-Archiv.")

        with zipfile.ZipFile(xml_path, "r") as outer:
            for info in outer.infolist():
                if info.is_dir():
                    continue

                lower = info.filename.lower()

                if re.fullmatch(r"p-[0-9a-f]{4}\.zip", Path(info.filename).name.lower()):
                    nested = outer.read(info)
                    result.update(_read_nested_zip_xmls(nested, project_password))
                    continue

                if lower.endswith((".xml", ".knx")):
                    try:
                        data = outer.read(info)
                        enc = detect_encoding(data)
                        found = _extract_group_addresses_from_xml_text(data.decode(enc, errors="replace"))
                        _log.debug("%d GA(s) in äußerem Eintrag %s", len(found), info.filename)
                        result.update(found)
                    except Exception as exc:
                        _log.warning("Äußerer ZIP-Eintrag übersprungen (%s): %s", info.filename, exc)
                        continue

        if not result:
            raise EtsProjectReadError(
                "In der .knxproj-Datei wurden keine Gruppenadressen gefunden. "
                "Falls das Projekt passwortgeschützt ist, bitte mit ETS-Projektpasswort erneut versuchen "
                "oder alternativ den Gruppenadress-Export als XML verwenden."
            )
        _log.info("%d ETS-Gruppenadressen aus .knxproj gelesen", len(result))
        return result

    if suffix == ".xml":
        data = xml_path.read_bytes()
        enc = detect_encoding(data)
        result_xml = _extract_group_addresses_from_xml_text(data.decode(enc, errors="replace"))
        _log.info("%d ETS-Gruppenadressen aus XML gelesen", len(result_xml))
        return result_xml

    data = xml_path.read_bytes()
    enc = detect_encoding(data)
    result_fallback = _extract_group_addresses_from_xml_text(data.decode(enc, errors="replace"))
    _log.info("%d ETS-Gruppenadressen gelesen (Fallback-Modus)", len(result_fallback))
    return result_fallback
