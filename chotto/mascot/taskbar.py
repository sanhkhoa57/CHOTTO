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

from ..config import MASCOT_DEFAULT_COLORS, MASCOT_FPS_RANGE, config_stamp, data_dir, load_config
from ..platforms import any_process_running, is_default_handler
from ..platforms import overlay as ov
from ..util import clamp as _clamp
from . import qr, speech
from .brain import POSE_INDEX, WARNING_LEVELS, Frame, MascotBrain
from .bubble import SpeechBubble
from .panel import ActionPanel, Button
from .recolor import POSES, normalize_colors, recolored_pose, source_poses
from .scan import QrScan

if TYPE_CHECKING:
    import tkinter as tk

    from PIL import Image

__all__ = ["PLACE_FLAG", "TaskbarMascot", "body_seed", "outline_sprite", "place_flag_set", "set_place_flag", "supported"]

_LOG = logging.getLogger("chotto")


def supported() -> bool:
    """Máy này hiện được nhân vật không (hệ điều hành có cửa sổ overlay trong suốt + Pillow có ImageTk)."""
    if not ov.SUPPORTED:
        return False
    try:
        from PIL import ImageTk  # noqa: F401
    except Exception:  # noqa: BLE001 - thiếu Pillow hoặc thiếu phần Tk của Pillow
        return False
    return True


_BASE_SCALE: Final[float] = 0.30              # 488 px gốc → ~146 px ở 100% scale (gấp đôi bản đầu: 0.15)
_STOP_MUL: Final[float] = 2.0                 # tư thế "Khoan đã!" to gấp đôi cỡ thường (= gấp 4 bản đầu)
_STOP_SS: Final[int] = 2                      # tư thế "Khoan đã!" dựng x2 rồi gộp 2x2 (siêu lấy mẫu) cho nét khi lắc
_TILE_CACHE_MAX: Final[int] = 96              # số khung siêu lấy mẫu nhớ sẵn (lắc 1,6° làm tròn 0,001 rad ≈ 28 góc x vài vị trí lẻ)
_DESIGN_SCALE: Final[float] = 0.31           # tỉ lệ sprite trong khung hoạt ảnh của bản thiết kế
_SLOW_MS: Final[int] = 120
_POLL_MS: Final[int] = 1500
_OUTLINE_PX: Final[float] = 2.0                # độ dày viền đen quanh nhân vật ở 100% (nhân theo DPI), kiểu nét anime
_OUTLINE_RGB: Final[tuple[int, int, int]] = (26, 18, 32)   # đen tím ấm (đen tuyền trông gắt trên nền sáng)
_RIM_RGB: Final[tuple[int, int, int]] = (255, 250, 242)    # đường sáng mảnh ngoài viền: nổi trên taskbar tối, gần như vô hình trên nền sáng
_RIM_ALPHA: Final[int] = 120                   # nhạt: đậm quá thì trên nền tối thành chuỗi chấm trắng lởm chởm


def body_seed(pose: int, size: tuple[int, int]) -> Image.Image:
    """Phần THÂN nhân vật (điểm thuộc nhóm màu 1-6 trong mask) ở cỡ ``size``: hiệu ứng như zZ, dấu !, vệt bụi không thuộc nhóm nào."""
    from PIL import Image as PILImage

    img, msk = source_poses()[pose]
    groups = msk.getchannel("R").point(lambda v: 255 if 1 <= v <= 6 else 0)
    solid = img.getchannel("A").point(lambda v: 255 if v >= 96 else 0)
    from PIL import ImageChops

    seed = ImageChops.multiply(groups, solid).resize(size, PILImage.Resampling.BOX)
    return seed.point(lambda v: 255 if v >= 64 else 0)


def outline_sprite(image: Image.Image, width_px: float, seed: Image.Image | None = None) -> tuple[Image.Image, int]:
    """Viền kiểu anime quanh hình (RGBA): nét tối dày ``width_px`` + đường sáng mảnh bên ngoài (để viền vẫn nổi trên taskbar tối),
    kèm làm nét nhẹ màu bên trong. Trả về (ảnh RGBA đã nới lề, số điểm ảnh lề mỗi phía).

    ``seed`` (ảnh "L" cùng cỡ ``image``): vùng được viền. Truyền phần THÂN nhân vật để các hiệu ứng nhỏ tách rời (zZ, dấu !, vệt bụi)
    không bị viền thành cục đen; thiếu thì dùng toàn bộ phần không trong suốt.
    """
    from PIL import Image as PILImage
    from PIL import ImageFilter

    from PIL import ImageChops

    radius = max(1, round(width_px))
    rim = max(1, round(width_px * 0.6))
    pad = radius + rim + 2
    size = (image.width + 2 * pad, image.height + 2 * pad)
    r, g, b, a = image.split()
    sharp = PILImage.merge("RGB", (r, g, b)).filter(ImageFilter.UnsharpMask(radius=1.2, percent=45, threshold=3))
    solid_seed = (seed if seed is not None else a).point(lambda v: 255 if v >= 96 else 0)
    # Ảnh gốc có một vành sáng li ti ở mép (sót lại khi tách nền); tô màu xong nó thành chấm trắng/hồng đè lên nét viền.
    # Gọt mép thân đi ~nửa nét viền để nét tối bên dưới lộ ra (chỉ quanh thân; hiệu ứng tách rời giữ nguyên).
    erode = max(1, round(width_px * 0.5))
    near_body = solid_seed.filter(ImageFilter.MaxFilter(2 * erode + 3))
    a = ImageChops.composite(a.filter(ImageFilter.MinFilter(2 * erode + 1)), a, near_body)
    body = PILImage.merge("RGBA", (*sharp.split(), a))
    core = PILImage.new("L", size, 0)
    core.paste(solid_seed, (pad, pad))
    dark = core.filter(ImageFilter.MaxFilter(2 * radius + 1))
    light = dark.filter(ImageFilter.MaxFilter(2 * rim + 1)).filter(ImageFilter.GaussianBlur(1.0))
    canvas = PILImage.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(PILImage.new("RGBA", size, (*_RIM_RGB, 255)), mask=light.point(lambda v: v * _RIM_ALPHA // 255))
    canvas.paste(PILImage.new("RGBA", size, (*_OUTLINE_RGB, 255)), mask=dark.filter(ImageFilter.GaussianBlur(0.6)))
    canvas.alpha_composite(body, (pad, pad))
    return canvas, pad
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
_DUST_RGBA: Final[tuple[int, int, int, int]] = (216, 210, 200, 255)
_MENU: Final[dict[str, tuple[str, str]]] = {"en": ("Open Chotto", "Hide character"),
                                            "vi": ("Mở CHOTTO", "Ẩn nhân vật")}   # hai mục còn lại lấy chữ ở ``qr.TEXT``
_GREET_GAP: Final[float] = 30.0                 # giây tối thiểu giữa hai lời chào
_IDLE_RANGE: Final[tuple[float, float]] = (480.0, 900.0)   # giây giữa hai lần nhân vật tự nói khi rảnh


@dataclass
class _Dust:
    x: float
    h: float
    r: float
    vx: float
    life: float = 0.5


class TaskbarMascot:
    """Cửa sổ nhân vật trên luồng Tk của agent. Mọi phương thức công khai đều không ném lỗi."""

    def __init__(self, root: tk.Tk, open_app: Callable[[], None], open_link: Callable[[str], None] | None = None) -> None:
        """Gắn vào cửa sổ gốc ``root`` (ẩn) của agent; ``open_app`` mở cửa sổ ứng dụng CHOTTO.

        ``open_link`` đưa một link vào luồng chặn link của agent (có màn hình cảnh báo); thiếu thì kết quả QR không có nút mở.
        """
        self._root = root
        self._open_app = open_app
        self._open_link = open_link
        self._panel: ActionPanel | None = None
        self._scan: QrScan | None = None
        self._events: collections.deque[tuple[str, str]] = collections.deque()
        self._reload = threading.Event()
        self._broken = False
        self._enabled = False
        self._switch_on = False                # công tắc "mascot_enabled" trong cấu hình (khác với đang hiện)
        self._startup = "login"
        self._frame_s = 1 / 60                  # nhịp khung hình theo cài đặt mascot_fps (bù thời gian dựng khung để nhịp không lệch)
        self._zalo_names: tuple[str, ...] = ()
        self._timing: tuple[float, float] = (3.0, 3.0)          # (giây ngủ, giây chạy) theo cài đặt
        self._colors: tuple[str, ...] = tuple(MASCOT_DEFAULT_COLORS)
        self._lang = "en"
        self._stamp: tuple[int, int] | None = None
        self._window: Any = None
        self._canvas: Any = None
        self._surface: Any = None                           # ``overlay.Surface`` (Win32 layered / Tk trong suốt trên macOS)
        self._brain: MascotBrain | None = None
        self._poses: list[Image.Image | None] | None = None       # từng tư thế đã tô (tư thế mới tô xong thì thay ngay, không đợi đủ bốn)
        self._incoming: collections.deque[tuple[tuple[str, ...], int, Image.Image]] = collections.deque()
        self._rendering: tuple[str, ...] | None = None
        self._cache: dict[int, Any] = {}                    # tư thế -> (sprite RGBa, lề viền, hệ số siêu lấy mẫu), xem ``_base``
        self._tile_cache: dict[tuple[Any, ...], Any] = {}   # khung siêu lấy mẫu đã dựng (tư thế "Khoan đã!"), xoá cùng ``_cache``
        self._dust: list[_Dust] = []
        self._dust_cache: dict[int, Any] = {}
        self._sprite_h = 1
        self._dust_timer = 0.0
        self._last = time.monotonic()
        self._loop_id: str | None = None
        self._scale = _BASE_SCALE
        self._unit = 1.0
        self._area: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._size: tuple[int, int] = (1, 1)
        self._hwnd: Any = 0                   # tay cầm cửa sổ (``overlay.handle``)
        self._pinned = False
        self._pos = 0.85                      # vị trí cố định, tỉ lệ 0..1 trên vùng chạy
        self._placing = False
        self._dragging = False
        self._bubble: SpeechBubble | None = None
        self._greeted = -_GREET_GAP
        self._presented: tuple[Any, ...] | None = None   # khung đang hiện (khung không đổi thì khỏi vẽ lại)
        self._fine = False                    # đang giữ bộ hẹn giờ 1 ms (chỉ khi có hoạt ảnh)
        self._idle_due = 0.0

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
        scan, self._scan = self._scan, None
        panel, self._panel = self._panel, None
        for gone in (scan.cancel if scan is not None else None, panel.destroy if panel is not None else None):
            if gone is not None:
                try:
                    gone()
                except Exception:  # noqa: BLE001
                    pass
        bubble, self._bubble = self._bubble, None
        if bubble is not None:
            bubble.destroy()
        window, self._window = self._window, None
        if window is not None:
            try:
                window.destroy()
            except Exception:  # noqa: BLE001
                pass
        surface, self._surface = self._surface, None
        if surface is not None:
            surface.close()
        self._cache.clear()
        self._tile_cache.clear()
        self._set_fine(False)

    def _poll(self) -> None:
        """Theo dõi cấu hình mỗi ``_POLL_MS`` (dự phòng cho tín hiệu ``config_changed``)."""
        self._apply_config(force=self._stamp is None)
        self._reconcile()
        if self._enabled and self._window is not None:
            self._place_bounds()                      # đổi độ phân giải / dời taskbar
            self._idle_talk()
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
        self._frame_s = 1 / _clamp(float(cfg["mascot_fps"]), *map(float, MASCOT_FPS_RANGE))
        self._zalo_names = tuple(cfg["zalo_processes"]) + tuple(cfg["zalo_bundle_ids"])     # macOS so cả bundle id
        timing = (float(cfg["mascot_sleep_s"]), float(cfg["mascot_run_s"]))
        if timing != self._timing:                              # lưu cài đặt khác không được làm lại giấc ngủ đang dở
            self._timing = timing
            if self._brain is not None:
                self._brain.set_timing(*timing)
        self._reconcile()
        self._sync_pin()

    def _reconcile(self) -> None:
        """Hiện/ẩn theo công tắc; chế độ "zalo" thì chỉ hiện khi Zalo đang chạy.

        CHOTTO không phải trình mở link (chưa đặt, hoặc người dùng giữ trình duyệt cũ) thì không hiện: nhân vật là dấu hiệu
        "đang được bảo vệ". Không xác định được (``None``) thì vẫn hiện.
        """
        want = (self._switch_on and is_default_handler() is not False
                and (self._startup != "zalo" or any_process_running(self._zalo_names)))
        if want and not self._enabled:
            self._show()
        elif not want and self._enabled:
            self._hide()

    def _render_async(self, colors: tuple[str, ...]) -> None:
        """Tô màu trên luồng nền, TƯ THẾ ĐANG HIỆN TRƯỚC (hiện ngay khi xong), ba tư thế còn lại tô tiếp sau đó.

        Có lệnh đổi màu mới hơn thì bỏ dở việc đang làm. Tk nhận từng tư thế ở khung hình sau.
        """
        if self._rendering == colors:
            return
        self._rendering = colors
        first = POSE_INDEX[self._brain.state] if self._brain is not None else 0

        def work() -> None:
            for n in [first] + [p for p in range(POSES) if p != first]:
                if self._rendering != colors:
                    return                                # đã có bộ màu mới hơn
                try:
                    image = recolored_pose(colors, n)
                except Exception:  # noqa: BLE001 - lỗi tô màu: dùng màu gốc
                    _LOG.exception("Không tô màu được nhân vật, dùng màu gốc")
                    image = source_poses()[n][0]
                self._incoming.append((colors, n, image))
            if self._rendering == colors:
                self._rendering = None

        threading.Thread(target=work, name="chotto-mascot-paint", daemon=True).start()

    def _show(self) -> None:
        if not supported():
            _LOG.info("Nhân vật không khả dụng trên máy này (cần Windows/macOS + Pillow), bỏ qua")
            self._broken = True
            return
        self._enabled = True
        self._presented = None
        previous = ov.foreground()                      # lấy TRƯỚC khi dựng cửa sổ (dựng xong có thể đã thành foreground)
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
        now = time.monotonic()
        if now - self._greeted >= _GREET_GAP:         # mỗi lần nhân vật vừa hiện ra thì chào (chống chào dồn khi hiện/ẩn liên tục)
            self._greeted = now
            self._root.after(1500, lambda: self._safe(lambda: self._say("normal", speech.pick("hello"))))
        _LOG.info("Hiện nhân vật taskbar")

    def _sync_pin(self) -> None:
        """Áp trạng thái cố định/vị trí lên nhân vật (đang kéo thì không giật nó về chỗ cũ)."""
        brain = self._brain
        if brain is None:
            return
        brain.set_pinned(self._pinned or self._placing or self._chatting() or self._panel_open())
        if self._pinned and not self._placing and not self._dragging:
            brain.drag_to(brain.left + _clamp(self._pos) * (brain.right - brain.left))

    def _set_placing(self, on: bool) -> None:
        if on and not (self._enabled and self._pinned):
            on = False                              # chỉ chọn vị trí khi đang hiện và đã bật "cố định"
        self._placing = on
        self._dragging = False
        if self._canvas is not None:
            self._canvas.configure(cursor="sb_h_double_arrow" if on else "")
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
        own = ov.own(self._hwnd)
        if previous and previous != own and ov.foreground() == own:
            ov.set_foreground(previous)

    def _set_fine(self, on: bool) -> None:
        """Bộ hẹn giờ 1 ms chỉ bật lúc đang chạy/giật mình (cặp bật/tắt luôn cân bằng)."""
        if on != self._fine:
            self._fine = on
            ov.fine_timer(on)

    def _hide(self) -> None:
        self._enabled = False
        self._set_fine(False)
        self._cancel_scan()
        if self._bubble is not None:
            self._bubble.close_chat()
            self._bubble.hide()
        if self._window is not None:
            self._window.withdraw()
        _LOG.info("Ẩn nhân vật taskbar")

    def _build(self) -> None:
        import tkinter as tk

        dpi = ov.dpi_scale()
        self._scale = _BASE_SCALE * dpi
        self._unit = self._scale / _DESIGN_SCALE
        big = self._scale * _STOP_MUL            # khung phải chứa được tư thế to nhất
        width = int(259 * big * 1.12 + 60 * self._unit)
        height = int(488 * big * 1.03 + 30 * self._unit + 4)
        window = tk.Toplevel(self._root)
        window.withdraw()
        ov.prepare(window)                       # macOS: trước overrideredirect, nếu không nền ra đen
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        canvas = tk.Canvas(window, width=width, height=height, highlightthickness=0, bd=0)       # chỉ để nhận chuột; hình vẽ qua LayeredSurface
        canvas.pack()
        canvas.bind("<Button-3>", lambda e: self._safe(lambda: self._menu(e.x_root, e.y_root)))
        canvas.bind("<Button-2>", lambda e: self._safe(lambda: self._menu(e.x_root, e.y_root)))       # macOS: chuột phải là Button-2
        canvas.bind("<Control-Button-1>", lambda e: self._safe(lambda: self._menu(e.x_root, e.y_root)))
        canvas.bind("<Double-Button-1>", lambda e: None if self._placing else self._safe(self._open_choices))
        canvas.bind("<ButtonPress-1>", lambda e: self._safe(lambda: self._press(e)))
        canvas.bind("<B1-Motion>", lambda e: self._safe(lambda: self._motion(e)))
        canvas.bind("<ButtonRelease-1>", lambda e: self._safe(lambda: self._release(e)))
        window.update_idletasks()
        self._hwnd = ov.handle(window)
        ov.make_tool_window(self._hwnd)
        ov.enable_layered(self._hwnd)
        self._surface = ov.Surface(self._hwnd, width, height)
        self._window, self._canvas = window, canvas
        self._size = (width, height)
        self._brain = MascotBrain(0, 1, unit=self._unit, reduced_motion=not ov.animations_enabled())
        self._brain.set_timing(*self._timing)
        self._bubble = SpeechBubble(self._root, dpi, self._on_chat_change)
        if ov.QR_SUPPORTED:                     # bảng chọn nhanh chỉ để chọn giữa quét QR và hỏi đáp
            self._panel = ActionPanel(self._root, dpi, self._on_panel_change)
            self._scan = QrScan(self._root, dpi, self._safe, self._on_capturing, self._on_qr_reading, self._on_qr_report)

    def _place_bounds(self) -> None:
        self._area = ov.work_area()
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
        words = qr.texts(self._lang)
        menu = tk.Menu(self._window, tearoff=0)
        if ov.QR_SUPPORTED:
            menu.add_command(label=words["scan"], command=lambda: self._safe(self._start_scan))
        menu.add_command(label=words["ask"], command=lambda: self._safe(self._open_chat))
        menu.add_command(label=open_label, command=lambda: self._safe(self._open_app))
        menu.add_command(label=hide_label, command=lambda: self._safe(self._hide_by_user))
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    # ---- lời thoại + hỏi đáp (chotto/mascot/bubble.py) ----
    def _chatting(self) -> bool:
        return self._bubble is not None and self._bubble.chatting

    def _say(self, kind: speech.Kind, text: str) -> None:
        """Nói một câu (bỏ qua khi đang chat, đang mở bảng nút hoặc đang chụp); đặt lại đồng hồ "rảnh rỗi"."""
        if self._bubble is None or not self._enabled or self._chatting() or self._panel_open() or self._capturing():
            return
        self._idle_due = time.monotonic() + random.uniform(*_IDLE_RANGE)
        self._bubble.say(kind, text)
        self._schedule(0)

    def _idle_talk(self) -> None:
        now = time.monotonic()
        if not self._idle_due:
            self._idle_due = now + random.uniform(*_IDLE_RANGE)
        elif now >= self._idle_due and self._brain is not None and not self._brain.warning and self._bubble is not None                 and not self._bubble.visible and not self._panel_open():
            self._say("thought", speech.pick("idle"))

    def _open_chat(self) -> None:
        if self._bubble is not None and self._enabled and not self._placing:
            self._cancel_scan()
            self._bubble.open_chat()
            self._schedule(0)                                            # đặt chỗ bong bóng + ô chat ngay ở khung hình tới

    # ---- thanh chọn nhanh + quét QR (panel.py, scan.py) ----
    def _panel_open(self) -> bool:
        return self._panel is not None and self._panel.visible

    def _capturing(self) -> bool:
        return self._scan is not None and self._scan.capturing

    def _cancel_scan(self) -> None:
        """Hủy lượt quét đang dở và đóng bảng nút (lớp phủ không được che cửa sổ khác)."""
        if self._scan is not None:
            self._scan.cancel()
        if self._panel is not None:
            self._panel.close()

    def _clear_bubble(self) -> None:
        if self._bubble is not None:
            self._bubble.close_chat()
            self._bubble.hide()

    def _open_choices(self) -> None:
        """Nhấn đúp: hai ô "Quét QR" và "Hỏi Chotto" (máy không quét được QR thì mở thẳng ô chat)."""
        if not ov.QR_SUPPORTED:
            self._open_chat()
            return
        if self._panel is None or not self._enabled or self._placing or self._capturing():
            return
        self._cancel_scan()
        self._clear_bubble()
        words = qr.texts(self._lang)
        self._panel.show("normal", words["choose"], [Button("scan", words["scan"], True), Button("ask", words["ask"])],
                         lambda key: self._safe(lambda: self._choose(key)), big=True, modal=True)
        self._schedule(0)

    def _choose(self, key: str) -> None:
        if self._panel is not None:
            self._panel.close()
        if key == "scan":
            self._start_scan()
        elif key == "ask":
            self._open_chat()

    def _start_scan(self) -> None:
        if self._scan is None or not self._enabled or self._placing or self._capturing():
            return
        self._cancel_scan()
        self._clear_bubble()
        self._scan.start(self._lang)

    def _on_panel_change(self, on: bool) -> None:
        self._on_chat_change(on or self._chatting())

    def _on_capturing(self, on: bool) -> None:
        """Giấu nhân vật trong lúc chụp và chọn vùng. Đẩy khung trong suốt thay vì ``withdraw``: hiện lại bằng Tk sẽ cướp focus."""
        if on and self._surface is not None:
            width, height = self._size
            self._surface.update(bytes(width * height * 4), self._area[0], self._area[3] - height)
        self._presented = None
        self._schedule(0)

    def _on_qr_reading(self) -> None:
        if self._bubble is not None and self._enabled:
            self._bubble.say("thought", qr.texts(self._lang)["reading"], keep=True)
            self._schedule(0)

    def _on_qr_report(self, report: qr.QrReport) -> None:
        if not self._enabled or self._panel is None or self._chatting():
            return
        self._idle_due = time.monotonic() + random.uniform(*_IDLE_RANGE)
        if not report.payload:                                          # không thấy mã / lỗi: chỉ báo nhẹ, tự ẩn
            self._say(report.kind, report.message)
            return
        self._clear_bubble()
        self._show_report(report, copied=False)
        self._schedule(0)

    def _show_report(self, report: qr.QrReport, copied: bool) -> None:
        assert self._panel is not None
        words = qr.texts(self._lang)
        buttons = [Button("copy", words["copied" if copied else "copy"])]
        if report.link and self._open_link is not None:
            buttons.append(Button("open", words["open"], primary=report.level == "SAFE"))
        self._panel.show(report.kind, report.message, buttons,
                         lambda key: self._safe(lambda: self._report_action(report, key)))

    def _report_action(self, report: qr.QrReport, key: str) -> None:
        if key == "copy":
            self._root.clipboard_clear()
            self._root.clipboard_append(report.payload)
            self._show_report(report, copied=True)
        elif key == "open" and report.link and self._open_link is not None:
            if self._panel is not None:
                self._panel.close()
            self._open_link(report.link)                                # qua đúng luồng chặn link: link rủi ro vẫn hiện cảnh báo

    def _on_chat_change(self, on: bool) -> None:
        if self._brain is not None:
            self._brain.attend(on)
        self._sync_pin()
        self._schedule(0)

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
        started = time.perf_counter()
        if self._reload.is_set():
            self._apply_config()
        if not self._enabled or self._window is None or self._brain is None:
            self._events.clear()
            return
        while self._incoming:
            colors, n, image = self._incoming.popleft()
            if colors != self._colors:
                continue                                  # kết quả của bộ màu cũ
            if self._poses is None:
                self._poses = [None] * POSES
            self._poses[n] = image
            self._cache.pop(n, None)
            if n == POSE_INDEX["stop"]:
                self._tile_cache.clear()
            self._presented = None
        brain = self._brain
        while self._events:
            event, level = self._events.popleft()
            if event == "warning_open" and level in WARNING_LEVELS:
                self._cancel_scan()                           # lớp phủ/bảng nút không được che màn hình cảnh báo
                brain.warning_opened()
                self._say("alert", speech.pick("warn"))
            elif event == "warning_closed":
                brain.warning_closed()
                self._say("normal", speech.pick("closed"))
        now = time.monotonic()
        dt, self._last = now - self._last, now
        brain.tick(dt)
        frame = brain.frame()
        if self._capturing():                                       # đang chụp/chọn vùng: không vẽ lại nhân vật
            self._set_fine(False)
            self._schedule(_SLOW_MS)
            return
        if self._poses is not None and self._poses[frame.pose] is not None:
            self._draw(frame, dt)
        moving = brain.animating or bool(self._dust) or self._dragging or (brain.state == "sleep" and not brain.reduced_motion)
        self._set_fine(moving)                                              # thở cũng cần 60 khung/giây mới mượt như web
        spent = time.perf_counter() - started
        self._schedule(max(1, round((self._frame_s - spent) * 1000)) if moving else _SLOW_MS)

    def _base(self, pose: int) -> tuple[Any, int, int]:
        """Sprite của tư thế, alpha đã nhân trước (RGBa) để nội suy không viền đen. Cache theo tư thế.

        Trả về (ảnh, lề viền, hệ số siêu lấy mẫu k): ảnh dựng ở cỡ màn hình x k; ``_sprite_tile`` biến đổi ở cỡ đó rồi thu về.
        Tư thế "Khoan đã!" có ảnh gốc nhỏ nhất mà hiện to nhất (gần 1:1 với ảnh gốc) và lắc liên tục: vẽ thẳng ở cỡ màn hình
        thì nội suy bilinear lúc xoay làm nhòe thêm nửa điểm ảnh. Dựng x2 rồi gộp 2x2 thì nét giữ được, chỉ tốn ~4 lần pixel.
        """
        cached = self._cache.get(pose)
        if cached is not None:
            return cached  # type: ignore[no-any-return]
        from PIL import Image as PILImage

        assert self._poses is not None
        src = self._poses[pose]
        assert src is not None
        stop = pose == POSE_INDEX["stop"]
        k = _STOP_SS if stop else 1
        scale = self._scale * (_STOP_MUL if stop else 1.0) * k
        size = (max(1, round(src.width * scale)), max(1, round(src.height * scale)))
        sized = src.resize(size, PILImage.Resampling.LANCZOS)                 # KHÔNG làm nét thêm: ảnh gốc có chấm nhiễu, làm nét thì thành chấm trắng
        framed, pad = outline_sprite(sized, _OUTLINE_PX * self._scale / _BASE_SCALE * k, body_seed(pose, size))
        entry = (framed.convert("RGBa"), pad, k)
        self._cache[pose] = entry
        return entry

    def _sprite_tile(self, frame: Frame, frac_x: float) -> tuple[Any, int, int, int]:
        """Vẽ sprite với co giãn/xoay/lật/dịch chuyển LẺ TỚI MỘT PHẦN ĐIỂM ẢNH (như GPU trên web), quanh chân giữa của nó.

        Trả về (ảnh RGBa nhỏ vừa khít sprite, x, y của góc trái trên trong khung, chiều cao sprite để đặt bong bóng thoại).
        """
        from PIL import Image as PILImage

        base, pad, k = self._base(frame.pose)
        key: tuple[Any, ...] | None = None
        if k > 1:                                                             # siêu lấy mẫu tốn ~4 lần: nhớ khung (tư thế lắc qua lại nên lặp lại)
            frame = Frame(frame.pose, 0.0, frame.dx, frame.dy, frame.flip, frame.sx, frame.sy, round(frame.rot * 1000) / 1000)
            key = (frame, frac_x, self._size)
            hit = self._tile_cache.get(key)
            if hit is not None:
                return hit  # type: ignore[no-any-return]
        bw, bh = base.size
        width, height = self._size
        flip = -1.0 if frame.flip else 1.0
        theta = -frame.rot if frame.flip else frame.rot                       # góc xoay nhìn thấy trên màn hình (ngược chiều kim đồng hồ dương)
        c, s = math.cos(theta), math.sin(theta)
        p, q = frame.sx * flip, frame.sy
        m00, m01, m10, m11 = c * p, s * q, -s * p, c * q                      # M = R · diag(sx·lật, sy)
        px, py = (width / 2 + frac_x + frame.dx) * k, (height + frame.dy) * k   # chân giữa sprite trong khung (toạ độ x k)
        xs, ys = [], []
        foot = bh - pad                                                       # chân nằm trên đáy ảnh một khoảng bằng lề viền
        for cx, cy in ((-bw / 2, -foot), (bw / 2, -foot), (bw / 2, float(pad)), (-bw / 2, float(pad))):
            xs.append(px + m00 * cx + m01 * cy)
            ys.append(py + m10 * cx + m11 * cy)
        ox, oy = (math.floor(min(xs)) // k - 1) * k, (math.floor(min(ys)) // k - 1) * k   # góc tile thẳng hàng lưới k để gộp đúng điểm ảnh
        tw, th = (-(-math.ceil(max(xs)) // k) + 1) * k - ox, (-(-math.ceil(max(ys)) // k) + 1) * k - oy
        det = m00 * m11 - m01 * m10
        i00, i01, i10, i11 = m11 / det, -m01 / det, -m10 / det, m00 / det     # nghịch đảo của M
        rx, ry = ox - px, oy - py
        data = (i00, i01, bw / 2 + i00 * rx + i01 * ry, i10, i11, foot + i10 * rx + i11 * ry)
        tile = base.transform((tw, th), PILImage.Transform.AFFINE, data, resample=PILImage.Resampling.BILINEAR)   # như GPU trên web
        result = (tile, ox, oy, round(max(ys) - min(ys)))
        if key is not None:
            result = (tile.reduce(k), ox // k, oy // k, round((max(ys) - min(ys)) / k))   # gộp kxk (alpha đã nhân trước nên không viền đen)
            if len(self._tile_cache) >= _TILE_CACHE_MAX:
                self._tile_cache.pop(next(iter(self._tile_cache)))
            self._tile_cache[key] = result
        return result

    @staticmethod
    def _blit(dst: Any, src: Any, x: int, y: int) -> None:
        """Dán ``src`` (RGBA, alpha mềm) lên ``dst`` tại (x, y), cắt phần lọt ra ngoài."""
        left, top = max(0, -x), max(0, -y)
        right, bottom = min(src.width, dst.width - x), min(src.height, dst.height - y)
        if right > left and bottom > top:
            dst.alpha_composite(src.crop((left, top, right, bottom)), (x + left, y + top))

    def _draw(self, frame: Frame, dt: float) -> None:
        """Dựng cả khung hình bằng Pillow rồi đổi ảnh + vị trí cửa sổ trong một lệnh (không rách hình, viền mịn)."""
        from PIL import Image as PILImage

        surface, (width, height) = self._surface, self._size
        if surface is None:
            return
        _left, _top, _right, bottom = self._area
        win_x = math.floor(frame.x - width / 2)
        frac_x = round((frame.x - width / 2 - win_x) * 16) / 16
        self._step_dust(dt)
        # làm tròn tham số tới 1/16 điểm ảnh: các khung giống hệt nhau (đang đứng/thở rất chậm) thì không vẽ lại
        f = Frame(frame.pose, frame.x, round(frame.dx * 16) / 16, round(frame.dy * 16) / 16, frame.flip,
                  round(frame.sx * 2500) / 2500, round(frame.sy * 2500) / 2500, round(frame.rot * 5000) / 5000)
        present = (f, win_x, frac_x, bottom) if not self._dust and not self._placing else None
        if present is None or present != self._presented:
            tile, tx, ty, self._sprite_h = self._sprite_tile(f, frac_x)
            if self._dust or self._placing:                                   # có bụi/đường gợi ý: ghép theo alpha thường
                image = PILImage.new("RGBA", (width, height), (0, 0, 0, 0))
                self._paint_dust(image, win_x)
                self._blit(image, tile.convert("RGBA"), tx, ty)
                if self._placing:                                             # đường đứt gợi ý "kéo tôi sang trái/phải"
                    from PIL import ImageDraw

                    draw = ImageDraw.Draw(image)
                    for x0 in range(4, width - 8, 7):
                        draw.line((x0, height - 2, x0 + 4, height - 2), fill=(212, 162, 74, 255), width=2)
                packed = image.convert("RGBa")
            else:                                                             # thở/đứng/nhảy: dán thẳng (đã nhân alpha trước), khỏi đổi định dạng
                packed = PILImage.new("RGBa", (width, height))
                packed.paste(tile, (tx, ty))
            surface.update(packed.tobytes("raw", "BGRa"), win_x, bottom - height)
            self._presented = present
        sprite_top = bottom + round(frame.dy) - self._sprite_h
        if self._bubble is not None and self._bubble.visible:
            self._bubble.place(round(frame.x + frame.dx), sprite_top, self._area)
        if self._panel is not None:                            # luôn báo chỗ để bảng vừa mở hiện đúng vị trí ngay
            self._panel.place(round(frame.x + frame.dx), sprite_top, self._area)

    def _step_dust(self, dt: float) -> None:
        """Bụi nhẹ sau gót khi chạy: sinh hạt mới và cho các hạt cũ bay, lớn dần, tàn đi."""
        brain = self._brain
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

    def _dust_disc(self, radius: int) -> Any:
        """Hình tròn bụi khử răng cưa (vẽ lớn gấp 4 rồi thu nhỏ), cache theo bán kính."""
        disc = self._dust_cache.get(radius)
        if disc is None:
            from PIL import Image as PILImage
            from PIL import ImageDraw

            big = PILImage.new("RGBA", (radius * 8, radius * 8), (0, 0, 0, 0))
            ImageDraw.Draw(big).ellipse((0, 0, radius * 8 - 1, radius * 8 - 1), fill=_DUST_RGBA)
            disc = self._dust_cache[radius] = big.resize((radius * 2, radius * 2), PILImage.Resampling.LANCZOS)
        return disc

    def _paint_dust(self, image: Any, win_x: int) -> None:
        height = self._size[1]
        for p in self._dust:
            r = max(1, round(p.r * min(1.0, p.life / 0.25)))
            self._blit(image, self._dust_disc(r), round(p.x - win_x) - r, round(height - p.h) - r)
