"""Mọi thứ phụ thuộc hệ điều hành của bản Desktop, sau một API chung.

- ``common``: phần dùng chung (lệnh khởi chạy, chống vòng lặp, quy tắc nhận diện Zalo).
- ``windows`` / ``macos`` / ``linux``: đăng ký trình mở link, mở trình duyệt thật, tự khởi động, nhận diện nguồn gọi.
- ``win32_window`` / ``cocoa_window`` (+ ``window`` để chọn): thủ thuật cửa sổ cho giao diện pywebview và nhân vật.

Đăng ký, mở trình duyệt, tự khởi động, nhận diện nguồn gọi và thủ thuật cửa sổ chỉ đi qua đây.
"""
from __future__ import annotations

import importlib
import logging
import sys
from collections.abc import Iterable, Mapping, MutableMapping
from typing import Any, Final, Protocol, cast

from . import windows
from .common import Caller, PlatformSetupError, build_browser_argv, decide_from_evidence, is_http_url
from .windows import split_windows_command

__all__ = [
    "Caller",
    "PlatformSetupError",
    "agent_argv",
    "any_process_running",
    "build_browser_argv",
    "decide_from_evidence",
    "detect_caller",
    "disable_autostart",
    "enable_autostart",
    "install",
    "is_default_handler",
    "open_in_real_browser",
    "spawn_agent",
    "split_windows_command",
    "ui_host_argv",
    "uninstall",
]

_LOG = logging.getLogger("chotto.platforms")


class _Backend(Protocol):
    """Các hàm mỗi mô-đun hệ điều hành (``windows``, ``macos``, ``linux``) phải có."""

    def agent_argv(self) -> list[str]: ...
    def ui_host_argv(self) -> list[str]: ...
    def spawn_agent(self, argv: list[str]) -> None: ...
    def enable_autostart(self, argv: list[str]) -> None: ...
    def disable_autostart(self) -> None: ...
    def is_default_handler(self) -> bool | None: ...
    def install(self, cfg: MutableMapping[str, Any]) -> str: ...
    def uninstall(self, cfg: Mapping[str, Any]) -> str: ...
    def open_url(self, url: str, cfg: Mapping[str, Any]) -> bool: ...
    def detect_caller(self, cfg: Mapping[str, Any]) -> Caller: ...


_NAME: Final[str] = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
_OS: Final[_Backend] = cast(_Backend, importlib.import_module(f".{_NAME}", __name__))
SUPPORTED: Final[bool] = _NAME != "linux"          # đăng ký được làm trình mở link mặc định


def agent_argv() -> list[str]:
    """Lệnh khởi động agent thường trú (argv, không qua shell)."""
    return _OS.agent_argv()


def ui_host_argv() -> list[str]:
    """Lệnh chạy tiến trình giao diện HTML (``main.py ui-host``), nói chuyện qua stdin/stdout."""
    return _OS.ui_host_argv()


def spawn_agent() -> bool:
    """Khởi động agent tách rời khỏi tiến trình hiện tại; ``False`` nếu không chạy được lệnh."""
    argv = agent_argv()
    try:
        _OS.spawn_agent(argv)
    except OSError:
        _LOG.exception("Không khởi động được agent")
        return False
    _LOG.info("Đã khởi động agent: %s", argv[0])
    return True


def enable_autostart() -> None:
    """Cho agent tự chạy khi đăng nhập.

    Raises:
        PlatformSetupError: Không ghi được cấu hình tự khởi động.
    """
    _OS.enable_autostart(agent_argv())


def disable_autostart() -> None:
    """Gỡ tự khởi động; không có gì để gỡ thì bỏ qua. Không ném lỗi."""
    _OS.disable_autostart()


def is_default_handler() -> bool | None:
    """CHOTTO có đang là trình mở link https mặc định không; ``None`` nếu không xác định được."""
    try:
        return _OS.is_default_handler()
    except (OSError, ValueError, PlatformSetupError):
        _LOG.warning("Không xác định được trình xử lý link mặc định", exc_info=True)
        return None


def install(cfg: MutableMapping[str, Any]) -> str:
    """Đăng ký CHOTTO, bật tự khởi động agent và khởi động agent ngay.

    ``cfg`` được cập nhật với trình duyệt thật cần chuyển tiếp (người gọi lưu lại).

    Raises:
        PlatformSetupError: Không đăng ký được.
    """
    message = _OS.install(cfg)
    if not SUPPORTED:
        return message
    if cfg.get("agent_enabled", True):
        try:
            enable_autostart()
        except PlatformSetupError:
            _LOG.exception("Không bật được tự khởi động")
            return message + " (Không bật được chạy nền cùng hệ thống; CHOTTO vẫn hoạt động nhưng chậm hơn.)"
        spawn_agent()
    return message


def uninstall(cfg: Mapping[str, Any] | None = None) -> str:
    """Gỡ đăng ký CHOTTO và tắt tự khởi động. macOS: trả trình mở link về trình duyệt đã ghi nhớ lúc cài."""
    disable_autostart()
    return _OS.uninstall(cfg or {})


def any_process_running(names: Iterable[str]) -> bool:
    """Có tiến trình nào trong ``names`` (tên file, không phân biệt hoa thường) đang chạy không. Chỉ Windows; nơi khác ``False``."""
    if sys.platform != "win32":
        return False
    wanted = {str(n).lower() for n in names}
    try:
        return bool(wanted & windows.running_process_names())
    except OSError:
        _LOG.debug("Không liệt kê được tiến trình", exc_info=True)
        return False


def open_in_real_browser(url: str, cfg: Mapping[str, Any]) -> bool:
    """Chuyển ``url`` cho trình duyệt thật, không bao giờ gọi lại CHOTTO.

    Args:
        url: URL http/https đã chuẩn hóa (``Result.open_url``).
        cfg: Cấu hình chứa trình duyệt đã lưu lúc cài đặt.

    Returns:
        ``True`` nếu đã khởi chạy trình duyệt; ``False`` nếu không có trình duyệt dùng được hoặc URL
        không phải http/https (người gọi phải báo cho người dùng).
    """
    if not is_http_url(url):
        _LOG.error("Từ chối chuyển tiếp URL không phải http/https")
        return False
    return _OS.open_url(url, cfg)


def detect_caller(cfg: Mapping[str, Any]) -> Caller:
    """Link có xuất phát từ Zalo không (đo TRƯỚC khi tạo cửa sổ); mọi lỗi trả ``Caller(None, ...)``.

    Args:
        cfg: Cấu hình chứa ``zalo_processes`` (Windows) và ``zalo_bundle_ids`` (macOS).
    """
    try:
        return _OS.detect_caller(cfg)
    except (OSError, ValueError, AttributeError) as exc:
        _LOG.warning("Nhận diện nguồn gọi lỗi", exc_info=True)
        return Caller(None, f"lỗi: {exc}")
