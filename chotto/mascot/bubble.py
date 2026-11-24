"""Bong bóng thoại + ô chat của nhân vật taskbar (cửa sổ Tk riêng, bám theo nhân vật; chạy trên luồng Tk của agent).

Cửa sổ trong suốt theo màu khóa như cửa sổ nhân vật. Bình thường không nhận focus (WS_EX_NOACTIVATE); chỉ khi mở ô chat mới
nhận focus để gõ được, đóng ô chat thì trả lại. Gọi API chạy trên luồng nền, kết quả về Tk qua hàng đợi (``after``).
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
_KEY: Final[str] = "#ff00fe"
_INK: Final[str] = "#15101a"
_TYPE_MS: Final[int] = 18
_HIDE_MS: Final[int] = 9000
_MAX_TEXT_W: Final[int] = 300                  # bề rộng chữ tối đa (điểm ảnh ở 100%)


class SpeechBubble:
    """Một bong bóng duy nhất; ``say`` thay lời đang hiện. Không phương thức nào ném lỗi ra ngoài (``TaskbarMascot._safe`` bọc)."""

    def __init__(self, root: tk.Tk, unit_dpi: float, on_chat_change: Callable[[bool], None]) -> None:
        self._root = root
        self._u = unit_dpi
        self._on_chat_change = on_chat_change
        self._win: Any = None
        self._canvas: Any = None
        self._hwnd = 0
        self._bar: Any = None
        self._entry: Any = None
        self._send: Any = None
        self._var: Any = None
        self._font: Any = None
        self._photo: Any = None
        self._size = (1, 1)
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
        from tkinter import font as tkfont

        u = self._u
        win = tk.Toplevel(self._root)
        win.withdraw()
        win.overrideredirect(True)
        win.configure(bg=_KEY)
        win.attributes("-transparentcolor", _KEY)
        win.attributes("-topmost", True)
        canvas = tk.Canvas(win, width=10, height=10, bg=_KEY, highlightthickness=0, bd=0)
        canvas.pack()
        win.update_idletasks()
        self._hwnd = w32.toplevel_hwnd(int(win.winfo_id()))
        w32.make_tool_window(self._hwnd)
        self._font = tkfont.Font(root=self._root, family="Segoe UI", size=-round(15 * u), weight="bold")
        bar = tk.Frame(canvas, bg="#ffffff", highlightthickness=round(2 * u), highlightbackground=_INK, bd=0)
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
        self._win, self._canvas, self._bar, self._entry, self._send = win, canvas, bar, entry, send

    def _clip(self) -> None:
        value = self._var.get()
        if len(value) > speech.MAX_LEN:
            self._var.set(value[:speech.MAX_LEN])

    def _wrap(self, text: str) -> list[str]:
        limit = round(_MAX_TEXT_W * self._u)
        lines: list[str] = []
        current = ""
        for word in text.split():
            trial = f"{current} {word}".strip()
            if current and self._font.measure(trial) > limit:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        return lines or [""]

    # ---- nói ----
    def say(self, kind: speech.Kind, text: str, keep: bool = False) -> None:
        """Hiện ``text`` trong bong bóng kiểu ``kind`` (gõ từng chữ). ``keep``: không tự ẩn (đang chat)."""
        from PIL import ImageTk

        self._ensure()
        self._cancel_jobs()
        u = self._u
        lines = self._wrap(text)
        line_h = self._font.metrics("linespace")
        text_w = max(self._font.measure(line) for line in lines)
        img_w, img_h, tx, ty = speech.layout(kind, text_w, line_h * len(lines), u)
        self._img_w, self._img_h = img_w, img_h
        self._photo = ImageTk.PhotoImage(self._flat(speech.render_bubble(kind, img_w, img_h, u)), master=self._win)
        bar_h = round(46 * u) if self._chat else 0
        win_w = max(img_w, round(340 * u)) if self._chat else img_w
        win_h = img_h + (bar_h + round(4 * u) if self._chat else 0)
        self._size = (win_w, win_h)
        canvas = self._canvas
        canvas.configure(width=win_w, height=win_h)
        canvas.delete("all")
        canvas.create_image(win_w - img_w, 0, image=self._photo, anchor="nw")
        items = [canvas.create_text(win_w - img_w + tx, ty + i * line_h, text="", anchor="nw", font=self._font, fill=_INK)
                 for i in range(len(lines))]
        if self._chat:
            canvas.create_window(0, img_h + round(4 * u), window=self._bar, anchor="nw", width=win_w, height=bar_h)
        self._geom = None
        self._visible = True
        self._win.deiconify()
        self._win.attributes("-topmost", True)
        total = sum(len(line) for line in lines)
        shown = 0

        def step() -> None:
            nonlocal shown
            shown = min(total, shown + 1)
            left = shown
            for item, line in zip(items, lines, strict=True):
                canvas.itemconfigure(item, text=line[:max(0, min(len(line), left))])
                left -= len(line)
            if shown < total:
                self._type_job = self._root.after(_TYPE_MS, step)
            else:
                self._type_job = None
                if not keep and not self._chat:
                    self._hide_job = self._root.after(_HIDE_MS, self.hide)

        step()

    @staticmethod
    def _flat(image: Any) -> Any:
        """RGBA → RGB trên nền màu khóa (điểm trong suốt thành màu khóa)."""
        from PIL import Image

        flat = Image.new("RGB", image.size, (255, 0, 254))
        flat.paste(image.convert("RGB"), mask=image.getchannel("A"))
        return flat

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
        win, self._win = self._win, None
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
        width, height = self._size
        left, top, right, _bottom = area
        x = max(left, min(right - width, tip_x - width + round(44 * self._u)))
        y = max(top, sprite_top - height - round(2 * self._u))
        geom = (x, y, width, height)
        if geom != self._geom:
            self._win.geometry(f"{width}x{height}+{x}+{y}")
            self._geom = geom

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
        w32.set_noactivate(self._hwnd, False)
        self._win.after(60, self._focus)

    def _focus(self) -> None:
        try:
            self._win.focus_force()
            self._entry.focus_force()
        except Exception:  # noqa: BLE001
            _LOG.debug("Không đặt được focus cho ô chat", exc_info=True)

    def close_chat(self) -> None:
        if not self._chat:
            return
        self._chat = False
        self._busy = False
        if self._win is not None:
            w32.set_noactivate(self._hwnd, True)
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
        if speech.quota_left() <= 0:
            self.say("normal", speech.pick("quota"), keep=True)
            return
        speech.quota_use()
        self._busy = True
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
