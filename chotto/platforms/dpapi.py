"""Mã hóa bí mật bằng Windows DPAPI (``CryptProtectData``/``CryptUnprotectData``).

Chỉ đúng tài khoản Windows đã mã hóa mới giải được (khóa gắn với mật khẩu đăng nhập), nên chép file sang máy/tài khoản
khác là vô dụng. Dùng cho khóa API riêng của nhân vật taskbar. Ngoài Windows mọi hàm ném ``OSError``.
"""
from __future__ import annotations

import ctypes
import sys
from typing import Any

__all__ = ["available", "protect", "unprotect"]

_ENTROPY = b"CHOTTO mascot BYOK v1"          # "muối" phụ: ứng dụng khác cùng tài khoản gọi DPAPI trần không giải được
_UI_FORBIDDEN = 0x1


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def available() -> bool:
    """Máy này có DPAPI không."""
    return sys.platform == "win32"


def _blob(data: bytes) -> tuple[_Blob, Any]:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf     # giữ ``buf`` sống tới khi gọi xong


def _run(encrypt: bool, data: bytes) -> bytes:
    if sys.platform != "win32":
        raise OSError("DPAPI chỉ có trên Windows")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32")
    data_in, _keep_in = _blob(data)
    entropy, _keep_e = _blob(_ENTROPY)
    out = _Blob()
    if encrypt:
        ok = crypt32.CryptProtectData(ctypes.byref(data_in), None, ctypes.byref(entropy), None, None, _UI_FORBIDDEN,
                                      ctypes.byref(out))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(data_in), None, ctypes.byref(entropy), None, None, _UI_FORBIDDEN,
                                        ctypes.byref(out))
    if not ok:
        raise OSError(ctypes.get_last_error(), "DPAPI " + ("mã hóa" if encrypt else "giải mã") + " thất bại")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def protect(data: bytes) -> bytes:
    """Mã hóa ``data`` cho tài khoản Windows hiện tại.

    Raises:
        OSError: Không phải Windows hoặc DPAPI lỗi.
    """
    return _run(True, data)


def unprotect(data: bytes) -> bytes:
    """Giải mã dữ liệu do ``protect`` tạo (cùng tài khoản Windows).

    Raises:
        OSError: Không phải Windows, dữ liệu hỏng hoặc của tài khoản khác.
    """
    return _run(False, data)
