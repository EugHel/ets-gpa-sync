"""
Unit-Tests für das Lizenzsystem (Phase LIZENZ-1).
Keine Online-Calls, keine echte Hardware-Bindung.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpa_ga_sync.licensing.machine_id import get_machine_id
from gpa_ga_sync.licensing.status import LicenseInfo, LicenseStatus
from gpa_ga_sync.licensing.storage import (
    LicenseStorage,
    StoredData,
    make_trial_hmac,
)
from gpa_ga_sync.licensing.trial import TrialManager, TRIAL_DAYS
from gpa_ga_sync.licensing.license_manager import LicenseManager
from gpa_ga_sync.licensing.providers.null import NullProvider
from gpa_ga_sync.licensing.providers.offline import (
    OfflineLicenseProvider,
    build_license_blob,
)

# ── Test-RSA-Schlüsselpaar (wird einmal beim Modul-Import generiert) ──────────

try:
    from cryptography.hazmat.primitives.asymmetric import rsa, padding as rsa_padding
    from cryptography.hazmat.primitives import hashes as crypto_hashes, serialization

    _TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _TEST_PUBLIC_KEY_PEM: bytes = _TEST_PRIVATE_KEY.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _RSA_AVAILABLE = True
except Exception:
    _TEST_PRIVATE_KEY = None
    _TEST_PUBLIC_KEY_PEM = b""
    _RSA_AVAILABLE = False

_MACHINE_ID = "a" * 64   # Fester Dummy-Wert für reproduzierbare Tests


def _make_storage(tmp: Path) -> LicenseStorage:
    """Erstellt eine LicenseStorage, die ausschließlich temp-Verzeichnisse nutzt."""
    return LicenseStorage(
        machine_id=_MACHINE_ID,
        dat_path=tmp / "license.dat",
        marker_path=tmp / ".trial_marker",
    )


def _make_clock(dt: datetime):
    """Gibt eine Clock-Funktion zurück, die immer ``dt`` liefert."""
    return lambda: dt


def _advance(base: datetime, days: float) -> datetime:
    return base + timedelta(days=days)


_T0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
# 1. MACHINE-ID
# ══════════════════════════════════════════════════════════════════════════════

class TestMachineId(unittest.TestCase):

    def test_returns_string(self):
        mid = get_machine_id()
        self.assertIsInstance(mid, str)

    def test_is_hex_string_64_chars(self):
        mid = get_machine_id()
        self.assertEqual(len(mid), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in mid))

    def test_non_empty(self):
        mid = get_machine_id()
        self.assertNotEqual(mid, "")

    def test_deterministic_within_call(self):
        # Zweimaliger Aufruf auf derselben Maschine muss gleich sein.
        mid1 = get_machine_id()
        mid2 = get_machine_id()
        self.assertEqual(mid1, mid2)

    def test_different_mac_gives_different_id(self):
        with patch("gpa_ga_sync.licensing.machine_id.uuid.getnode", return_value=0xAABBCCDDEEFF):
            id1 = get_machine_id()
        with patch("gpa_ga_sync.licensing.machine_id.uuid.getnode", return_value=0x112233445566):
            id2 = get_machine_id()
        self.assertNotEqual(id1, id2)


# ══════════════════════════════════════════════════════════════════════════════
# 2. TRIAL-HMAC & STORAGE
# ══════════════════════════════════════════════════════════════════════════════

class TestTrialHmac(unittest.TestCase):

    def test_deterministic(self):
        h1 = make_trial_hmac(1_000_000.0, _MACHINE_ID)
        h2 = make_trial_hmac(1_000_000.0, _MACHINE_ID)
        self.assertEqual(h1, h2)

    def test_different_start_different_hmac(self):
        h1 = make_trial_hmac(1_000_000.0, _MACHINE_ID)
        h2 = make_trial_hmac(2_000_000.0, _MACHINE_ID)
        self.assertNotEqual(h1, h2)

    def test_different_machine_different_hmac(self):
        h1 = make_trial_hmac(1_000_000.0, "a" * 64)
        h2 = make_trial_hmac(1_000_000.0, "b" * 64)
        self.assertNotEqual(h1, h2)

    def test_is_hex_string(self):
        h = make_trial_hmac(1_000_000.0, _MACHINE_ID)
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))


class TestStorage(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _storage(self) -> LicenseStorage:
        return _make_storage(self._path)

    def test_load_returns_empty_if_no_file(self):
        data = self._storage().load()
        self.assertIsNone(data.trial_start)
        self.assertFalse(data.hklm_written)

    def test_save_and_load_roundtrip(self):
        s = self._storage()
        d = StoredData(trial_start=12345.0, trial_hmac="abc", machine_id=_MACHINE_ID)
        s.save(d)
        loaded = s.load()
        self.assertEqual(loaded.trial_start, 12345.0)
        self.assertEqual(loaded.trial_hmac, "abc")

    def test_data_is_encrypted_on_disk(self):
        s = self._storage()
        d = StoredData(trial_start=99999.0, trial_hmac="testhash")
        s.save(d)
        raw = (self._path / "license.dat").read_bytes()
        # Die Rohdaten dürfen nicht als Klartext-JSON lesbar sein.
        self.assertNotIn(b"trial_start", raw)

    def test_tampered_dat_returns_empty(self):
        s = self._storage()
        dat = self._path / "license.dat"
        dat.write_bytes(b"this is not valid encrypted data at all")
        data = s.load()
        self.assertIsNone(data.trial_start)

    def test_programdata_marker_written(self):
        s = self._storage()
        data = StoredData(
            trial_start=1234.0,
            trial_hmac=make_trial_hmac(1234.0, _MACHINE_ID),
            machine_id=_MACHINE_ID,
        )
        data = s.write_cross_checks(data)
        s.save(data)
        self.assertTrue(data.programdata_written)
        self.assertTrue((self._path / ".trial_marker").exists())

    def test_verify_cross_checks_ok(self):
        s = self._storage()
        expected_hmac = make_trial_hmac(1234.0, _MACHINE_ID)
        data = StoredData(
            trial_start=1234.0, trial_hmac=expected_hmac,
            machine_id=_MACHINE_ID,
        )
        data = s.write_cross_checks(data)
        s.save(data)
        self.assertTrue(s.verify_cross_checks(data))

    def test_verify_fails_if_marker_tampered(self):
        s = self._storage()
        expected_hmac = make_trial_hmac(1234.0, _MACHINE_ID)
        data = StoredData(
            trial_start=1234.0, trial_hmac=expected_hmac,
            machine_id=_MACHINE_ID,
        )
        data = s.write_cross_checks(data)
        s.save(data)
        # Marker nachträglich manipulieren
        (self._path / ".trial_marker").write_text("tampered", encoding="utf-8")
        self.assertFalse(s.verify_cross_checks(data))

    def test_verify_fails_if_marker_deleted(self):
        s = self._storage()
        expected_hmac = make_trial_hmac(1234.0, _MACHINE_ID)
        data = StoredData(
            trial_start=1234.0, trial_hmac=expected_hmac,
            machine_id=_MACHINE_ID,
        )
        data = s.write_cross_checks(data)
        s.save(data)
        (self._path / ".trial_marker").unlink()
        self.assertFalse(s.verify_cross_checks(data))

    def test_verify_skips_hklm_if_not_written(self):
        # Wenn hklm_written=False, darf HKLM nicht geprüft werden.
        s = self._storage()
        data = StoredData(
            trial_start=1234.0,
            trial_hmac=make_trial_hmac(1234.0, _MACHINE_ID),
            machine_id=_MACHINE_ID,
            hklm_written=False,  # explizit nicht geschrieben
            programdata_written=False,
        )
        # Ohne programdata_written läuft kein Check → immer True
        self.assertTrue(s.verify_cross_checks(data))

    def test_clear_all_removes_dat(self):
        s = self._storage()
        s.save(StoredData(trial_start=1.0, trial_hmac="x"))
        s.clear_all()
        self.assertFalse((self._path / "license.dat").exists())


# ══════════════════════════════════════════════════════════════════════════════
# 3. TRIAL-LOGIK
# ══════════════════════════════════════════════════════════════════════════════

class TestTrialManager(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _setup(self, clock_dt=None, days=TRIAL_DAYS):
        clock = _make_clock(clock_dt or _T0)
        storage = _make_storage(self._path)
        trial = TrialManager(days=days, clock=clock)
        return storage, trial

    def test_unlicensed_before_trial_start(self):
        storage, trial = self._setup()
        info = trial.get_status(storage)
        self.assertEqual(info.status, LicenseStatus.UNLICENSED)

    def test_trial_starts_on_ensure_started(self):
        storage, trial = self._setup()
        trial.ensure_started(storage)
        data = storage.load()
        self.assertIsNotNone(data.trial_start)

    def test_trial_active_on_day_0(self):
        storage, trial = self._setup(clock_dt=_T0)
        trial.ensure_started(storage)
        info = trial.get_status(storage)
        self.assertEqual(info.status, LicenseStatus.TRIAL)

    def test_trial_days_remaining_correct(self):
        storage, trial = self._setup(clock_dt=_T0)
        trial.ensure_started(storage)
        # Nach 3 Tagen → 11 verbleibend
        trial._clock = _make_clock(_advance(_T0, 3))
        info = trial.get_status(storage)
        self.assertEqual(info.status, LicenseStatus.TRIAL)
        self.assertEqual(info.days_remaining, TRIAL_DAYS - 3)

    def test_trial_expired_after_14_days(self):
        storage, trial = self._setup(clock_dt=_T0)
        trial.ensure_started(storage)
        trial._clock = _make_clock(_advance(_T0, 14))
        info = trial.get_status(storage)
        self.assertEqual(info.status, LicenseStatus.TRIAL_EXPIRED)
        self.assertEqual(info.days_remaining, 0)

    def test_trial_expired_slightly_after_14_days(self):
        storage, trial = self._setup(clock_dt=_T0)
        trial.ensure_started(storage)
        trial._clock = _make_clock(_advance(_T0, 14.001))
        info = trial.get_status(storage)
        self.assertEqual(info.status, LicenseStatus.TRIAL_EXPIRED)

    def test_trial_still_active_just_before_expiry(self):
        storage, trial = self._setup(clock_dt=_T0)
        trial.ensure_started(storage)
        trial._clock = _make_clock(_advance(_T0, 13.99))
        info = trial.get_status(storage)
        self.assertEqual(info.status, LicenseStatus.TRIAL)

    def test_ensure_started_is_idempotent(self):
        """Zweimaliges ensure_started darf den Trial nicht zurücksetzen."""
        storage, trial = self._setup(clock_dt=_T0)
        trial.ensure_started(storage)
        ts1 = storage.load().trial_start
        trial._clock = _make_clock(_advance(_T0, 5))
        trial.ensure_started(storage)
        ts2 = storage.load().trial_start
        self.assertEqual(ts1, ts2)

    def test_custom_trial_duration(self):
        storage, trial = self._setup(clock_dt=_T0, days=7)
        trial.ensure_started(storage)
        trial._clock = _make_clock(_advance(_T0, 7))
        info = trial.get_status(storage)
        self.assertEqual(info.status, LicenseStatus.TRIAL_EXPIRED)

    def test_tamper_hmac_mismatch_returns_expired(self):
        storage, trial = self._setup(clock_dt=_T0)
        trial.ensure_started(storage)
        # HMAC in der Datei direkt manipulieren
        data = storage.load()
        data.trial_hmac = "0" * 64
        storage.save(data)
        info = trial.get_status(storage)
        self.assertEqual(info.status, LicenseStatus.TRIAL_EXPIRED)

    def test_tamper_marker_deletion_returns_expired(self):
        storage, trial = self._setup(clock_dt=_T0)
        trial.ensure_started(storage)
        data = storage.load()
        if data.programdata_written:
            marker = self._path / ".trial_marker"
            marker.unlink(missing_ok=True)
            info = trial.get_status(storage)
            self.assertEqual(info.status, LicenseStatus.TRIAL_EXPIRED)


# ══════════════════════════════════════════════════════════════════════════════
# 4. NULL-PROVIDER
# ══════════════════════════════════════════════════════════════════════════════

class TestNullProvider(unittest.TestCase):

    def test_validate_returns_unlicensed_by_default(self):
        p = NullProvider()
        r = p.validate("anykey", _MACHINE_ID)
        self.assertFalse(r.valid)
        self.assertEqual(r.status, LicenseStatus.UNLICENSED)

    def test_validate_returns_licensed_when_always_valid(self):
        p = NullProvider(always_valid=True)
        r = p.validate("anykey", _MACHINE_ID)
        self.assertTrue(r.valid)
        self.assertEqual(r.status, LicenseStatus.LICENSED)

    def test_activate_fails_by_default(self):
        r = NullProvider().activate("key", _MACHINE_ID)
        self.assertFalse(r.success)

    def test_activate_succeeds_when_always_valid(self):
        r = NullProvider(always_valid=True).activate("key", _MACHINE_ID)
        self.assertTrue(r.success)

    def test_deactivate_false_by_default(self):
        self.assertFalse(NullProvider().deactivate("key", _MACHINE_ID))

    def test_deactivate_true_when_always_valid(self):
        self.assertTrue(NullProvider(always_valid=True).deactivate("key", _MACHINE_ID))


# ══════════════════════════════════════════════════════════════════════════════
# 5. OFFLINE-PROVIDER
# ══════════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(_RSA_AVAILABLE, "cryptography-Paket nicht verfügbar")
class TestOfflineProvider(unittest.TestCase):

    def setUp(self):
        self._provider = OfflineLicenseProvider(_TEST_PUBLIC_KEY_PEM)

    def _make_blob(self, machine_id=_MACHINE_ID, product="gpa-ga-sync",
                   expires_at=None) -> str:
        return build_license_blob(
            _TEST_PRIVATE_KEY, machine_id=machine_id,
            product=product, expires_at=expires_at,
        )

    def test_valid_license_accepted(self):
        blob = self._make_blob()
        r = self._provider.validate(blob, _MACHINE_ID)
        self.assertTrue(r.valid)
        self.assertEqual(r.status, LicenseStatus.LICENSED)

    def test_wrong_machine_id_rejected(self):
        blob = self._make_blob(machine_id="other" * 12)
        r = self._provider.validate(blob, _MACHINE_ID)
        self.assertFalse(r.valid)
        self.assertEqual(r.status, LicenseStatus.LICENSE_INVALID)

    def test_wrong_product_rejected(self):
        blob = self._make_blob(product="other-product")
        r = self._provider.validate(blob, _MACHINE_ID)
        self.assertFalse(r.valid)

    def test_expired_license_rejected(self):
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        blob = self._make_blob(expires_at=past)
        r = self._provider.validate(blob, _MACHINE_ID)
        self.assertFalse(r.valid)
        self.assertEqual(r.status, LicenseStatus.TRIAL_EXPIRED)

    def test_no_expiry_is_permanent(self):
        blob = self._make_blob(expires_at=None)
        r = self._provider.validate(blob, _MACHINE_ID)
        self.assertTrue(r.valid)
        self.assertIsNone(r.expires_at)

    def test_tampered_payload_rejected(self):
        blob = self._make_blob()
        # Mittlere Zeile des Blobs verändern
        lines = blob.splitlines()
        if len(lines) > 2:
            lines[2] = lines[2][:-2] + "XX"
        tampered = "\n".join(lines)
        r = self._provider.validate(tampered, _MACHINE_ID)
        self.assertFalse(r.valid)

    def test_invalid_format_rejected(self):
        r = self._provider.validate("das ist kein lizenz-blob", _MACHINE_ID)
        self.assertFalse(r.valid)
        self.assertEqual(r.status, LicenseStatus.LICENSE_INVALID)

    def test_activate_returns_license_data(self):
        blob = self._make_blob()
        r = self._provider.activate(blob, _MACHINE_ID)
        self.assertTrue(r.success)
        self.assertIsNotNone(r.license_data)
        self.assertIn("blob", r.license_data)

    def test_deactivate_always_true(self):
        self.assertTrue(self._provider.deactivate("any", _MACHINE_ID))

    def test_wrong_public_key_rejected(self):
        # Anderen Public Key verwenden → Signatur ungültig
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pub = other_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        wrong_provider = OfflineLicenseProvider(other_pub)
        blob = self._make_blob()
        r = wrong_provider.validate(blob, _MACHINE_ID)
        self.assertFalse(r.valid)


# ══════════════════════════════════════════════════════════════════════════════
# 6. LICENSE-MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class TestLicenseManager(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_manager(self, always_valid=False, clock_dt=None):
        storage = _make_storage(self._path)
        trial = TrialManager(clock=_make_clock(clock_dt or _T0))
        provider = NullProvider(always_valid=always_valid)
        return LicenseManager(provider, storage, trial)

    def test_unlicensed_before_ensure_started(self):
        mgr = self._make_manager()
        info = mgr.get_status()
        self.assertEqual(info.status, LicenseStatus.UNLICENSED)

    def test_trial_after_ensure_started(self):
        mgr = self._make_manager()
        mgr.ensure_trial_started()
        info = mgr.get_status()
        self.assertEqual(info.status, LicenseStatus.TRIAL)

    def test_activate_stores_license(self):
        mgr = self._make_manager(always_valid=True)
        mgr.ensure_trial_started()
        result = mgr.activate("testkey")
        self.assertTrue(result.success)
        storage = _make_storage(self._path)
        data = storage.load()
        # Schlüssel muss als Hash gespeichert sein, nie im Klartext
        expected_hash = hashlib.sha256("testkey".encode()).hexdigest()
        self.assertEqual(data.license_key_hash, expected_hash)

    def test_activate_returns_licensed_status(self):
        mgr = self._make_manager(always_valid=True)
        mgr.ensure_trial_started()
        mgr.activate("testkey")
        info = mgr.get_status()
        self.assertEqual(info.status, LicenseStatus.LICENSED)

    def test_cache_invalidated_after_activate(self):
        mgr = self._make_manager(always_valid=True)
        mgr.ensure_trial_started()
        _ = mgr.get_status()               # Cache befüllen
        mgr.activate("testkey")
        self.assertIsNone(mgr._cache)     # Cache muss geleert sein

    def test_deactivate_removes_license(self):
        mgr = self._make_manager(always_valid=True)
        mgr.ensure_trial_started()
        mgr.activate("testkey")
        mgr.deactivate()
        storage = _make_storage(self._path)
        data = storage.load()
        self.assertIsNone(data.license_key_hash)

    def test_key_never_stored_in_plaintext(self):
        """Lizenzschlüssel darf niemals im Klartext auf der Platte liegen."""
        mgr = self._make_manager(always_valid=True)
        mgr.ensure_trial_started()
        mgr.activate("SuperSecretKey-1234")
        raw = (self._path / "license.dat").read_bytes()
        self.assertNotIn(b"SuperSecretKey-1234", raw)


if __name__ == "__main__":
    unittest.main()
