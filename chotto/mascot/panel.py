"""Bong bóng có nút bấm của nhân vật taskbar: thanh chọn nhanh (Quét QR / Hỏi Chotto) và bảng kết quả quét QR.

Cùng kiểu truyện tranh với ``bubble.py``: Pillow vẽ cả bong bóng lẫn nút, đưa lên một cửa sổ layered; bấm nút nào thì dò
theo toạ độ. Phần dựng hình (``render_panel``, ``hit``) không đụng Tk.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from ..platforms import overlay as ov
from . import speech

if TYPE_CHECKING:
    import tkinter as tk

    from PIL import Image

__all__ = ["CLOSE", "ActionPanel", "Button", "hit", "render_panel"]

CLOSE: Final[str] = "close"
_TIP_X: Final[int] = 41                        # như ``bubble._TIP_X``
_TEXT_W: Final[int] = 300
_INK: Final[tuple[int, int, int]] = (21, 16, 26)
_SOFT: Final[tuple[int, int, int]] = (238, 232, 224)
Rect = tuple[int, int, int, int]


@dataclass(frozen=True)
class Button:
    key: str
    label: str
    primary: bool = False


def _wrap(font: Any, text: str, limit: int) -> list[str]:
    """Như ``speech.wrap_text`` nhưng giữ xuống dòng và bẻ cả "từ" dài hơn một dòng (link trong mã QR)."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        for line in speech.wrap_text(font, paragraph, limit):
            while len(line) > 1 and font.getlength(line) > limit:
                cut = len(line) - 1
                while cut > 1 and font.getlength(line[:cut]) > limit:
                    cut -= 1
                lines.append(line[:cut])
                line = line[cut:]
            lines.append(line)
    return lines


def render_panel(kind: str, text: str, buttons: Sequence[Button], u: float, big: bool = False) -> tuple[Image.Image, dict[str, Rect]]:
    """(ảnh RGBA, vùng bấm theo khóa nút, kể cả ``CLOSE``). ``big``: nút cao thành "ô" lựa chọn."""
    from PIL import ImageDraw

    px = round(15 * u)
    font = speech.load_font(px)
    line_h, close_w, gap = round(px * 1.4), round(26 * u), round(8 * u)
    button_h, side = round((54 if big else 34) * u), round(14 * u)
    widths = [round(font.getlength(b.label)) + 2 * side for b in buttons]
    row_w = sum(widths) + gap * max(0, len(buttons) - 1)
    lines = _wrap(font, text, round(_TEXT_W * u) - close_w)
    text_w = max(round(font.getlength(line)) for line in lines) + close_w
    inner_w = max(text_w, row_w, round(240 * u))
    inner_h = line_h * len(lines) + (round(10 * u) + button_h if buttons else 0)
    width, height, x, y = speech.layout(kind, inner_w, inner_h, u)
    image = speech.render_bubble(kind, width, height, u)
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_h), line, font=font, fill=_INK)

    size = round(22 * u)
    close = (x + inner_w - size, y - round(2 * u), x + inner_w, y - round(2 * u) + size)
    draw.ellipse(close, fill=_SOFT)
    pad, stroke = round(7 * u), max(2, round(2 * u))
    draw.line((close[0] + pad, close[1] + pad, close[2] - pad, close[3] - pad), fill=_INK, width=stroke)
    draw.line((close[0] + pad, close[3] - pad, close[2] - pad, close[1] + pad), fill=_INK, width=stroke)
    areas: dict[str, Rect] = {CLOSE: close}

    if buttons:
        if big:                                                   # các ô chia đều hết bề ngang
            widths = [(inner_w - gap * (len(buttons) - 1)) // len(buttons)] * len(buttons)
        left, top = x, y + line_h * len(lines) + round(10 * u)
        for button, w in zip(buttons, widths):
            rect = (left, top, left + w, top + button_h)
            draw.rounded_rectangle(rect, radius=round(10 * u), fill=_INK if button.primary else _SOFT, outline=_INK,
                                   width=max(2, round(2 * u)))
            draw.text((left + w / 2, top + button_h / 2), button.label, font=font, anchor="mm",
                      fill=(255, 255, 255) if button.primary else _INK)
            areas[button.key] = rect
            left += w + gap
    return image, areas


def hit(areas: dict[str, Rect], x: int, y: int) -> str | None:
    """Khóa của nút chứa điểm ``(x, y)``."""
    for key, (left, top, right, bottom) in areas.items():
        if left <= x < right and top <= y < bottom:
            return key
    return None


class ActionPanel:
    """Một bảng nút duy nhất. ``modal``: nhận focus (để Esc tới được) và tự đóng khi bấm ra ngoài."""

    def __init__(self, root: tk.Tk, unit_dpi: float, on_change: Callable[[bool], None]) -> None:
        self._root = root
        self._u = unit_dpi
        self._on_change = on_change
        self._win: Any = None
        self._canvas: Any = None
        self._hwnd: Any = 0
        self._surface: Any = None                                 # ``overlay.Surface``
        self._areas: dict[str, Rect] = {}
        self._actions: Callable[[str], None] | None = None
        self._frame = b""
        self._size = (1, 1)
        self._xy: tuple[int, int] | None = None
        self._anchor: tuple[int, int, tuple[int, int, int, int]] | None = None
        self._previous = 0
        self._modal = False
        self.visible = False

    def _ensure(self) -> None:
        if self._win is not None:
            return
        import tkinter as tk

        win = tk.Toplevel(self._root)
        win.withdraw()
        ov.prepare(win)                                          # macOS: trước overrideredirect, nếu không nền ra đen
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        canvas = tk.Canvas(win, width=1, height=1, highlightthickness=0, bd=0, takefocus=1)
        canvas.pack()
        canvas.bind("<ButtonRelease-1>", lambda e: self.click(e.x, e.y))
        canvas.bind("<Motion>", lambda e: canvas.configure(cursor="hand2" if hit(self._areas, e.x, e.y) else ""))
        win.bind("<Escape>", lambda _e: self.close())
        win.bind("<FocusOut>", lambda _e: self._focus_lost())
        win.update_idletasks()
        self._hwnd = ov.handle(win)
        ov.make_tool_window(self._hwnd)
        ov.enable_layered(self._hwnd)
        self._win, self._canvas = win, canvas

    def show(self, kind: speech.Kind, text: str, buttons: Sequence[Button], on_action: Callable[[str], None],
             big: bool = False, modal: bool = False) -> None:
        """Hiện bảng (thay bảng đang mở). Bấm nút gọi ``on_action(khóa)``; bảng KHÔNG tự đóng, trừ nút ✕."""
        self._ensure()
        image, self._areas = render_panel(kind, text, buttons, self._u, big)
        self._actions = on_action
        self._size = image.size
        self._frame = image.convert("RGBa").tobytes("raw", "BGRa")
        old, self._surface = self._surface, ov.Surface(self._hwnd, *image.size)
        if old is not None:
            old.close()
        self._canvas.configure(width=image.width, height=image.height)
        was_visible, self.visible = self.visible, True
        self._xy = None
        self._modal = False                                      # chưa có focus thì chưa xét "mất focus"
        ov.set_noactivate(self._hwnd, not modal)
        self._win.deiconify()
        self._win.attributes("-topmost", True)
        if self._anchor is not None:
            self.place(*self._anchor)
        if modal:
            self._previous = ov.foreground()
            self._win.after(60, self._take_focus)
        if not was_visible:
            self._on_change(True)

    def _take_focus(self) -> None:
        if not self.visible or self._win is None:
            return
        ov.allow_typing()                                        # macOS: CHOTTO chạy nền, phải lên trước mới nhận Esc/focus
        self._win.focus_force()
        self._canvas.focus_force()
        self._win.after(250, self._arm)

    def _arm(self) -> None:
        """Chỉ bật "bấm ra ngoài thì đóng" khi chắc chắn đã giữ được focus."""
        if self.visible and self._win is not None and self._win.focus_displayof() is not None:
            self._modal = True

    def _focus_lost(self) -> None:
        if self._modal and self._win is not None:
            self._win.after(80, self._close_if_unfocused)

    def _close_if_unfocused(self) -> None:
        if self._modal and self.visible and self._win is not None and self._win.focus_displayof() is None:
            self._previous = 0                                   # người dùng tự chuyển sang chỗ khác: đừng kéo focus về
            self.close()

    def click(self, x: int, y: int) -> None:
        key = hit(self._areas, x, y)
        if key == CLOSE:
            self.close()
        elif key is not None and self._actions is not None:
            self._actions(key)

    def place(self, tip_x: int, sprite_top: int, area: tuple[int, int, int, int]) -> None:
        """Như ``SpeechBubble.place``: đuôi chỉ xuống nhân vật, kẹp trong vùng làm việc."""
        self._anchor = (tip_x, sprite_top, area)
        if not self.visible or self._surface is None:
            return
        width, height = self._size
        left, top, right, _bottom = area
        x = max(left, min(right - width, tip_x - width + round(_TIP_X * self._u)))
        y = max(top, sprite_top - height - round(2 * self._u))
        if (x, y) != self._xy:
            self._xy = (x, y)
            self._surface.update(self._frame, x, y)

    def close(self) -> None:
        if not self.visible:
            return
        self.visible = self._modal = False
        previous, self._previous = self._previous, 0
        if self._win is not None:
            ov.set_noactivate(self._hwnd, True)
            self._win.withdraw()
        if previous and previous != ov.own(self._hwnd):
            ov.set_foreground(previous)
        self._on_change(False)

    def destroy(self) -> None:
        self.visible = self._modal = False
        surface, self._surface = self._surface, None
        if surface is not None:
            surface.close()
        win, self._win = self._win, None
        if win is not None:
            try:
                win.destroy()
            except Exception:  # noqa: BLE001
                pass
