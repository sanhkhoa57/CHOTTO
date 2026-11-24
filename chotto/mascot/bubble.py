"""Bong bóng thoại + ô chat của nhân vật taskbar (cửa sổ Tk riêng, bám theo nhân vật; chạy trên luồng Tk của nhân vật).

Bong bóng (hình + chữ) do Pillow vẽ rồi đưa lên cửa sổ layered alpha từng điểm ảnh (``LayeredSurface``, như nhân vật): viền
và chữ khử răng cưa, không dùng màu khóa. Ô chat là cửa sổ Tk thường riêng, nằm ngay dưới bong bóng, chỉ hiện khi đang chat.
Bình thường không cửa sổ nào nhận focus (WS_EX_NOACTIVATE); chỉ khi mở ô chat mới nhận focus để gõ được, đóng thì trả lại.
Gọi API chạy trên luồng nền, kết quả về Tk qua hàng đợi (``after``).
"""
from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

from ..platforms import win32_window as w32
from . import speech

if TYPE_CHECKING:
    import tkinter as tk

__all__ = ["SpeechBubble"]

_LOG = logging.getLogger("chotto")
_INK: Final[str] = "#15101a"
_TYPE_MS: Final[int] = 18
_HIDE_MS: Final[int] = 9000
_MAX_TEXT_W: Final[int] = 300                  # bề rộng chữ tối đa (điểm ảnh ở 100%)
_TIP_X: Final[int] = 41                        # mũi đuôi cách mép PHẢI ảnh bong bóng chừng này (khớp ``speech._shape``: m + bóng + 20)


class SpeechBubble:
    """Một bong bóng duy nhất; ``say`` thay lời đang hiện. Không phương thức nào ném lỗi ra ngoài (``TaskbarMascot._safe`` bọc)."""

    def __init__(self, root: tk.Tk, unit_dpi: float, on_chat_change: Callable[[bool], None]) -> None:
        self._root = root
        self._u = unit_dpi
        self._on_chat_change = on_chat_change
        self._win: Any = None                       # cửa sổ layered chứa bong bóng
        self._hwnd = 0
        self._surface: w32.LayeredSurface | None = None
        self._barwin: Any = None                    # cửa sổ ô chat (dưới bong bóng)
        self._bar_hwnd = 0
        self._bar: Any = None
        self._entry: Any = None
        self._send: Any = None
        self._var: Any = None
        self._font: Any = None                      # font Pillow vẽ chữ trong bong bóng
        self._base: Any = None                      # ảnh bong bóng chưa có chữ (RGBA)
        self._lines: list[str] = []
        self._text_xy = (0, 0)
        self._line_h = 1
        self._frame = b""                           # khung hình đang hiện (BGRa), vẽ lại ở vị trí mới khi nhân vật chạy
        self._xy: tuple[int, int] | None = None     # góc trái trên bong bóng trên màn hình; None = chưa được đặt chỗ, chưa vẽ
        self._px = 16
        self._anchor: tuple[int, int, tuple[int, int, int, int]] | None = None   # (tip_x, sprite_top, vùng) của lần ``place`` gần nhất
        self._bar_shown = False
        self._size = (1, 1)                         # cỡ vùng gồm bong bóng (căn phải) + ô chat bên dưới
        self._img_w = 1
        self._img_h = 1
        self._visible = False
        self._chat = False
        self._busy = False
        self._type_job: str | None = None
        self._hide_job: str | None = None
        self._results: queue.Queue[tuple[str, speech.Kind]] = queue.Queue()
        self._geom: tuple[int, int, int, int] | None = None

    # ---- trạng thái ----
    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def chatting(self) -> bool:
        return self._chat

    # ---- dựng cửa sổ ----
    def _ensure(self) -> None:
        if self._win is not None:
            return
        import tkinter as tk

        u = self._u
        win = tk.Toplevel(self._root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        tk.Canvas(win, width=1, height=1, highlightthickness=0, bd=0).pack()                   # chỉ để có cửa sổ; hình đến từ LayeredSurface
        win.update_idletasks()
        self._hwnd = w32.toplevel_hwnd(int(win.winfo_id()))
        w32.make_tool_window(self._hwnd)
        w32.enable_layered(self._hwnd)
        barwin = tk.Toplevel(self._root)
        barwin.withdraw()
        barwin.overrideredirect(True)
        barwin.attributes("-topmost", True)
        barwin.update_idletasks()
        self._bar_hwnd = w32.toplevel_hwnd(int(barwin.winfo_id()))
        w32.make_tool_window(self._bar_hwnd)
        self._px = round(16 * u)
        self._font = speech.load_font(self._px)
        bar = tk.Frame(barwin, bg="#ffffff", highlightthickness=round(2 * u), highlightbackground=_INK, bd=0)
        bar.pack(fill="both", expand=True)
        self._var = tk.StringVar(master=win)                          # có master: luồng nhân vật dùng Tk riêng, không được rơi về Tk mặc định
        self._var.trace_add("write", lambda *_: self._clip())
        entry = tk.Entry(bar, textvariable=self._var, font=("Segoe UI", -round(14 * u)), relief="flat", bg="#f3eee8", fg=_INK,
                         insertbackground=_INK, bd=0)
        entry.pack(side="left", fill="x", expand=True, padx=(round(6 * u), round(4 * u)), pady=round(6 * u), ipady=round(5 * u))
        send = tk.Button(bar, text="Gửi", font=("Segoe UI", -round(13 * u), "bold"), bg=_INK, fg="#ffffff", activebackground="#333",
                         activeforeground="#ffffff", relief="flat", bd=0, padx=round(10 * u), command=self._submit)
        send.pack(side="left", pady=round(6 * u))
        close = tk.Button(bar, text="✕", font=("Segoe UI", -round(13 * u), "bold"), bg="#e8e1d6", fg=_INK, relief="flat", bd=0,
                          padx=round(8 * u), command=self.close_chat)
        close.pack(side="left", padx=round(6 * u), pady=round(6 * u))
        entry.bind("<Return>", lambda _e: self._submit())
        entry.bind("<Escape>", lambda _e: self.close_chat())
        self._win, self._barwin, self._bar, self._entry, self._send = win, barwin, bar, entry, send

    def _clip(self) -> None:
        value = self._var.get()
        if len(value) > speech.MAX_LEN:
            self._var.set(value[:speech.MAX_LEN])

    # ---- nói ----
    def say(self, kind: speech.Kind, text: str, keep: bool = False) -> None:
        """Hiện ``text`` trong bong bóng kiểu ``kind`` (gõ từng chữ). ``keep``: không tự ẩn (đang chat)."""
        self._ensure()
        self._cancel_jobs()
        u = self._u
        self._lines = speech.wrap_text(self._font, text, round(_MAX_TEXT_W * u))
        self._line_h = round(self._px * 1.4)
        text_w = max(round(self._font.getlength(line)) for line in self._lines) + 1
        img_w, img_h, tx, ty = speech.layout(kind, text_w, self._line_h * len(self._lines), u)
        self._img_w, self._img_h, self._text_xy = img_w, img_h, (tx, ty)
        self._base = speech.render_bubble(kind, img_w, img_h, u)
        bar_h = round(46 * u) if self._chat else 0
        win_w = max(img_w, round(340 * u)) if self._chat else img_w
        win_h = img_h + (bar_h + round(4 * u) if self._chat else 0)
        self._size = (win_w, win_h)
        old, self._surface = self._surface, w32.LayeredSurface(self._hwnd, img_w, img_h)
        if old is not None:
            old.close()
        self._geom = None
        self._xy = None
        self._visible = True
        self._paint(0)
        self._win.deiconify()
        self._win.attributes("-topmost", True)
        if self._anchor is not None:                                  # đã biết chỗ: hiện đúng vị trí ngay, khỏi đợi khung hình sau
            self.place(*self._anchor)
        total = sum(len(line) for line in self._lines)
        shown = 0

        def step() -> None:
            nonlocal shown
            shown = min(total, shown + 1)
            self._paint(shown)
            if shown < total:
                self._type_job = self._root.after(_TYPE_MS, step)
            else:
                self._type_job = None
                if not keep and not self._chat:
                    self._hide_job = self._root.after(_HIDE_MS, self.hide)

        step()

    def _paint(self, shown: int) -> None:
        """Vẽ bong bóng với ``shown`` ký tự đầu đã gõ rồi đẩy lên cửa sổ (nếu đã có vị trí)."""
        tx, ty = self._text_xy
        image = speech.paint_text(self._base, self._font, self._lines, tx, ty, self._line_h, shown)
        self._frame = image.convert("RGBa").tobytes("raw", "BGRa")
        self._push()

    def _push(self) -> None:
        if self._surface is not None and self._xy is not None and self._frame:
            self._surface.update(self._frame, *self._xy)

    def _cancel_jobs(self) -> None:
        for job in (self._type_job, self._hide_job):
            if job is not None:
                try:
                    self._root.after_cancel(job)
                except Exception:  # noqa: BLE001
                    pass
        self._type_job = self._hide_job = None

    def hide(self) -> None:
        """Ẩn bong bóng (đang chat thì giữ nguyên)."""
        if self._chat:
            return
        self._cancel_jobs()
        self._visible = False
        if self._win is not None:
            self._win.withdraw()

    def destroy(self) -> None:
        self._cancel_jobs()
        self._visible = self._chat = False
        surface, self._surface = self._surface, None
        if surface is not None:
            surface.close()
        wins, self._win, self._barwin = (self._win, self._barwin), None, None
        for win in wins:
            if win is not None:
                try:
                    win.destroy()
                except Exception:  # noqa: BLE001
                    pass

    # ---- đặt vị trí (gọi mỗi khung hình của nhân vật) ----
    def place(self, tip_x: int, sprite_top: int, area: tuple[int, int, int, int]) -> None:
        """Đuôi bong bóng chỉ xuống ``tip_x``; đáy bong bóng sát đỉnh nhân vật ``sprite_top``; kẹp trong vùng làm việc."""
        if not self._visible or self._win is None:
            return
        self._anchor = (tip_x, sprite_top, area)
        u = self._u
        width, height = self._size
        left, top, right, _bottom = area
        x = max(left, min(right - width, tip_x - width + round(_TIP_X * u)))
        y = max(top, sprite_top - height - round(2 * u))
        geom = (x, y, width, height)
        if geom == self._geom:
            return
        self._geom = geom
        self._xy = (x + width - self._img_w, y)                        # bong bóng căn phải trong vùng; ô chat (nếu có) ngay dưới
        self._push()
        if self._chat and self._barwin is not None:
            self._barwin.geometry(f"{width}x{round(46 * u)}+{x}+{y + self._img_h + round(4 * u)}")
            if not self._bar_shown:                                     # chỉ hiện sau khi đã có chỗ, khỏi nháy ở góc màn hình
                self._barwin.deiconify()
                self._barwin.attributes("-topmost", True)
                self._bar_shown = True

    # ---- chat ----
    def open_chat(self) -> None:
        """Mở ô nhập (nhận focus bàn phím)."""
        if self._chat:
            return
        self._ensure()
        self._chat = True
        self._busy = False
        self._var.set("")
        self._on_chat_change(True)
        self.say("normal", speech.pick("open"), keep=True)
        w32.set_noactivate(self._bar_hwnd, False)
        self._barwin.after(60, self._focus)

    def _focus(self, tries: int = 0) -> None:
        if self._barwin is None or not self._chat:
            return
        if not self._bar_shown and tries < 20:                          # ô chat chỉ hiện sau lần đặt chỗ đầu: chờ rồi thử lại
            self._barwin.after(40, lambda: self._focus(tries + 1))
            return
        try:
            self._barwin.focus_force()
            self._entry.focus_force()
        except Exception:  # noqa: BLE001
            _LOG.debug("Không đặt được focus cho ô chat", exc_info=True)

    def close_chat(self) -> None:
        if not self._chat:
            return
        self._chat = False
        self._busy = False
        if self._barwin is not None:
            w32.set_noactivate(self._bar_hwnd, True)
            self._barwin.withdraw()
        self._bar_shown = False
        self._on_chat_change(False)
        self._visible = False
        self._cancel_jobs()
        if self._win is not None:
            self._win.withdraw()

    def _submit(self) -> None:
        if self._busy or not self._chat:
            return
        text = self._var.get().strip()
        if not speech.check_input(text):                          # trượt bộ lọc: không gọi máy chủ
            self.say("alert", speech.pick("refuse"), keep=True)
            return
        self._busy = True                                         # bản cài trên máy: hỏi tự do (hạn mức ngày chỉ áp cho trang web)
        self._var.set("")
        self._entry.configure(state="disabled")
        self._send.configure(state="disabled")
        self.say("thought", speech.pick("loading"), keep=True)

        def work() -> None:
            self._results.put(speech.ask(text))

        threading.Thread(target=work, name="chotto-mascot-ask", daemon=True).start()
        self._root.after(150, self._poll_result)

    def _poll_result(self) -> None:
        try:
            reply, kind = self._results.get_nowait()
        except queue.Empty:
            if self._chat and self._busy:
                self._root.after(150, self._poll_result)
            return
        if not self._chat:
            return                                                  # đã đóng ô chat trong lúc chờ
        self._busy = False
        self._entry.configure(state="normal")
        self._send.configure(state="normal")
        self.say(kind, reply, keep=True)
        self._entry.focus_force()
