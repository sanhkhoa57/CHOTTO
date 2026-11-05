"""Phía agent của giao diện HTML: khởi chạy, giữ sẵn và nói chuyện với tiến trình ``ui-host``.

``WebUI.present`` có cùng hợp đồng với ``ui.show_friction`` (trả ``(mở?, ms cân nhắc, kết quả đang hiện)``)
nên ``build_handler`` chỉ cần thử nó trước. Mọi sự cố (thiếu pywebview, host chết giữa chừng, không sẵn
sàng kịp) đều ném ``WebUIError`` để người gọi quay về giao diện Tk: chính sách fail-safe không đổi.
Đặt biến môi trường ``CHOTTO_UI=tk`` để luôn dùng Tk.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import IO, TYPE_CHECKING, Any, Final

from .. import platform_setup

if TYPE_CHECKING:
    from ..engine import Result

__all__ = ["WebUI", "WebUIError", "enabled"]

_LOG = logging.getLogger("chotto")

_CREATE_NO_WINDOW: Final[int] = 0x08000000
_POLL_S: Final[float] = 0.03
_MAX_FAILURES: Final[int] = 3            # host chết ngay ngần ấy lần liên tiếp thì thôi, dùng Tk cho phiên này

ViewOf = Callable[["Result", bool], dict[str, Any]]


class WebUIError(RuntimeError):
    """Giao diện HTML không dùng được cho lần hiển thị này (người gọi quay về Tk)."""


def enabled() -> bool:
    """``False`` khi người dùng ép dùng Tk (``CHOTTO_UI=tk``)."""
    return os.environ.get("CHOTTO_UI", "").strip().lower() != "tk"


@dataclass
class _Waiter:
    """Chỗ nhận quyết định của một màn hình đệm."""

    event: threading.Event = field(default_factory=threading.Event)
    proceed: bool | None = None
    dwell_ms: int = 0


class WebUI:
    """Một tiến trình ``ui-host`` dùng lại cho nhiều cửa sổ."""

    def __init__(self, argv: Callable[[], list[str]] = platform_setup.ui_host_argv, ready_timeout: float = 10.0) -> None:
        """Tạo (chưa khởi chạy).

        Args:
            argv: Lệnh chạy host.
            ready_timeout: Thời gian tối đa chờ host sẵn sàng (lần khởi động lạnh mất khoảng 1 giây).
        """
        self._argv = argv
        self._ready_timeout = ready_timeout
        self._proc: subprocess.Popen[str] | None = None
        self._stdin: IO[str] | None = None
        self._ready = threading.Event()
        self._dead = threading.Event()
        self._lock = threading.Lock()
        self._waiters: dict[int, _Waiter] = {}
        self._ids = itertools.count(1)
        self._failures = 0
        self._settings_open = False

    # ---- vòng đời tiến trình ----
    def start(self) -> bool:
        """Khởi chạy host nếu chưa chạy (không chờ); ``False`` nếu không chạy được."""
        with self._lock:
            if self._proc is not None and not self._dead.is_set():
                return True
            if self._failures >= _MAX_FAILURES:
                return False
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            try:
                proc = subprocess.Popen(
                    self._argv(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", bufsize=1, env=env, close_fds=True,
                    creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            except OSError:
                _LOG.exception("Không khởi chạy được giao diện HTML")
                self._failures += 1
                return False
            self._proc, self._stdin = proc, proc.stdin
            self._ready.clear()
            self._dead.clear()
        threading.Thread(target=self._read, args=(proc,), name="chotto-webui", daemon=True).start()
        return True

    def _read(self, proc: subprocess.Popen[str]) -> None:
        """Luồng đọc thông điệp của host đến khi host thoát."""
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if isinstance(message, dict):
                    self._on_message(message)
        except (OSError, ValueError):
            _LOG.info("Mất kết nối với giao diện HTML")
        finally:
            stdin: IO[str] | None = None
            with self._lock:
                if self._proc is proc:
                    if not self._ready.is_set():
                        self._failures += 1
                    self._dead.set()
                    self._settings_open = False
                    stdin, self._stdin = self._stdin, None
                    waiters = list(self._waiters.values())
                else:
                    waiters = []
            for waiter in waiters:
                waiter.event.set()            # proceed vẫn là None ⇒ present ném WebUIError
            for stream in (stdin, proc.stdout):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
            code: int | None = None
            try:
                code = proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            _LOG.info("Giao diện HTML đã thoát (mã %s)", code)

    def _on_message(self, message: dict[str, Any]) -> None:
        op = message.get("op")
        if op == "ready":
            self._failures = 0
            self._ready.set()
            _LOG.info("Giao diện HTML sẵn sàng (pid %s)", message.get("pid"))
        elif op == "decision":
            waiter = self._waiters.get(int(message.get("id", 0)))
            if waiter is not None:
                waiter.proceed = bool(message.get("proceed"))
                waiter.dwell_ms = int(message.get("dwell_ms", 0))
                waiter.event.set()
        elif op == "settings_closed":
            self._settings_open = False

    def _send(self, message: dict[str, Any]) -> None:
        stream = self._stdin
        if stream is None or self._dead.is_set():
            raise WebUIError("Giao diện HTML không chạy")
        try:
            stream.write(json.dumps(message, ensure_ascii=False) + "\n")
            stream.flush()
        except (OSError, ValueError) as exc:
            raise WebUIError("Không gửi được cho giao diện HTML") from exc

    def _wait_ready(self, pump: Callable[[], None]) -> None:
        if not self.start():
            raise WebUIError("Giao diện HTML không khởi chạy được")
        deadline = time.monotonic() + self._ready_timeout
        while not self._ready.is_set():
            if self._dead.is_set() or time.monotonic() > deadline:
                raise WebUIError("Giao diện HTML không sẵn sàng")
            pump()
            self._ready.wait(_POLL_S)

    def stop(self) -> None:
        """Yêu cầu host thoát (đóng stdin: host tự đóng mọi cửa sổ)."""
        with self._lock:
            stream, self._stdin = self._stdin, None
            proc = self._proc
        if stream is not None:
            try:
                stream.write(json.dumps({"op": "quit"}) + "\n")
                stream.close()
            except (OSError, ValueError):
                pass
        if proc is not None:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    # ---- các màn hình ----
    def present(self, view_of: ViewOf, result: Result, seconds_for: Callable[[str], int],
                pending: Future[Result] | None, pump: Callable[[], None]) -> tuple[bool, int, Result]:
        """Hiện màn hình đệm và chờ quyết định (cùng hợp đồng với ``ui.show_friction``).

        Args:
            view_of: Tạo dữ liệu hiển thị từ ``(kết quả, đang tra Tầng 3)``.
            result: Kết quả (sơ bộ nếu ``pending`` khác ``None``).
            seconds_for: Thời gian khóa theo mức rủi ro.
            pending: Kết quả cuối của Tầng 3 đang chạy nền.
            pump: Cho vòng lặp Tk xử lý sự kiện trong lúc chờ (giữ agent phản hồi).

        Raises:
            WebUIError: Không hiện được hoặc host chết trước khi có quyết định.
        """
        self._wait_ready(pump)
        fid = next(self._ids)
        waiter = _Waiter()
        self._waiters[fid] = waiter
        shown = result
        try:
            self._send({"op": "friction", "id": fid,
                        "payload": {"view": view_of(result, pending is not None), "lock_s": seconds_for(result.level)}})
            updated = pending is None
            while not waiter.event.wait(_POLL_S):
                pump()
                if not updated and pending is not None and pending.done():
                    final = pending.result()
                    updated = True
                    shown = final
                    self._send({"op": "update", "id": fid,
                                "payload": {"view": view_of(final, False), "lock_s": seconds_for(final.level)}})
        finally:
            self._waiters.pop(fid, None)
        if waiter.proceed is None:
            raise WebUIError("Giao diện HTML thoát trước khi người dùng quyết định")
        return waiter.proceed, waiter.dwell_ms, shown

    def open_settings(self, pump: Callable[[], None]) -> bool:
        """Mở cửa sổ ứng dụng; ``False`` nếu giao diện HTML không dùng được (người gọi mở bản Tk)."""
        try:
            self._wait_ready(pump)
            self._send({"op": "settings"})
        except WebUIError:
            _LOG.warning("Không mở được cửa sổ ứng dụng HTML, dùng Tk", exc_info=True)
            return False
        self._settings_open = True
        return True

    @property
    def settings_open(self) -> bool:
        """Cửa sổ ứng dụng HTML còn mở không."""
        return self._settings_open and not self._dead.is_set()
