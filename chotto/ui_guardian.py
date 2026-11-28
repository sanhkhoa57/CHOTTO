"""Hộp thoại mã PIN giám hộ cho giao diện Tk dự phòng (tiếng Việt)."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog

from . import guardian

__all__ = ["ask_pin", "describe"]


def describe(result: guardian.AuthResult) -> str:
    """Câu báo lỗi xác thực."""
    if result.error == "locked":
        minutes, seconds = divmod(result.locked_for, 60)
        return f"Nhập sai quá nhiều lần. Thử lại sau {minutes}:{seconds:02d}."
    if result.error == "wrong":
        return f"Mã không đúng. Còn {result.attempts_left} lần thử."
    if result.error == "invalid_pin":
        return "Mã PIN mới phải gồm 4 đến 6 chữ số."
    return "Không đọc được dữ liệu giám hộ. Liên kết vẫn bị khóa."


def _forgot(parent: tk.Misc) -> None:
    """Đặt lại PIN bằng mã khôi phục và hiện mã khôi phục mới."""
    key = simpledialog.askstring("CHOTTO", "Nhập mã khôi phục đã lưu (CHOTTO-XXXX-XXXX-XXXX):", parent=parent)
    if not key:
        return
    new = simpledialog.askstring("CHOTTO", "Mã PIN mới (4 đến 6 chữ số):", show="•", parent=parent)
    if new is None:
        return
    again = simpledialog.askstring("CHOTTO", "Nhập lại mã PIN mới:", show="•", parent=parent)
    if again is None:
        return
    if new != again:
        messagebox.showerror("CHOTTO", "Hai lần nhập không giống nhau.", parent=parent)
        return
    result = guardian.recover(key, new)
    if not result.ok:
        messagebox.showerror("CHOTTO", describe(result), parent=parent)
        return
    messagebox.showinfo("CHOTTO", "Đã đặt PIN mới.\n\nMÃ KHÔI PHỤC MỚI (mã cũ hết hiệu lực):\n\n"
                        f"{result.recovery_key}\n\nHãy chụp ảnh bằng điện thoại hoặc ghi lại, không lưu trên máy này. "
                        "Chỉ bấm OK khi đã lưu xong.", parent=parent)


def ask_pin(parent: tk.Tk | tk.Toplevel, title: str) -> str | None:
    """Hỏi PIN đến khi đúng hoặc người dùng bỏ cuộc; trả về PIN đúng hoặc ``None``."""
    dialog = tk.Toplevel(parent)
    dialog.title("CHOTTO")
    dialog.resizable(False, False)
    dialog.attributes("-topmost", True)
    found: list[str] = []
    tk.Label(dialog, text=title, wraplength=320, justify="left").pack(padx=20, pady=(16, 8))
    entry = tk.Entry(dialog, show="•", width=12, justify="center", font=("", 16))
    entry.pack()
    status = tk.Label(dialog, text="", fg="#b3261e", wraplength=320)
    status.pack(padx=20, pady=(6, 0))

    def submit() -> None:
        pin = entry.get()
        result = guardian.verify_pin(pin)
        if result.ok:
            found.append(pin)
            dialog.destroy()
            return
        entry.delete(0, "end")
        status.config(text=describe(result))

    def forgot() -> None:
        _forgot(dialog)
        if dialog.winfo_exists():
            entry.focus_set()

    bar = tk.Frame(dialog)
    bar.pack(padx=20, pady=(10, 4))
    tk.Button(bar, text="Hủy", command=dialog.destroy, width=9).pack(side="left", padx=4)
    tk.Button(bar, text="Xác nhận", command=submit, width=9).pack(side="left", padx=4)
    tk.Button(dialog, text="Quên mã PIN?", command=forgot, relief="flat", fg="#1a56b0").pack(pady=(0, 12))
    dialog.bind("<Return>", lambda _e: submit())
    dialog.bind("<Escape>", lambda _e: dialog.destroy())
    dialog.update_idletasks()
    dialog.geometry(f"+{(dialog.winfo_screenwidth() - dialog.winfo_reqwidth()) // 2}"
                    f"+{(dialog.winfo_screenheight() - dialog.winfo_reqheight()) // 3}")
    try:
        dialog.grab_set()
    except tk.TclError:
        pass
    entry.focus_force()
    parent.wait_window(dialog)
    return found[0] if found else None
