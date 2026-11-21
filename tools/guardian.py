#!/usr/bin/env python3
"""Công cụ của NGƯỜI GIÁM HỘ cho Guardian mode của tiện ích CHOTTO (xem ``docs/GUARDIAN-MODE.md``).

Mọi thứ chạy offline. Khóa và bí mật nằm trong thư mục người giám hộ NGOÀI repo (mặc định
``%APPDATA%\\CHOTTO-Guardian`` trên Windows, ``~/.chotto-guardian`` nơi khác; đổi bằng ``--dir`` hoặc biến môi trường
``CHOTTO_GUARDIAN_DIR``). Công cụ từ chối ghi vào bên trong repo để không lỡ commit secret.

Lệnh:
  init                      sinh khóa Ed25519 + bí mật HMAC
  sign-policy policy.json   ký chính sách, tự tăng version
  make-reg --browser chrome|edge   xuất file .reg (managed storage), file gỡ bỏ và file làm cứng (CHỈ TẠO, không áp dụng)
  code <tên miền> <nonce>   chấm lại tên miền bằng engine, cảnh báo, rồi in mã 6 số
  make-html                 tạo trang guardian.html (nhúng bí mật) để dùng offline trên điện thoại

Chỉ ``init``/``sign-policy`` cần gói ``cryptography`` (Ed25519); mã mở khóa và .reg chỉ dùng thư viện chuẩn.
Không tự viết thuật toán mật mã: HMAC-SHA256/SHA-256 từ ``hmac``/``hashlib``, Ed25519 từ ``cryptography``.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
EXTENSION_MANIFEST: Final[Path] = ROOT / "extension" / "manifest.json"
HTML_TEMPLATE: Final[Path] = Path(__file__).resolve().parent / "guardian.html"

CODE_CONTEXT: Final[str] = "CHOTTO-GUARDIAN-v1"
POLICY_CONTEXT: Final[bytes] = b"CHOTTO-GUARDIAN-POLICY-v1\n"
CODE_DIGITS: Final[int] = 6
LEVELS: Final[tuple[str, ...]] = ("WARN", "HIGH", "BLOCKED")
KEYS_FILE: Final[str] = "keys.json"

BROWSERS: Final[dict[str, str]] = {
    "chrome": r"SOFTWARE\Policies\Google\Chrome",
    "edge": r"SOFTWARE\Policies\Microsoft\Edge",
}


class GuardianError(Exception):
    """Lỗi người dùng có thể sửa được (thông điệp tiếng Việt, in ra rồi thoát mã 2)."""


# ---------------------------------------------------------------- mã hóa cơ bản


def b64u(data: bytes) -> str:
    """Base64url không đệm."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64u_decode(text: str) -> bytes:
    """Giải base64url (có hoặc không đệm).

    Raises:
        GuardianError: Không phải base64 hợp lệ.
    """
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError) as exc:
        raise GuardianError("Chuỗi base64 không hợp lệ.") from exc


def normalize_domain(text: str) -> str:
    """Tên miền chuẩn: chữ thường, không dấu chấm cuối, dạng ASCII/punycode (giống ``codec.js``).

    Raises:
        GuardianError: Tên miền rỗng hoặc không hợp lệ.
    """
    clean = text.strip().lower().rstrip(".")
    if not clean:
        raise GuardianError("Thiếu tên miền.")
    if not clean.isascii():
        try:
            clean = clean.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise GuardianError(f"Tên miền không hợp lệ: {text!r}") from exc
    if not re.fullmatch(r"[a-z0-9.\-:\[\]]{1,253}", clean) or "|" in clean:
        raise GuardianError(f"Tên miền không hợp lệ: {text!r}")
    return clean


def normalize_nonce(text: str) -> str:
    """Nonce chuẩn: bỏ gạch/khoảng trắng, chữ hoa, đúng 8 ký tự base32.

    Raises:
        GuardianError: Sai dạng.
    """
    clean = re.sub(r"[\s-]", "", text).upper()
    if not re.fullmatch(r"[A-Z2-7]{8}", clean):
        raise GuardianError(f"Mã thử thách không hợp lệ: {text!r} (cần 8 ký tự, ví dụ K7QF-3MZD).")
    return clean


def challenge_message(domain: str, nonce: str) -> str:
    """Thông điệp HMAC (cũng là nội dung mã QR): ``CHOTTO-GUARDIAN-v1|<tên miền>|<nonce>``."""
    return f"{CODE_CONTEXT}|{domain}|{nonce}"


def compute_code(secret: bytes, domain: str, nonce: str) -> str:
    """Mã mở khóa 6 số: HMAC-SHA256 rồi cắt bớt kiểu HOTP (RFC 4226 §5.3)."""
    mac = hmac.new(secret, challenge_message(domain, nonce).encode("utf-8"), hashlib.sha256).digest()
    offset = mac[-1] & 0x0F
    binary = int.from_bytes(mac[offset:offset + 4], "big") & 0x7FFFFFFF
    return str(binary % 10 ** CODE_DIGITS).zfill(CODE_DIGITS)


def parse_challenge(first: str, second: str | None) -> tuple[str, str]:
    """Nhận ``<tên miền> <nonce>`` hoặc chuỗi dán nguyên từ QR ``CHOTTO-GUARDIAN-v1|<tên miền>|<nonce>``.

    Raises:
        GuardianError: Sai dạng.
    """
    if second is None:
        parts = first.strip().split("|")
        if len(parts) != 3 or parts[0] != CODE_CONTEXT:
            raise GuardianError("Hãy nhập: code <tên miền> <mã thử thách>, hoặc dán nguyên nội dung mã QR.")
        return normalize_domain(parts[1]), normalize_nonce(parts[2])
    return normalize_domain(first), normalize_nonce(second)


def extension_id_from_key(key_b64: str) -> str:
    """ID tiện ích (32 ký tự a-p) từ trường ``key`` của manifest (giống Chrome)."""
    digest = hashlib.sha256(base64.b64decode(key_b64, validate=True)).hexdigest()[:32]
    return "".join(chr(ord("a") + int(ch, 16)) for ch in digest)


def manifest_extension_id() -> str:
    """ID tiện ích đã ghim trong ``extension/manifest.json``.

    Raises:
        GuardianError: Manifest chưa có ``key`` (chạy ``tools/gen_extension_key.py``).
    """
    try:
        key = json.loads(EXTENSION_MANIFEST.read_text("utf-8")).get("key")
    except (OSError, ValueError) as exc:
        raise GuardianError(f"Không đọc được manifest: {exc}") from exc
    if not key:
        raise GuardianError("Manifest chưa ghim ID: chạy python tools/gen_extension_key.py")
    return extension_id_from_key(key)


# ---------------------------------------------------------------- thư mục & khóa


def default_dir() -> Path:
    """Thư mục người giám hộ mặc định (ngoài repo)."""
    env = os.environ.get("CHOTTO_GUARDIAN_DIR")
    if env:
        return Path(env)
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "CHOTTO-Guardian"
    return Path.home() / ".chotto-guardian"


def ensure_outside_repo(path: Path) -> Path:
    """Từ chối đường dẫn nằm trong repo (tránh commit nhầm khóa/secret).

    Raises:
        GuardianError: Nằm trong repo.
    """
    resolved = path.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise GuardianError(f"Từ chối ghi vào trong repo ({resolved}). Hãy dùng thư mục ngoài repo bằng --dir.")
    return resolved


def restrict_permissions(path: Path) -> bool:
    """Giới hạn quyền chỉ chủ sở hữu (chmod trên POSIX, icacls trên Windows). ``False`` nếu không làm được."""
    try:
        if os.name == "posix":
            path.chmod(0o700 if path.is_dir() else 0o600)
            return True
        user = os.environ.get("USERNAME")
        if not user:
            return False
        grant = f"{user}:(OI)(CI)F" if path.is_dir() else f"{user}:F"
        done = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", grant],
                              capture_output=True, check=False, timeout=30)
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _write_private(path: Path, text: str) -> None:
    path.write_text(text, "utf-8")
    restrict_permissions(path)


def load_keys(directory: Path) -> dict[str, Any]:
    """Đọc ``keys.json``.

    Raises:
        GuardianError: Chưa ``init`` hoặc file hỏng.
    """
    try:
        data = json.loads((directory / KEYS_FILE).read_text("utf-8"))
        for field in ("ed25519_private", "ed25519_public", "hmac_secret", "policy_version"):
            if field not in data:
                raise ValueError(f"thiếu {field}")
        return dict(data)
    except FileNotFoundError as exc:
        raise GuardianError(f"Chưa có khóa trong {directory}. Chạy: python tools/guardian.py init") from exc
    except (OSError, ValueError) as exc:
        raise GuardianError(f"{directory / KEYS_FILE} hỏng: {exc}") from exc


def init_keys(directory: Path, *, force: bool = False) -> dict[str, Any]:
    """Sinh khóa Ed25519 + bí mật HMAC 32 byte và lưu vào ``directory``.

    Raises:
        GuardianError: Đã có khóa (không ``force``) hoặc thư mục nằm trong repo.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    directory = ensure_outside_repo(directory)
    target = directory / KEYS_FILE
    if target.exists() and not force:
        raise GuardianError(f"{target} đã tồn tại (dùng --force để ghi đè: mọi máy đã cài .reg cũ sẽ mất hiệu lực).")
    directory.mkdir(parents=True, exist_ok=True)
    restrict_permissions(directory)
    private = Ed25519PrivateKey.generate()
    raw_private = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                        serialization.NoEncryption())
    raw_public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    keys = {
        "about": "BÍ MẬT của người giám hộ. Không chia sẻ, không đưa vào repo.",
        "ed25519_private": b64u(raw_private),
        "ed25519_public": b64u(raw_public),
        "hmac_secret": b64u(secrets.token_bytes(32)),
        "policy_version": 0,
    }
    _write_private(target, json.dumps(keys, indent=2) + "\n")
    return keys


# ---------------------------------------------------------------- chính sách ký


def build_policy_payload(fields: dict[str, Any], version: int) -> str:
    """Chuỗi JSON chính sách (khóa sắp xếp, gọn) — đúng chuỗi này được ký và được tiện ích xác minh.

    Raises:
        GuardianError: Trường sai kiểu hoặc ngoài miền giá trị (cùng luật với ``parsePolicyPayload`` của JS).
    """
    allowed = {"allow_domains", "require_levels", "challenge_ttl_sec", "version", "issued_at"}
    unknown = set(fields) - allowed
    if unknown:
        raise GuardianError(f"Trường lạ trong policy: {', '.join(sorted(unknown))}")
    payload: dict[str, Any] = {"version": version, "issued_at": int(time.time())}
    levels = fields.get("require_levels", ["HIGH", "BLOCKED"])
    if not isinstance(levels, list) or not levels or any(item not in LEVELS for item in levels):
        raise GuardianError(f"require_levels phải là danh sách không rỗng gồm {LEVELS}.")
    payload["require_levels"] = sorted(set(levels) | {"BLOCKED"}, key=LEVELS.index)
    allow = fields.get("allow_domains", [])
    if not isinstance(allow, list) or len(allow) > 500 or any(not isinstance(item, str) for item in allow):
        raise GuardianError("allow_domains phải là danh sách chuỗi (tối đa 500).")
    payload["allow_domains"] = sorted({normalize_domain(item) for item in allow})
    ttl = fields.get("challenge_ttl_sec", 600)
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 60 <= ttl <= 3600:
        raise GuardianError("challenge_ttl_sec phải là số nguyên 60..3600.")
    payload["challenge_ttl_sec"] = ttl
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign_payload(private_b64: str, payload: str) -> str:
    """Chữ ký Ed25519 (base64url) lên ``POLICY_CONTEXT + payload``."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.from_private_bytes(b64u_decode(private_b64))
    return b64u(key.sign(POLICY_CONTEXT + payload.encode("utf-8")))


def verify_envelope(public_b64: str, envelope: dict[str, Any], min_version: int = 0) -> dict[str, Any]:
    """Xác minh phong bì ``{payload, signature}`` như tiện ích sẽ làm; trả payload đã giải.

    Raises:
        GuardianError: Sai chữ ký, sai cấu trúc hoặc version thấp hơn ``min_version``.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    payload, signature = envelope.get("payload"), envelope.get("signature")
    if not isinstance(payload, str) or not isinstance(signature, str):
        raise GuardianError("Phong bì thiếu payload/signature.")
    try:
        Ed25519PublicKey.from_public_bytes(b64u_decode(public_b64)).verify(
            b64u_decode(signature), POLICY_CONTEXT + payload.encode("utf-8"))
    except (InvalidSignature, ValueError) as exc:
        raise GuardianError("Chữ ký không hợp lệ.") from exc
    data = json.loads(payload)
    if int(data.get("version", 0)) < min_version:
        raise GuardianError(f"Version {data.get('version')} thấp hơn mức tối thiểu {min_version}.")
    return dict(data)


def sign_policy(directory: Path, policy_file: Path, out: Path | None = None) -> tuple[Path, int]:
    """Ký ``policy_file``, tăng version và lưu phong bì cạnh file (hoặc ``out``).

    Raises:
        GuardianError: Chưa init, policy hỏng.
    """
    keys = load_keys(directory)
    try:
        fields = json.loads(policy_file.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise GuardianError(f"Không đọc được {policy_file}: {exc}") from exc
    if not isinstance(fields, dict):
        raise GuardianError("policy.json phải là một đối tượng JSON.")
    version = int(keys["policy_version"]) + 1
    payload = build_policy_payload(fields, version)
    envelope = {"payload": payload, "signature": sign_payload(keys["ed25519_private"], payload)}
    target = out or policy_file.with_suffix(".signed.json")
    target.write_text(json.dumps(envelope, indent=2) + "\n", "utf-8")
    keys["policy_version"] = version
    _write_private(directory / KEYS_FILE, json.dumps(keys, indent=2) + "\n")
    return target, version


# ---------------------------------------------------------------- .reg


def _reg_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def make_reg_files(browser: str, extension_id: str, public_b64: str, secret_b64: str,
                   min_policy_version: int) -> dict[str, str]:
    """Nội dung ba file .reg: ``policy`` (bật Guardian), ``remove`` (gỡ), ``hardening`` (làm cứng, tách riêng).

    Raises:
        GuardianError: Trình duyệt hoặc ID không hợp lệ.
    """
    if browser not in BROWSERS:
        raise GuardianError(f"Trình duyệt phải là một trong {sorted(BROWSERS)}.")
    if not re.fullmatch(r"[a-p]{32}", extension_id):
        raise GuardianError(f"ID tiện ích không hợp lệ: {extension_id!r}")
    base = BROWSERS[browser]
    extension_key = rf"HKEY_LOCAL_MACHINE\{base}\3rdparty\extensions\{extension_id}"
    policy_key = extension_key + r"\policy"
    browser_key = rf"HKEY_LOCAL_MACHINE\{base}"
    head = "Windows Registry Editor Version 5.00\r\n"
    policy = (
        f"{head}\r\n"
        "; CHOTTO Guardian mode: chính sách quản lý cho tiện ích. CHỨA BÍ MẬT HMAC: không chia sẻ, không đưa vào repo.\r\n"
        "; Chạy bằng tài khoản Administrator (chuột phải > Merge). Gỡ bằng file -remove.reg.\r\n"
        "; Sau đó mở chrome://policy (hoặc edge://policy), bấm 'Reload policies' và kiểm tra các giá trị hiện ra.\r\n"
        f"[{policy_key}]\r\n"
        '"guardian_enabled"=dword:00000001\r\n'
        f'"guardian_public_key"={_reg_string(public_b64)}\r\n'
        f'"guardian_secret"={_reg_string(secret_b64)}\r\n'
        f'"min_policy_version"=dword:{min_policy_version:08x}\r\n'
    )
    hardening_names = ["IncognitoModeAvailability", "DeveloperToolsAvailability"]
    if browser == "edge":
        hardening_names = ["InPrivateModeAvailability", "DeveloperToolsAvailability"]
    verified = {
        "chrome": "IncognitoModeAvailability=1: trang trợ giúp của Google nói đặt 1 sẽ tắt chế độ ẩn danh. "
                  "DeveloperToolsAvailability và ExtensionDeveloperModeSettings: CHƯA KIỂM CHỨNG với tài liệu chính thức của Chrome.",
        "edge": "InPrivateModeAvailability=1 (tắt InPrivate), DeveloperToolsAvailability=2 (không cho dùng DevTools) và "
                "ExtensionDeveloperModeSettings=1 (cấm chế độ nhà phát triển, Edge >= 128): khớp tài liệu Microsoft Learn.",
    }[browser]
    hardening = (
        f"{head}\r\n"
        "; CHOTTO Guardian: policy LÀM CỨNG gợi ý. Áp dụng SAU khi đã nạp tiện ích, và KHÔNG dùng cho demo 'load unpacked':\r\n"
        ";   - DeveloperToolsAvailability=2 tắt hẳn DevTools (kể cả để bạn gỡ lỗi).\r\n"
        ";   - ExtensionDeveloperModeSettings=1 cấm chế độ nhà phát triển => không 'Load unpacked' được nữa, và tiện ích unpacked\r\n"
        ";     CÓ THỂ bị tắt (chưa kiểm chứng) => dòng này để dạng chú thích; chỉ bật khi tiện ích được cài bằng chính sách.\r\n"
        f"; Kiểm chứng: {verified}\r\n"
        f"[{browser_key}]\r\n"
        f'"{hardening_names[0]}"=dword:00000001\r\n'
        f'"{hardening_names[1]}"=dword:00000002\r\n'
        '; "ExtensionDeveloperModeSettings"=dword:00000001\r\n'
    )
    remove = (
        f"{head}\r\n"
        "; Gỡ chính sách Guardian của CHOTTO (xóa cả khóa chính sách tiện ích lẫn các giá trị làm cứng ở trên).\r\n"
        "; Lưu ý: các giá trị làm cứng có thể do quản trị khác đặt; kiểm tra trước khi áp dụng.\r\n"
        f"[-{extension_key}]\r\n\r\n"
        f"[{browser_key}]\r\n"
        f'"{hardening_names[0]}"=-\r\n'
        f'"{hardening_names[1]}"=-\r\n'
        '"ExtensionDeveloperModeSettings"=-\r\n'
    )
    return {"policy": policy, "remove": remove, "hardening": hardening}


def write_reg(path: Path, text: str) -> None:
    """Ghi file .reg dạng UTF-16 LE có BOM (định dạng regedit chuẩn), quyền chỉ chủ sở hữu."""
    path.write_bytes(text.encode("utf-16"))
    restrict_permissions(path)


# ---------------------------------------------------------------- chấm lại tên miền bằng engine


def assess_domain(domain: str) -> dict[str, Any]:
    """Chấm lại tên miền bằng engine Python của CHOTTO (Tầng 1 + 2, KHÔNG gọi mạng).

    Returns:
        ``{"level", "score", "reasons"}``.
    """
    with tempfile.TemporaryDirectory(prefix="chotto-guardian-") as data_dir:
        os.environ["CHOTTO_DATA_DIR"] = data_dir
        sys.path.insert(0, str(ROOT))
        from chotto.config import DEFAULTS, load_rules
        from chotto.engine import Engine

        engine = Engine(dict(DEFAULTS, tier3_enabled=False, ai_advice=True), rules=load_rules())
        try:
            result = engine.inspect(f"https://{domain}/")
        finally:
            engine.release()
    return {"level": str(result.level), "score": int(result.score), "reasons": list(result.reasons)}


def format_code(code: str) -> str:
    """``123456`` → ``123 456``."""
    return f"{code[:3]} {code[3:]}"


def render_banner(domain: str, assessment: dict[str, Any]) -> str:
    """Khối chữ lớn: tên miền sẽ được mở, mức rủi ro và nhắc phòng lừa."""
    bar = "=" * 64
    lines = [bar, "  NGƯỜI NHỜ BẠN ĐANG MUỐN MỞ TRANG:", "", f"      {domain.upper()}", ""]
    level = assessment["level"]
    if level in ("HIGH", "BLOCKED"):
        lines += [f"  !!! CHOTTO chấm trang này mức {level} (điểm {assessment['score']}/100) !!!"]
    else:
        lines += [f"  CHOTTO chấm trang này mức {level} (điểm {assessment['score']}/100)."]
    lines += [f"   - {reason}" for reason in assessment["reasons"][:4]]
    lines += [
        "",
        "  Trước khi đưa mã, hãy tự hỏi:",
        "   * Chính người thân của bạn đang bấm link này, và bạn gọi lại bằng số quen thuộc để hỏi chưa?",
        "   * Ai gọi điện/nhắn tin giục bạn đọc mã gấp đều có thể là kẻ lừa đảo.",
        bar,
    ]
    return "\n".join(lines)


def code_command(directory: Path, first: str, second: str | None, *, assume_yes: bool) -> int:
    """Lệnh ``code``: chấm lại, cảnh báo, xác nhận, in mã."""
    domain, nonce = parse_challenge(first, second)
    keys = load_keys(directory)
    assessment = assess_domain(domain)
    print(render_banner(domain, assessment))
    if not assume_yes:
        if not sys.stdin.isatty():
            raise GuardianError("Cần xác nhận tương tác (hoặc dùng --yes nếu bạn hiểu rủi ro).")
        typed = input("Gõ lại tên miền ở trên để xác nhận bạn muốn cấp mã (Enter để hủy): ").strip().lower()
        if typed != domain:
            print("Đã hủy, không cấp mã.")
            return 1
    secret = b64u_decode(keys["hmac_secret"])
    print(f"\n  MÃ MỞ KHÓA cho {domain} / {nonce[:4]}-{nonce[4:]}:   {format_code(compute_code(secret, domain, nonce))}\n"
          "  (Chỉ dùng được một lần, chỉ cho đúng liên kết này, hết hạn sau vài phút.)")
    return 0


# ---------------------------------------------------------------- trang HTML offline


def make_html(directory: Path, out: Path | None = None) -> Path:
    """Sinh ``guardian-app.html`` có nhúng bí mật HMAC (ngoài repo).

    Raises:
        GuardianError: Chưa init hoặc đích nằm trong repo.
    """
    keys = load_keys(directory)
    template = HTML_TEMPLATE.read_text("utf-8")
    marker = '"secret": ""'
    if marker not in template:
        raise GuardianError("guardian.html thiếu chỗ nhúng bí mật.")
    target = ensure_outside_repo(out or directory / "guardian-app.html")
    target.write_text(template.replace(marker, f'"secret": "{keys["hmac_secret"]}"', 1), "utf-8")
    restrict_permissions(target)
    return target


# ---------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    """Bộ phân tích dòng lệnh."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=None, help="thư mục người giám hộ (ngoài repo)")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="sinh khóa Ed25519 + bí mật HMAC")
    init.add_argument("--force", action="store_true")
    sign = sub.add_parser("sign-policy", help="ký chính sách, tăng version")
    sign.add_argument("policy", type=Path)
    sign.add_argument("--out", type=Path, default=None)
    reg = sub.add_parser("make-reg", help="xuất file .reg (chỉ tạo, không áp dụng)")
    reg.add_argument("--browser", choices=sorted(BROWSERS), required=True)
    reg.add_argument("--extension-id", default=None, help="mặc định: ID ghim trong extension/manifest.json")
    reg.add_argument("--min-policy-version", type=int, default=None, help="mặc định: version chính sách đã ký gần nhất")
    reg.add_argument("--out", type=Path, default=None)
    code = sub.add_parser("code", help="in mã mở khóa cho một thử thách")
    code.add_argument("domain", help="tên miền, hoặc nguyên nội dung mã QR")
    code.add_argument("nonce", nargs="?", default=None)
    code.add_argument("--yes", action="store_true", help="bỏ qua bước gõ lại tên miền để xác nhận")
    html = sub.add_parser("make-html", help="tạo guardian-app.html nhúng bí mật")
    html.add_argument("--out", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Điểm vào."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    directory: Path = args.dir or default_dir()
    try:
        if args.command == "init":
            keys = init_keys(directory, force=args.force)
            print(f"Đã tạo khóa trong {directory}\nKhóa công khai: {keys['ed25519_public']}\n"
                  "Sao lưu thư mục này ở nơi an toàn: mất nó là mất quyền cấp mã.")
        elif args.command == "sign-policy":
            target, version = sign_policy(directory, args.policy, args.out)
            print(f"Đã ký chính sách version {version}: {target}\n"
                  "Nhập file này ở trang Cài đặt của tiện ích (mục Guardian). "
                  "Để chống hạ cấp, chạy lại make-reg với --min-policy-version mới rồi Merge bằng Admin.")
        elif args.command == "make-reg":
            keys = load_keys(directory)
            out_dir = ensure_outside_repo(args.out or directory)
            out_dir.mkdir(parents=True, exist_ok=True)
            minimum = int(keys["policy_version"]) if args.min_policy_version is None else args.min_policy_version
            files = make_reg_files(args.browser, args.extension_id or manifest_extension_id(),
                                   keys["ed25519_public"], keys["hmac_secret"], minimum)
            names = {"policy": f"chotto-guardian-{args.browser}.reg", "remove": f"chotto-guardian-{args.browser}-remove.reg",
                     "hardening": f"chotto-guardian-{args.browser}-hardening.reg"}
            for kind, text in files.items():
                write_reg(out_dir / names[kind], text)
                print(f"Đã tạo {out_dir / names[kind]}")
            print("CHƯA áp dụng gì. Tự chạy file .reg bằng quyền Administrator (xem docs/GUARDIAN-MODE.md).")
        elif args.command == "code":
            return code_command(directory, args.domain, args.nonce, assume_yes=args.yes)
        elif args.command == "make-html":
            print(f"Đã tạo {make_html(directory, args.out)} (có chứa bí mật HMAC: chỉ chép sang thiết bị của bạn).")
    except GuardianError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
