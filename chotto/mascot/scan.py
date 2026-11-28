"""Một lượt quét QR: chụp màn hình → kéo chọn → giải mã + thẩm định trên luồng nền → trả báo cáo về luồng Tk."""
from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

from . import qr, snip

if TYPE_CHECKING:
    import tkinter as tk

__all__ = ["QrScan"]

_LOG = logging.getLogger("chotto")
_SETTLE_MS: Final[int] = 180                   # đợi bong bóng/nhân vật biến khỏi màn hình rồi mới chụp
_POLL_MS: Final[int] = 100


class QrScan:
    """Chỉ một lượt tại một thời điểm.

    ``safe``: bọc mọi callback chạy trên Tk (``TaskbarMascot._safe``). ``on_capturing(True)``: đang chụp/chọn vùng (giấu nhân vật);
    ``on_capturing(False)``: xong phần chọn. ``on_reading``: đang giải mã. ``on_report``: có kết quả.
    """

    def __init__(self, root: tk.Tk, unit_dpi: float, safe: Callable[[Callable[[], None]], None],
                 on_capturing: Callable[[bool], None], on_reading: Callable[[], None],
                 on_report: Callable[[qr.QrReport], None]) -> None:
        self._root = root
        self._u = unit_dpi
        self._safe = safe
        self._on_capturing = on_capturing
        self._on_reading = on_reading
        self._on_report = on_report
        self._generation = 0                    # kết quả của lượt đã hủy thì bỏ
        self._overlay: Any = None
        self._lang = "en"
        self.capturing = False

    def start(self, lang: str) -> None:
        if self.capturing:
            return
        self._generation += 1
        generation = self._generation
        self._lang = lang
        self.capturing = True
        self._on_capturing(True)
        self._root.after(_SETTLE_MS, lambda: self._safe(lambda: self._capture(generation)))

    def cancel(self) -> None:
        """Hủy lượt đang chạy (đang chọn vùng hoặc đang giải mã)."""
        self._generation += 1
        overlay, self._overlay = self._overlay, None
        if overlay is not None:
            overlay.cancel()
        self._end_capture()

    def _end_capture(self) -> None:
        if self.capturing:
            self.capturing = False
            self._on_capturing(False)

    def _capture(self, generation: int) -> None:
        if generation != self._generation:
            return
        try:
            image, origin, scale = snip.grab_screen()
            def register(overlay: snip.SnipOverlay) -> None:
                # Ghi nhận trước khi hàm dựng xử lý sự kiện Tk (macOS: update() có thể mở màn cảnh báo rồi gọi cancel()).
                self._overlay = overlay

            overlay = snip.SnipOverlay(self._root, image, origin, qr.texts(self._lang)["hint"], self._u,
                                       lambda picked: self._safe(lambda: self._picked(generation, picked)), scale,
                                       register=register)
            if generation != self._generation:          # lượt đã bị hủy trong lúc dựng: không để lớp phủ sót lại
                overlay.cancel()
                return
        except snip.ScreenPermissionError:          # macOS: chưa cấp quyền Ghi màn hình (Cài đặt vừa được mở sẵn)
            _LOG.info("Chưa có quyền Ghi màn hình để quét QR")
            self._end_capture()
            self._on_report(qr.QrReport("failed", qr.texts(self._lang)["permission"]))
        except Exception:  # noqa: BLE001 - không chụp/dựng được lớp phủ: báo lỗi, nhân vật chạy tiếp
            if generation != self._generation:          # bị hủy giữa lúc dựng (cửa sổ đã đóng): không báo lỗi
                return
            _LOG.exception("Không mở được chế độ chọn vùng quét QR")
            self._end_capture()
            self._on_report(qr.QrReport("failed", qr.texts(self._lang)["failed"]))

    def _picked(self, generation: int, image: Any) -> None:
        if generation != self._generation:
            return
        self._overlay = None
        self._end_capture()
        if image is not None:
            self._decode(generation, image)

    def _decode(self, generation: int, image: Any) -> None:
        results: queue.Queue[qr.QrReport] = queue.Queue()
        lang = self._lang
        self._on_reading()
        threading.Thread(target=lambda: results.put(qr.scan(image, lang)), name="chotto-mascot-qr", daemon=True).start()

        def poll() -> None:
            if generation != self._generation:
                return
            try:
                report = results.get_nowait()
            except queue.Empty:
                self._root.after(_POLL_MS, lambda: self._safe(poll))
                return
            self._on_report(report)

        self._root.after(_POLL_MS, lambda: self._safe(poll))
