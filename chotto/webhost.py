"""Tiến trình giao diện HTML (``main.py ui-host``): vẽ màn hình đệm và cửa sổ ứng dụng bằng pywebview.

pywebview đòi chạy trên luồng chính, mà luồng chính của agent đã thuộc về Tk (IPC, Apple Event). Vì vậy
giao diện chạy trong một tiến trình con được agent giữ sẵn (cửa sổ sau hiện trong khoảng 0,2 giây) và
nói chuyện với agent bằng từng dòng JSON:

  agent → host:  {"op": "friction", "id", "payload": {"view", "lock_s"}}
                 {"op": "update", "id", "payload": {"view", "lock_s"}}
                 {"op": "settings"}   {"op": "quit"}
  host → agent:  {"op": "ready", "pid"}
                 {"op": "decision", "id", "proceed", "dwell_ms"}
                 {"op": "settings_closed"}
                 {"op": "config_changed"}   (cửa sổ ứng dụng vừa lưu cài đặt: agent đọc lại ngay, ví dụ nhân vật taskbar)

Chính sách an toàn: host tự kiểm lại thời gian khóa nút "vẫn mở" (không tin JavaScript), đóng cửa sổ
bằng bất kỳ cách nào đều là "không mở", và agent mất liên lạc (stdin đóng) thì host tự thoát. Mọi lỗi
của host khiến agent quay về giao diện Tk (``chotto/service/webui.py``).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, TextIO

from . import __version__, logdb, platforms
from .config import SETTINGS_KEYS, load_config, resource_path
from .messages import msg as _msg
from .platforms import win32_window
from .platforms import window as osw
from .core.url import SUPPORTED_SCHEMES, get_scheme
from .tier1 import last_update_success
from .viewmodel import friction_view

if TYPE_CHECKING:
    from .engine import Engine

__all__ = ["AppApi", "FrictionApi", "Host", "run_host"]

_LOG = logging.getLogger("chotto")

BG: Final[str] = "#0c0a08"
_APP_BG: Final[str] = "#fbf6f1"                 # nền sáng của cửa sổ ứng dụng (tránh chớp đen lúc mở)
_APP_W: Final[int] = 420                         # cửa sổ ứng dụng theo tỉ lệ điện thoại (~9:19,5)
_APP_H: Final[int] = 880
_UNLOCK_SLACK_S: Final[float] = 0.25          # bù độ trễ hiển thị của đồng hồ đếm ngược phía JavaScript
_MAX_CHECK_URL: Final[int] = 4096


def _mascot_supported() -> bool:
    """Máy này hiện được nhân vật taskbar không (để cửa sổ ứng dụng báo "chỉ có trên Windows")."""
    from . import mascot

    return mascot.supported()


def web_root() -> Path:
    """Thư mục ``chotto/web`` (HTML, CSS, JS, font) cả khi chạy mã nguồn lẫn khi đóng gói."""
    return resource_path("web")


class Wire:
    """Đầu ghi giao thức (một dòng JSON mỗi thông điệp), an toàn giữa nhiều luồng."""

    def __init__(self, out: TextIO) -> None:
        """Ghi vào ``out`` (stdout thật của tiến trình)."""
        self._out = out
        self._lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> None:
        """Gửi một thông điệp; agent đã thoát thì bỏ qua."""
        line = json.dumps(message, ensure_ascii=False)
        with self._lock:
            try:
                self._out.write(line + "\n")
                self._out.flush()
            except (OSError, ValueError):
                _LOG.info("Không gửi được thông điệp cho agent (agent đã thoát?)")


def _when_shown(window: Any, handler: Callable[[], None]) -> None:
    """Gọi ``handler`` khi cửa sổ đã hiện, kể cả khi sự kiện ``shown`` đã phát xong TRƯỚC lúc đăng ký.

    Cửa sổ tạo sau ``webview.start`` có thể hiện ngay trên luồng giao diện; nếu chỉ ``events.shown += handler`` thì
    có lúc handler không bao giờ chạy (cửa sổ cảnh báo không được căn giữa / không lấy focus). Gọi trùng thì vô hại.
    """
    window.events.shown += handler
    is_set = getattr(window.events.shown, "is_set", None)
    if callable(is_set) and is_set():
        threading.Thread(target=handler, name="chotto-shown", daemon=True).start()


class FrictionApi:
    """Cầu nối JavaScript của một màn hình đệm. Chỉ các phương thức không có dấu ``_`` được lộ ra JS."""

    def __init__(self, fid: int, payload: dict[str, Any], lock_s: float, wire: Wire,
                 on_done: Callable[[int], None]) -> None:
        """Tạo cầu nối cho màn hình đệm ``fid``.

        Args:
            fid: Mã màn hình đệm (do agent đặt).
            payload: ``{"view", "lock_s"}`` ban đầu.
            lock_s: Số giây khóa nút "vẫn mở".
            wire: Kênh gửi quyết định về agent.
            on_done: Gọi khi đã có quyết định (để host đóng cửa sổ).
        """
        self._fid = fid
        self._payload = payload
        self._opened = time.monotonic()
        self._unlock_at = self._opened + max(0.0, lock_s)
        self._wire = wire
        self._on_done = on_done
        self._done = False
        self._lock = threading.Lock()
        self._window: Any = None

    def initial(self) -> dict[str, Any]:
        """Dữ liệu hiển thị hiện hành (JS gọi khi trang sẵn sàng)."""
        with self._lock:
            return self._payload

    def decide(self, proceed: bool) -> dict[str, bool]:
        """Người dùng chọn; "vẫn mở" trước khi hết giờ khóa bị từ chối."""
        with self._lock:
            if self._done:
                return {"ok": True}
            if proceed and time.monotonic() < self._unlock_at - _UNLOCK_SLACK_S:
                return {"ok": False}
            self._done = True
        self._finish(bool(proceed))
        return {"ok": True}

    def minimize(self) -> None:
        """Thu nhỏ cửa sổ."""
        if self._window is not None:
            self._window.minimize()

    def _finish(self, proceed: bool) -> None:
        dwell_ms = int((time.monotonic() - self._opened) * 1000)
        self._wire.send({"op": "decision", "id": self._fid, "proceed": proceed, "dwell_ms": dwell_ms})
        self._on_done(self._fid)

    def _update(self, payload: dict[str, Any], lock_s: float) -> None:
        """Tầng 3 xong: thay dữ liệu và kéo dài thời gian khóa (tính từ lúc mở cửa sổ, chỉ tăng)."""
        with self._lock:
            if self._done:
                return
            self._payload = payload
            self._unlock_at = max(self._unlock_at, self._opened + max(0.0, lock_s))
        if self._window is not None:
            try:
                self._window.evaluate_js(f"window.CHOTTO && window.CHOTTO.update({json.dumps(payload)})")
            except Exception:  # noqa: BLE001 - trang chưa sẵn sàng: initial() sẽ trả dữ liệu mới
                _LOG.debug("Chưa cập nhật được màn hình đệm", exc_info=True)

    def _closed(self) -> None:
        """Cửa sổ bị đóng (nút X của hệ thống, Alt+F4...): luôn là "không mở"."""
        with self._lock:
            if self._done:
                return
            self._done = True
        self._finish(False)


def _settings_of(cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Các khóa cài đặt mà cửa sổ ứng dụng được xem và sửa."""
    return {key: cfg[key] for key in SETTINGS_KEYS}


def _blacklist_text(stamp: float | None, now: datetime | None = None, lang: str = "en") -> str:
    """Câu mô tả lần cập nhật danh sách lừa đảo gần nhất."""
    if stamp is None:
        return _msg(lang, "never")
    when = datetime.fromtimestamp(stamp)
    today = (now or datetime.now()).date()
    if when.date() == today:
        return _msg(lang, "today", time=f"{when:%H:%M}")
    if (today - when.date()).days == 1:
        return _msg(lang, "yesterday", time=f"{when:%H:%M}")
    return _msg(lang, "date", date=f"{when:%d/%m/%Y}")


class AppApi:
    """Cầu nối JavaScript của cửa sổ ứng dụng (Tổng quan, Kiểm tra link, Nhật ký, Cài đặt)."""

    def __init__(self, host: Host) -> None:
        """Gắn với ``host`` (để lấy cửa sổ khi mở hộp thoại lưu file)."""
        self._host = host
        self._engine: Engine | None = None
        self._engine_lock = threading.Lock()

    def state(self) -> dict[str, Any]:
        """Toàn bộ dữ liệu cho cửa sổ."""
        cfg = load_config()
        return {
            "version": __version__,
            "settings": _settings_of(cfg),
            "summary": logdb.summary(7),
            "recent": logdb.recent(30) if cfg["log_decisions"] else [],
            "default_handler": platforms.is_default_handler(),
            "blacklist_text": _blacklist_text(last_update_success(), lang=cfg["ui_language"]),
            "mascot_supported": _mascot_supported(),
        }

    def save(self, values: dict[str, Any]) -> dict[str, Any]:
        """Lưu ngay các khóa cài đặt được phép (giá trị sai được ``validate_config`` đưa về hợp lệ)."""
        from .service.app import save_settings

        lang = load_config()["ui_language"]
        clean = {key: values[key] for key in SETTINGS_KEYS if isinstance(values, dict) and key in values}
        try:
            save_settings(clean)
        except OSError as exc:
            _LOG.exception("Không lưu được cấu hình")
            return {"ok": False, "error": _msg(lang, "save_failed", error=exc)}
        self._host.config_changed()
        return {"ok": True, "settings": _settings_of(load_config())}

    def mascot_place(self, on: bool) -> None:
        """Bật/tắt chế độ "chọn vị trí" bằng file cờ (cửa sổ này có thể không cùng tiến trình với agent)."""
        from . import mascot

        mascot.set_place_flag(bool(on))

    def mascot(self) -> dict[str, Any]:
        """Sprite, mask (data URL) và tham số tô màu cho phần xem trước nhân vật (JavaScript tô màu tại chỗ)."""
        import base64

        from . import mascot

        try:
            poses = []
            for n in range(4):
                pair = {}
                for key, name in (("img", "pose"), ("mask", "mask")):
                    raw = resource_path("mascot", "assets", f"{name}_{n}.png").read_bytes()
                    pair[key] = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
                poses.append(pair)
            palette = mascot.load_palette()
        except (OSError, ValueError, KeyError):
            _LOG.exception("Không đọc được asset nhân vật")
            return {"ok": False, "supported": False}
        return {"ok": True, "supported": mascot.supported(), "poses": poses,
                "palette": {"default": list(palette.default), "pivot": list(palette.pivot),
                            "params": [list(p) for p in palette.params],
                            "swatches": [list(s) for s in palette.swatches]}}

    def check(self, url: str) -> dict[str, Any]:
        """Kiểm tra một link người dùng dán vào (không mở trang)."""
        from .engine import Engine

        lang = load_config()["ui_language"]
        text = str(url).strip()[:_MAX_CHECK_URL]
        if not text:
            return {"ok": False, "error": _msg(lang, "empty")}
        if get_scheme(text) not in SUPPORTED_SCHEMES:
            text = "https://" + text.split("://", 1)[-1]
        try:
            with self._engine_lock:
                if self._engine is None:
                    self._engine = Engine(load_config())
                try:
                    result = self._engine.inspect(text)
                finally:
                    self._engine.release()
                rules = self._engine.rules
        except Exception:  # noqa: BLE001 - trả lỗi về giao diện thay vì làm treo lời gọi JS
            _LOG.exception("Kiểm tra link thủ công lỗi")
            return {"ok": False, "error": _msg(lang, "check_failed")}
        if result.tier_reached == 0:
            return {"ok": False, "error": _msg(lang, "not_link")}
        if result.level == "SAFE":
            return {"ok": True, "level": "SAFE", "score": result.score, "domain": result.display_domain or result.host}
        return {"ok": True, "level": result.level, "score": result.score,
                "view": friction_view(result, False, rules, lang)}

    def action(self, name: str) -> dict[str, Any]:
        """Chạy tác vụ: ``install`` | ``uninstall`` | ``update`` | ``export`` (câu trả lời theo ``ui_language``)."""
        from .service import app as service

        lang = load_config()["ui_language"]
        try:
            if name == "install":
                return {"ok": True, "message": service.install_action(lang)}
            if name == "uninstall":
                return {"ok": True, "message": service.uninstall_action(lang)}
            if name == "update":
                return {"ok": True, "message": service.update_action(lang)}
            if name == "export":
                path = self._host.ask_save_path("chotto_log.csv")
                return {"ok": True, "message": service.export_action(path, lang) if path else ""}
        except Exception as exc:  # noqa: BLE001 - lỗi của tác vụ phải về được giao diện
            _LOG.exception("Tác vụ '%s' lỗi", name)
            return {"ok": False, "message": _msg(lang, "failed", error=exc)}
        return {"ok": False, "message": _msg(lang, "unknown")}

    def window(self, op: str) -> None:
        """Điều khiển cửa sổ từ thanh tiêu đề tự vẽ."""
        self._host.app_window_op(op)

    def resize_begin(self, edge: str) -> None:
        """Bắt đầu kéo giãn cửa sổ từ mép/góc ``edge`` (tổ hợp các chữ n, s, e, w)."""
        self._host.app_resize_begin(str(edge))

    def resize_move(self, dx: float, dy: float) -> None:
        """Kéo giãn tiếp: ``dx``, ``dy`` là độ dời con trỏ (điểm ảnh vật lý) từ lúc bắt đầu."""
        self._host.app_resize_move(float(dx), float(dy))


class Host:
    """Vòng đời các cửa sổ pywebview trong tiến trình giao diện."""

    def __init__(self, wire: Wire, webview: Any, read_line: Callable[[], str]) -> None:
        """Tạo host.

        Args:
            wire: Kênh gửi về agent.
            webview: Mô-đun ``webview`` (tiêm vào để kiểm thử).
            read_line: Đọc một dòng từ agent (rỗng = agent đã đóng kết nối).
        """
        self._wire = wire
        self._webview = webview
        self._read_line = read_line
        self._frictions: dict[int, tuple[Any, FrictionApi]] = {}
        self._app_window: Any = None
        self._app_maximized = False
        self._faded_out = False           # cửa sổ đang mờ hẳn vì thu nhỏ xuống thanh tác vụ
        self._normal_rect: tuple[int, int, int, int] | None = None
        self._anim_busy = False
        self._resize: tuple[int, set[str], tuple[int, int, int, int], float] | None = None
        self._keeper: Any = None
        self._lock = threading.Lock()

    # ---- màn hình đệm ----
    def _friction_height(self) -> int:
        try:
            screen_h = int(self._webview.screens[0].height)
        except Exception:  # noqa: BLE001 - không đọc được màn hình: dùng cỡ an toàn
            screen_h = 900
        return max(560, min(740, screen_h - 80))

    def _centered(self, width: int, height: int) -> dict[str, int]:
        """``x``/``y`` để cửa sổ ``width`` x ``height`` nằm giữa màn hình chính (không chỉ vị trí thì Windows xếp vào góc)."""
        try:
            screen = self._webview.screens[0]
            return {"x": max(0, (int(screen.width) - width) // 2), "y": max(0, (int(screen.height) - height) // 2)}
        except Exception:  # noqa: BLE001 - không đọc được màn hình: để hệ điều hành tự đặt
            return {}

    def open_friction(self, fid: int, payload: dict[str, Any]) -> None:
        """Mở màn hình đệm ``fid``."""
        api = FrictionApi(fid, payload, float(payload.get("lock_s", 0)), self._wire, self._close_friction)
        height = self._friction_height()
        window = self._webview.create_window(
            _msg(str(payload.get("view", {}).get("lang", "en")), "friction_title"),
            url=str(web_root() / "friction.html"), js_api=api,
            width=620, height=height, min_size=(460, 520), frameless=True, easy_drag=False,
            on_top=True, background_color=_APP_BG, text_select=True, **self._centered(620, height))
        api._window = window  # noqa: SLF001 - cùng mô-đun
        osw.reload_on_show(window, str(web_root() / "friction.html"))
        with self._lock:
            self._frictions[fid] = (window, api)
        window.events.closed += lambda: self._on_friction_closed(fid)
        _when_shown(window, lambda: osw.center_on_screen(window, 620, 740))
        _when_shown(window, lambda: osw.activate(window))
        if osw.REFOCUS_ON_LOAD:
            window.events.loaded += lambda: osw.activate(window)             # trang tải xong: lấy focus lần nữa để Esc dùng được ngay

    def _on_friction_closed(self, fid: int) -> None:
        with self._lock:
            entry = self._frictions.pop(fid, None)
        if entry is not None:
            entry[1]._closed()  # noqa: SLF001

    def _close_friction(self, fid: int) -> None:
        with self._lock:
            entry = self._frictions.pop(fid, None)
        if entry is not None:
            try:
                entry[0].destroy()
            except Exception:  # noqa: BLE001 - cửa sổ đã đóng
                _LOG.debug("Cửa sổ đệm đã đóng", exc_info=True)

    def update_friction(self, fid: int, payload: dict[str, Any]) -> None:
        """Cập nhật màn hình đệm đang mở."""
        with self._lock:
            entry = self._frictions.get(fid)
        if entry is not None:
            entry[1]._update(payload, float(payload.get("lock_s", 0)))  # noqa: SLF001

    # ---- cửa sổ ứng dụng ----
    def open_settings(self) -> None:
        """Mở (hoặc đưa lên trước) cửa sổ ứng dụng."""
        if self._app_window is not None:
            try:
                self._app_window.restore()
                self._app_window.show()
                osw.activate(self._app_window)
                self._reveal_if_faded()
                return
            except Exception:  # noqa: BLE001 - cửa sổ cũ hỏng: tạo cửa sổ mới
                self._app_window = None
        window = self._webview.create_window(
            "Chotto", url=str(web_root() / "app.html"), js_api=AppApi(self), width=_APP_W, height=_APP_H,
            min_size=(360, 640), frameless=True, easy_drag=False, background_color=_APP_BG, text_select=True,
            hidden=osw.HIDE_UNTIL_LOADED, **self._centered(_APP_W, _APP_H))   # Windows: ẩn hẳn tới khi trang tải xong (không nháy)
        self._app_window = window
        osw.reload_on_show(window, str(web_root() / "app.html"))
        window.events.closed += self._on_settings_closed
        _when_shown(window, lambda: osw.center_on_screen(window, _APP_W, _APP_H))
        _when_shown(window, lambda: osw.activate(window))
        window.events.shown += lambda: osw.enable_snap(window)
        window.events.shown += lambda: osw.set_icon(window, str(web_root().parent.parent / "packaging" / "chotto.ico"))
        opened = threading.Event()

        def reveal() -> None:
            if not opened.is_set():
                opened.set()
                osw.fade(window, 0, 0, 0)                                   # trong suốt hoàn toàn TRƯỚC khi hiện, để không nháy
                try:
                    window.show()
                except Exception:  # noqa: BLE001 - cửa sổ đã đóng
                    return
                osw.activate(window)
                osw.fade(window, 0, 255, 220)

        window.events.loaded += lambda: threading.Timer(0.12, reveal).start()
        threading.Timer(2.5, reveal).start()                             # phòng khi sự kiện loaded không đến
        self._app_maximized = False
        self._faded_out = False
        self._normal_rect = None
        window.events.maximized += lambda: setattr(self, "_app_maximized", True)
        # Khôi phục sau khi thu nhỏ xuống thanh tác vụ không có nghĩa là hết phóng to kiểu tự vẽ (còn _normal_rect).
        window.events.restored += self._on_app_restored

    def _on_app_restored(self) -> None:
        """Cửa sổ được khôi phục (từ thanh tác vụ hoặc từ phóng to của hệ điều hành)."""
        self._app_maximized = self._normal_rect is not None
        self._reveal_if_faded()

    def _reveal_if_faded(self) -> None:
        """Hiện dần lại cửa sổ đã mờ hẳn khi thu nhỏ (gọi ở mọi đường mở lại để không bao giờ kẹt trong suốt)."""
        window = self._app_window
        if window is None or not self._faded_out:
            return
        self._faded_out = False
        threading.Thread(target=osw.fade, args=(window, 0, 255, 200), name="chotto-reveal", daemon=True).start()

    def config_changed(self) -> None:
        """Báo agent đọc lại cấu hình ngay (không chờ lần kiểm tra định kỳ)."""
        self._wire.send({"op": "config_changed"})

    def _on_settings_closed(self) -> None:
        self._app_window = None
        from . import mascot

        mascot.set_place_flag(False)                 # đóng cửa sổ ứng dụng = hết chế độ chọn vị trí
        self._wire.send({"op": "settings_closed"})

    def app_window_op(self, op: str) -> None:
        """Thu nhỏ / phóng to / đóng cửa sổ ứng dụng."""
        window = self._app_window
        if window is None:
            return
        if op == "minimize":
            self._faded_out = True
            osw.fade(window, 255, 0, 140)          # mờ dần rồi mới thu xuống thanh tác vụ; mở lại sẽ hiện dần
            window.minimize()
        elif op == "toggle_maximize":
            if not self._animate_maximize(window):       # không làm được hiệu ứng thì dùng phóng to/thu nhỏ của hệ điều hành
                if self._app_maximized:       # ``window.maximized`` của pywebview chỉ là tham số khởi tạo, không theo dõi trạng thái
                    window.restore()
                else:
                    window.maximize()
        elif op == "close":
            osw.fade(window, 255, 0, 150)
            window.destroy()

    def _animate_maximize(self, window: Any) -> bool:
        """Phóng to / thu nhỏ có hiệu ứng chuyển dần (Windows). ``False`` nếu không làm được (người gọi dùng cách thường).

        Cửa sổ không viền không có hiệu ứng của hệ điều hành, nên ta tự dời/giãn cửa sổ giữa kích thước thường và
        vùng làm việc của màn hình (không che thanh tác vụ). Không dùng WindowState, nên bấm lần nữa là về đúng kích thước cũ.
        """
        if not osw.CUSTOM_FRAME or self._anim_busy:
            return self._anim_busy
        try:
            hwnd = win32_window.native_hwnd(window)
            current = win32_window.window_rect(hwnd)
            if self._app_maximized and self._normal_rect is None:
                return False                              # đã phóng to bằng hệ điều hành (vd. Win+Up): để nó tự khôi phục
            if self._app_maximized:
                target = self._normal_rect
            else:
                target = win32_window.monitor_work_rect(hwnd)
                if target is not None:
                    self._normal_rect = current
            if target is None:
                return False
        except Exception:  # noqa: BLE001 - hiệu ứng chỉ là phần thêm
            _LOG.debug("Không dựng được hiệu ứng phóng to", exc_info=True)
            return False
        going_up = not self._app_maximized
        self._app_maximized = going_up
        if not going_up:
            self._normal_rect = None
        self._anim_busy = True

        def run() -> None:
            try:
                steps, duration = 14, 0.16
                for i in range(1, steps + 1):
                    k = 1 - (1 - i / steps) ** 3                      # ease-out cubic
                    l, t, r, b = (round(a + (z - a) * k) for a, z in zip(current, target))
                    win32_window.set_window_rect(hwnd, (l, t, r, b))
                    time.sleep(duration / steps)
            except Exception:  # noqa: BLE001
                _LOG.debug("Hiệu ứng phóng to bị gián đoạn", exc_info=True)
            finally:
                self._anim_busy = False

        threading.Thread(target=run, name="chotto-anim", daemon=True).start()
        return True

    def app_resize_begin(self, edge: str) -> None:
        """Cửa sổ không viền của WinForms không có mép để kéo, nên giao diện tự vẽ mép và gọi vào đây."""
        self._resize = None
        window = self._app_window
        if window is None or self._app_maximized or not osw.CUSTOM_FRAME:
            return
        try:
            hwnd = win32_window.native_hwnd(window)
            self._resize = (hwnd, set(edge) & set("nsew"), win32_window.window_rect(hwnd),
                            win32_window.window_dpi_scale(hwnd))
        except Exception:  # noqa: BLE001 - chỉ là tiện ích kéo giãn
            _LOG.debug("Không bắt đầu được kéo giãn", exc_info=True)

    def app_resize_move(self, dx: float, dy: float) -> None:
        """Áp kích thước mới trong lúc kéo giãn (không nhỏ hơn kích thước tối thiểu)."""
        state = self._resize
        if state is None:
            return
        hwnd, edges, (left, top, right, bottom), scale = state
        min_w, min_h = round(760 * scale), round(560 * scale)
        if "e" in edges:
            right = max(right + round(dx), left + min_w)
        if "w" in edges:
            left = min(left + round(dx), right - min_w)
        if "s" in edges:
            bottom = max(bottom + round(dy), top + min_h)
        if "n" in edges:
            top = min(top + round(dy), bottom - min_h)
        try:
            win32_window.set_window_rect(hwnd, (left, top, right, bottom))
        except Exception:  # noqa: BLE001
            _LOG.debug("Không kéo giãn được", exc_info=True)

    def ask_save_path(self, filename: str) -> str:
        """Hộp thoại lưu file của hệ thống; rỗng nếu người dùng hủy."""
        window = self._app_window
        if window is None:
            return ""
        dialog = getattr(getattr(self._webview, "FileDialog", None), "SAVE", None) or self._webview.SAVE_DIALOG
        chosen = window.create_file_dialog(dialog, save_filename=filename, file_types=("CSV (*.csv)",))
        if isinstance(chosen, (list, tuple)):
            chosen = chosen[0] if chosen else ""
        return str(chosen or "")

    # ---- vòng đời ----
    def quit(self) -> None:
        """Đóng mọi cửa sổ (đóng cửa sổ đệm = "không mở") rồi thoát vòng lặp pywebview."""
        with self._lock:
            frictions = list(self._frictions.items())
            self._frictions.clear()
        for _, (window, api) in frictions:
            api._closed()  # noqa: SLF001
            try:
                window.destroy()
            except Exception:  # noqa: BLE001
                _LOG.debug("Cửa sổ đệm đã đóng", exc_info=True)
        for window in (self._app_window, self._keeper):
            if window is not None:
                try:
                    window.destroy()
                except Exception:  # noqa: BLE001
                    _LOG.debug("Cửa sổ đã đóng", exc_info=True)

    def dispatch(self, message: dict[str, Any]) -> bool:
        """Xử lý một thông điệp từ agent; ``False`` khi phải thoát."""
        op = message.get("op")
        if op == "friction":
            self.open_friction(int(message["id"]), dict(message["payload"]))
        elif op == "update":
            self.update_friction(int(message["id"]), dict(message["payload"]))
        elif op == "settings":
            self.open_settings()
        elif op == "quit":
            return False
        else:
            _LOG.warning("Thông điệp không hiểu: %s", op)
        return True

    def serve(self) -> None:
        """Thân luồng phục vụ (pywebview gọi sau khi khởi động GUI): đọc lệnh đến khi agent đóng kết nối."""
        self._wire.send({"op": "ready", "pid": os.getpid()})
        try:
            while True:
                line = self._read_line()
                if not line:
                    break
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("không phải object")
                    if not self.dispatch(message):
                        break
                except (ValueError, KeyError, TypeError):
                    _LOG.exception("Thông điệp hỏng từ agent")
                except Exception:  # noqa: BLE001 - một cửa sổ lỗi không được làm chết host
                    _LOG.exception("Host xử lý thông điệp lỗi")
        finally:
            self.quit()

    def run(self) -> int:
        """Khởi động pywebview trên luồng chính (chặn đến khi thoát)."""
        self._keeper = self._webview.create_window("Chotto", html="<title>Chotto</title>", hidden=True,
                                                   background_color=BG)
        self._webview.start(self.serve, private_mode=True)
        return 0


def run_host() -> int:
    """Điểm vào của ``main.py ui-host``.

    Returns:
        0 khi thoát bình thường; 3 khi không có pywebview hoặc không dựng được GUI.
    """
    proto_out = sys.stdout
    sys.stdout = sys.stderr                     # thư viện in ra stdout không được làm hỏng giao thức
    for stream in (sys.stdin, proto_out):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    if proto_out is None or sys.stdin is None:
        return 3
    try:
        import webview
    except ImportError:
        _LOG.warning("Không có pywebview: agent dùng giao diện Tk")
        return 3
    host = Host(Wire(proto_out), webview, sys.stdin.readline)
    try:
        return host.run()
    except Exception:  # noqa: BLE001 - agent sẽ thấy stdout đóng và quay về Tk
        _LOG.exception("Không chạy được giao diện HTML")
        return 3
