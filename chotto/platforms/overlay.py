"""Cửa sổ overlay của nhân vật, chọn theo hệ điều hành: Windows dùng ``win32_window`` (layered window), macOS dùng
``cocoa_overlay`` (Tk trong suốt). Mã nhân vật chỉ gọi qua đây.

``handle`` là "tay cầm" cửa sổ: HWND trên Windows, chính cửa sổ Tk trên macOS. ``token`` (``foreground``/``own``) để so
"ai đang ở phía trước": HWND trên Windows, PID ứng dụng trên macOS.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Final

from . import cocoa_overlay, win32_window

__all__ = ["BORDERLESS_INPUT", "QR_SUPPORTED", "SUPPORTED", "Surface", "allow_typing", "animations_enabled",
           "dpi_scale", "enable_layered", "fine_timer", "foreground", "handle", "make_tool_window", "own",
           "set_foreground", "set_noactivate", "work_area"]

_WIN: Final[bool] = sys.platform == "win32"
_MAC: Final[bool] = sys.platform == "darwin"

SUPPORTED: Final[bool] = _WIN or _MAC
QR_SUPPORTED: Final[bool] = _WIN          # quét QR (chọn vùng màn hình) mới có trên Windows
BORDERLESS_INPUT: Final[bool] = _WIN      # cửa sổ không viền nhận được bàn phím (macOS: không chắc, dùng cửa sổ có tiêu đề)

Surface: Any = win32_window.LayeredSurface if _WIN else cocoa_overlay.Surface


def handle(window: Any) -> Any:
    """Tay cầm của cửa sổ Tk ``window`` (gọi sau ``update_idletasks``)."""
    return win32_window.toplevel_hwnd(int(window.winfo_id())) if _WIN else window


def make_tool_window(h: Any) -> None:
    """Không có nút trên thanh tác vụ, luôn nổi."""
    if _WIN:
        win32_window.make_tool_window(h)
    elif _MAC:
        cocoa_overlay.make_tool_window(h)


def enable_layered(h: Any) -> None:
    """Cho phép vẽ bằng ``Surface`` (alpha từng điểm ảnh)."""
    if _WIN:
        win32_window.enable_layered(h)
    elif _MAC:
        cocoa_overlay.enable_layered(h)


def set_noactivate(h: Any, on: bool) -> None:
    """Bật/tắt "không lấy focus" (chỉ Windows)."""
    if _WIN:
        win32_window.set_noactivate(h, on)


def allow_typing() -> None:
    """Chuẩn bị nhận bàn phím cho ô chat (macOS: đưa CHOTTO lên trước)."""
    if _MAC:
        cocoa_overlay.activate_self()


def fine_timer(on: bool) -> None:
    """Bộ hẹn giờ 1 ms (chỉ Windows cần)."""
    if _WIN:
        win32_window.fine_timer(on)


def dpi_scale() -> float:
    """Hệ số phóng to: Windows tính theo DPI; macOS là 1 vì Tk đã dùng point."""
    return win32_window.system_dpi_scale() if _WIN else 1.0


def animations_enabled() -> bool:
    if _WIN:
        return win32_window.animations_enabled()
    return cocoa_overlay.animations_enabled() if _MAC else True


def work_area() -> tuple[int, int, int, int]:
    """Vùng chạy của nhân vật: Windows là trên thanh taskbar, macOS là trên Dock.

    Raises:
        OSError: Không đọc được.
    """
    return win32_window.taskbar_work_area() if _WIN else cocoa_overlay.work_area()


def foreground() -> int:
    if _WIN:
        return win32_window.foreground_window()
    return cocoa_overlay.foreground() if _MAC else 0


def own(h: Any) -> int:
    """Token của chính nhân vật để so với ``foreground``."""
    return int(h) if _WIN else os.getpid()


def set_foreground(token: int) -> None:
    if _WIN:
        win32_window.set_foreground(token)
    elif _MAC:
        cocoa_overlay.set_foreground(token)
