"""Màn hình cảnh báo kiểu mới bằng Tkinter (đường lùi khi giao diện HTML không chạy được).

Cùng cấu trúc, cùng chữ và cùng bảng màu với giao diện HTML (``chotto/web/shield.*``) và tiện ích: dữ liệu đến từ
``chotto.shield.shield_view``. Mặc định chỉ có ba thứ: (a) một câu kết luận, (b) tên miền thật làm nổi bật,
(c) hành động; lý do chi tiết nằm trong mục thu gọn "Xem vì sao". Nút "vẫn mở" là ``Label`` (không nhận Enter/Space)
nên không thể bấm theo phản xạ bằng bàn phím; thanh tiến trình mảnh thay cho vòng đếm ngược của bản HTML.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, Final

import tkinter as tk

__all__ = ["Shield"]

BG: Final[str] = "#0c0a08"
PANEL: Final[str] = "#161310"
FG: Final[str] = "#f4efe7"
MUTED: Final[str] = "#b3aa9d"
LINE: Final[str] = "#3a352e"
ACCENT: Final[str] = "#c9a45a"
ACCENT_INK: Final[str] = "#17110a"
OK: Final[str] = "#7fc8a0"
TONES: Final[dict[str, tuple[str, str, str]]] = {      # (màu chính, màu chữ, nền tô sáng)
    "WARN": ("#e0a84a", "#f2c986", "#3a2c0f"),
    "HIGH": ("#e5484d", "#ffa598", "#3d1517"),
    "BLOCKED": ("#d93636", "#ffb4a8", "#4a1414"),
}
WIDTH: Final[int] = 480
_URL_CHARS: Final[int] = 30


class _Pill(tk.Label):
    """Nút dạng ``Label`` (không nhận phím); ``command`` chỉ chạy khi nút bật và được bấm bằng chuột."""

    def __init__(self, master: tk.Misc, text: str, command: Callable[[], None], bg: str, fg: str, font: tuple[str, int, str],
                 border: str = "", pady: int = 8) -> None:
        super().__init__(master, text=text, bg=bg, fg=fg, font=font, padx=16, pady=pady, cursor="hand2",
                         highlightthickness=1 if border else 0, highlightbackground=border or bg, highlightcolor=border or bg)
        self._command = command
        self._enabled = True
        self.bind("<ButtonRelease-1>", lambda _e: command() if self._enabled else None)

    def set_enabled(self, enabled: bool, text: str | None = None, fg: str | None = None) -> None:
        self._enabled = enabled
        self.config(cursor="hand2" if enabled else "arrow")
        if text is not None:
            self.config(text=text)
        if fg is not None:
            self.config(fg=fg)


class Shield:
    """Các widget của màn hình cảnh báo; ``render`` vẽ lại khi Tầng 3 trả kết quả (bố cục không nhảy)."""

    def __init__(self, top: tk.Toplevel, ui_font: str, mono_font: str, on_back: Callable[[], None],
                 on_proceed: Callable[[], None]) -> None:
        self._top = top
        self.copy_allowed: Callable[[], bool] | None = None      # kiểm lại lúc bấm "chép địa chỉ" (Guardian Mode)
        self._font = ui_font
        self._mono = mono_font
        self._view: dict[str, Any] = {}
        self._proceed_text = ""
        self._open = False
        self.accent_bar = tk.Frame(top, bg=BG, height=6)
        self.accent_bar.pack(fill="x")
        body = tk.Frame(top, bg=BG, padx=28, pady=20)
        body.pack(fill="both")

        head = tk.Frame(body, bg=BG)
        head.pack(fill="x")
        self.icon = tk.Canvas(head, width=48, height=48, bg=BG, highlightthickness=0)
        self.icon.pack(side="left")
        self.chip = tk.Label(head, text="", bg=BG, font=(ui_font, 11, "bold"), anchor="w")
        self.chip.pack(side="left", padx=(12, 0))
        self.headline = tk.Label(body, text="", bg=BG, fg=FG, font=(ui_font, 17, "bold"), wraplength=WIDTH, justify="left",
                                 anchor="w")
        self.headline.pack(fill="x", pady=(14, 0))
        self.sub = tk.Label(body, text="", bg=BG, fg=MUTED, font=(ui_font, 11), wraplength=WIDTH, justify="left", anchor="w")
        self.sub.pack(fill="x", pady=(4, 0))

        self.panel = tk.Frame(body, bg=PANEL, padx=16, pady=12)
        self.panel.pack(fill="x", pady=(16, 0))
        self.caption = tk.Label(self.panel, text="", bg=PANEL, fg=MUTED, font=(ui_font, 9, "bold"), anchor="w")
        self.caption.pack(fill="x")
        self.url = tk.Text(self.panel, width=_URL_CHARS, height=1, wrap="char", bd=0, highlightthickness=0, bg=PANEL, fg=FG,
                           font=(mono_font, 15), padx=0, pady=4, cursor="arrow", takefocus=0)
        self.url.pack(fill="x", pady=(4, 0))
        self.puny = tk.Label(self.panel, text="", bg=PANEL, fg=MUTED, font=(mono_font, 9), anchor="w")
        self.status = tk.Label(self.panel, text="", bg=PANEL, fg=MUTED, font=(ui_font, 10), wraplength=WIDTH - 40,
                               justify="left", anchor="w")

        self.why_toggle = tk.Label(body, text="", bg=BG, fg=MUTED, font=(ui_font, 11, "bold"), cursor="hand2", anchor="w")
        self.why_toggle.bind("<ButtonRelease-1>", lambda _e: self._toggle_why())
        self.why_toggle.pack(fill="x", pady=(10, 0))
        self.why = tk.Frame(body, bg=BG)

        self.back = _Pill(body, "", on_back, ACCENT, ACCENT_INK, (ui_font, 13, "bold"), pady=12)
        self.back.pack(fill="x", pady=(14, 0))
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(8, 0))
        row.columnconfigure((0, 1), weight=1, uniform="a")
        self.copy = _Pill(row, "", self._copy, BG, FG, (ui_font, 10, "bold"), border=LINE)
        self.copy.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.report = _Pill(row, "", self._report, BG, FG, (ui_font, 10, "bold"), border=LINE)
        self.report.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.proceed = _Pill(body, "", on_proceed, BG, MUTED, (ui_font, 9, "normal"), border=LINE, pady=5)
        self.proceed.pack(pady=(12, 0))
        self.progress = tk.Canvas(body, width=120, height=3, bg=BG, highlightthickness=0)
        self.progress.pack(pady=(4, 0))
        self._bar = self.progress.create_rectangle(0, 0, 0, 3, width=0, fill=BG)
        self.note = tk.Label(body, text="", bg=BG, fg=MUTED, font=(ui_font, 9))
        self.note.pack(pady=(6, 0))
        self.hint = tk.Label(body, text="", bg=BG, fg=MUTED, font=(ui_font, 9))
        self.hint.pack()
        self.guard = tk.Label(body, text="", bg=PANEL, fg=FG, font=(ui_font, 12, "bold"), wraplength=WIDTH - 40,
                              justify="left", padx=14, pady=12)

    # ---- vẽ ----
    def _draw_icon(self, level: str, main: str, ink: str) -> None:
        c = self.icon
        c.delete("all")
        if level == "BLOCKED":
            c.create_rectangle(0, 0, 48, 48, fill=main, width=0)
            c.create_rectangle(14, 22, 34, 38, outline=ink, width=3)
            c.create_arc(17, 10, 31, 30, start=0, extent=180, style="arc", outline=ink, width=3)
        elif level == "HIGH":
            points = [16, 6, 32, 6, 42, 16, 42, 32, 32, 42, 16, 42, 6, 32, 6, 16]
            c.create_polygon(points, outline=main, fill=PANEL, width=3)
            c.create_text(24, 24, text="!", fill=ink, font=(self._font, 18, "bold"))
        else:
            c.create_polygon(24, 6, 44, 40, 4, 40, outline=main, fill=PANEL, width=3, joinstyle="round")
            c.create_text(24, 29, text="!", fill=ink, font=(self._font, 15, "bold"))

    def _render_url(self, domain: dict[str, Any], tone: tuple[str, str, str]) -> None:
        text = self.url
        text.config(state="normal")
        text.delete("1.0", "end")
        text.tag_configure("dim", foreground=MUTED, font=(self._mono, 15))
        text.tag_configure("decoy", foreground=MUTED, overstrike=True, font=(self._mono, 15))
        text.tag_configure("reg", foreground=FG, font=(self._mono, 15, "bold"))
        text.tag_configure("hit", foreground=tone[1], background=tone[2], font=(self._mono, 15, "bold"))
        text.tag_configure("odd", foreground=tone[1], underline=True, font=(self._mono, 15, "bold"))
        if domain["userinfo"]:
            text.insert("end", domain["userinfo"], "decoy")
        if domain["prefix"]:
            text.insert("end", domain["prefix"], "decoy" if domain["decoyPrefix"] else "dim")
        registered = domain["registered"]
        hit = domain["hit"]
        start = registered.find(hit) if hit else -1
        for index, char in enumerate(registered):
            tags = ["reg"]
            if start >= 0 and start <= index < start + len(hit):
                tags.append("hit")
            if domain["punycode"] and ord(char) > 127:
                tags.append("odd")
            text.insert("end", char, tuple(tags))
        if domain["rest"]:
            text.insert("end", domain["rest"], "dim")
        total = len(domain["userinfo"]) + len(domain["prefix"]) + len(registered) + len(domain["rest"])
        text.config(height=max(1, math.ceil(total / _URL_CHARS)), state="disabled")

    def render(self, view: dict[str, Any], reserve: bool = False) -> None:
        """Vẽ ``view`` (từ ``chotto.shield.shield_view``); ``reserve``: giữ chỗ hai dòng cho câu kết luận khi Tầng 3 còn chạy."""
        level = view["level"] if view["level"] in TONES else "WARN"
        main, ink, _ = tone = TONES[level]
        self._view = view
        self.accent_bar.config(bg=main)
        self._draw_icon(level, main, "#ffffff" if level == "BLOCKED" else ink)
        self.chip.config(text=view["levelLabel"], fg=ink)
        self.headline.config(text=view["headline"], height=2 if reserve or view["checking"] else 0)
        self.sub.config(text=view["reasonShort"])
        self.caption.config(text=view["labels"]["caption"])
        self._render_url(view["domain"], tone)
        self.puny.pack_forget()
        self.status.pack_forget()
        if view["domain"]["punycode"]:
            self.puny.config(text=view["domain"]["punycode"])
            self.puny.pack(fill="x")
        if view["checking"]:
            self.status.config(text=view["labels"]["checking"], fg=MUTED)
            self.status.pack(fill="x", pady=(8, 0))
        elif view["officialLine"]:
            self.status.config(text="✓ " + view["officialLine"], fg=OK)
            self.status.pack(fill="x", pady=(8, 0))
        self.why_toggle.config(text=("▾ " if self._open else "▸ ") + view["labels"]["why"])
        for child in self.why.winfo_children():
            child.destroy()
        for row in view["details"]:
            tk.Label(self.why, text="•  " + row["text"], bg=BG, fg=FG, font=(self._font, 10), wraplength=WIDTH - 20,
                     justify="left", anchor="w").pack(fill="x", pady=2)
        if not view["details"]:
            self.why_toggle.pack_forget()
        elif not self.why_toggle.winfo_ismapped():
            self.why_toggle.pack(fill="x", pady=(10, 0), before=self.back)
        actions = view["actions"]
        self.back.config(text=actions["back"])
        self.copy.config(text=actions["copy"])
        self.report.config(text=actions["report"])
        self.hint.config(text=actions["hint"])
        self._proceed_text = actions["proceed"]
        self.progress.itemconfigure(self._bar, fill=main)
        self._render_guard(view.get("guardian"))

    def _render_guard(self, info: dict[str, str] | None) -> None:
        """Guardian Mode: lời nhắn, giấu nút sao chép địa chỉ; cấm thì bỏ hẳn nút "vẫn mở" (mức chỉ tăng)."""
        if not info:
            return
        self.guard.config(text=info["message"])
        if not self.guard.winfo_manager():
            self.guard.pack(fill="x", pady=(14, 0), before=self.back)
        self.copy.grid_remove()
        self.report.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0)
        if info["policy"] == "pin":
            self._proceed_text = info["pinLabel"]
        else:
            self.proceed.pack_forget()
            self.progress.pack_forget()

    def _toggle_why(self) -> None:
        self._open = not self._open
        if self._open:
            self.why.pack(fill="x", before=self.back)
        else:
            self.why.pack_forget()
        label = self._view["labels"]["why"]
        self.why_toggle.config(text=("▾ " if self._open else "▸ ") + label)

    # ---- hành động phụ (không gửi dữ liệu ra ngoài: chỉ chép vào clipboard) ----
    def _share(self, button: _Pill, text: str, done: str) -> None:
        old = str(button.cget("text"))
        self._top.clipboard_clear()
        self._top.clipboard_append(text)
        self.note.config(text=done)
        button.config(text=done)
        self._top.after(2200, lambda: button.winfo_exists() and button.config(text=old))

    def _copy(self) -> None:
        if self.copy_allowed is not None and not self.copy_allowed():     # Guardian vừa bật: chép địa chỉ là đường lách
            self.copy.grid_remove()
            return
        self._share(self.copy, self._view["actions"]["copyText"], self._view["actions"]["copied"])

    def _report(self) -> None:
        self._share(self.report, self._view["actions"]["reportText"], self._view["actions"]["reported"])

    def set_lock(self, remaining: float, total: float) -> None:
        """Cập nhật nút "vẫn mở": còn khóa thì mờ kèm thanh tiến trình mảnh, hết khóa thì bấm được."""
        left = math.ceil(max(0.0, remaining))
        width = 120 * max(0.0, min(1.0, remaining / max(total, 0.001)))
        self.progress.coords(self._bar, 0, 0, width, 3)
        if remaining > 0:
            self.proceed.set_enabled(False, f"{self._proceed_text} ({left})", MUTED)
        else:
            self.proceed.set_enabled(True, self._proceed_text, FG)
