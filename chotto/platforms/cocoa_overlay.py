"""Cửa sổ overlay trong suốt cho nhân vật trên macOS (Tk trong suốt + AppKit qua PyObjC). Chỉ gọi trên macOS.

Khác Windows:
- Không có ``UpdateLayeredWindow``: mỗi khung hình được dán vào một ``PhotoImage`` có kênh alpha, đặt trên ``Canvas`` nền
  ``systemTransparent`` trong cửa sổ ``-transparent`` của Tk (Cocoa tự ghép alpha từng điểm ảnh).
- Tọa độ Tk trên macOS tính bằng point, gốc ở góc trái trên màn hình chính. Không có taskbar: nhân vật đứng trên mép Dock
  (đáy ``visibleFrame``).
- Tk trên macOS CHỈ chạy được ở luồng chính: nhân vật dùng chung luồng Tk của agent (xem ``mascot/runner.py``).
- Cửa sổ không viền của Tk không nhận được bàn phím ổn định: ô chat dùng cửa sổ có thanh tiêu đề (``BORDERLESS_INPUT``).

AppKit là phần tô điểm (mức cửa sổ, hiện trên mọi Desktop): thiếu PyObjC hay lỗi thì nhân vật vẫn chạy với ``-topmost`` của Tk.
"""
from __future__ import annotations

import logging
import os
from typing import Any

__all__ = ["Surface", "animations_enabled", "enable_layered", "foreground", "make_tool_window", "set_foreground",
           "work_area"]

_LOG = logging.getLogger("chotto")
_TITLE = "chotto-overlay-"
# canJoinAllSpaces | stationary | ignoresCycle | fullScreenAuxiliary: hiện trên mọi Desktop, không lọt vào Cmd+`
_BEHAVIOR = (1 << 0) | (1 << 4) | (1 << 6) | (1 << 8)


def _appkit() -> Any:
    import AppKit  # type: ignore[import-untyped,import-not-found,unused-ignore]

    return AppKit


def make_tool_window(window: Any) -> None:
    """Đặt tên riêng để sau này tìm được ``NSWindow`` của cửa sổ Tk (Tk chỉ tạo ``NSWindow`` khi cửa sổ hiện lần đầu)."""
    window.title(f"{_TITLE}{id(window)}")


def enable_layered(window: Any) -> None:
    """Nền trong suốt cho cả cửa sổ (từng điểm ảnh của ``PhotoImage`` mang alpha riêng)."""
    window.attributes("-transparent", True)
    window.configure(bg="systemTransparent")


def _tune(window: Any) -> bool:
    """Chỉnh ``NSWindow``: nổi trên Dock, có ở mọi Desktop, không bóng, không bị ẩn khi app mất focus. ``True`` khi xong."""
    try:
        appkit = _appkit()
        title = str(window.title())
        for ns in appkit.NSApplication.sharedApplication().windows():
            if str(ns.title()) != title:
                continue
            ns.setOpaque_(False)
            ns.setBackgroundColor_(appkit.NSColor.clearColor())
            ns.setHasShadow_(False)
            ns.setHidesOnDeactivate_(False)
            ns.setCollectionBehavior_(_BEHAVIOR)
            ns.setLevel_(appkit.NSStatusWindowLevel)
            return True
    except Exception:  # noqa: BLE001 - chỉ là tô điểm
        _LOG.debug("Không chỉnh được NSWindow của nhân vật", exc_info=True)
        return True                                    # thiếu PyObjC: thôi, khỏi thử lại mỗi khung hình
    return False                                       # cửa sổ chưa hiện: thử lại ở khung sau


class Surface:
    """Cùng hợp đồng với ``win32_window.LayeredSurface``: ``update`` nhận BGRa (alpha nhân trước) và vị trí cửa sổ."""

    def __init__(self, window: Any, width: int, height: int) -> None:
        import tkinter as tk

        from PIL import ImageTk

        self._window = window
        self._size = (width, height)
        canvas = next((c for c in window.winfo_children() if c.winfo_class() == "Canvas"), None)
        if canvas is None:
            canvas = tk.Canvas(window, highlightthickness=0, bd=0)
            canvas.pack()
        canvas.configure(width=width, height=height, bg="systemTransparent")
        self._canvas = canvas
        self._photo: Any = ImageTk.PhotoImage("RGBA", (width, height), master=window)
        self._item = canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._xy: tuple[int, int] | None = None
        self._tuned = False

    def update(self, bgra: bytes, x: int, y: int) -> None:
        """Dán khung hình rồi dời cửa sổ tới ``(x, y)`` (point)."""
        from PIL import Image

        width, height = self._size
        if len(bgra) != width * height * 4:
            raise ValueError("Sai kích thước khung hình")
        image = Image.frombuffer("RGBa", self._size, bgra, "raw", "BGRa", 0, 1).convert("RGBA")
        self._photo.paste(image)
        if (x, y) != self._xy:
            self._window.geometry(f"{width}x{height}+{x}+{y}")
            self._xy = (x, y)
        if not self._tuned:
            self._tuned = _tune(self._window)

    def close(self) -> None:
        try:
            self._canvas.delete(self._item)
        except Exception:  # noqa: BLE001 - cửa sổ đã bị hủy
            pass
        self._photo = None


def work_area() -> tuple[int, int, int, int]:
    """(trái, trên, phải, đáy) của vùng nhìn thấy trên màn hình chính (trừ thanh menu và Dock), đơn vị point, gốc trên-trái.

    Raises:
        OSError: Không đọc được (thiếu PyObjC).
    """
    try:
        appkit = _appkit()
        screen = appkit.NSScreen.screens()[0]          # màn hình chính (có thanh menu): gốc tọa độ của Tk
        full, visible = screen.frame(), screen.visibleFrame()
    except Exception as exc:  # noqa: BLE001
        raise OSError("Không đọc được vùng màn hình") from exc
    height = full.size.height
    top = height - (visible.origin.y + visible.size.height)
    bottom = height - visible.origin.y
    return (int(visible.origin.x), int(top), int(visible.origin.x + visible.size.width), int(bottom))


def animations_enabled() -> bool:
    """``False`` khi người dùng bật "Giảm chuyển động" trong Trợ năng."""
    try:
        return not bool(_appkit().NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion())
    except Exception:  # noqa: BLE001
        return True


def foreground() -> int:
    """PID của ứng dụng đang ở phía trước (0 nếu không biết)."""
    try:
        app = _appkit().NSWorkspace.sharedWorkspace().frontmostApplication()
        return int(app.processIdentifier()) if app is not None else 0
    except Exception:  # noqa: BLE001
        return 0


def set_foreground(pid: int) -> None:
    """Trả focus cho ứng dụng ``pid`` (bỏ qua nếu là chính CHOTTO hoặc 0)."""
    if not pid or pid == os.getpid():
        return
    try:
        app = _appkit().NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if app is not None:
            app.activateWithOptions_(0)
    except Exception:  # noqa: BLE001
        _LOG.debug("Không trả focus được", exc_info=True)


def activate_self() -> None:
    """Đưa CHOTTO lên trước để ô chat nhận được bàn phím."""
    try:
        _appkit().NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:  # noqa: BLE001
        _LOG.debug("Không kích hoạt được CHOTTO", exc_info=True)


def running_app_names() -> set[str]:
    """Tên (chữ thường) của các ứng dụng đang chạy: tên hiển thị, tên file chạy và bundle id."""
    names: set[str] = set()
    try:
        for app in _appkit().NSWorkspace.sharedWorkspace().runningApplications():
            for value in (app.localizedName(), app.bundleIdentifier(),
                          app.executableURL().lastPathComponent() if app.executableURL() is not None else None):
                if value:
                    names.add(str(value).lower())
    except Exception:  # noqa: BLE001
        _LOG.debug("Không liệt kê được ứng dụng đang chạy", exc_info=True)
    return names
