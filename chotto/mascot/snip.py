"""Chụp màn hình và lớp phủ kéo chọn vùng (kiểu Snipping Tool), chạy trên luồng Tk của nhân vật.

Lớp phủ hiện ảnh chụp đã làm mờ trên toàn bộ màn hình ảo; vùng đang kéo hiện lại ảnh gốc. Toạ độ đều là pixel vật lý
(agent đã bật DPI awareness) nên khớp 1:1 với ảnh chụp, kể cả nhiều màn hình có DPI khác nhau.
"""
from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

from ..platforms import win32_window as w32
from ..platforms.cocoa_overlay import ScreenPermissionError
from . import qr

if TYPE_CHECKING:
    import tkinter as tk

    from PIL import Image

__all__ = ["ScreenPermissionError", "SnipOverlay", "grab_screen"]

_LOG = logging.getLogger("chotto")
_DIM: Final[float] = 0.45                      # độ sáng còn lại của phần ngoài vùng chọn
_ACCENT: Final[str] = "#f2a33a"
_MAC: Final[bool] = sys.platform == "darwin"


def grab_screen() -> tuple[Image.Image, tuple[int, int], float]:
    """(ảnh màn hình, góc trái trên của nó theo toạ độ màn hình, số pixel ảnh trên một đơn vị toạ độ Tk).

    Windows: cả màn hình ảo, pixel vật lý (tỉ lệ 1). macOS: màn hình chính, ảnh Retina gấp đôi point của Tk.

    Raises:
        ScreenPermissionError: macOS chưa cấp quyền Ghi màn hình.
        OSError: Không chụp được (màn hình khóa, phiên từ xa đã ngắt...).
    """
    if _MAC:
        from ..platforms import cocoa_overlay

        image, scale = cocoa_overlay.grab_main_screen()
        return image, (0, 0), scale
    from PIL import ImageGrab

    left, top = w32.virtual_screen_origin()
    return ImageGrab.grab(all_screens=True).convert("RGB"), (left, top), 1.0


class SnipOverlay:
    """Một lần chọn vùng: gọi ``on_done`` đúng MỘT lần với ảnh đã cắt, hoặc ``None`` nếu hủy."""

    def __init__(self, root: tk.Tk, image: Image.Image, origin: tuple[int, int], hint: str, unit_dpi: float,
                 on_done: Callable[[Image.Image | None], None], scale: float = 1.0,
                 register: Callable[[SnipOverlay], None] | None = None) -> None:
        """``register`` được gọi ngay khi có cửa sổ, TRƯỚC mọi lần xử lý sự kiện Tk: macOS dùng chung Tk với agent, ``update()``
        trong hàm dựng có thể chạy việc khác (vd. mở màn cảnh báo) cần hủy được lớp phủ này."""
        import tkinter as tk

        from PIL import Image as PILImage
        from PIL import ImageTk

        self._full, self._scale = image, scale            # ảnh gốc (cắt từ đây cho nét) và tỉ lệ pixel/toạ độ Tk
        if scale != 1.0:                                  # macOS Retina: hiển thị theo point
            image = image.resize((round(image.width / scale), round(image.height / scale)), PILImage.Resampling.LANCZOS)
        self._image = image
        self._on_done = on_done
        self._done = False
        self._start: tuple[int, int] | None = None
        self._end = (0, 0)
        self._pending = False
        self._armed = False
        self._bright: Any = None                           # PhotoImage vùng chọn (giữ tham chiếu để Tk không mất ảnh)
        self._esc: Any = None                              # macOS: bộ theo dõi phím Esc (NSEvent)

        win = tk.Toplevel(root)
        win.withdraw()
        win.title(f"chotto-overlay-snip-{id(win)}")          # macOS: để tìm NSWindow (``raise_overlay``)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        canvas = tk.Canvas(win, width=image.width, height=image.height, highlightthickness=0, bd=0, cursor="crosshair", bg="#000")
        canvas.pack(fill="both", expand=True)
        self._win, self._canvas = win, canvas
        if register is not None:
            register(self)
        try:
            dim = image.point([round(v * _DIM) for v in range(256)] * 3)
            self._dim: Any = ImageTk.PhotoImage(dim, master=win)          # có master: luồng nhân vật dùng Tk riêng
            canvas.create_image(0, 0, anchor="nw", image=self._dim)
            self._patch = canvas.create_image(0, 0, anchor="nw", state="hidden")
            self._frame = canvas.create_rectangle(0, 0, 0, 0, outline=_ACCENT, width=max(2, round(2 * unit_dpi)), state="hidden")
            self._draw_hint(hint, origin, unit_dpi)
            canvas.bind("<ButtonPress-1>", lambda e: self._press(e.x, e.y))
            canvas.bind("<B1-Motion>", lambda e: self._drag(e.x, e.y))
            canvas.bind("<ButtonRelease-1>", lambda e: self._release(e.x, e.y))
            canvas.bind("<Button-3>", lambda _e: self.cancel())
            canvas.bind("<Button-2>", lambda _e: self.cancel())           # macOS: chuột phải
            win.bind("<Escape>", lambda _e: self.cancel())
            win.bind("<FocusOut>", lambda _e: self._focus_lost())
            win.geometry(f"{image.width}x{image.height}+{origin[0]}+{origin[1]}")
            win.deiconify()
            win.update_idletasks()
            if _MAC:
                from ..platforms import cocoa_overlay

                win.update()                                   # NSWindow phải có rồi mới nâng lên được
                if self._done:                                 # bị hủy ngay trong update(): không nâng cửa sổ đã đóng
                    return
                cocoa_overlay.raise_overlay(win)
                # Esc của Tk không tới cửa sổ không viền trên Aqua → nghe phím qua NSEvent
                self._esc = cocoa_overlay.watch_escape(lambda: win.after(0, self.cancel))
            else:
                hwnd = w32.toplevel_hwnd(int(win.winfo_id()))
                w32.set_window_rect(hwnd, (origin[0], origin[1], origin[0] + image.width, origin[1] + image.height))
                win.attributes("-topmost", True)
                w32.force_foreground(hwnd)
            win.focus_force()
            canvas.focus_force()
            win.after(400, self._arm)
        except Exception:
            self._destroy()                                    # không bao giờ để lại lớp phủ che màn hình
            raise

    def _draw_hint(self, hint: str, origin: tuple[int, int], u: float) -> None:
        """Dòng gợi ý ở giữa mép trên màn hình CHÍNH (toạ độ màn hình 0,0)."""
        x = -origin[0] + self._win.winfo_screenwidth() // 2
        y = -origin[1] + round(48 * u)
        label = self._canvas.create_text(x, y, text=hint, fill="#ffffff", font=("Segoe UI", -round(16 * u), "bold"))
        x0, y0, x1, y1 = self._canvas.bbox(label)
        pad = round(12 * u)
        box = self._canvas.create_rectangle(x0 - pad, y0 - pad // 2, x1 + pad, y1 + pad // 2, fill="#15101a", outline=_ACCENT)
        self._canvas.tag_lower(box, label)

    def _arm(self) -> None:
        if not self._done and self._win.focus_displayof() is not None:
            self._armed = True

    def _focus_lost(self) -> None:
        """Alt+Tab / phím Windows: hủy, kẻo lớp phủ che màn hình mà phím Esc không tới được."""
        if self._armed and not self._done:
            self._win.after(80, self._cancel_if_unfocused)

    def _cancel_if_unfocused(self) -> None:
        if not self._done and self._win.focus_displayof() is None:
            self.cancel()

    def _press(self, x: int, y: int) -> None:
        self._start, self._end = (x, y), (x, y)

    def _drag(self, x: int, y: int) -> None:
        if self._start is None:
            return
        self._end = (x, y)
        if not self._pending:                                  # gộp nhiều sự kiện chuột thành một lần vẽ
            self._pending = True
            self._win.after_idle(self._redraw)

    def _box(self) -> qr.Box | None:
        if self._start is None:
            return None
        return qr.selection_box(*self._start, *self._end, *self._image.size)

    def _redraw(self) -> None:
        self._pending = False
        if self._done:
            return
        box = self._box()
        if box is None:
            self._canvas.itemconfigure(self._patch, state="hidden")
            self._canvas.itemconfigure(self._frame, state="hidden")
            return
        from PIL import ImageTk

        self._bright = ImageTk.PhotoImage(qr.crop(self._image, box), master=self._win)
        self._canvas.coords(self._patch, box[0], box[1])
        self._canvas.itemconfigure(self._patch, image=self._bright, state="normal")
        self._canvas.coords(self._frame, *box)
        self._canvas.itemconfigure(self._frame, state="normal")

    def _release(self, x: int, y: int) -> None:
        if self._start is None or self._done:
            return
        self._end = (x, y)
        box = self._box()
        if box is None:                                        # bấm nhầm: cho kéo lại
            self._start = None
            self._redraw()
            return
        self._finish(qr.crop(self._full, self._full_box(box)))

    def _full_box(self, box: qr.Box) -> qr.Box:
        """Vùng chọn (toạ độ hiển thị) đổi sang pixel của ảnh gốc."""
        if self._scale == 1.0:
            return box
        x0, y0, x1, y1 = (round(v * self._scale) for v in box)
        return (x0, y0, min(x1, self._full.width), min(y1, self._full.height))

    def cancel(self) -> None:
        self._finish(None)

    def _finish(self, result: Image.Image | None) -> None:
        if self._done:
            return
        self._destroy()
        self._on_done(result)

    def _destroy(self) -> None:
        self._done = True
        self._dim = self._bright = None
        if self._esc is not None:
            from ..platforms import cocoa_overlay

            cocoa_overlay.unwatch_escape(self._esc)
            self._esc = None
        try:
            self._win.destroy()
        except Exception:  # noqa: BLE001
            _LOG.debug("Không đóng được lớp phủ chọn vùng", exc_info=True)
