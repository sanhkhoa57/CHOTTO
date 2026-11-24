"""Chạy nhân vật taskbar trên LUỒNG Tk RIÊNG, tách khỏi luồng Tk chính của agent.

Vì sao: luồng Tk chính của agent còn xử lý link, chờ màn hình cảnh báo (chỉ "bơm" Tk mỗi vài chục mili giây), mở cài đặt...
Dùng chung luồng đó thì mỗi lần nó bận (đúng lúc cảnh báo) nhân vật bị bóp nhịp hoặc đứng hình. Luồng riêng có vòng ``mainloop``
riêng nên nhịp vẽ không phụ thuộc agent đang làm gì.

Quy tắc: mọi thứ của Tk (cửa sổ, ``after``, biến Tk) chỉ được đụng ở luồng này. Ra ngoài chỉ có ``notify`` / ``request_reload``
(hàng đợi và cờ, an toàn mọi luồng) và ``stop``. Yêu cầu "mở ứng dụng" từ nhân vật phải do ``open_app`` tự chuyển về luồng chính
(vd. đặt một cờ để vòng lặp chính xử lý), không gọi Tk của luồng chính từ đây.
"""
from __future__ import annotations

import gc
import logging
import sys
import threading
from collections.abc import Callable
from typing import Any

from .taskbar import TaskbarMascot

__all__ = ["MascotRunner"]

_LOG = logging.getLogger("chotto")
_START_TIMEOUT_S = 5.0
_STOP_TIMEOUT_S = 2.0


class MascotRunner:
    """Giữ một ``TaskbarMascot`` chạy trên luồng nền có ``tk.Tk`` riêng. Mọi phương thức công khai đều không ném lỗi."""

    def __init__(self, open_app: Callable[[], None]) -> None:
        self._open_app = open_app
        self._mascot: TaskbarMascot | None = None
        self._root: Any = None
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Khởi động luồng nhân vật và đợi nó dựng xong (tối đa vài giây)."""
        # Chu kỳ nhường GIL mặc định 5 ms: luồng khác (xử lý link, cập nhật danh sách đen...) đang tính toán thì mỗi khung hình của nhân vật
        # phải chờ hàng chục mili giây. Hạ xuống 0,5 ms: đo được 11 -> 53 khung/giây dưới tải nặng, chi phí không đáng kể cho agent này.
        sys.setswitchinterval(0.0005)
        self._thread = threading.Thread(target=self._run, name="chotto-mascot-tk", daemon=True)
        self._thread.start()
        self._ready.wait(_START_TIMEOUT_S)

    def _run(self) -> None:
        root: Any = None
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            mascot = TaskbarMascot(root, self._open_app)
            self._root, self._mascot = root, mascot
            mascot.start()
        except Exception:  # noqa: BLE001 - phần trang trí không được làm chết agent
            _LOG.exception("Không khởi động được luồng nhân vật taskbar")
            self._mascot = None
            self._ready.set()
            return
        self._ready.set()
        try:
            root.mainloop()
        except Exception:  # noqa: BLE001
            _LOG.exception("Luồng nhân vật taskbar gặp lỗi")
        finally:
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass
            # Tcl chỉ được giải phóng ở đúng luồng đã tạo ra nó: bỏ mọi tham chiếu và thu gom NGAY TẠI ĐÂY.
            self._mascot = self._root = None
            root = None
            gc.collect()

    # ---- an toàn mọi luồng ----
    def notify(self, event: str, level: str = "") -> None:
        """Sự kiện từ ``LinkHandler`` (``warning_open`` / ``warning_closed``)."""
        mascot = self._mascot
        if mascot is not None:
            mascot.notify(event, level)

    def request_reload(self) -> None:
        """Cấu hình vừa đổi: nhân vật đọc lại ở khung hình tới."""
        mascot = self._mascot
        if mascot is not None:
            mascot.request_reload()

    def stop(self) -> None:
        """Gỡ nhân vật và kết thúc luồng (agent thoát)."""
        if self._root is None or self._mascot is None:
            return
        finished = threading.Event()

        def finish() -> None:                                    # chạy TRÊN luồng nhân vật (mọi tham chiếu Tk sống và chết ở đó)
            try:
                if self._mascot is not None:
                    self._mascot.stop()
            finally:
                if self._root is not None:
                    self._root.quit()
                finished.set()

        try:
            self._root.after(0, finish)
        except Exception:  # noqa: BLE001 - Tk đã chết: không còn gì để gỡ
            return
        finished.wait(_STOP_TIMEOUT_S)
        thread = self._thread
        if thread is not None:
            thread.join(_STOP_TIMEOUT_S)
