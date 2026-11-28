"""Vòng đời giao diện: chế độ một tiến trình (dự phòng) và agent thường trú.

- ``run_once``: xử lý một link rồi thoát, hoặc mở cửa sổ cài đặt (như bản 1.0). Dùng khi agent chưa
  chạy hoặc bị tắt trong cấu hình.
- ``run_resident``: agent thường trú. Giữ engine trong RAM, nhận link qua IPC (Windows) hoặc Apple Event
  (macOS), hiển thị lần lượt từng màn hình đệm, tự nạp lại cấu hình khi file thay đổi và tự cập nhật
  danh sách đen mỗi ngày trên luồng nền.
"""
from __future__ import annotations

import collections
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, Final

from .. import guardian, logdb, platforms
from ..config import SETTINGS_KEYS, Config, config_stamp, load_config, load_rules, save_config
from ..messages import msg
from ..platforms import Caller, detect_caller
from ..platforms import window as osw
from ..engine import Engine, Result
from ..tier1 import BlacklistError, update_due, update_from_sources
from . import agent as agent_mod
from . import ipc
from . import webui as webui_mod
from .handler import LinkHandler, SecondsFor
from .webui import WebUI, WebUIError

if TYPE_CHECKING:
    import tkinter as tk

    from ..mascot import MascotRunner
    from ..ui import SettingsActions

__all__ = ["AutoUpdater", "build_handler", "run_once", "run_resident"]

_LOG = logging.getLogger("chotto")

_MAC_EVENT_WAIT_MS: Final[int] = 2500
_POLL_MS: Final[int] = 50
_AUTO_UPDATE_FIRST_MS: Final[int] = 2 * 60 * 1000       # để máy khởi động xong rồi mới tải
_AUTO_UPDATE_EVERY_MS: Final[int] = 15 * 60 * 1000


def _record_desktop(cfg: Config) -> Callable[[Result, str, int], bool]:
    """Hàm ghi nhật ký cho Desktop theo cấu hình lưu giữ."""
    def record(result: Result, decision: str, dwell_ms: int) -> bool:
        return logdb.record(result, decision, dwell_ms, "desktop", cfg["log_retention_days"])

    return record


def save_settings(values: dict[str, Any]) -> None:
    """Lưu các khóa của cửa sổ cài đặt lên cấu hình mới nhất trên đĩa (không ghi đè trình duyệt đã lưu).

    Raises:
        OSError: Không ghi được ``config.json``.
    """
    current: dict[str, Any] = dict(load_config())
    current.update({key: values[key] for key in SETTINGS_KEYS if key in values})
    save_config(current)


def install_action(lang: str = "vi") -> str:
    """Tác vụ cài đặt. Tiếng Việt trả câu hướng dẫn chi tiết theo hệ điều hành, tiếng Anh trả câu ngắn.

    Raises:
        PlatformSetupError: Không đăng ký được.
        OSError: Không lưu được cấu hình.
    """
    cfg: dict[str, Any] = dict(load_config())
    detail = platforms.install(cfg)
    save_config(cfg)
    return detail if lang == "vi" else msg(lang, "installed")


def uninstall_action(lang: str = "vi") -> str:
    """Tác vụ gỡ đăng ký: gỡ handler, tắt tự khởi động và tắt agent đang chạy."""
    detail = platforms.uninstall(load_config())
    agent_mod.stop_agent()
    return detail if lang == "vi" else msg(lang, "uninstalled")


def update_action(lang: str = "vi") -> str:
    """Tác vụ cập nhật danh sách đen."""
    count = update_from_sources(load_rules(), log=lambda line: _LOG.info("%s", line))
    return msg(lang, "updated", count=count) if count else msg(lang, "unchanged")


def export_action(path: str, lang: str = "vi") -> str:
    """Tác vụ xuất nhật ký ra ``path``."""
    return msg(lang, "exported", count=logdb.export_csv(path), path=path)


def clear_log_action(lang: str = "vi") -> str:
    """Tác vụ xóa toàn bộ nhật ký quyết định."""
    logdb.clear()
    return msg(lang, "cleared")


def _pump(root: tk.Tk | None) -> Callable[[], None]:
    """Hàm cho vòng lặp Tk xử lý sự kiện trong lúc chờ giao diện HTML (không có Tk: không làm gì)."""
    def pump() -> None:
        if root is None:
            return
        try:
            root.update()
        except Exception:  # noqa: BLE001 - Tk đã bị hủy: chờ tiếp bằng event.wait
            _LOG.debug("Không cập nhật được Tk", exc_info=True)

    return pump


def make_webui() -> WebUI | None:
    """Giao diện HTML của phiên này; ``None`` khi người dùng ép dùng Tk (``CHOTTO_UI=tk``)."""
    return WebUI() if webui_mod.enabled() else None


def build_handler(cfg: Config, root: tk.Tk | None, web: WebUI | None = None,
                  notify: Callable[[str, str], None] | None = None) -> LinkHandler:
    """Dựng ``LinkHandler``: giao diện HTML nếu có, không được thì Tk, cuối cùng là hộp thoại hệ thống."""
    from .. import ui

    rules: dict[str, Any] = {}
    offered = [""]                      # PIN giao diện gửi kèm quyết định "mở"; dùng đúng một lần

    def policy_of(level: str) -> guardian.OpenPolicy:
        # Chặt nhất giữa cấu hình của handler và file trên đĩa (có thể vừa bật Guardian khi cảnh báo đang mở).
        return guardian.strictest(guardian.open_policy(cfg, level), guardian.open_policy(load_config(), level))

    def guard_of(level: str, lang: str) -> dict[str, str] | None:
        policy = policy_of(level)
        if policy == "allow":
            return None
        return guardian.screen_info(policy, load_config()["guardian_contact"] or cfg["guardian_contact"], lang)

    def authorize() -> bool:
        pin, offered[0] = offered[0], ""
        return bool(pin) and guardian.verify_pin(pin).ok

    def offer(pin: str) -> None:
        offered[0] = pin

    def view_of(result: Result, checking: bool) -> dict[str, Any]:
        from ..shield import shield_view

        if not rules:
            rules.update(load_rules())
        # Điểm rủi ro chỉ hiện ở Desktop (to, nhìn là hiểu); view dùng chung với tiện ích không có khóa này.
        view = {**shield_view(result, checking, rules, cfg["ui_language"]), "score": max(0, min(100, int(result.score)))}
        info = guard_of(result.level, cfg["ui_language"])
        if info is not None:
            view["guardian"] = info
            view["actions"] = {**view["actions"], "copyText": ""}       # chép nguyên địa chỉ là đường lách
        return view

    def present(result: Result, seconds_for: SecondsFor, pending: Future[Result] | None) -> tuple[bool, int, Result]:
        offered[0] = ""
        if web is not None:
            try:
                return web.present(view_of, result, seconds_for, pending, _pump(root), on_pin=offer)
            except WebUIError:
                _LOG.warning("Giao diện HTML không dùng được, chuyển sang Tk", exc_info=True)
        if root is None:
            raise RuntimeError("Không có giao diện Tk")
        return ui.show_friction(root, result, seconds_for, pending, guard_of=guard_of, on_pin=offer)

    return LinkHandler(
        cfg=cfg,
        engine_factory=lambda: Engine(cfg),
        present=present,
        open_url=lambda target: platforms.open_in_real_browser(target, cfg),
        alert=lambda message: ui.native_alert("CHOTTO", message),
        record=_record_desktop(cfg),
        notify=notify,
        policy=policy_of,
        authorize=authorize,
    )


def _settings_actions() -> SettingsActions:
    """Các tác vụ nút bấm của cửa sổ cài đặt."""
    from .. import ui

    return ui.SettingsActions(install=install_action, uninstall=uninstall_action,
                              update_blacklist=update_action, export_log=export_action)


def _create_root() -> tk.Tk | None:
    """Tạo cửa sổ gốc Tk ẩn; ``None`` nếu máy không có Tk/không có màn hình."""
    try:
        import tkinter as tk

        created = tk.Tk()
        created.withdraw()
        return created
    except Exception:  # noqa: BLE001 - không có Tk: vẫn xử lý link với chính sách fail-safe
        _LOG.exception("Không khởi tạo được Tk")
        return None


def run_once(url: str | None = None, force: bool = False, gui: bool = False, caller: Caller | None = None) -> int:
    """Chế độ một tiến trình: xử lý ``url`` (và link đến thêm qua Apple Event) rồi thoát, hoặc mở cài đặt.

    Args:
        url: Link nhận qua argv; ``None`` để mở cửa sổ cài đặt.
        force: Bỏ qua bước nhận diện Zalo.
        gui: macOS: mở cài đặt ngay thay vì chờ Apple Event.
        caller: Nguồn gọi đã đo sẵn (launcher đo trước khi thử gửi cho agent).

    Returns:
        Mã thoát tiến trình.
    """
    from .. import ui

    ui.enable_dpi_awareness()
    cfg = load_config()
    if url and not force and caller is None:
        caller = detect_caller(cfg)        # phải đo TRƯỚC khi tạo cửa sổ
    root = _create_root()
    web = make_webui()
    if web is not None:
        web.start()                        # khởi động lạnh song song với việc thẩm định
    try:
        return _run_once_ui(url, force, gui, caller, cfg, root, web)
    finally:
        if web is not None:
            web.stop()


def _run_once_ui(url: str | None, force: bool, gui: bool, caller: Caller | None, cfg: Config, root: tk.Tk | None,
                 web: WebUI | None) -> int:
    """Thân của ``run_once`` sau khi đã có cửa sổ gốc Tk (nếu có) và giao diện HTML (nếu có)."""
    from .. import ui

    handler = build_handler(cfg, root, web)
    if root is None:
        if url:
            handler.handle(url, caller, force)
            return 0
        if web is not None and web.open_settings(_pump(None)):
            while web.settings_open:
                time.sleep(0.2)
            return 0
        ui.native_alert("CHOTTO", "Không mở được giao diện CHOTTO (thiếu Tk).")
        return 1
    window: tk.Tk = root

    pending: collections.deque[tuple[str, Caller | None]] = collections.deque()
    state = {"busy": False, "settings": False, "handled": False}

    def drain() -> None:
        if state["busy"]:
            return
        state["busy"] = True
        try:
            while pending:
                link, link_caller = pending.popleft()
                handler.handle(link, link_caller, force)
        finally:
            state["busy"] = False
        if not state["settings"] and window.winfo_exists():
            window.destroy()

    def on_url(link: str, link_caller: Caller | None = None) -> None:
        state["handled"] = True
        if link_caller is None and not force:
            link_caller = detect_caller(cfg)
        pending.append((link, link_caller))
        window.after(0, drain)

    def open_settings() -> None:
        state["settings"] = True
        if web is not None and web.open_settings(_pump(window)):
            def watch() -> None:
                if web.settings_open or state["busy"]:
                    window.after(200, watch)
                elif window.winfo_exists():
                    window.destroy()             # cửa sổ ứng dụng HTML đã đóng: thoát như bản Tk

            window.after(200, watch)
            return
        ui.show_settings(window, cfg, save_settings, _settings_actions())

    if sys.platform == "darwin":
        window.createcommand("::tk::mac::LaunchURL", lambda link: on_url(str(link)))   # Apple Event kAEGetURL

    if url:
        window.after(10, lambda: on_url(url, caller))
    elif sys.platform == "darwin" and not gui:
        window.after(_MAC_EVENT_WAIT_MS, lambda: None if state["handled"] else open_settings())
    else:
        open_settings()
    window.mainloop()
    return 0


class AutoUpdater:
    """Tự cập nhật danh sách đen trên luồng nền khi đến hạn (mỗi ngày; thử lại sau 1 giờ nếu lỗi).

    Engine đang chạy tự thấy danh sách mới ở lần tra sau (file dấu vân tay đổi), không cần khởi động lại.
    """

    def __init__(self, enabled: Callable[[], bool], due: Callable[[], bool] = update_due,
                 run: Callable[[], int] | None = None) -> None:
        """Tạo bộ tự cập nhật.

        Args:
            enabled: Đọc cấu hình ``auto_update`` hiện hành.
            due: Đã đến hạn cập nhật chưa.
            run: Hàm cập nhật (mặc định: ``update_from_sources`` với bộ luật đóng gói).
        """
        self._enabled = enabled
        self._due = due
        self._run = run or (lambda: update_from_sources(load_rules(), log=lambda line: _LOG.info("%s", line)))
        self._thread: threading.Thread | None = None

    def _work(self) -> None:
        """Thân luồng nền: không bao giờ để lỗi thoát ra ngoài."""
        try:
            count = self._run()
            _LOG.info("Tự cập nhật danh sách đen: %s", f"{count} mục" if count else "không thay đổi")
        except BlacklistError:
            _LOG.exception("Tự cập nhật danh sách đen thất bại")
        except Exception:  # noqa: BLE001 - luồng nền của agent không được chết im lặng
            _LOG.exception("Lỗi không lường trước khi tự cập nhật danh sách đen")

    def tick(self) -> bool:
        """Kiểm tra và khởi chạy cập nhật nếu cần; ``True`` nếu vừa khởi chạy."""
        if self._thread is not None and self._thread.is_alive():
            return False
        try:
            if not self._enabled() or not self._due():
                return False
        except Exception:  # noqa: BLE001 - đọc cấu hình/trạng thái lỗi: bỏ qua lượt này
            _LOG.exception("Không kiểm tra được lịch tự cập nhật")
            return False
        self._thread = threading.Thread(target=self._work, name="chotto-auto-update", daemon=True)
        self._thread.start()
        return True

    def join(self, timeout: float | None = None) -> None:
        """Chờ lượt cập nhật đang chạy (dùng trong kiểm thử)."""
        if self._thread is not None:
            self._thread.join(timeout)


class _HandlerCache:
    """Giữ ``LinkHandler`` (và engine trong RAM); dựng lại khi ``config.json`` thay đổi."""

    def __init__(self, root: tk.Tk, web: WebUI | None = None,
                 notify: Callable[[str, str], None] | None = None) -> None:
        """Tạo bộ đệm cho cửa sổ gốc ``root`` (giao diện HTML ``web`` và người nghe ``notify`` nếu có)."""
        self._root = root
        self._web = web
        self._notify = notify
        self._stamp: tuple[int, int] | None = None
        self._handler: LinkHandler | None = None

    def get(self) -> LinkHandler:
        """Handler hiện hành (nạp lại cấu hình nếu file đã đổi)."""
        stamp = config_stamp()
        if self._handler is None or stamp != self._stamp:
            if self._handler is not None:
                _LOG.info("config.json thay đổi, nạp lại cấu hình")
            self._stamp = stamp
            self._handler = build_handler(load_config(), self._root, self._web, self._notify)
        return self._handler

    @property
    def cfg(self) -> Config:
        """Cấu hình hiện hành."""
        return self.get().cfg


def _start_mascot(open_app: Callable[[], None], web: WebUI | None,
                  open_link: Callable[[str], None] | None = None, main_root: Any = None) -> MascotRunner | None:
    """Nhân vật taskbar (tự ẩn/hiện theo ``mascot_enabled``) trên luồng Tk riêng; lỗi bất kỳ chỉ ghi log, agent chạy tiếp.

    ``open_app`` và ``open_link`` (link từ mã QR người dùng xác nhận mở) được gọi từ luồng nhân vật nên chỉ được đặt cờ/xếp hàng
    (không đụng Tk của luồng chính).
    """
    try:
        from ..mascot import MascotRunner

        mascot = MascotRunner(open_app, open_link, main_root)
        if web is not None:
            def changed() -> None:
                mascot.request_reload()
                _stop_local_ai_unless_selected()

            web.on_config_changed = changed
        mascot.start()
        return mascot
    except Exception:  # noqa: BLE001 - phần trang trí không được làm chết agent
        _LOG.exception("Không khởi động được nhân vật taskbar")
        return None


def _stop_local_ai_unless_selected(force: bool = False) -> None:
    """Tắt ``llama-server`` của nhân vật khi thoát agent (``force``) hoặc khi chế độ AI không còn là ``local``/đổi model."""
    try:
        from ..mascot import local_ai

        cfg = load_config()
        if force or cfg["mascot_ai_mode"] != "local":
            local_ai.SERVER.stop()
        else:
            for model in local_ai.CATALOG:
                if model.id != cfg["mascot_local_model"]:
                    local_ai.SERVER.stop_if_model(model.id)
    except Exception:  # noqa: BLE001 - chỉ là dọn dẹp
        _LOG.exception("Không tắt được AI Local")


def run_resident(open_settings_after_ms: int | None = None, show_settings_now: bool = False) -> int:
    """Agent thường trú: chạy đến khi nhận lệnh tắt.

    Args:
        open_settings_after_ms: macOS: mở cửa sổ cài đặt nếu sau ngần ấy mili-giây chưa có link nào
            (người dùng tự mở CHOTTO.app). ``None`` để không tự mở.
        show_settings_now: Mở cửa sổ cài đặt ngay khi khởi động.

    Returns:
        Mã thoát: 0 khi tắt bình thường hoặc đã có agent khác, 1 khi không chạy được.
    """
    from .. import ui

    ui.enable_dpi_awareness()
    root = _create_root()
    if root is None:
        return 1
    window: tk.Tk = root
    core = agent_mod.AgentCore()
    server: ipc.IPCServer | None = None
    try:
        candidate = ipc.IPCServer(core.handle)
        candidate.start()
        server = candidate
    except ipc.AgentAlreadyRunning:
        _LOG.info("Đã có agent khác đang chạy, thoát")
        window.destroy()
        return 0
    except ipc.IPCError:
        _LOG.exception("Không mở được kênh IPC")
        if sys.platform != "darwin":       # Windows không có kênh nào khác để nhận link: vô dụng nếu chạy tiếp
            window.destroy()
            return 1

    web = make_webui()
    if web is not None:
        web.start()                    # giữ sẵn: màn hình đệm sau hiện trong khoảng 0,2 giây
    state: dict[str, Any] = {"busy": False, "handled": False, "settings": None}
    open_flag = threading.Event()                  # nhân vật (luồng Tk riêng) xin mở ứng dụng: luồng chính tự xử lý ở drain
    # Link từ mã QR đi cùng hàng đợi với link bấm thật (force: luôn kiểm tra, link rủi ro vẫn hiện màn hình cảnh báo).
    def open_scanned(url: str) -> None:
        core.submit(agent_mod.LinkRequest(url, None, True))

    mascot = _start_mascot(open_flag.set, web, open_scanned, window)
    handlers = _HandlerCache(window, web, mascot.notify if mascot is not None else None)

    def drain() -> None:
        if open_flag.is_set():
            open_flag.clear()
            window.after(0, open_settings)
        if core.quit_requested.is_set() and not state["busy"]:
            shutdown()         # không bao giờ đóng ngang màn hình đệm người dùng đang cân nhắc
            return
        if not state["busy"]:
            state["busy"] = True
            try:
                while not core.links.empty() and not core.quit_requested.is_set():
                    request = core.links.get_nowait()
                    state["handled"] = True
                    handlers.get().handle(request.url, request.caller, request.force)
            except Exception:  # noqa: BLE001 - agent không bao giờ được chết vì một link
                _LOG.exception("Agent xử lý link lỗi")
            finally:
                state["busy"] = False
        if window.winfo_exists():
            window.after(_POLL_MS, drain)

    def shutdown() -> None:
        if mascot is not None:
            mascot.stop()
        _stop_local_ai_unless_selected(force=True)
        if server is not None:
            server.stop()
        if window.winfo_exists():
            window.destroy()

    def open_settings() -> None:
        if web is not None and web.open_settings(_pump(window)):
            return
        existing = state["settings"]
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            return
        import tkinter as tk

        top = tk.Toplevel(window)
        state["settings"] = top
        ui.show_settings(top, handlers.cfg, save_settings, _settings_actions(), on_close=top.destroy)

    if sys.platform == "darwin":
        def on_url(link: object) -> None:
            caller = detect_caller(handlers.cfg)
            core.submit(agent_mod.LinkRequest(str(link), caller, False))

        window.createcommand("::tk::mac::LaunchURL", on_url)                 # Apple Event kAEGetURL
        window.createcommand("::tk::mac::ReopenApplication", open_settings)  # người dùng mở lại CHOTTO.app
        window.createcommand("::tk::mac::Quit", shutdown)

    updater = AutoUpdater(enabled=lambda: handlers.cfg["auto_update"])

    def auto_update() -> None:
        updater.tick()
        if window.winfo_exists():
            window.after(_AUTO_UPDATE_EVERY_MS, auto_update)

    window.after(_AUTO_UPDATE_FIRST_MS, auto_update)
    if show_settings_now:
        window.after(0, open_settings)
    elif open_settings_after_ms is not None:
        window.after(open_settings_after_ms, lambda: None if state["handled"] else open_settings())
    window.after(0, drain)
    _LOG.info("Agent sẵn sàng (pid %s)", os.getpid())
    try:
        window.mainloop()
    finally:
        if server is not None:
            server.stop()
        if web is not None:
            web.stop()
    return 0
