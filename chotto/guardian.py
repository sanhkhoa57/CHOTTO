"""Guardian Mode (Bảo vệ Gia đình): mã PIN giám hộ, mã khôi phục offline và chính sách mở link.

Chỉ lưu **hash** (scrypt, muối ngẫu nhiên) trong ``data_dir()/guardian.bin``, không bao giờ lưu PIN hay mã khôi
phục dạng đọc được, và không ghi gì vào ``config.json``. Trên Windows cả file còn được mã hóa DPAPI; hệ điều hành
khác chỉ có hash với quyền ``0600``.

Mọi lỗi đều **đóng**: file mất, hỏng hay không giải mã được thì không PIN nào đúng.

Giới hạn cần biết: PIN chặn thao tác trong CHOTTO, không chặn được người có toàn quyền trên tài khoản máy tính
(sửa file cấu hình, xóa dữ liệu, đổi trình duyệt mặc định trong Cài đặt hệ điều hành).
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sys
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from .config import data_dir
from .platforms import dpapi

__all__ = ["LOCKOUT_S", "MAX_FAILURES", "RECOVERY_ALPHABET", "AuthResult", "GuardianError", "OpenPolicy", "PinRequired",
           "change_pin", "confirm", "has_pin", "is_corrupt", "lockout_remaining", "needs_pin", "normalize_recovery_key", "open_policy",
           "recover", "screen_info", "setup", "strictest", "valid_pin", "verify_pin"]

MAX_FAILURES: Final[int] = 5          # số lần sai liên tiếp (PIN và mã khôi phục đếm chung) thì khóa
LOCKOUT_S: Final[int] = 300
RECOVERY_ALPHABET: Final[str] = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"     # bỏ 0 O 1 I L
_FILE: Final[str] = "guardian.bin"
_PREFIX: Final[str] = "CHOTTO"
_GROUPS: Final[int] = 3
_GROUP_LEN: Final[int] = 4
_LOCK_WAIT_S: Final[float] = 10.0
_PIN_RE: Final[re.Pattern[str]] = re.compile(r"[0-9]{4,6}")
_SCRYPT: Final[dict[str, int]] = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
_THREAD_LOCK = threading.Lock()

OpenPolicy = Literal["allow", "pin", "deny"]
AuthError = Literal["", "wrong", "locked", "unavailable", "invalid_pin"]


class GuardianError(RuntimeError):
    """Thao tác không hợp lệ (đặt PIN khi đã có, PIN sai định dạng) hoặc không ghi được dữ liệu."""


class PinRequired(GuardianError):
    """Thao tác cần PIN giám hộ (Guardian Mode đang bật lúc thực hiện) mà người gọi chưa kiểm PIN."""


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Kết quả một lần xác thực.

    Attributes:
        ok: Đúng.
        error: ``wrong`` | ``locked`` | ``unavailable`` (không có/hỏng dữ liệu) | ``invalid_pin`` (PIN mới sai dạng).
        attempts_left: Số lần còn được thử trước khi bị khóa.
        locked_for: Số giây còn bị khóa (0 = không khóa).
        recovery_key: Mã khôi phục mới (sau ``change_pin``/``recover`` thành công; hiển thị một lần).
    """

    ok: bool
    error: AuthError = ""
    attempts_left: int = MAX_FAILURES
    locked_for: int = 0
    recovery_key: str = ""


def open_policy(cfg: Mapping[str, Any], level: str) -> OpenPolicy:
    """Người dùng được làm gì với một link ở mức ``level``: mở tự do, cần PIN, hay cấm hẳn.

    Mức lạ hoặc chính sách lạ đều bị coi là cấm khi Guardian Mode đang bật.
    """
    if not cfg.get("guardian_enabled"):
        return "allow"
    if level == "SAFE":
        return "allow"
    if level == "WARN" and cfg.get("guardian_warn_policy") == "pin":
        return "pin"
    return "deny"


def strictest(*policies: str) -> OpenPolicy:
    """Chính sách chặt nhất trong các chính sách (giá trị lạ coi là cấm)."""
    if all(p == "allow" for p in policies):
        return "allow"
    return "pin" if all(p in ("allow", "pin") for p in policies) else "deny"


def needs_pin(current: Mapping[str, Any], wanted: Mapping[str, Any]) -> bool:
    """Đổi cấu hình từ ``current`` sang ``wanted`` có phải nhập PIN không.

    Bật/tắt Guardian Mode luôn cần. Khi đang bật: mọi thay đổi làm yếu bảo vệ hoặc giấu hoạt động đều cần.
    """
    if bool(current.get("guardian_enabled")) != bool(wanted.get("guardian_enabled")):
        return True
    if not current.get("guardian_enabled"):
        return False
    if any(current.get(k) != wanted.get(k) for k in ("guardian_warn_policy", "guardian_contact")):
        return True
    if int(wanted.get("friction_seconds", 0)) < int(current.get("friction_seconds", 0)):
        return True
    if any(current.get(k) and not wanted.get(k) for k in ("agent_enabled", "log_decisions", "tier3_enabled")):
        return True
    return current.get("unknown_caller_policy") == "inspect" and wanted.get("unknown_caller_policy") != "inspect"


def screen_info(policy: OpenPolicy, contact: str, lang: str) -> dict[str, str]:
    """Phần Guardian của màn hình cảnh báo (dùng chung cho giao diện HTML và Tk)."""
    if lang == "vi":
        who, pin_label = contact or "người thân", "Nhập mã PIN giám hộ để mở"
        message = f"Đang bật Bảo vệ Gia đình. Nếu cần mở, hãy nhờ {who} kiểm tra giúp nhé!"
    else:
        who, pin_label = contact or "someone in your family", "Enter guardian PIN to open"
        message = f"Family Protection is on. If you need this link, ask {who} to check it for you!"
    return {"policy": policy, "message": message, "pinLabel": pin_label}


def valid_pin(pin: object) -> bool:
    """PIN hợp lệ: 4 đến 6 chữ số ASCII."""
    return isinstance(pin, str) and _PIN_RE.fullmatch(pin) is not None


def normalize_recovery_key(text: str) -> str:
    """Chuẩn hóa mã khôi phục người dùng gõ lại: bỏ dấu cách/gạch, viết hoa, bỏ tiền tố ``CHOTTO``."""
    compact = re.sub(r"[\s\-–—_]", "", str(text)).upper()
    return compact.removeprefix(_PREFIX)


def _new_recovery_key() -> str:
    groups = ("".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(_GROUP_LEN)) for _ in range(_GROUPS))
    return "-".join((_PREFIX, *groups))


def _hash(secret: str, salt: bytes) -> bytes:
    return hashlib.scrypt(secret.encode("utf-8"), salt=salt, **_SCRYPT)


def _record(secret: str) -> dict[str, str]:
    salt = secrets.token_bytes(16)
    return {"salt": salt.hex(), "hash": _hash(secret, salt).hex()}


def _matches(secret: str, record: Mapping[str, str]) -> bool:
    return hmac.compare_digest(_hash(secret, bytes.fromhex(record["salt"])), bytes.fromhex(record["hash"]))


def _path() -> Path:
    return data_dir() / _FILE


@contextlib.contextmanager
def _locked() -> Iterator[None]:
    """Khóa giữa các luồng và các tiến trình (agent và tiến trình giao diện cùng đếm số lần sai)."""
    with _THREAD_LOCK, open(data_dir() / (_FILE + ".lock"), "a+b") as handle:
        deadline = time.monotonic() + _LOCK_WAIT_S
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise GuardianError("Dữ liệu giám hộ đang bận") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _load() -> dict[str, Any] | None:
    """Dữ liệu đã giải mã và kiểm tra; ``None`` nếu không có hoặc hỏng."""
    try:
        raw = _path().read_bytes()
        if dpapi.available():
            raw = dpapi.unprotect(raw)
        data = json.loads(raw.decode("utf-8"))
        for name in ("pin", "recovery"):
            bytes.fromhex(data[name]["salt"])
            bytes.fromhex(data[name]["hash"])
        data["failures"] = int(data["failures"])
        data["locked_until"] = float(data["locked_until"])
        data["confirmed"] = data.get("confirmed") is True
        return dict(data)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _store(data: Mapping[str, Any]) -> None:
    raw = json.dumps(dict(data)).encode("utf-8")
    path = _path()
    temp = path.with_name(f"{_FILE}.{os.getpid()}.tmp")
    try:
        if dpapi.available():
            raw = dpapi.protect(raw)
        with open(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as handle:
            handle.write(raw)
        os.replace(temp, path)
    except OSError as exc:
        raise GuardianError("Không lưu được dữ liệu giám hộ") from exc
    finally:
        temp.unlink(missing_ok=True)


def has_pin() -> bool:
    """Đã có PIN hoàn chỉnh chưa (người dùng đã xác nhận lưu mã khôi phục).

    File hỏng cũng tính là "đã có": khi đó không được đặt đè.
    """
    if not _path().exists():
        return False
    data = _load()
    return data is None or bool(data["confirmed"])


def is_corrupt() -> bool:
    """Có file dữ liệu giám hộ nhưng không đọc được (hỏng, của tài khoản khác...)."""
    return _path().exists() and _load() is None


def setup(pin: str, replace_corrupt: bool = False) -> str:
    """Đặt PIN lần đầu. PIN chỉ hoàn chỉnh sau ``confirm``; bỏ dở thì lần sau ``setup`` đặt lại được.

    Args:
        pin: PIN mới.
        replace_corrupt: Cho đặt đè lên file hỏng. Chỉ người gọi đã chắc Guardian Mode đang TẮT mới được dùng
            (đang bật mà cho đặt đè thì xóa file là vượt được khóa).

    Returns:
        Mã khôi phục dạng đọc được. Chỉ trả về đúng lần này, không lưu lại ở đâu.

    Raises:
        GuardianError: PIN sai dạng, đã có PIN, hoặc không ghi được.
    """
    if not valid_pin(pin):
        raise GuardianError("Mã PIN phải gồm 4 đến 6 chữ số")
    with _locked():
        if has_pin() and not (replace_corrupt and _load() is None):
            raise GuardianError("Đã có mã PIN giám hộ")
        key = _new_recovery_key()
        _store({"pin": _record(pin), "recovery": _record(normalize_recovery_key(key)),
                "failures": 0, "locked_until": 0.0, "confirmed": False})
    return key


def _remaining(data: Mapping[str, Any]) -> int:
    # Chặn trên bằng LOCKOUT_S: chỉnh lùi đồng hồ không làm thời gian khóa dài ra vô hạn.
    return max(0, min(LOCKOUT_S, math.ceil(float(data["locked_until"]) - time.time())))


def lockout_remaining() -> int:
    """Số giây còn bị tạm khóa xác thực (0 = đang nhập được)."""
    data = _load()
    return 0 if data is None else _remaining(data)


def _check(data: dict[str, Any], kind: Literal["pin", "recovery"], secret: str) -> AuthResult:
    """So một bí mật với hash đã lưu và cập nhật bộ đếm. Phải gọi trong ``_locked()``."""
    wait = _remaining(data)
    if wait:
        return AuthResult(False, "locked", 0, wait)
    if _matches(secret, data[kind]):
        if data["failures"] or data["locked_until"]:
            data.update(failures=0, locked_until=0.0)
            _store(data)
        return AuthResult(True)
    failures = int(data["failures"]) + 1
    if failures >= MAX_FAILURES:
        data.update(failures=0, locked_until=time.time() + LOCKOUT_S)
        _store(data)                       # ghi không được thì ném lỗi, không bao giờ cho thử miễn phí
        return AuthResult(False, "locked", 0, LOCKOUT_S)
    data["failures"] = failures
    _store(data)
    return AuthResult(False, "wrong", MAX_FAILURES - failures)


def _authenticate(kind: Literal["pin", "recovery"], secret: str, new_pin: str | None = None,
                  confirming: bool = False) -> AuthResult:
    """Xác thực và (tùy chọn) đặt PIN mới trong cùng một lần giữ khóa. Không bao giờ ném lỗi."""
    try:
        with _locked():
            data = _load()
            if data is None:
                return AuthResult(False, "unavailable", 0)
            result = _check(data, kind, secret)
            if result.ok and confirming and not data["confirmed"]:
                data["confirmed"] = True
                _store(data)
            if not result.ok or new_pin is None:
                return result
            data["confirmed"] = True
            data["pin"] = _record(new_pin)
            key = _new_recovery_key()      # mỗi lần đổi PIN là một mã khôi phục mới, mã cũ hết hiệu lực
            data["recovery"] = _record(normalize_recovery_key(key))
            _store(data)
            return AuthResult(True, recovery_key=key)
    except (GuardianError, OSError, ValueError):
        return AuthResult(False, "unavailable", 0)


def verify_pin(pin: object) -> AuthResult:
    """Kiểm tra PIN giám hộ (sai quá ``MAX_FAILURES`` lần liên tiếp thì tạm khóa)."""
    return _authenticate("pin", pin if isinstance(pin, str) else "")


def confirm(pin: object) -> AuthResult:
    """Người dùng xác nhận đã lưu mã khôi phục: PIN vừa đặt trở thành chính thức."""
    return _authenticate("pin", pin if isinstance(pin, str) else "", confirming=True)


def change_pin(current: object, new_pin: str) -> AuthResult:
    """Đổi PIN khi biết PIN hiện tại. Cấp mã khôi phục mới (trong ``recovery_key``), mã cũ hết hiệu lực."""
    if not valid_pin(new_pin):
        return AuthResult(False, "invalid_pin")
    return _authenticate("pin", current if isinstance(current, str) else "", new_pin)


def recover(recovery_key: str, new_pin: str) -> AuthResult:
    """Quên PIN: dùng mã khôi phục đặt PIN mới và nhận mã khôi phục mới."""
    if not valid_pin(new_pin):
        return AuthResult(False, "invalid_pin")
    return _authenticate("recovery", normalize_recovery_key(recovery_key), new_pin)
