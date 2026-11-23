"""Cửa sổ nhân vật trên thanh taskbar (Windows), chạy trên luồng Tk sẵn có của agent.

Fail-safe tuyệt đối: thiếu Pillow, không phải Windows, không có màn hình hoặc cửa sổ lỗi giữa chừng thì chỉ ghi
log rồi tắt nhân vật cho phiên này. Không có đường mã nào ở đây được ném lỗi ra agent hay làm chậm luồng chặn link
(``notify`` chỉ xếp sự kiện vào hàng đợi). Mọi lời gọi Win32 nằm trong ``chotto.platforms.win32_window``.
"""
from __future__ import annotations

import collections
import logging
import math
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from ..config import MASCOT_DEFAULT_COLORS, config_stamp, data_dir, load_config
from ..platforms import any_process_running
from ..platforms import win32_window as w32
from ..platforms import window as osw
from ..util import clamp as _clamp
from .brain import POSE_INDEX, WARNING_LEVELS, Frame, MascotBrain
from .recolor import normalize_colors, recolored_poses, source_poses

if TYPE_CHECKING:
    import tkinter as tk

    from PIL import Image

__all__ = ["PLACE_FLAG", "TaskbarMascot", "place_flag_set", "set_place_flag", "supported"]

_LOG = logging.getLogger("chotto")


def supported() -> bool:
    """Máy này hiện được nhân vật không (hệ điều hành có cửa sổ overlay trong suốt + Pillow có ImageTk)."""
    if not osw.OVERLAY_SUPPORTED:
        return False
    try:
        from PIL import ImageTk  # noqa: F401
    except Exception:  # noqa: BLE001 - thiếu Pillow hoặc thiếu phần Tk của Pillow
        return False
    return True


_KEY: Final[str] = "#ff00fe"                  # màu trong suốt (-transparentcolor): không có trong sprite
_KEY_RGB: Final[tuple[int, int, int]] = (255, 0, 254)
_BASE_SCALE: Final[float] = 0.30              # 488 px gốc → ~146 px ở 100% scale (gấp đôi bản đầu: 0.15)
_STOP_MUL: Final[float] = 2.0                 # tư thế "Khoan đã!" to gấp đôi cỡ thường (= gấp 4 bản đầu)
_DESIGN_SCALE: Final[float] = 0.31            # tỉ lệ sprite trong khung hoạt ảnh của bản thiết kế
_FAST_MS: Final[int] = 33
_SLOW_MS: Final[int] = 120
_POLL_MS: Final[int] = 1500
_FLAG_MS: Final[int] = 250
PLACE_FLAG: Final[str] = "mascot_place.flag"   # có file này = người dùng đang kéo nhân vật để chọn vị trí


def set_place_flag(on: bool) -> None:
    """Bật/tắt cờ "chọn vị trí" (file trong thư mục dữ liệu); không bao giờ ném lỗi."""
    path = data_dir() / PLACE_FLAG
    try:
        if on:
            path.write_text("1", "utf-8")
        else:
            path.unlink(missing_ok=True)
    except OSError:
        _LOG.warning("Không ghi được cờ chọn vị trí nhân vật", exc_info=True)


def place_flag_set() -> bool:
    """Cờ "chọn vị trí" đang bật không."""
    try:
        return (data_dir() / PLACE_FLAG).exists()
    except OSError:
        return False
_DUST: Final[str] = "#d8d2c8"
_MENU: Final[dict[str, tuple[str, str]]] = {"en": ("Open Chotto", "Hide character"),
                                            "vi": ("Mở CHOTTO", "Ẩn nhân vật")}


@dataclass
class _Dust:
    x: float
    h: float
    r: float
    vx: float
    life: float = 0.5


class TaskbarMascot:
    """Cửa sổ nhân vật trên luồng Tk của agent. Mọi phương thức công khai đều không ném lỗi."""

    def __init__(self, root: tk.Tk, open_app: Callable[[], None]) -> None:
        """Gắn vào cửa sổ gốc ``root`` (ẩn) của agent; ``open_app`` mở cửa sổ ứng dụng CHOTTO."""
        self._root = root
        self._open_app = open_app
        self._events: collections.deque[tuple[str, str]] = collections.deque()
        self._reload = threading.Event()
        self._broken = False
        self._enabled = False
        self._switch_on = False                # công tắc "mascot_enabled" trong cấu hình (khác với đang hiện)
        self._startup = "login"
        self._zalo_names: tuple[str, ...] = ()
        self._colors: tuple[str, ...] = tuple(MASCOT_DEFAULT_COLORS)
        self._lang = "en"
        self._stamp: tuple[int, int] | None = None
        self._window: Any = None
        self._canvas: Any = None
        self._sprite_item: int | None = None
        self._brain: MascotBrain | None = None
        self._poses: tuple[Image.Image, ...] | None = None
        self._incoming: tuple[tuple[str, ...], tuple[Image.Image, ...]] | None = None
        self._rendering: tuple[str, ...] | None = None
        self._cache: dict[tuple[int, bool, int, int, int], Any] = {}
        self._dust: list[_Dust] = []
        self._dust_items: list[int] = []
        self._dust_timer = 0.0
        self._last = time.monotonic()
        self._loop_id: str | None = None
        self._geom: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._shown_key: tuple[int, bool, int, int, int] | None = None
        self._scale = _BASE_SCALE
        self._unit = 1.0
        self._area: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._size: tuple[int, int] = (1, 1)
        self._hwnd = 0
        self._pinned = False
        self._pos = 0.85                      # vị trí cố định, tỉ lệ 0..1 trên vùng chạy
        self._placing = False
        self._dragging = False

    # ---- giao diện công khai (gọi từ bất kỳ luồng nào) ----
    def notify(self, event: str, level: str = "") -> None:
        """Sự kiện từ ``LinkHandler``: ``warning_open`` (kèm mức) | ``warning_closed``. Chỉ xếp hàng, không chặn."""
        self._events.append((event, level))

    def request_reload(self) -> None:
        """Cấu hình vừa đổi (tín hiệu từ cửa sổ ứng dụng): đọc lại ở khung hình tới."""
        self._reload.set()

    def start(self) -> None:
        """Bắt đầu theo dõi cấu hình (nhân vật chỉ hiện khi ``mascot_enabled``)."""
        set_place_flag(False)                         # cờ "chọn vị trí" còn sót từ phiên trước
        self._safe(self._poll)
        self._safe(self._watch_flag)

    def stop(self) -> None:
        """Gỡ cửa sổ (agent thoát)."""
        self._broken = True
        set_place_flag(False)
        self._destroy()

    def _watch_flag(self) -> None:
        """Theo dõi cờ "chọn vị trí" do cửa sổ ứng dụng đặt (qua file, vì cửa sổ có thể thuộc tiến trình khác agent)."""
        want = place_flag_set() and self._enabled and self._pinned
        if want != self._placing:
            self._set_placing(want)
        if not self._broken:
            self._root.after(_FLAG_MS, lambda: self._safe(self._watch_flag))

    # ---- nội bộ ----
    def _safe(self, fn: Callable[[], None]) -> None:
        if self._broken:
            return
        try:
            fn()
        except Exception:  # noqa: BLE001 - nhân vật không bao giờ được làm chết agent
            _LOG.exception("Nhân vật trên taskbar gặp lỗi, tắt nhân vật cho phiên này")
            self._broken = True
            self._destroy()

    def _destroy(self) -> None:
        try:
            if self._loop_id is not None:
                self._root.after_cancel(self._loop_id)
        except Exception:  # noqa: BLE001
            pass
        self._loop_id = None
        window, self._window = self._window, None
        if window is not None:
            try:
                window.destroy()
            except Exception:  # noqa: BLE001
                pass
        self._cache.clear()
        self._sprite_item = None
        self._dust_items = []

    def _poll(self) -> None:
        """Theo dõi cấu hình mỗi ``_POLL_MS`` (dự phòng cho tín hiệu ``config_changed``)."""
        self._apply_config(force=self._stamp is None)
        self._reconcile()
        if self._enabled and self._window is not None:
            self._place_bounds()                      # đổi độ phân giải / dời taskbar
        if not self._broken:
            self._root.after(_POLL_MS, lambda: self._safe(self._poll))

    def _apply_config(self, force: bool = False) -> None:
        stamp = config_stamp()
        if not force and stamp == self._stamp and not self._reload.is_set():
            return
        self._reload.clear()
        self._stamp = stamp
        cfg = load_config()
        self._lang = cfg["ui_language"]
        self._pinned = bool(cfg["mascot_pinned"])
        self._pos = float(cfg["mascot_pos"])
        colors = normalize_colors(cfg["mascot_colors"])
        if colors != self._colors or self._poses is None:
            self._colors = colors
            self._render_async(colors)
        self._switch_on = bool(cfg["mascot_enabled"])
        self._startup = cfg["mascot_startup"]
        self._zalo_names = tuple(cfg["zalo_processes"])
        self._reconcile()
        self._sync_pin()

    def _reconcile(self) -> None:
        """Hiện/ẩn theo công tắc; chế độ "zalo" thì chỉ hiện khi Zalo đang chạy."""
        want = self._switch_on and (self._startup != "zalo" or any_process_running(self._zalo_names))
        if want and not self._enabled:
            self._show()
        elif not want and self._enabled:
            self._hide()

    def _render_async(self, colors: tuple[str, ...]) -> None:
        """Tô màu trên luồng nền (lần đầu mất tới ~1 giây); Tk nhận kết quả ở khung hình sau."""
        if self._rendering == colors:
            return
        self._rendering = colors

        def work() -> None:
            try:
                poses = recolored_poses(colors)
            except Exception:  # noqa: BLE001 - lỗi tô màu: dùng màu gốc
                _LOG.exception("Không tô màu được nhân vật, dùng màu gốc")
                poses = tuple(img for img, _ in source_poses())
            self._incoming = (colors, poses)

        threading.Thread(target=work, name="chotto-mascot-paint", daemon=True).start()

    def _show(self) -> None:
        if not supported():
            _LOG.info("Nhân vật taskbar không khả dụng trên máy này (cần Windows + Pillow), bỏ qua")
            self._broken = True
            return
        self._enabled = True
        previous = w32.foreground_window()                      # lấy TRƯỚC khi dựng cửa sổ (dựng xong có thể đã thành foreground)
        if self._window is None:
            self._build()
        self._place_bounds()
        self._sync_pin()
        self._window.deiconify()
        self._window.attributes("-topmost", True)
        # Tk kích hoạt cửa sổ khi hiện (kể cả có WS_EX_NOACTIVATE) nếu tiến trình đang được quyền foreground:
        # trả focus cho cửa sổ trước đó sau khi Tk xử lý xong sự kiện hiện cửa sổ.
        for delay in (30, 250, 600):
            self._root.after(delay, lambda: self._safe(lambda: self._give_back_focus(previous)))
        self._last = time.monotonic()
        self._schedule(0)
        _LOG.info("Hiện nhân vật taskbar")

    def _sync_pin(self) -> None:
        """Áp trạng thái cố định/vị trí lên nhân vật (đang kéo thì không giật nó về chỗ cũ)."""
        brain = self._brain
        if brain is None:
            return
        brain.set_pinned(self._pinned or self._placing)
        if self._pinned and not self._placing and not self._dragging:
            brain.drag_to(brain.left + _clamp(self._pos) * (brain.right - brain.left))

    def _set_placing(self, on: bool) -> None:
        if on and not (self._enabled and self._pinned):
            on = False                              # chỉ chọn vị trí khi đang hiện và đã bật "cố định"
        self._placing = on
        self._dragging = False
        if self._canvas is not None:
            self._canvas.configure(cursor="sb_h_double_arrow" if on else "")
            self._canvas.delete("hint")
            if on:
                width, height = self._size
                self._canvas.create_line(4, height - 1, width - 4, height - 1, fill="#d4a24a", width=2, dash=(4, 3), tags="hint")
        self._sync_pin()
        self._schedule(0)

    def _press(self, event: Any) -> None:
        if self._placing:
            self._dragging = True
            self._motion(event)

    def _motion(self, event: Any) -> None:
        if self._dragging and self._brain is not None:
            self._brain.drag_to(float(event.x_root))

    def _release(self, _event: Any) -> None:
        """Thả chuột: lưu vị trí (tỉ lệ trên vùng chạy) vào cấu hình."""
        brain = self._brain
        if not self._dragging or brain is None:
            return
        self._dragging = False
        span = brain.right - brain.left
        self._pos = _clamp((brain.x - brain.left) / span) if span > 0 else 0.5
        from ..service.app import save_settings

        try:
            save_settings({"mascot_pos": round(self._pos, 4)})
        except OSError:
            _LOG.exception("Không lưu được vị trí nhân vật")
        self._stamp = config_stamp()

    def _give_back_focus(self, previous: int) -> None:
        if previous and previous != self._hwnd and w32.foreground_window() == self._hwnd:
            w32.set_foreground(previous)

    def _hide(self) -> None:
        self._enabled = False
        if self._window is not None:
            self._window.withdraw()
        _LOG.info("Ẩn nhân vật taskbar")

    def _build(self) -> None:
        import tkinter as tk

        dpi = w32.system_dpi_scale()
        self._scale = _BASE_SCALE * dpi
        self._unit = self._scale / _DESIGN_SCALE
        big = self._scale * _STOP_MUL            # khung phải chứa được tư thế to nhất
        width = int(259 * big * 1.12 + 60 * self._unit)
        height = int(488 * big * 1.03 + 30 * self._unit + 4)
        window = tk.Toplevel(self._root)
        window.withdraw()
        window.overrideredirect(True)
        window.configure(bg=_KEY)
        window.attributes("-transparentcolor", _KEY)
        window.attributes("-topmost", True)
        canvas = tk.Canvas(window, width=width, height=height, bg=_KEY, highlightthickness=0, bd=0)
        canvas.pack()
        canvas.bind("<Button-3>", lambda e: self._safe(lambda: self._menu(e.x_root, e.y_root)))
        canvas.bind("<Double-Button-1>", lambda e: None if self._placing else self._safe(self._open_app))
        canvas.bind("<ButtonPress-1>", lambda e: self._safe(lambda: self._press(e)))
        canvas.bind("<B1-Motion>", lambda e: self._safe(lambda: self._motion(e)))
        canvas.bind("<ButtonRelease-1>", lambda e: self._safe(lambda: self._release(e)))
        window.update_idletasks()
        self._hwnd = w32.toplevel_hwnd(int(window.winfo_id()))
        w32.make_tool_window(self._hwnd)
        self._window, self._canvas = window, canvas
        self._size = (width, height)
        self._brain = MascotBrain(0, 1, unit=self._unit, reduced_motion=not w32.animations_enabled())

    def _place_bounds(self) -> None:
        self._area = w32.taskbar_work_area()
        left, _top, right, _bottom = self._area
        half = self._size[0] / 2
        if self._brain is not None:
            first = self._brain.right <= 1
            self._brain.set_bounds(left + half, right - half)
            if first:
                self._brain.x = left + half + (right - left - 2 * half) * 0.85

    def _menu(self, x: int, y: int) -> None:
        import tkinter as tk

        open_label, hide_label = _MENU.get(self._lang, _MENU["en"])
        menu = tk.Menu(self._window, tearoff=0)
        menu.add_command(label=open_label, command=lambda: self._safe(self._open_app))
        menu.add_command(label=hide_label, command=lambda: self._safe(self._hide_by_user))
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _hide_by_user(self) -> None:
        """"Ẩn nhân vật" trong menu: lưu ``mascot_enabled = false`` để công tắc trong ứng dụng khớp."""
        from ..service.app import save_settings

        self._switch_on = False
        self._hide()
        try:
            save_settings({"mascot_enabled": False})
        except OSError:
            _LOG.exception("Không lưu được cấu hình khi ẩn nhân vật")
        self._stamp = config_stamp()

    def _schedule(self, ms: int) -> None:
        if self._loop_id is not None:
            try:
                self._root.after_cancel(self._loop_id)
            except Exception:  # noqa: BLE001
                pass
        self._loop_id = self._root.after(ms, lambda: self._safe(self._frame))

    def _frame(self) -> None:
        self._loop_id = None
        if self._reload.is_set():
            self._apply_config()
        if not self._enabled or self._window is None or self._brain is None:
            self._events.clear()
            return
        incoming, self._incoming = self._incoming, None
        if incoming is not None and incoming[0] == self._colors:
            self._poses = incoming[1]
            self._cache.clear()
            self._shown_key = None
            self._rendering = None
        brain = self._brain
        while self._events:
            event, level = self._events.popleft()
            if event == "warning_open" and level in WARNING_LEVELS:
                brain.warning_opened()
            elif event == "warning_closed":
                brain.warning_closed()
        now = time.monotonic()
        dt, self._last = now - self._last, now
        brain.tick(dt)
        if self._poses is not None:
            self._draw(brain.frame(), dt)
        self._schedule(_FAST_MS if brain.animating or self._dust or self._dragging else _SLOW_MS)

    def _sprite(self, frame: Frame) -> tuple[Any, tuple[int, bool, int, int, int]]:
        """PhotoImage của khung hình (lượng tử hóa biến dạng để cache được vài chục ảnh là đủ)."""
        key = (frame.pose, frame.flip, round(frame.sx * 100), round(frame.sy * 100), round(frame.rot * 100))
        cached = self._cache.get(key)
        if cached is not None:
            return cached, key
        from PIL import Image as PILImage
        from PIL import ImageTk

        assert self._poses is not None
        src = self._poses[frame.pose]
        scale = self._scale * (_STOP_MUL if frame.pose == POSE_INDEX["stop"] else 1.0)
        w = max(1, round(src.width * scale * key[2] / 100))
        h = max(1, round(src.height * scale * key[3] / 100))
        img = src.resize((w, h), PILImage.Resampling.LANCZOS)
        if key[4]:
            img = img.rotate(math.degrees(key[4] / 100), resample=PILImage.Resampling.BICUBIC, expand=True)
        if frame.flip:
            img = img.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
        alpha = img.getchannel("A").point(lambda a: 255 if a >= 110 else 0)
        flat = PILImage.new("RGB", img.size, _KEY_RGB)
        flat.paste(img.convert("RGB"), mask=alpha)
        photo = ImageTk.PhotoImage(flat, master=self._window)
        if len(self._cache) > 96:
            self._cache.clear()
        self._cache[key] = photo
        return photo, key

    def _draw(self, frame: Frame, dt: float) -> None:
        canvas, (width, height) = self._canvas, self._size
        photo, key = self._sprite(frame)
        cx, cy = width / 2 + frame.dx, height + frame.dy
        if self._sprite_item is None:
            self._sprite_item = canvas.create_image(cx, cy, image=photo, anchor="s")
        else:
            if key != self._shown_key:
                canvas.itemconfigure(self._sprite_item, image=photo)
            canvas.coords(self._sprite_item, cx, cy)
        self._shown_key = key
        left, _top, _right, bottom = self._area
        geom = (round(frame.x - width / 2), bottom - height, width, height)
        if geom != self._geom:
            self._window.geometry(f"{width}x{height}+{geom[0]}+{geom[1]}")
            self._geom = geom
        self._draw_dust(frame, dt, geom[0])

    def _draw_dust(self, frame: Frame, dt: float, win_x: int) -> None:
        """Bụi nhẹ sau gót khi chạy (chấm nhỏ dần rồi biến mất)."""
        brain, canvas, height = self._brain, self._canvas, self._size[1]
        assert brain is not None
        u = self._unit
        if brain.state == "run" and not brain.reduced_motion:
            self._dust_timer -= dt
            if self._dust_timer <= 0:
                self._dust_timer = 0.15
                self._dust.append(_Dust(brain.x - brain.direction * 18 * u, 2 * u, (3 + random.random() * 3) * u,
                                        -brain.direction * (20 + random.random() * 25) * u))
        alive = []
        for p in self._dust:
            p.life -= dt
            p.x += p.vx * dt
            p.h += 10 * u * dt
            p.r += 3 * u * dt
            if p.life > 0:
                alive.append(p)
        self._dust = alive
        for item in self._dust_items:
            canvas.delete(item)
        self._dust_items = []
        for p in alive:
            r = p.r * min(1.0, p.life / 0.25)
            x, y = p.x - win_x, height - p.h
            self._dust_items.append(canvas.create_oval(x - r, y - r, x + r, y + r, fill=_DUST, outline=""))
        if self._sprite_item is not None and self._dust_items:
            canvas.tag_raise(self._sprite_item)
