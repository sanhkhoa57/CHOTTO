"""Chọn thủ thuật cửa sổ theo hệ điều hành cho giao diện pywebview (``webhost``) và nhân vật taskbar.

Hệ điều hành không có thủ thuật nào thì hàm tương ứng không làm gì. Mọi hàm ở đây không bao giờ ném lỗi.
"""
from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any, Final

from . import cocoa_window, win32_window

__all__ = [
    "CUSTOM_FRAME",
    "HIDE_UNTIL_LOADED",
    "OVERLAY_SUPPORTED",
    "REFOCUS_ON_LOAD",
    "activate",
    "center_on_screen",
    "enable_snap",
    "fade",
    "reload_on_show",
    "set_icon",
    "watch_session_end",
]

_LOG = logging.getLogger("chotto")

_WIN: Final[bool] = sys.platform == "win32"
_MAC: Final[bool] = sys.platform == "darwin"

CUSTOM_FRAME: Final[bool] = _WIN          # khung tự vẽ: phóng to có hiệu ứng, kéo giãn bằng mép HTML (win32_window)
HIDE_UNTIL_LOADED: Final[bool] = _WIN     # ẩn cửa sổ ứng dụng tới khi trang tải xong rồi hiện dần (không nháy)
REFOCUS_ON_LOAD: Final[bool] = _WIN       # lấy focus lần nữa khi trang tải xong (để phím Esc dùng được ngay)
OVERLAY_SUPPORTED: Final[bool] = _WIN or _MAC   # cửa sổ trong suốt cho nhân vật (chi tiết: platforms/overlay.py)


def reload_on_show(window: Any, url: str) -> None:
    """Tải lại trang khi cửa sổ hiện (chỉ macOS cần: cửa sổ tạo sau ``webview.start`` ra đen)."""
    if _MAC:
        cocoa_window.reload_on_show(window, url)


def activate(window: Any) -> None:
    """Đưa cửa sổ lên trước và lấy focus."""
    if _WIN:
        win32_window.activate(window)
    elif _MAC:
        cocoa_window.activate(window)


def center_on_screen(window: Any, width: int, max_height: int, margin: int = 24) -> None:
    """Đặt cửa sổ giữa vùng làm việc của màn hình đang chứa con trỏ chuột, thu nhỏ để luôn lọt màn hình."""
    try:
        if _WIN:
            win32_window.center_on_screen(window, width, max_height, margin)
        elif _MAC:
            cocoa_window.center_on_screen(window, width, max_height, margin)
    except Exception:  # noqa: BLE001 - chỉ là vị trí hiển thị, không được làm hỏng cửa sổ
        _LOG.debug("Không căn giữa được cửa sổ", exc_info=True)


def set_icon(window: Any, ico: str) -> None:
    """Đặt icon cửa sổ khi chạy từ mã nguồn (Windows)."""
    if _WIN:
        win32_window.set_icon(window, ico)


def enable_snap(window: Any) -> None:
    """Cho cửa sổ không viền dùng được Snap của Windows."""
    if _WIN:
        win32_window.enable_snap(window)


def watch_session_end(callback: Callable[[], None]) -> None:
    """Gọi ``callback`` khi phiên kết thúc (tắt máy/đăng xuất/khởi động lại); chỉ Windows, nơi khác không làm gì."""
    if _WIN:
        win32_window.watch_session_end(callback)


def fade(window: Any, start: int, end: int, ms: int = 160) -> None:
    """Làm mờ/hiện dần cả cửa sổ (Windows); nơi khác không làm gì."""
    if _WIN:
        win32_window.fade(window, start, end, ms)
