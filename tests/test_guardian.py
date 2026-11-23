"""Kiểm thử ``tools/guardian.py``: mã khớp vector chung với JS, ký/xác minh chính sách, .reg, thư mục ngoài repo, chấm lại tên miền."""
from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac as hmac_module
import io
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import gen_extension_key  # noqa: E402
import guardian  # noqa: E402

VECTORS = json.loads((ROOT / "tests" / "data" / "guardian_vectors.json").read_text("utf-8"))
SECRET = guardian.b64u_decode(VECTORS["hmac_secret"])


class CodeTests(unittest.TestCase):
    """Mã mở khóa và các hàm chuẩn hóa."""

    def test_vectors_match_shared_file(self) -> None:
        for case in VECTORS["codes"]:
            with self.subTest(case["message"]):
                self.assertEqual(guardian.challenge_message(case["domain"], case["nonce"]), case["message"])
                self.assertEqual(guardian.compute_code(SECRET, case["domain"], case["nonce"]), case["code"])

    def test_hotp_truncation_matches_rfc4226_algorithm(self) -> None:
        """Cắt bớt đúng RFC 4226 §5.3: 31 bit từ offset = nibble thấp của byte cuối."""
        message = guardian.challenge_message("example.com", "AAAAAAAAAAAA").encode()
        mac = hmac_module.new(SECRET, message, hashlib.sha256).digest()
        offset = mac[-1] & 0xF
        expected = ((mac[offset] & 0x7F) << 24 | mac[offset + 1] << 16 | mac[offset + 2] << 8 | mac[offset + 3]) % 10**6
        self.assertEqual(guardian.compute_code(SECRET, "example.com", "AAAAAAAAAAAA"), f"{expected:06d}")

    def test_code_depends_on_domain_nonce_and_secret(self) -> None:
        base = guardian.compute_code(SECRET, "a.com", "AAAAAAAAAAAA")
        self.assertNotEqual(base, guardian.compute_code(SECRET, "b.com", "AAAAAAAAAAAA"))
        self.assertNotEqual(base, guardian.compute_code(SECRET, "a.com", "AAAAAAAB"))
        self.assertNotEqual(base, guardian.compute_code(bytes(32), "a.com", "AAAAAAAAAAAA"))
        self.assertRegex(base, r"^\d{6}$")

    def test_normalize(self) -> None:
        self.assertEqual(guardian.normalize_domain(" Example.COM. "), "example.com")
        self.assertTrue(guardian.normalize_domain("vietcombánk.com").startswith("xn--"))
        self.assertEqual(guardian.normalize_domain("my_host.example.com"), "my_host.example.com")
        self.assertEqual(guardian.normalize_nonce("k7qf-3mzd-x9hp"), "K7QF3MZDX9HP")
        for bad in ("", "a|b.com", "exa mple.com"):
            with self.assertRaises(guardian.GuardianError):
                guardian.normalize_domain(bad)
        for bad in ("K7QF-3MZD", "K7QF-3MZD-X9H1", "K7QF-3MZD-X9HO", "!!!!!!!!!!!!"):
            with self.assertRaises(guardian.GuardianError):
                guardian.normalize_nonce(bad)

    def test_parse_challenge_accepts_qr_payload(self) -> None:
        self.assertEqual(guardian.parse_challenge("CHOTTO-GUARDIAN-v1|Example.com|k7qf-3mzd-x9hp", None), ("example.com", "K7QF3MZDX9HP"))
        self.assertEqual(guardian.parse_challenge("example.com", "K7QF-3MZD-X9HP"), ("example.com", "K7QF3MZDX9HP"))
        with self.assertRaises(guardian.GuardianError):
            guardian.parse_challenge("example.com", None)
        with self.assertRaises(guardian.GuardianError):
            guardian.parse_challenge("OTHER|example.com|K7QF3MZDX9HP", None)

    def test_nonce_alphabet_is_unambiguous_and_strong(self) -> None:
        self.assertEqual(guardian.NONCE_ALPHABET, VECTORS["nonce_alphabet"])
        for bad in "ILO01":
            self.assertNotIn(bad, guardian.NONCE_ALPHABET)
        self.assertEqual(len(set(guardian.NONCE_ALPHABET)), len(guardian.NONCE_ALPHABET))
        self.assertGreaterEqual(guardian.NONCE_LENGTH * math.log2(len(guardian.NONCE_ALPHABET)), 40)
        self.assertEqual(guardian.format_nonce("K7QF3MZDX9HP"), "K7QF-3MZD-X9HP")

    def test_nonce_stream_vectors(self) -> None:
        for item in VECTORS["nonce_streams"]:
            self.assertEqual(guardian.nonce_from_bytes(bytes.fromhex(item["hex"])), item["nonce"], item["hex"])

    def test_name_and_page_url_vectors(self) -> None:
        for item in VECTORS["names"]:
            self.assertEqual(guardian.sanitize_name(item["input"]), item["expected"], repr(item["input"]))
        for item in VECTORS["page_urls"]:
            self.assertEqual(guardian.sanitize_page_url(item["input"]), item["expected"], repr(item["input"]))
        for item in VECTORS["share_links"]:
            self.assertEqual(guardian.build_share_link(item["page"], item["domain"], item["nonce"]), item["link"])

    def test_parse_challenge_accepts_share_link(self) -> None:
        link = guardian.build_share_link("https://example.github.io/CHOTTO/guardian/", "vietcombank-xacthuc.top", "K7QF3MZDX9HP")
        self.assertEqual(guardian.parse_challenge(link, None), ("vietcombank-xacthuc.top", "K7QF3MZDX9HP"))
        self.assertEqual(guardian.parse_challenge(f"  {link}\n", None), ("vietcombank-xacthuc.top", "K7QF3MZDX9HP"))
        with self.assertRaises(guardian.GuardianError):
            guardian.parse_challenge(link.replace("#v=1", "#v=9"), None)

    def test_reg_has_optional_name_and_page_url(self) -> None:
        extension_id = "a" * 32
        plain = guardian.make_reg_files("chrome", extension_id, "PUB", "SEC", 0)["policy"]
        self.assertNotIn("guardian_name", plain)
        self.assertNotIn("guardian_page_url", plain)
        named = guardian.make_reg_files("chrome", extension_id, "PUB", "SEC", 0, name="  Bà\u202e  Lan ",
                                        page_url="https://example.github.io/CHOTTO/guardian/")["policy"]
        self.assertIn('"guardian_name"="Bà Lan"', named)
        self.assertIn('"guardian_page_url"="https://example.github.io/CHOTTO/guardian/"', named)
        self.assertNotIn("\u202e", named)
        with self.assertRaises(guardian.GuardianError):
            guardian.make_reg_files("chrome", extension_id, "PUB", "SEC", 0, page_url="http://example.com/g/")

    def test_export_guardian_setup_string_and_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "g"
            keys = guardian.init_keys(directory)
            self.assertEqual(guardian.setup_string(keys), "CHOTTO-GUARDIAN-SETUP-v1:" + keys["hmac_secret"])
            page = guardian.make_setup_html(directory, "https://example.github.io/CHOTTO/guardian/", Path(tmp) / "setup.html")
            text = page.read_text("utf-8")
            self.assertIn(keys["hmac_secret"], text)
            self.assertIn("qrcode", text)
            with self.assertRaises(guardian.GuardianError):
                guardian.make_setup_html(directory, "http://example.com/", Path(tmp) / "bad.html")
            with self.assertRaises(guardian.GuardianError):
                guardian.make_setup_html(directory, "https://example.com/", ROOT / "setup-test.html")


class PolicyTests(unittest.TestCase):
    """Khóa, ký và xác minh chính sách."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "g"
        self.keys = guardian.init_keys(self.dir)

    def test_init_creates_keys_and_refuses_overwrite(self) -> None:
        self.assertEqual(len(guardian.b64u_decode(self.keys["ed25519_public"])), 32)
        self.assertGreaterEqual(len(guardian.b64u_decode(self.keys["hmac_secret"])), 32)
        self.assertEqual(guardian.load_keys(self.dir), self.keys)
        with self.assertRaises(guardian.GuardianError):
            guardian.init_keys(self.dir)
        self.assertNotEqual(guardian.init_keys(self.dir, force=True)["hmac_secret"], self.keys["hmac_secret"])

    def test_refuses_directory_inside_repo(self) -> None:
        with self.assertRaises(guardian.GuardianError):
            guardian.init_keys(ROOT / "tools" / "_guardian_test")
        self.assertFalse((ROOT / "tools" / "_guardian_test").exists())
        with self.assertRaises(guardian.GuardianError):
            guardian.make_html(self.dir, ROOT / "guardian-app.html")

    def test_load_keys_missing_and_corrupt(self) -> None:
        with self.assertRaises(guardian.GuardianError):
            guardian.load_keys(self.dir / "nope")
        (self.dir / "keys.json").write_text("{không phải json", "utf-8")
        with self.assertRaises(guardian.GuardianError):
            guardian.load_keys(self.dir)

    def test_vector_signature_verifies(self) -> None:
        policy = VECTORS["policy"]
        envelope = {"payload": policy["payload"], "signature": policy["signature"]}
        self.assertEqual(guardian.verify_envelope(policy["public_key"], envelope)["version"], 7)

    def test_sign_policy_bumps_version_and_verifies(self) -> None:
        policy = Path(self._tmp.name) / "policy.json"
        policy.write_text(json.dumps({"allow_domains": ["Vietcombank.com.vn"], "require_levels": ["WARN", "HIGH"]}), "utf-8")
        first, v1 = guardian.sign_policy(self.dir, policy, Path(self._tmp.name) / "v1.signed.json")
        second, v2 = guardian.sign_policy(self.dir, policy)
        self.assertEqual((v1, v2), (1, 2))
        envelope = json.loads(second.read_text("utf-8"))
        data = guardian.verify_envelope(self.keys["ed25519_public"], envelope, min_version=2)
        self.assertEqual(data["allow_domains"], ["vietcombank.com.vn"])
        self.assertEqual(data["require_levels"], ["WARN", "HIGH", "BLOCKED"])
        self.assertEqual(guardian.load_keys(self.dir)["policy_version"], 2)
        with self.assertRaises(guardian.GuardianError):          # version thấp hơn mức tối thiểu
            guardian.verify_envelope(self.keys["ed25519_public"], json.loads(first.read_text("utf-8")), min_version=2)

    def test_tampered_or_foreign_signature_is_rejected(self) -> None:
        payload = guardian.build_policy_payload({}, 1)
        signature = guardian.sign_payload(self.keys["ed25519_private"], payload)
        good = {"payload": payload, "signature": signature}
        guardian.verify_envelope(self.keys["ed25519_public"], good)
        for bad in ({"payload": payload.replace('"version":1', '"version":9'), "signature": signature},
                    {"payload": payload, "signature": signature[:-3] + "AAA"},
                    {"payload": payload}, {"payload": 5, "signature": "x"}):
            with self.assertRaises(guardian.GuardianError):
                guardian.verify_envelope(self.keys["ed25519_public"], bad)
        other = guardian.init_keys(Path(self._tmp.name) / "other")
        with self.assertRaises(guardian.GuardianError):
            guardian.verify_envelope(other["ed25519_public"], good)

    def test_policy_validation(self) -> None:
        for fields in ({"require_levels": []}, {"require_levels": ["TUY_Y"]}, {"challenge_ttl_sec": 5},
                       {"challenge_ttl_sec": True}, {"allow_domains": [5]}, {"lạ": 1}):
            with self.subTest(fields), self.assertRaises(guardian.GuardianError):
                guardian.build_policy_payload(fields, 1)
        data = json.loads(guardian.build_policy_payload({"require_levels": ["WARN"]}, 3))
        self.assertEqual((data["version"], data["require_levels"], data["challenge_ttl_sec"]), (3, ["WARN", "BLOCKED"], 600))

    def test_make_html_embeds_secret_outside_repo(self) -> None:
        text = guardian.make_html(self.dir).read_text("utf-8")
        self.assertIn(self.keys["hmac_secret"], text)
        self.assertNotIn(self.keys["hmac_secret"], (ROOT / "tools" / "guardian.html").read_text("utf-8"))
        self.assertNotRegex(text, r"(src|href)=\"https?://")   # không tải tài nguyên ngoài


class RegTests(unittest.TestCase):
    """Xuất .reg (chỉ tạo file)."""

    EXT = "a" * 32

    def test_chrome_and_edge_paths_and_values(self) -> None:
        for browser, hive in (("chrome", r"SOFTWARE\Policies\Google\Chrome"), ("edge", r"SOFTWARE\Policies\Microsoft\Edge")):
            files = guardian.make_reg_files(browser, self.EXT, "PUBKEY", "SECRET", 5)
            policy = files["policy"]
            self.assertIn(rf"[HKEY_LOCAL_MACHINE\{hive}\3rdparty\extensions\{self.EXT}\policy]", policy)
            self.assertIn('"guardian_enabled"=dword:00000001', policy)
            self.assertIn('"guardian_public_key"="PUBKEY"', policy)
            self.assertIn('"guardian_secret"="SECRET"', policy)
            self.assertIn('"min_policy_version"=dword:00000005', policy)
            self.assertTrue(policy.startswith("Windows Registry Editor Version 5.00\r\n"))
            self.assertIn(rf"[-HKEY_LOCAL_MACHINE\{hive}\3rdparty\extensions\{self.EXT}]", files["remove"])
            self.assertNotIn("SECRET", files["remove"])
            self.assertNotIn("SECRET", files["hardening"])
            self.assertIn("DeveloperToolsAvailability", files["hardening"])
            self.assertIn('; "ExtensionDeveloperModeSettings"', files["hardening"])   # dòng nguy hiểm để dạng chú thích
        self.assertIn('"InPrivateModeAvailability"=dword:00000001', guardian.make_reg_files("edge", self.EXT, "p", "s", 1)["hardening"])
        self.assertIn('"IncognitoModeAvailability"=dword:00000001', guardian.make_reg_files("chrome", self.EXT, "p", "s", 1)["hardening"])

    def test_rejects_bad_input_and_escapes(self) -> None:
        with self.assertRaises(guardian.GuardianError):
            guardian.make_reg_files("firefox", self.EXT, "p", "s", 1)
        with self.assertRaises(guardian.GuardianError):
            guardian.make_reg_files("chrome", "ABC", "p", "s", 1)
        self.assertEqual(guardian._reg_string('a"b\\c'), '"a\\"b\\\\c"')

    def test_write_reg_is_utf16_with_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.reg"
            guardian.write_reg(path, "Windows Registry Editor Version 5.00\r\n; tiếng Việt\r\n")
            raw = path.read_bytes()
            self.assertEqual(raw[:2], b"\xff\xfe")
            self.assertIn("tiếng Việt", raw.decode("utf-16"))

    def test_manifest_extension_id_is_pinned_and_stable(self) -> None:
        ext = guardian.manifest_extension_id()
        self.assertRegex(ext, r"^[a-p]{32}$")
        key = json.loads((ROOT / "platforms" / "extension" / "manifest.json").read_text("utf-8"))["key"]
        self.assertEqual(gen_extension_key.extension_id_from_key(key), ext)

    def test_cli_make_reg_writes_three_files_without_touching_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "g"
            guardian.init_keys(directory)
            with contextlib.redirect_stdout(io.StringIO()), mock.patch("subprocess.run") as run:
                run.return_value.returncode = 0
                self.assertEqual(guardian.main(["--dir", str(directory), "make-reg", "--browser", "chrome"]), 0)
            for name in ("chotto-guardian-chrome.reg", "chotto-guardian-chrome-remove.reg", "chotto-guardian-chrome-hardening.reg"):
                self.assertTrue((directory / name).exists(), name)
            for call in run.call_args_list:        # chỉ icacls (đổi quyền file), không bao giờ reg/regedit
                self.assertEqual(call.args[0][0], "icacls")


@unittest.skipIf(os.environ.get("CHOTTO_SKIP_ENGINE"), "bỏ qua chấm lại bằng engine")
class AssessTests(unittest.TestCase):
    """Chấm lại tên miền bằng engine và lệnh ``code``."""

    def test_assess_flags_phishing_domain(self) -> None:
        self.assertIn(guardian.assess_domain("vietcombank-xacthuc.top")["level"], ("HIGH", "BLOCKED"))
        self.assertEqual(guardian.assess_domain("vietcombank.com.vn")["level"], "SAFE")

    def test_code_command_prints_banner_and_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "g"
            keys = guardian.init_keys(directory)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(guardian.code_command(directory, "vietcombank-xacthuc.top", "k7qf-3mzd-x9hp", assume_yes=True), 0)
            text = out.getvalue()
            self.assertIn("VIETCOMBANK-XACTHUC.TOP", text)
            self.assertIn("HIGH", text)
            expected = guardian.compute_code(guardian.b64u_decode(keys["hmac_secret"]), "vietcombank-xacthuc.top", "K7QF3MZDX9HP")
            self.assertIn(guardian.format_code(expected), text)

    def test_code_command_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "g"
            guardian.init_keys(directory)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), mock.patch("sys.stdin.isatty", return_value=True), \
                    mock.patch("builtins.input", return_value="sai-ten-mien.com"):
                self.assertEqual(guardian.code_command(directory, "momo-hoantien.vip", "K7QF3MZDX9HP", assume_yes=False), 1)
            self.assertNotIn("MÃ MỞ KHÓA", out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()), mock.patch("sys.stdin.isatty", return_value=False),                     self.assertRaises(guardian.GuardianError):
                guardian.code_command(directory, "momo-hoantien.vip", "K7QF3MZDX9HP", assume_yes=False)


if __name__ == "__main__":
    unittest.main()
