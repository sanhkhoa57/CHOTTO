"""Linux: ngoài phạm vi chính, chỉ đủ để chạy thử (mở link bằng ``xdg-open``, không đăng ký handler)."""
from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Mapping, MutableMapping
from typing import Any

from .common import Caller, default_argv, spawn_in_new_session

__all__ = [
    "agent_argv",
    "detect_caller",
    "disable_autostart",
    "enable_autostart",
    "install",
    "is_default_handler",
    "open_url",
    "spawn_agent",
    "ui_host_argv",
    "uninstall",
]

_LOG = logging.getLogger("chotto.platforms")
_UNSUPPORTED = "Chỉ hỗ trợ Windows và macOS."


def agent_argv() -> list[str]:
    """Lệnh khởi động agent."""
    return default_argv("agent")


def ui_host_argv() -> list[str]:
    """Lệnh chạy tiến trình giao diện HTML."""
    return default_argv("ui-host")


def spawn_agent(argv: list[str]) -> None:
    """Khởi động agent tách rời.

    Raises:
        OSError: Không chạy được lệnh.
    """
    spawn_in_new_session(argv)


def enable_autostart(argv: list[str]) -> None:
    """Không hỗ trợ tự khởi động trên Linux."""


def disable_autostart() -> None:
    """Không có gì để gỡ."""


def is_default_handler() -> None:
    """Không xác định được trên Linux."""
    return None


def handler_released() -> bool:
    """Linux không đăng ký handler: không có gì để nhả."""
    return True


def install(cfg: MutableMapping[str, Any]) -> str:
    """Không đăng ký handler trên Linux."""
    return _UNSUPPORTED


def uninstall(cfg: Mapping[str, Any]) -> str:
    """Không có đăng ký để gỡ."""
    return _UNSUPPORTED


def open_url(url: str, cfg: Mapping[str, Any]) -> bool:
    """Mở bằng ``xdg-open`` trừ khi CHOTTO đang là trình duyệt mặc định (tránh vòng lặp)."""
    xdg_open = shutil.which("xdg-open")
    if not xdg_open:
        return False
    settings = shutil.which("xdg-settings")
    if settings:
        try:
            current = subprocess.run([settings, "get", "default-web-browser"], capture_output=True, text=True,
                                     timeout=3, check=False).stdout
        except (OSError, subprocess.SubprocessError):
            current = ""
        if "chotto" in current.lower():
            _LOG.error("CHOTTO đang là trình duyệt mặc định trên Linux, không thể chuyển tiếp an toàn")
            return False
    try:
        subprocess.Popen([xdg_open, url], close_fds=True)
    except OSError:
        _LOG.exception("xdg-open lỗi")
        return False
    return True


def detect_caller(cfg: Mapping[str, Any]) -> Caller:
    """Không nhận diện được nguồn gọi trên Linux."""
    return Caller(None, "nền tảng không hỗ trợ")
