"""Phần dùng chung mọi hệ điều hành: lệnh khởi chạy CHOTTO, chống vòng lặp, quy tắc nhận diện nguồn gọi.

Mọi hàm ở đây thuần (hoặc chỉ dùng thư viện chuẩn đa nền tảng) nên kiểm thử được trên mọi máy.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ..core.url import SUPPORTED_SCHEMES, get_scheme

__all__ = [
    "APP_NAME",
    "AMBIGUOUS_PROCESSES",
    "Caller",
    "MAX_ANCESTORS",
    "OWN_BUNDLE",
    "PlatformSetupError",
    "build_browser_argv",
    "decide_from_evidence",
    "default_argv",
    "is_http_url",
    "is_self",
    "main_script",
    "python_launcher",
    "spawn_in_new_session",
]

_LOG = logging.getLogger("chotto.platforms")

APP_NAME: Final[str] = "CHOTTO"
OWN_BUNDLE: Final[str] = "vn.chotto.app"          # bundle id của CHOTTO.app (macOS)
MAX_ANCESTORS: Final[int] = 6                     # số tầng tiến trình cha / ứng dụng phía trước tối đa cần xét
_PLACEHOLDERS: Final[tuple[str, ...]] = ("%1", "%l", "%L")

# Tiến trình không cho biết nguồn thật của link (shell, dịch vụ hệ thống, chính CHOTTO lúc đóng gói).
AMBIGUOUS_PROCESSES: Final[frozenset[str]] = frozenset({
    "explorer.exe", "svchost.exe", "sihost.exe", "runtimebroker.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "searchhost.exe", "applicationframehost.exe", "openwith.exe",
    "dllhost.exe", "cmd.exe", "conhost.exe", "python.exe", "pythonw.exe", "chotto.exe",
})


class PlatformSetupError(RuntimeError):
    """Không đăng ký/gỡ đăng ký được handler (thông điệp tiếng Việt để hiển thị)."""


# ---------------- lệnh khởi chạy CHOTTO ----------------
def main_script() -> Path:
    """Đường dẫn ``main.py`` khi chạy từ mã nguồn."""
    return Path(__file__).resolve().parent.parent.parent / "main.py"


def python_launcher() -> str:
    """Trình thông dịch chạy CHOTTO từ mã nguồn (Windows: ``pythonw.exe`` để không hiện cửa sổ console)."""
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else python)


def default_argv(command: str) -> list[str]:
    """Lệnh chạy ``main.py <command>``: bản đóng gói gọi thẳng file thực thi, mã nguồn gọi qua Python."""
    if getattr(sys, "frozen", False):
        return [sys.executable, command]
    return [python_launcher(), str(main_script()), command]


def spawn_in_new_session(argv: list[str]) -> None:
    """Khởi chạy tách rời (phiên mới, không giữ stdin/stdout) cho macOS/Linux.

    Raises:
        OSError: Không chạy được lệnh.
    """
    subprocess.Popen(argv, start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------- chống vòng lặp, chuyển tiếp ----------------
def _same_file(a: str, b: str) -> bool:
    """So sánh hai đường dẫn file theo nội dung hệ thống tệp (không phân biệt hoa thường trên Windows)."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def is_self(argv: list[str]) -> bool:
    """``True`` nếu lệnh ``argv`` sẽ khởi chạy lại chính CHOTTO (nguyên nhân vòng lặp vô hạn)."""
    if not argv or not argv[0]:
        return False
    if _same_file(argv[0], sys.executable):
        return True
    script = str(main_script())
    return any(arg.lower().endswith("main.py") and _same_file(arg, script) for arg in argv[1:])


def is_http_url(url: str) -> bool:
    """Chỉ chuyển tiếp http/https (CHOTTO chỉ đăng ký hai scheme này)."""
    return get_scheme(url) in SUPPORTED_SCHEMES


def build_browser_argv(command_args: list[str], url: str) -> list[str]:
    """Thay ``%1``/``%l``/``%L`` bằng ``url`` trong từng phần tử argv; bỏ ``%*``; không có chỗ thì nối ``url`` vào cuối.

    URL luôn là một phần tử argv riêng (không ghép chuỗi lệnh) nên không thể chèn tham số.
    """
    replaced = False
    result: list[str] = []
    for arg in command_args:
        if arg == "%*":
            continue
        new = arg
        for placeholder in _PLACEHOLDERS:
            if placeholder in new:
                new = new.replace(placeholder, url)
                replaced = True
        result.append(new)
    if not replaced:
        result.append(url)
    return result


# ---------------- nhận diện nguồn gọi ----------------
@dataclass(frozen=True)
class Caller:
    """Kết quả nhận diện nguồn gọi (link có xuất phát từ Zalo hay không).

    Attributes:
        from_zalo: ``True`` = có bằng chứng từ Zalo; ``False`` = bằng chứng dương tính là ứng dụng KHÁC
            (không phải Zalo, CHOTTO hay shell hệ thống) ⇒ được chuyển thẳng; ``None`` = không xác định ⇒
            áp dụng ``unknown_caller_policy`` (mặc định: vẫn kiểm tra).
        evidence: Mô tả bằng chứng (ghi log, không chứa URL).
    """

    from_zalo: bool | None
    evidence: str = ""


def decide_from_evidence(
    ancestors: list[str], foreground: str | None, zalo_names: set[str], own_names: set[str]
) -> Caller:
    """Quy tắc quyết định thuần, dùng chung cho mọi hệ điều hành.

    Args:
        ancestors: Tên file thực thi của các tiến trình tổ tiên (gần nhất trước), chữ thường.
        foreground: Tên tiến trình / bundle id của ứng dụng phía trước (chữ thường) hoặc ``None``.
        zalo_names: Tên tiến trình / bundle id của Zalo (chữ thường).
        own_names: Tên của chính CHOTTO (chữ thường).
    """
    chain = ",".join(ancestors)
    if zalo_names.intersection(ancestors):
        return Caller(True, f"tiến trình cha: {chain}")
    if foreground in zalo_names:
        return Caller(True, f"cửa sổ foreground: {foreground}")
    if foreground and foreground not in own_names and foreground not in AMBIGUOUS_PROCESSES:
        return Caller(False, f"foreground={foreground}, cha={chain}")
    return Caller(None, f"không xác định (foreground={foreground}, cha={chain})")
