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

__all__ = ["Surface", "animations_enabled", "enable_layered", "foreground", "grab_main_screen", "make_tool_window",
           "raise_overlay", "ScreenPermissionError", "set_foreground", "unwatch_escape", "watch_escape", "work_area"]

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
    """Nền trong suốt cho cả cửa sổ (từng điểm ảnh của ``PhotoImage`` mang alpha riêng).

    PHẢI gọi ngay sau ``tk.Toplevel(...)``, TRƯỚC ``overrideredirect``/``update_idletasks``: Tk 9 trên Aqua chỉ áp
    ``-transparent`` lúc dựng ``NSWindow``; đặt muộn (hay đặt LẠI lần hai) thì nền ra ĐEN đặc (khung đen sau lưng nhân vật).
    Chỉ gọi qua ``overlay.prepare``, đúng một lần mỗi cửa sổ.
    """
    window.attributes("-transparent", True)
    window.configure(bg="systemTransparent")
    window.attributes("-alpha", 0.0)       # vô hình tới khi ``_Layer`` gắn xong (không thì lần hiện đầu nháy một ô đen)


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


def _ns_window(window: Any) -> Any:
    """``NSWindow`` của cửa sổ Tk (tìm theo tên do ``make_tool_window`` đặt); ``None`` nếu chưa có."""
    title = str(window.title())
    return next((ns for ns in _appkit().NSApplication.sharedApplication().windows() if str(ns.title()) == title), None)


class _Layer:
    """Hình vẽ bằng ``CALayer`` đặt trên view của Tk (view Tk bị làm trong suốt hẳn nhưng vẫn nhận chuột).

    Lý do: Tk 9 trên Aqua tô ĐEN đặc mọi vùng vẽ lại trong cửa sổ ``-transparent`` (Canvas lẫn Label, ``paste`` lẫn
    ``PhotoImage`` mới; đã đo bằng ``CGWindowListCreateImage``) nên không thể vẽ khung hình động bằng Tk.
    """

    def __init__(self, ns: Any, width: int, height: int) -> None:
        import Quartz  # type: ignore[import-untyped,import-not-found,unused-ignore]

        appkit = _appkit()
        self._quartz = Quartz
        self._appkit = appkit
        self._size = (width, height)
        self._space = Quartz.CGColorSpaceCreateDeviceRGB()
        content = ns.contentView()
        content.setAlphaValue_(0.0)                 # alpha 0 vẫn được hit-test (khác ``setHidden``): chuột vẫn tới Tk
        host = content.superview()
        host.setWantsLayer_(True)
        layer = Quartz.CALayer.layer()
        layer.setFrame_(((0, 0), (width, height)))
        layer.setContentsScale_(1.0)                # khung hình tính bằng point
        none = appkit.NSNull.null()
        layer.setActions_({"contents": none, "bounds": none, "position": none})   # không có hiệu ứng mờ dần giữa hai khung
        host.layer().addSublayer_(layer)
        self._layer = layer
        self._ns = ns

    def reveal(self) -> None:
        """Bỏ alpha 0 do ``enable_layered`` đặt (gọi SAU khi lớp đã có khung hình đầu tiên)."""
        self._ns.setAlphaValue_(1.0)

    def show(self, bgra: bytes) -> None:
        q = self._quartz
        width, height = self._size
        data = self._appkit.NSData.dataWithBytes_length_(bgra, len(bgra))
        image = q.CGImageCreate(width, height, 8, 32, width * 4, self._space,
                                q.kCGImageAlphaPremultipliedFirst | q.kCGBitmapByteOrder32Little,
                                q.CGDataProviderCreateWithCFData(data), None, False, q.kCGRenderingIntentDefault)
        self._layer.setContents_(image)

    def remove(self) -> None:
        self._layer.removeFromSuperlayer()


class Surface:
    """Cùng hợp đồng với ``win32_window.LayeredSurface``: ``update`` nhận BGRa (alpha nhân trước) và vị trí cửa sổ.

    Vẽ bằng ``CALayer`` (xem ``_Layer``). Thiếu PyObjC/Quartz thì lùi về ``PhotoImage`` trên Canvas (chạy được nhưng nền
    sau nhân vật ra đen do lỗi Tk).
    """

    def __init__(self, window: Any, width: int, height: int) -> None:
        import tkinter as tk

        self._window = window
        self._size = (width, height)
        canvas = next((c for c in window.winfo_children() if c.winfo_class() == "Canvas"), None)
        if canvas is None:
            canvas = tk.Canvas(window, highlightthickness=0, bd=0)
            canvas.pack()
        canvas.configure(width=width, height=height, bg="systemTransparent")
        self._canvas = canvas
        self._layer: _Layer | None = None
        self._photo: Any = None
        self._item: Any = None
        self._xy: tuple[int, int] | None = None
        self._tuned = False

    def _ensure_layer(self) -> None:
        """Dựng ``_Layer`` khi ``NSWindow`` đã có; không dựng được (thiếu PyObjC) thì dùng ``PhotoImage``."""
        try:
            ns = _ns_window(self._window)
            if ns is None:
                return                              # cửa sổ chưa hiện: thử lại ở khung sau
            self._layer = _Layer(ns, *self._size)
        except Exception:  # noqa: BLE001
            _LOG.warning("Không vẽ được bằng CALayer, dùng PhotoImage (nền có thể ra đen)", exc_info=True)
            from PIL import ImageTk

            self._photo = ImageTk.PhotoImage("RGBA", self._size, master=self._window)
            self._item = self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
            self._window.attributes("-alpha", 1.0)

    def update(self, bgra: bytes, x: int, y: int) -> None:
        """Hiện khung hình rồi dời cửa sổ tới ``(x, y)`` (point)."""
        width, height = self._size
        if len(bgra) != width * height * 4:
            raise ValueError("Sai kích thước khung hình")
        if (x, y) != self._xy:
            self._window.geometry(f"{width}x{height}+{x}+{y}")
            self._xy = (x, y)
        if not self._tuned:
            self._tuned = _tune(self._window)
        if self._layer is None and self._photo is None:
            self._ensure_layer()
            if self._layer is not None:
                self._layer.show(bgra)
                self._layer.reveal()
                return
        if self._layer is not None:
            self._layer.show(bgra)
        elif self._photo is not None:
            from PIL import Image

            self._photo.paste(Image.frombuffer("RGBa", self._size, bgra, "raw", "BGRa", 0, 1).convert("RGBA"))

    def close(self) -> None:
        try:
            if self._layer is not None:
                self._layer.remove()
            if self._item is not None:
                self._canvas.delete(self._item)
        except Exception:  # noqa: BLE001 - cửa sổ đã bị hủy
            pass
        self._layer = None
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


# ---------------- quét QR: chụp màn hình + lớp phủ chọn vùng ----------------
class ScreenPermissionError(PermissionError):
    """macOS chưa cấp quyền "Bản ghi âm thanh hệ thống & màn hình" cho CHOTTO (riêng Mac, để Windows không hiện nhầm câu nhắc)."""


def grab_main_screen() -> tuple[Any, float]:
    """(ảnh màn hình chính đủ độ phân giải, số pixel trên một point). Ảnh Retina gấp đôi kích thước point.

    Raises:
        ScreenPermissionError: Chưa có quyền Ghi màn hình (macOS đã được nhờ hỏi người dùng; cấp xong phải mở lại CHOTTO).
        OSError: Không chụp được.
    """
    try:
        import Quartz  # type: ignore[import-untyped,import-not-found,unused-ignore]

        if not Quartz.CGPreflightScreenCaptureAccess():
            Quartz.CGRequestScreenCaptureAccess()      # thêm CHOTTO vào danh sách (lần đầu macOS hiện hộp thoại)
            _open_screen_capture_settings()
            raise ScreenPermissionError("Chưa có quyền Ghi màn hình")
    except ImportError:
        pass                                           # thiếu PyObjC: cứ chụp, thiếu quyền thì ảnh chỉ có hình nền
    from PIL import ImageGrab

    image = ImageGrab.grab().convert("RGB")            # macOS: lệnh screencapture, chỉ màn hình chính
    try:
        points = float(_appkit().NSScreen.screens()[0].frame().size.width)
    except Exception:  # noqa: BLE001
        points = float(image.width)
    return image, max(1.0, image.width / points)


# macOS 13+: Cài đặt hệ thống > Quyền riêng tư & Bảo mật > "Ghi màn hình & âm thanh hệ thống" (tên mới từ macOS 15).
_SCREEN_CAPTURE_PANE = "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ScreenCapture"


def _open_screen_capture_settings() -> None:
    import subprocess

    try:
        subprocess.Popen(["/usr/bin/open", _SCREEN_CAPTURE_PANE], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        _LOG.debug("Không mở được trang quyền Ghi màn hình", exc_info=True)


_ESC_KEYCODE = 53


def watch_escape(callback: Any) -> Any:
    """Gọi ``callback`` khi bấm Esc lúc CHOTTO đang ở trước; trả về mã để ``unwatch_escape``.

    Cửa sổ Tk không viền (overrideredirect) trên Aqua không thành "key window" được nên ``<Escape>``
    của Tk không bao giờ tới; bộ theo dõi sự kiện cục bộ của NSEvent thì vẫn thấy phím.
    """
    try:
        appkit = _appkit()

        def handler(event: Any) -> Any:
            if int(event.keyCode()) == _ESC_KEYCODE:
                callback()
                return None                                    # nuốt phím Esc
            return event

        return appkit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(appkit.NSEventMaskKeyDown, handler)
    except Exception:  # noqa: BLE001
        _LOG.debug("Không theo dõi được phím Esc", exc_info=True)
        return None


def unwatch_escape(token: Any) -> None:
    if token is None:
        return
    try:
        _appkit().NSEvent.removeMonitor_(token)
    except Exception:  # noqa: BLE001
        _LOG.debug("Không gỡ được bộ theo dõi phím Esc", exc_info=True)


def raise_overlay(window: Any) -> None:
    """Đưa lớp phủ chọn vùng lên trên cả thanh menu và Dock, rồi lấy focus (để Esc tới được)."""
    activate_self()
    try:
        ns = _ns_window(window)
        if ns is not None:
            ns.setLevel_(_appkit().NSScreenSaverWindowLevel)
            ns.setCollectionBehavior_(_BEHAVIOR)
            ns.makeKeyAndOrderFront_(None)
    except Exception:  # noqa: BLE001 - chỉ là thứ tự cửa sổ
        _LOG.debug("Không nâng được lớp phủ chọn vùng", exc_info=True)
