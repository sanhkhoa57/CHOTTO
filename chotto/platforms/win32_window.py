"""Thủ thuật cửa sổ trên Windows (Win32 qua ``ctypes``) cho giao diện pywebview/WinForms và nhân vật taskbar.

Chỉ được gọi trên Windows (``chotto.platforms.window`` chọn giúp). ``ctypes.windll`` chỉ nạp bên trong hàm nên
mô-đun vẫn nhập được trên hệ điều hành khác. Mọi hàm "chỉ là hiển thị" đều tự nuốt lỗi.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

__all__ = [
    "activate",
    "animations_enabled",
    "center_on_screen",
    "enable_snap",
    "fade",
    "force_foreground",
    "foreground_window",
    "make_tool_window",
    "virtual_screen_origin",
    "monitor_work_rect",
    "native_hwnd",
    "set_foreground",
    "set_icon",
    "set_window_rect",
    "system_dpi_scale",
    "taskbar_work_area",
    "toplevel_hwnd",
    "watch_session_end",
    "window_dpi_scale",
    "window_rect",
]

_LOG = logging.getLogger("chotto")

Rect = tuple[int, int, int, int]
_SNAP_KEEPALIVE: list[Any] = []            # giữ tham chiếu WNDPROC, nếu không GC sẽ làm sập tiến trình


# ---------------- cửa sổ pywebview (WinForms) ----------------
def native_hwnd(window: Any) -> int:
    """HWND của Form WinForms bên dưới một cửa sổ pywebview."""
    return int(window.native.Handle.ToInt64())


def _force_foreground(hwnd: int) -> None:
    """Windows chặn tiến trình nền tự giành foreground; nhấn-nhả Alt ảo trước thì SetForegroundWindow được chấp nhận."""
    import ctypes

    user32 = ctypes.windll.user32
    user32.keybd_event(0x12, 0, 0, 0)                                    # VK_MENU xuống
    user32.keybd_event(0x12, 0, 2, 0)                                    # VK_MENU lên
    user32.SetForegroundWindow(hwnd)


def activate(window: Any) -> None:
    """Kích hoạt Form, giành foreground và đưa focus vào vùng WebView2 (để phím Esc tới được trang)."""
    try:
        native = window.native
        if native is None:
            return
        from System import Action  # type: ignore[import-not-found]  # pythonnet, chỉ có trên Windows

        def focus() -> None:
            native.Activate()
            _force_foreground(int(native.Handle.ToInt64()))
            for control in native.Controls:
                control.Focus()

        native.Invoke(Action(focus))
    except Exception:  # noqa: BLE001 - chỉ là tiện ích hiển thị, không bao giờ được làm hỏng màn hình đệm
        _LOG.debug("Không kích hoạt được cửa sổ", exc_info=True)


def set_icon(window: Any, ico: str) -> None:
    """Đặt icon cho cửa sổ (thanh tác vụ, Alt+Tab). Bản đóng gói đã có icon trong exe nên bỏ qua."""
    try:
        import ctypes
        from ctypes import wintypes

        if getattr(sys, "frozen", False) or not os.path.exists(ico):
            return
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT)
        user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        hwnd = wintypes.HWND(native_hwnd(window))
        for which, size in ((0, 16), (1, 32)):                          # ICON_SMALL, ICON_BIG
            handle = user32.LoadImageW(None, ico, 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
            if handle:
                user32.SendMessageW(hwnd, 0x0080, which, handle)        # WM_SETICON
    except Exception:  # noqa: BLE001 - chỉ là phần hiển thị
        _LOG.debug("Không đặt được icon cửa sổ", exc_info=True)


def enable_snap(window: Any) -> None:
    """Cho cửa sổ không viền dùng được chia cửa sổ của Windows (Win+←/→/↑, Snap layouts).

    Windows chỉ cho snap cửa sổ có kiểu ``WS_THICKFRAME`` + ``WS_MAXIMIZEBOX``. Ta thêm các kiểu đó rồi chặn
    ``WM_NCCALCSIZE`` để vùng nội dung vẫn phủ kín cửa sổ (không hiện khung hệ thống). Lỗi thì bỏ qua: cửa sổ
    vẫn dùng bình thường, chỉ không snap được.
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = wintypes.HWND(native_hwnd(window))
        lresult = ctypes.c_ssize_t
        wndproc_t = ctypes.WINFUNCTYPE(lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
        user32.CallWindowProcW.restype = lresult
        user32.CallWindowProcW.argtypes = (ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.GetSystemMetricsForDpi.argtypes = (ctypes.c_int, wintypes.UINT)
        user32.GetDpiForWindow.argtypes = (wintypes.HWND,)
        user32.IsZoomed.argtypes = (wintypes.HWND,)

        wm_nccalcsize = 0x0083
        old_proc = user32.GetWindowLongPtrW(hwnd, -4)           # GWLP_WNDPROC

        def proc(h: Any, msg: int, wparam: int, lparam: int) -> int:
            if msg == wm_nccalcsize and wparam:
                if user32.IsZoomed(h):                          # phóng to kiểu hệ thống: thụt vào bằng bề dày khung ẩn
                    dpi = user32.GetDpiForWindow(h) or 96
                    frame = user32.GetSystemMetricsForDpi(32, dpi) + user32.GetSystemMetricsForDpi(92, dpi)
                    rect = ctypes.cast(lparam, ctypes.POINTER(wintypes.RECT)).contents
                    rect.left += frame
                    rect.top += frame
                    rect.right -= frame
                    rect.bottom -= frame
                return 0
            return int(user32.CallWindowProcW(old_proc, h, msg, wparam, lparam))

        callback = wndproc_t(proc)
        _SNAP_KEEPALIVE.append(callback)
        user32.SetWindowLongPtrW(hwnd, -4, ctypes.cast(callback, ctypes.c_void_p).value or 0)
        style = user32.GetWindowLongPtrW(hwnd, -16)             # GWL_STYLE
        style |= 0x00040000 | 0x00010000 | 0x00020000           # THICKFRAME | MAXIMIZEBOX | MINIMIZEBOX
        user32.SetWindowLongPtrW(hwnd, -16, style)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)  # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED
    except Exception:  # noqa: BLE001 - chỉ là tiện ích, không bao giờ được làm hỏng cửa sổ
        _LOG.debug("Không bật được snap cửa sổ", exc_info=True)


def fade(window: Any, start: int, end: int, ms: int = 160) -> None:
    """Làm mờ/hiện dần cả cửa sổ (độ trong suốt 0-255), chặn luồng gọi trong ``ms`` mili giây.

    Dùng lớp trong suốt của Windows nên không phụ thuộc trang web đã vẽ xong hay chưa. Dừng ở ``255`` thì gỡ lớp
    trong suốt để WebView2 vẽ như thường. Lỗi thì bỏ qua.
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = wintypes.HWND(native_hwnd(window))
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
        user32.SetLayeredWindowAttributes.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD)
        ex = user32.GetWindowLongPtrW(hwnd, -20)                       # GWL_EXSTYLE
        user32.SetWindowLongPtrW(hwnd, -20, ex | 0x00080000)           # WS_EX_LAYERED
        steps = max(1, ms // 16)
        for i in range(steps + 1):
            k = i / steps
            user32.SetLayeredWindowAttributes(hwnd, 0, round(start + (end - start) * k), 0x2)   # LWA_ALPHA
            if i < steps:
                time.sleep(ms / 1000 / steps)
        if end >= 255:
            user32.SetWindowLongPtrW(hwnd, -20, ex & ~0x00080000)
    except Exception:  # noqa: BLE001 - chỉ là hiệu ứng
        _LOG.debug("Không làm mờ được cửa sổ", exc_info=True)


def center_on_screen(window: Any, width: int, max_height: int, margin: int = 24) -> None:
    """Đặt cửa sổ đúng giữa vùng làm việc (đã trừ taskbar) của màn hình đang chứa con trỏ chuột.

    ``width``/``max_height`` theo điểm logic (96 DPI); mọi phép đo dùng pixel vật lý nên không lệch ở 125%/150%.
    """
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    # Bản DLL riêng: đặt argtypes lên ``ctypes.windll.user32`` dùng chung sẽ đổi luôn chữ ký hàm mà pywebview
    # đang gọi (``window.move`` sập vì ArgumentError).
    user32 = ctypes.WinDLL("user32")
    hwnd = wintypes.HWND(native_hwnd(window))
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    user32.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
    monitor = user32.MonitorFromPoint(point, 2)                     # MONITOR_DEFAULTTONEAREST
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(MonitorInfo)
    user32.GetMonitorInfoW.argtypes = (wintypes.HMONITOR, ctypes.POINTER(MonitorInfo))
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return
    dpi_x, dpi_y = wintypes.UINT(96), wintypes.UINT(96)
    try:
        ctypes.WinDLL("shcore").GetDpiForMonitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))  # MDT_EFFECTIVE_DPI
    except (AttributeError, OSError):
        user32.GetDpiForWindow.argtypes = (wintypes.HWND,)
        dpi_x.value = user32.GetDpiForWindow(hwnd) or 96
    scale = (dpi_x.value or 96) / 96
    work = info.rcWork
    work_w, work_h = work.right - work.left, work.bottom - work.top
    gap = round(margin * scale)
    w = max(1, min(round(width * scale), work_w - 2 * gap))
    h = max(1, min(round(max_height * scale), work_h - 2 * gap))
    user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT)
    user32.SetWindowPos(hwnd, None, work.left + (work_w - w) // 2, work.top + (work_h - h) // 2,
                        w, h, 0x0014)                                # NOZORDER|NOACTIVATE


# ---------------- tự vẽ khung: phóng to có hiệu ứng, kéo giãn ----------------
def window_rect(hwnd: int) -> Rect:
    """(trái, trên, phải, dưới) của cửa sổ, pixel vật lý."""
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def monitor_work_rect(hwnd: int) -> Rect | None:
    """Vùng làm việc (đã trừ taskbar) của màn hình chứa cửa sổ; ``None`` nếu không đọc được."""
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    user32 = ctypes.windll.user32
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(MonitorInfo)
    monitor = user32.MonitorFromWindow(hwnd, 2)          # MONITOR_DEFAULTTONEAREST
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    work = info.rcWork
    return work.left, work.top, work.right, work.bottom


def window_dpi_scale(hwnd: int) -> float:
    """Tỉ lệ phóng to (DPI / 96) của màn hình chứa cửa sổ."""
    import ctypes

    return float(ctypes.windll.user32.GetDpiForWindow(hwnd) or 96) / 96


def set_window_rect(hwnd: int, rect: Rect) -> None:
    """Dời/giãn cửa sổ tới ``rect`` mà không đổi thứ tự trên dưới, không kích hoạt."""
    import ctypes

    left, top, right, bottom = rect
    ctypes.windll.user32.SetWindowPos(hwnd, 0, left, top, right - left, bottom - top, 0x0214)  # NOZORDER|NOACTIVATE|NOOWNERZORDER


# ---------------- cửa sổ overlay của nhân vật (Tk) ----------------
def toplevel_hwnd(child: int) -> int:
    """HWND của cửa sổ bọc ngoài một widget Tk (``winfo_id`` trả cửa sổ con)."""
    import ctypes

    return int(ctypes.windll.user32.GetParent(child) or child)


def taskbar_work_area() -> Rect:
    """Vùng chạy của nhân vật: hết chiều ngang màn hình chính, mép dưới là mép trên của thanh taskbar gốc.

    Vùng làm việc có thể hẹp hơn nếu có thanh công cụ tùy biến chiếm hai bên, nên lấy cả chiều ngang màn hình; mép
    dưới lấy từ ``Shell_TrayWnd`` khi nó nằm ở đáy màn hình. Pixel vật lý (agent đã bật DPI awareness).

    Raises:
        OSError: Không đọc được vùng làm việc.
    """
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    user32 = ctypes.windll.user32
    if not user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):   # SPI_GETWORKAREA
        raise OSError("SPI_GETWORKAREA thất bại")
    top, right, bottom = rect.top, rect.right, rect.bottom
    screen_w, screen_h = int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    tray = user32.FindWindowW("Shell_TrayWnd", None)
    tray_rect = wintypes.RECT()
    if tray and user32.IsWindowVisible(tray) and user32.GetWindowRect(tray, ctypes.byref(tray_rect)):
        if tray_rect.top > screen_h // 2 and tray_rect.right - tray_rect.left > screen_w // 2:
            bottom = tray_rect.top
    return 0, top, max(right, screen_w), bottom


def system_dpi_scale() -> float:
    """Tỉ lệ phóng to của hệ thống (DPI / 96, tối thiểu 1)."""
    try:
        import ctypes

        return max(1.0, int(ctypes.windll.user32.GetDpiForSystem()) / 96)
    except (AttributeError, OSError):
        return 1.0


def animations_enabled() -> bool:
    """Cài đặt "Hiệu ứng hoạt ảnh" của Windows (SPI_GETCLIENTAREAANIMATION); tắt = giảm chuyển động."""
    try:
        import ctypes
        from ctypes import wintypes

        value = wintypes.BOOL(True)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0):
            return bool(value.value)
    except (AttributeError, OSError):
        pass
    return True


def make_tool_window(hwnd: int) -> None:
    """WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE + luôn nổi: không có nút trên taskbar, không cướp focus."""
    import ctypes

    user32 = ctypes.windll.user32
    get = user32.GetWindowLongPtrW
    put = user32.SetWindowLongPtrW
    get.restype = put.restype = ctypes.c_ssize_t
    get.argtypes = (ctypes.c_void_p, ctypes.c_int)
    put.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t)
    style = get(hwnd, -20)                                                # GWL_EXSTYLE
    style = (style | 0x00000080 | 0x08000000) & ~0x00040000               # TOOLWINDOW | NOACTIVATE, bỏ APPWINDOW
    put(hwnd, -20, style)
    user32.SetWindowPos.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_uint)
    user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0020)  # TOPMOST, giữ chỗ


def enable_layered(hwnd: int) -> None:
    """Thêm WS_EX_LAYERED (để cập nhật bằng ``LayeredSurface``: alpha từng điểm ảnh, viền mịn, không dùng màu khóa)."""
    import ctypes

    user32 = ctypes.windll.user32
    get = user32.GetWindowLongPtrW
    put = user32.SetWindowLongPtrW
    get.restype = put.restype = ctypes.c_ssize_t
    get.argtypes = (ctypes.c_void_p, ctypes.c_int)
    put.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t)
    put(hwnd, -20, get(hwnd, -20) | 0x00080000)                           # WS_EX_LAYERED


class LayeredSurface:
    """Bề mặt 32-bit BGRA (alpha đã nhân trước) của một cửa sổ layered: ``update`` đổi ảnh VÀ vị trí trong MỘT lệnh
    (``UpdateLayeredWindow``) nên không rách hình, viền khử răng cưa như trên web. Cửa sổ phải đã gọi ``enable_layered``."""

    def __init__(self, hwnd: int, width: int, height: int) -> None:
        import ctypes
        from ctypes import wintypes

        class _Header(ctypes.Structure):
            _fields_ = [("size", ctypes.c_uint32), ("width", ctypes.c_int32), ("height", ctypes.c_int32), ("planes", ctypes.c_uint16),
                        ("bits", ctypes.c_uint16), ("compression", ctypes.c_uint32), ("image", ctypes.c_uint32),
                        ("xppm", ctypes.c_int32), ("yppm", ctypes.c_int32), ("used", ctypes.c_uint32), ("important", ctypes.c_uint32)]

        class _Blend(ctypes.Structure):
            _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("alpha", ctypes.c_ubyte), ("format", ctypes.c_ubyte)]

        self._ct = ctypes
        self._wt = wintypes
        self._blend = _Blend(0, 0, 255, 1)                                  # AC_SRC_OVER, AC_SRC_ALPHA
        self._hwnd, self._size = hwnd, (width, height)
        gdi32, user32 = ctypes.windll.gdi32, ctypes.windll.user32
        gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
        gdi32.CreateCompatibleDC.argtypes = (ctypes.c_void_p,)
        gdi32.CreateDIBSection.restype = ctypes.c_void_p
        gdi32.CreateDIBSection.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.c_void_p, ctypes.c_uint32)
        gdi32.SelectObject.restype = ctypes.c_void_p
        gdi32.SelectObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        gdi32.DeleteObject.argtypes = (ctypes.c_void_p,)
        gdi32.DeleteDC.argtypes = (ctypes.c_void_p,)
        user32.UpdateLayeredWindow.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32)
        header = _Header(ctypes.sizeof(_Header), width, -height, 1, 32, 0, width * height * 4, 0, 0, 0, 0)   # chiều cao âm = từ trên xuống
        self._dc = gdi32.CreateCompatibleDC(None)
        bits = ctypes.c_void_p()
        self._bitmap = gdi32.CreateDIBSection(self._dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        if not self._dc or not self._bitmap or not bits.value:
            raise OSError("Không tạo được bề mặt layered")
        self._bits = bits.value
        self._old = gdi32.SelectObject(self._dc, self._bitmap)

    def update(self, bgra: bytes, x: int, y: int) -> None:
        """Ghi khung hình ``bgra`` (đúng ``rộng x cao x 4`` byte, alpha đã nhân trước) và đặt cửa sổ tại ``(x, y)``."""
        ct, wt = self._ct, self._wt
        width, height = self._size
        if len(bgra) != width * height * 4:
            raise ValueError("Sai kích thước khung hình")
        ct.memmove(self._bits, bgra, len(bgra))
        pos, size, src = wt.POINT(x, y), wt.SIZE(width, height), wt.POINT(0, 0)
        ct.windll.user32.UpdateLayeredWindow(self._hwnd, None, ct.byref(pos), ct.byref(size), self._dc, ct.byref(src), 0,
                                             ct.byref(self._blend), 2)         # ULW_ALPHA

    def close(self) -> None:
        gdi32 = self._ct.windll.gdi32
        if self._dc:
            gdi32.SelectObject(self._dc, self._old)
            gdi32.DeleteObject(self._bitmap)
            gdi32.DeleteDC(self._dc)
            self._dc = self._bitmap = None


def fine_timer(on: bool) -> None:
    """Bật/hạ bộ hẹn giờ Windows xuống 1 ms (``timeBeginPeriod``); mặc định ~15,6 ms nên ``after(33)`` của Tk bị trễ thành 37-45 ms.
    Phải gọi cặp bật/tắt cân bằng; chỉ bật khi đang có hoạt ảnh vì nó làm máy ít được nghỉ (tốn pin)."""
    try:
        import ctypes

        (ctypes.windll.winmm.timeBeginPeriod if on else ctypes.windll.winmm.timeEndPeriod)(1)
    except (AttributeError, OSError):
        pass


def set_noactivate(hwnd: int, on: bool) -> None:
    """Bật/tắt WS_EX_NOACTIVATE (tắt = cửa sổ nhận được focus bàn phím, dùng cho ô chat của nhân vật)."""
    import ctypes

    user32 = ctypes.windll.user32
    get = user32.GetWindowLongPtrW
    put = user32.SetWindowLongPtrW
    get.restype = put.restype = ctypes.c_ssize_t
    get.argtypes = (ctypes.c_void_p, ctypes.c_int)
    put.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t)
    style = get(hwnd, -20)
    put(hwnd, -20, (style | 0x08000000) if on else (style & ~0x08000000))


def watch_session_end(callback: Callable[[], None]) -> None:
    """Gọi ``callback`` (trên luồng nền) khi phiên Windows sắp kết thúc: tắt máy, khởi động lại hoặc đăng xuất.

    Cần một cửa sổ thật để nhận ``WM_ENDSESSION`` (handler console không đến được tiến trình có user32), nên
    mở một cửa sổ ẩn trên luồng nền riêng. Lỗi thì bỏ qua: chỉ mất tính năng, không ảnh hưởng agent.
    """
    def run() -> None:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            lresult = ctypes.c_ssize_t
            wndproc_t = ctypes.WINFUNCTYPE(lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            user32.DefWindowProcW.restype = lresult
            user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE
            kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
            wm_endsession = 0x0016

            def proc(hwnd: Any, msg: int, wparam: int, lparam: int) -> int:
                if msg == wm_endsession and wparam:          # wParam = TRUE: phiên thật sự kết thúc
                    try:
                        callback()
                    except Exception:  # noqa: BLE001 - không để lỗi thoát ra ngoài WNDPROC
                        _LOG.exception("Lỗi khi xử lý kết thúc phiên")
                    return 0
                return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))

            callback_ref = wndproc_t(proc)
            _SNAP_KEEPALIVE.append(callback_ref)

            class WndClass(ctypes.Structure):
                _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", wndproc_t), ("cbClsExtra", ctypes.c_int),
                            ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HANDLE),
                            ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                            ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

            user32.RegisterClassW.argtypes = (ctypes.POINTER(WndClass),)
            user32.CreateWindowExW.restype = wintypes.HWND
            user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                               ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                               wintypes.HANDLE, wintypes.HINSTANCE, wintypes.LPVOID)
            cls = WndClass()
            cls.lpfnWndProc = callback_ref
            cls.hInstance = kernel32.GetModuleHandleW(None)
            cls.lpszClassName = "ChottoSessionWatcher"
            user32.RegisterClassW(ctypes.byref(cls))
            # Cửa sổ ẩn cấp cao nhất (không phải message-only: loại này không nhận WM_ENDSESSION).
            hwnd = user32.CreateWindowExW(0, cls.lpszClassName, "CHOTTO", 0, 0, 0, 0, 0, None, None, cls.hInstance, None)
            if not hwnd:
                return
            msg = wintypes.MSG()
            user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:  # noqa: BLE001 - chỉ là tiện ích
            _LOG.debug("Không theo dõi được kết thúc phiên", exc_info=True)

    threading.Thread(target=run, name="chotto-session-watch", daemon=True).start()


def foreground_window() -> int:
    """HWND đang ở foreground (0 nếu không có)."""
    import ctypes

    return int(ctypes.windll.user32.GetForegroundWindow() or 0)


def virtual_screen_origin() -> tuple[int, int]:
    """Góc trái trên của màn hình ảo (gộp mọi màn hình); âm nếu có màn hình phụ ở bên trái hoặc phía trên màn hình chính."""
    import ctypes

    user32 = ctypes.windll.user32
    return int(user32.GetSystemMetrics(76)), int(user32.GetSystemMetrics(77))   # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN


def force_foreground(hwnd: int) -> None:
    """Giành foreground cho cửa sổ của mình (để nhận phím Esc); chỉ gọi ngay sau thao tác của người dùng."""
    _force_foreground(hwnd)


def set_foreground(hwnd: int) -> None:
    """Trả foreground về ``hwnd`` (bỏ qua nếu 0)."""
    if hwnd:
        import ctypes

        ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
