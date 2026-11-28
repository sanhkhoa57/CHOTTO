"""Guardian Mode: PIN, mã khôi phục, chống dò mã và chính sách mở link."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chotto import guardian  # noqa: E402


class GuardianTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"CHOTTO_DATA_DIR": folder.name})
        env.start()
        self.addCleanup(env.stop)
        self.folder = Path(folder.name)
        self.now = 1_000_000.0
        clock = patch.object(guardian.time, "time", lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def _wrong(self, times: int) -> guardian.AuthResult:
        result = guardian.AuthResult(False)
        for _ in range(times):
            result = guardian.verify_pin("0000")
        return result

    def test_setup_and_verify(self) -> None:
        self.assertFalse(guardian.has_pin())
        key = guardian.setup("482915")
        self.assertTrue(guardian.confirm("482915").ok)
        self.assertTrue(guardian.has_pin())
        self.assertTrue(guardian.verify_pin("482915").ok)
        self.assertEqual(guardian.verify_pin("482916").error, "wrong")
        stored = (self.folder / "guardian.bin").read_bytes()
        for secret in ("482915", key, guardian.normalize_recovery_key(key)):
            self.assertNotIn(secret.encode(), stored)

    def test_pin_format(self) -> None:
        for bad in ("123", "1234567", "12a4", "", " 1234", "１２３４", 1234, None):
            self.assertFalse(guardian.valid_pin(bad), bad)
        for good in ("1234", "000000"):
            self.assertTrue(guardian.valid_pin(good))
        with self.assertRaises(guardian.GuardianError):
            guardian.setup("12")
        self.assertFalse(guardian.has_pin())

    def test_unconfirmed_setup_can_be_redone(self) -> None:
        guardian.setup("1234")
        self.assertFalse(guardian.has_pin())
        guardian.setup("5678")                            # bỏ dở ở màn hình mã khôi phục
        self.assertEqual(guardian.confirm("1234").error, "wrong")
        self.assertTrue(guardian.confirm("5678").ok)
        self.assertTrue(guardian.has_pin())

    def test_setup_cannot_overwrite(self) -> None:
        guardian.setup("1234")
        guardian.confirm("1234")
        with self.assertRaises(guardian.GuardianError):
            guardian.setup("9999")
        self.assertTrue(guardian.verify_pin("1234").ok)

    def test_recovery_key_shape(self) -> None:
        key = guardian.setup("1234")
        self.assertRegex(key, r"^CHOTTO(-[2-9A-HJKMNP-Z]{4}){3}$")
        for confusing in "0O1IL":
            self.assertNotIn(confusing, guardian.RECOVERY_ALPHABET)

    def test_lockout_after_five_failures_then_expires(self) -> None:
        guardian.setup("1234")
        self.assertEqual(self._wrong(4).attempts_left, 1)
        locked = self._wrong(1)
        self.assertEqual((locked.error, locked.locked_for), ("locked", guardian.LOCKOUT_S))
        self.now += 100
        during = guardian.verify_pin("1234")              # PIN đúng cũng bị từ chối khi đang khóa
        self.assertEqual((during.ok, during.locked_for), (False, 200))
        self.assertEqual(guardian.lockout_remaining(), 200)
        self.now += 201
        self.assertTrue(guardian.verify_pin("1234").ok)

    def test_success_resets_failure_count(self) -> None:
        guardian.setup("1234")
        self._wrong(4)
        self.assertTrue(guardian.verify_pin("1234").ok)
        self.assertEqual(self._wrong(4).error, "wrong")

    def test_clock_rollback_does_not_extend_lockout(self) -> None:
        guardian.setup("1234")
        self._wrong(5)
        self.now -= 86_400
        self.assertEqual(guardian.lockout_remaining(), guardian.LOCKOUT_S)

    def test_recovery_rotates_key(self) -> None:
        old = guardian.setup("1234")
        typed = old.lower().replace("-", " ")             # gõ lại thoải mái vẫn nhận
        result = guardian.recover(typed, "5678")
        self.assertTrue(result.ok)
        self.assertNotEqual(result.recovery_key, old)
        self.assertTrue(guardian.verify_pin("5678").ok)
        self.assertFalse(guardian.verify_pin("1234").ok)
        self.assertEqual(guardian.recover(old, "1111").error, "wrong")
        self.assertTrue(guardian.recover(result.recovery_key, "1111").ok)

    def test_recovery_shares_lockout_with_pin(self) -> None:
        key = guardian.setup("1234")
        self._wrong(3)
        guardian.recover("CHOTTO-AAAA-AAAA-AAAA", "5678")
        self.assertEqual(guardian.recover("CHOTTO-AAAA-AAAA-AAAA", "5678").error, "locked")
        self.assertEqual(guardian.recover(key, "5678").error, "locked")
        self.assertEqual(guardian.verify_pin("1234").error, "locked")

    def test_invalid_new_pin_does_not_consume_recovery_key(self) -> None:
        key = guardian.setup("1234")
        self.assertEqual(guardian.recover(key, "ab").error, "invalid_pin")
        self.assertTrue(guardian.recover(key, "5678").ok)

    def test_change_pin_rotates_recovery_key(self) -> None:
        old = guardian.setup("1234")
        self.assertEqual(guardian.change_pin("0000", "5678").error, "wrong")
        changed = guardian.change_pin("1234", "5678")
        self.assertTrue(changed.ok)
        self.assertRegex(changed.recovery_key, r"^CHOTTO-")
        self.assertNotEqual(changed.recovery_key, old)
        self.assertTrue(guardian.verify_pin("5678").ok)
        self.assertEqual(guardian.recover(old, "9999").error, "wrong")
        self.assertTrue(guardian.recover(changed.recovery_key, "9999").ok)

    def test_failed_change_keeps_recovery_key(self) -> None:
        key = guardian.setup("1234")
        self.assertEqual(guardian.change_pin("0000", "5678").recovery_key, "")
        self.assertTrue(guardian.recover(key, "9999").ok)

    def test_missing_or_corrupt_file_fails_closed(self) -> None:
        self.assertEqual(guardian.verify_pin("1234").error, "unavailable")
        guardian.setup("1234")
        (self.folder / "guardian.bin").write_bytes(b"rac")
        self.assertEqual(guardian.verify_pin("1234").error, "unavailable")
        self.assertTrue(guardian.has_pin())               # không cho đặt PIN đè lên file hỏng
        with self.assertRaises(guardian.GuardianError):
            guardian.setup("9999")

    def test_failure_that_cannot_be_saved_is_not_a_free_guess(self) -> None:
        guardian.setup("1234")
        with patch.object(guardian, "_store", side_effect=guardian.GuardianError("đĩa đầy")):
            self.assertEqual(guardian.verify_pin("0000").error, "unavailable")


class OpenPolicyTests(unittest.TestCase):
    def test_off_allows_everything(self) -> None:
        for level in ("SAFE", "WARN", "HIGH", "BLOCKED"):
            self.assertEqual(guardian.open_policy({"guardian_enabled": False}, level), "allow")

    def test_on(self) -> None:
        pin = {"guardian_enabled": True, "guardian_warn_policy": "pin"}
        lock = {"guardian_enabled": True, "guardian_warn_policy": "lock"}
        self.assertEqual([guardian.open_policy(pin, v) for v in ("SAFE", "WARN", "HIGH", "BLOCKED")],
                         ["allow", "pin", "deny", "deny"])
        self.assertEqual(guardian.open_policy(lock, "WARN"), "deny")
        self.assertEqual(guardian.open_policy(pin, "LA"), "deny")
        self.assertEqual(guardian.open_policy({"guardian_enabled": True}, "WARN"), "deny")


if __name__ == "__main__":
    unittest.main()
