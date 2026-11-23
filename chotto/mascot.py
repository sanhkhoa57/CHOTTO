"""Nhân vật đồng hành trên thanh taskbar (Windows): ngủ khi rảnh, giật mình và giơ tay "Khoan đã!" khi có link đáng ngờ.

Ba phần tách biệt để kiểm thử được mà không cần màn hình:

- ``recolor_*``: thuật toán tô màu liên tục chép từ ``design/chotto_mascot_customizer.html`` (Pillow, có cache).
- ``MascotBrain``: state machine thuần (``sleep`` / ``alert`` / ``run`` / ``stop``), không đụng tới Tk.
- ``TaskbarMascot``: cửa sổ overlay trên luồng Tk sẵn có của agent.

Fail-safe tuyệt đối: thiếu Pillow, không phải Windows, không có màn hình hoặc cửa sổ lỗi giữa chừng thì chỉ ghi
log rồi tắt nhân vật cho phiên này. Không có đường mã nào ở đây được ném lỗi ra agent hay làm chậm luồng chặn link
(``notify`` chỉ xếp sự kiện vào hàng đợi).
"""
from __future__ import annotations

import collections
import json
import logging
import math
import os
import random
import re
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Final, Literal

from .config import MASCOT_DEFAULT_COLORS, data_dir, load_config, resource_path

if TYPE_CHECKING:
    import tkinter as tk

    from PIL import Image

__all__ = [
    "ALERT_SECONDS",
    "REST_SECONDS",
    "RUN_SECONDS",
    "Frame",
    "MascotBrain",
    "Palette",
    "TaskbarMascot",
    "place_flag_set",
    "set_place_flag",
    "load_palette",
    "normalize_colors",
    "recolor_image",
    "recolor_pixels",
    "recolored_poses",
    "supported",
]

_LOG = logging.getLogger("chotto")

State = Literal["sleep", "alert", "run", "stop"]
POSE_INDEX: Final[dict[str, int]] = {"sleep": 0, "alert": 1, "run": 2, "stop": 3}
GROUPS: Final[int] = 6
ALERT_SECONDS: Final[float] = 0.8
RUN_SECONDS: Final[float] = 3.0       # mỗi nhịp chạy
REST_SECONDS: Final[float] = 3.0      # nghỉ (ngủ) giữa hai nhịp chạy
WARNING_LEVELS: Final[frozenset[str]] = frozenset({"WARN", "HIGH", "BLOCKED"})
_HEX: Final[re.Pattern[str]] = re.compile(r"^#[0-9a-fA-F]{6}$")


# ---------------------------------------------------------------- tô màu
@dataclass(frozen=True)
class Palette:
    """Tham số tô màu (``chotto/mascot_assets/palette.json``, trích từ bản thiết kế)."""

    default: tuple[str, ...]
    pivot: tuple[float, ...]                                     # độ sáng "giữa" của từng nhóm trong ảnh gốc
    params: tuple[tuple[float, float, float, float], ...]        # (ngưỡng viền thấp, cao, gamma tối, mức nâng sáng)
    swatches: tuple[tuple[str, ...], ...]


@lru_cache(maxsize=1)
def load_palette() -> Palette:
    """Đọc bảng tham số đóng gói kèm."""
    raw = json.loads(resource_path("mascot_assets", "palette.json").read_text("utf-8"))
    return Palette(
        default=tuple(str(c).lower() for c in raw["default"]),
        pivot=tuple(float(v) for v in raw["pivot"]),
        params=tuple((float(p[0]), float(p[1]), float(p[2]), float(p[3])) for p in raw["params"]),
        swatches=tuple(tuple(str(c).lower() for c in group) for group in raw["swatches"]),
    )


def normalize_colors(colors: object) -> tuple[str, ...]:
    """6 mã ``#rrggbb`` viết thường; dữ liệu sai thì trả về bộ màu mặc định."""
    if (isinstance(colors, (list, tuple)) and len(colors) == GROUPS
            and all(isinstance(c, str) and _HEX.match(c) for c in colors)):
        return tuple(str(c).lower() for c in colors)
    return tuple(MASCOT_DEFAULT_COLORS)


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _lum(r: float, g: float, b: float) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def _round(value: float) -> int:
    """Như ``Math.round`` của JavaScript với số không âm (Python ``round`` làm tròn kiểu ngân hàng)."""
    return int(value + 0.5)


def recolor_pixels(src: bytes, mask: bytes, colors: Sequence[str], palette: Palette) -> bytes:
    """Tô màu một ảnh RGBA (byte thô) theo mask: kênh R = số nhóm + 1, kênh G = 255 là điểm cần giữ nguyên.

    Giống hệt ``render()`` của bản thiết kế: nhóm trùng màu mặc định giữ nguyên ảnh gốc; viền đen được bảo vệ
    theo ngưỡng độ sáng từng nhóm; phần tối giữ tỉ lệ độ sáng, phần sáng nâng mềm về trắng; da giữ sắc má hồng;
    mắt chỉ chừa chấm sáng trắng tinh.
    """
    target = [_rgb(c) for c in normalize_colors(list(colors))]
    same = [c == d for c, d in zip(normalize_colors(list(colors)), palette.default)]
    if all(same):
        return bytes(src)
    base = [_rgb(c) for c in palette.default]
    base_lum = [_lum(*b) for b in base]
    skin_lum = _lum(*target[2])
    blush_k = 0.45 + 0.30 * min(1.0, skin_lum / base_lum[2])
    out = bytearray(src)
    memo: dict[int, tuple[int, int, int]] = {}
    for i in range(0, len(src), 4):
        if src[i + 3] == 0:
            continue
        k = mask[i] - 1
        if k < 0 or k >= GROUPS or mask[i + 1] == 255 or same[k]:
            continue
        r, g, b = src[i], src[i + 1], src[i + 2]
        key = (((r << 8 | g) << 8 | b) << 3) | k
        hit = memo.get(key)
        if hit is None:
            hit = _recolor_one(r, g, b, k, target[k], palette, base[2], base_lum[2], blush_k)
            memo[key] = hit
        out[i], out[i + 1], out[i + 2] = hit
    return bytes(out)


def _recolor_one(r: int, g: int, b: int, k: int, tk_: tuple[int, int, int], palette: Palette,
                 base_skin: tuple[int, int, int], base_skin_lum: float, blush_k: float) -> tuple[int, int, int]:
    """Màu mới của một điểm ảnh thuộc nhóm ``k`` (``tk_`` là màu đích của nhóm)."""
    y = _lum(r, g, b)
    low, high, gamma, lift = palette.params[k]
    w = _clamp((y - low) / (high - low))
    if k == 1:                                            # mắt: chấm sáng gần trắng tinh thì giữ nguyên
        mn, mx = min(r, g, b), max(r, g, b)
        if mn > 212 and mx - mn < 28:
            w *= _clamp((232 - mn) / 20)
    if w <= 0:
        return r, g, b
    pivot = palette.pivot[k]
    if y <= pivot:
        scale = max(0.0, y / pivot) ** gamma
        nr, ng, nb = tk_[0] * scale, tk_[1] * scale, tk_[2] * scale
    else:
        h = min(1.0, (y - pivot) / max(1.0, 255 - pivot)) * lift
        nr, ng, nb = tk_[0] + (255 - tk_[0]) * h, tk_[1] + (255 - tk_[1]) * h, tk_[2] + (255 - tk_[2]) * h
    if k == 2:                                            # da: giữ phần lệch màu so với da gốc (má hồng)
        ratio = y / base_skin_lum
        nr += (r - base_skin[0] * ratio) * blush_k
        ng += (g - base_skin[1] * ratio) * blush_k
        nb += (b - base_skin[2] * ratio) * blush_k
    nr, ng, nb = _clamp(nr, 0, 255), _clamp(ng, 0, 255), _clamp(nb, 0, 255)
    iw = 1 - w
    return _round(r * iw + nr * w), _round(g * iw + ng * w), _round(b * iw + nb * w)


def recolor_image(image: Image.Image, mask: Image.Image, colors: Sequence[str], palette: Palette) -> Image.Image:
    """Bản Pillow của ``recolor_pixels`` (ảnh và mask cùng kích thước)."""
    from PIL import Image as PILImage

    rgba = image.convert("RGBA")
    data = recolor_pixels(rgba.tobytes(), mask.convert("RGBA").tobytes(), colors, palette)
    return PILImage.frombytes("RGBA", rgba.size, data)


@lru_cache(maxsize=1)
def _source_poses() -> tuple[tuple[Image.Image, Image.Image], ...]:
    """4 cặp (sprite, mask) gốc."""
    from PIL import Image as PILImage

    pairs = []
    for n in range(len(POSE_INDEX)):
        with PILImage.open(resource_path("mascot_assets", f"pose_{n}.png")) as img, \
                PILImage.open(resource_path("mascot_assets", f"mask_{n}.png")) as msk:
            pairs.append((img.convert("RGBA"), msk.convert("RGBA")))
    return tuple(pairs)


@lru_cache(maxsize=4)
def recolored_poses(colors: tuple[str, ...]) -> tuple[Image.Image, ...]:
    """4 tư thế đã tô theo ``colors`` (cache theo bộ màu: tính một lần, hoạt ảnh chỉ dùng lại)."""
    palette = load_palette()
    return tuple(recolor_image(img, msk, colors, palette) for img, msk in _source_poses())


def supported() -> bool:
    """Máy này hiện được nhân vật không (Windows + Pillow có ImageTk)."""
    if sys.platform != "win32":
        return False
    try:
        from PIL import ImageTk  # noqa: F401
    except Exception:  # noqa: BLE001 - thiếu Pillow hoặc thiếu phần Tk của Pillow
        return False
    return True


# ---------------------------------------------------------------- state machine
@dataclass(frozen=True)
class Frame:
    """Một khung hình: tư thế, vị trí tâm (điểm ảnh màn hình), độ lệch và biến dạng."""

    pose: int
    x: float
    dx: float = 0.0          # rung ngang
    dy: float = 0.0          # âm = nhảy lên, dương = lún xuống dưới mép taskbar
    flip: bool = False
    sx: float = 1.0
    sy: float = 1.0
    rot: float = 0.0         # radian


@dataclass
class MascotBrain:
    """Hành vi của nhân vật, tách khỏi giao diện.

    Rảnh: ngủ (thở nhẹ), thỉnh thoảng chạy qua lại dọc taskbar rồi ngủ tiếp. Có cảnh báo: giật mình
    ``ALERT_SECONDS`` giây rồi giơ tay "Khoan đã!" đến khi màn hình cảnh báo đóng.
    """

    left: float
    right: float
    unit: float = 1.0                        # tỉ lệ so với bản thiết kế (khoảng cách/tốc độ nhân với hệ số này)
    reduced_motion: bool = False
    rng: random.Random = field(default_factory=random.Random)
    nap_range: tuple[float, float] = (15.0, 15.0)
    speed: float = 300.0                     # điểm ảnh/giây theo kích thước bản thiết kế (nhân ``unit``)
    state: State = field(default="sleep", init=False)
    t: float = field(default=0.0, init=False)
    x: float = field(default=0.0, init=False)
    direction: int = field(default=-1, init=False)
    warning: bool = field(default=False, init=False)
    pinned: bool = field(default=False, init=False)
    patrol: bool = field(default=False, init=False)      # đang tuần tra: chạy hết mép, quay đầu, cứ 3 giây lại nghỉ một nhịp
    _until: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.x = self.left + (self.right - self.left) * 0.85
        self._go("sleep")

    def set_pinned(self, pinned: bool) -> None:
        """Cố định tại chỗ (không chạy nữa); đang chạy thì dừng lại ngủ. Cảnh báo link vẫn làm nó giật mình/giơ tay."""
        self.pinned = pinned
        if pinned:
            self.patrol = False
            if self.state == "run":
                self._go("sleep")

    def drag_to(self, x: float) -> None:
        """Người dùng kéo nhân vật tới ``x`` (kẹp trong vùng chạy)."""
        self.x = _clamp(x, self.left, self.right)

    def set_bounds(self, left: float, right: float) -> None:
        """Đổi vùng chạy (đổi độ phân giải, dời taskbar)."""
        self.left, self.right = left, max(left, right)
        self.x = _clamp(self.x, self.left, self.right)

    def _go(self, state: State) -> None:
        self.state = state
        self.t = 0.0
        if state == "sleep":
            self._until = REST_SECONDS if self.patrol else self.rng.uniform(*self.nap_range)
        elif state == "run":
            if not self.patrol:                  # bắt đầu tuần tra: hướng về mép xa hơn cho có đường chạy dài
                self.patrol = True
                self.direction = -1 if self.x - self.left > self.right - self.x else 1
            self._until = RUN_SECONDS
        elif state == "alert":
            self._until = ALERT_SECONDS

    # ---- sự kiện ----
    def warning_opened(self) -> None:
        """Màn hình cảnh báo vừa mở: giật mình ngay (kể cả đang chạy hay đang giơ tay)."""
        self.warning = True
        self.patrol = False
        self._go("alert")

    def warning_closed(self) -> None:
        """Màn hình cảnh báo đã đóng: về trạng thái rảnh (cú giật mình đang dở thì cho diễn nốt)."""
        self.warning = False
        if self.state == "stop":
            self._go("sleep")

    # ---- thời gian ----
    def tick(self, dt: float) -> None:
        """Tiến ``dt`` giây."""
        dt = max(0.0, min(dt, 0.25))
        self.t += dt
        if self.state == "alert":
            if self.t >= self._until:
                self._go("stop" if self.warning else "sleep")
        elif self.state == "sleep":
            if (not self.reduced_motion and not self.pinned and self.t >= self._until
                    and self.right > self.left):
                self._go("run")
        elif self.state == "run":
            self.x += self.direction * self.speed * self.unit * dt
            if self.x <= self.left:              # chạm điểm cuối: quay đầu chạy tiếp
                self.x, self.direction = self.left, 1
            elif self.x >= self.right:
                self.x, self.direction = self.right, -1
            if self.t >= self._until:            # chạy đủ nhịp thì nghỉ một lát rồi chạy tiếp
                self._go("sleep")

    @property
    def animating(self) -> bool:
        """Đang có chuyển động nhanh (cần khung hình dày); ngủ thì vẽ thưa để đỡ CPU."""
        return self.state != "sleep" and not (self.state == "stop" and self.t > 0.4)

    def frame(self) -> Frame:
        """Khung hình hiện tại (số liệu theo bản thiết kế, nhân ``unit``)."""
        m = 0.0 if self.reduced_motion else 1.0
        t, u = self.t, self.unit
        pose = POSE_INDEX[self.state]
        if self.state == "sleep":
            breath = math.sin(t * 2.2) * m
            return Frame(pose, self.x, sx=1 - 0.008 * breath, sy=1 + 0.016 * breath)
        if self.state == "alert":
            dx = math.sin(t * 70) * 2 * u * m if t < 0.2 else 0.0
            dy, sx, sy = 0.0, 1.0, 1.0
            if t < 0.55:
                dy = -math.sin(t / 0.55 * math.pi) * 28 * u * m
            elif t < 0.72:
                sx, sy = 1 + 0.06 * m, 1 - 0.07 * m
            return Frame(pose, self.x, dx=dx, dy=dy, sx=sx, sy=sy)
        flip = self.direction > 0
        if self.state == "run":
            phase = t * 13
            rot = math.sin(phase) * 0.045 * m * (-1 if flip else 1)
            return Frame(pose, self.x, dy=-abs(math.sin(phase)) * 7 * u * m, flip=flip, rot=rot)
        scale = 1.0
        if m:
            scale = 0.88 + t / 0.14 * 0.17 if t < 0.14 else (1.05 - (t - 0.14) / 0.16 * 0.05 if t < 0.3 else 1.0)
        rise = (16 + (1 - t / 0.28) * 70) if (m and t < 0.28) else 16
        return Frame(pose, self.x, dy=rise * u, flip=flip, sx=scale, sy=scale)


# ---------------------------------------------------------------- cửa sổ Tk (Windows)
_KEY: Final[str] = "#ff00fe"                  # màu trong suốt (-transparentcolor): không có trong sprite
_KEY_RGB: Final[tuple[int, int, int]] = (255, 0, 254)
_BASE_SCALE: Final[float] = 0.15              # 488 px gốc → ~73 px ở 100% scale
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


def _work_area() -> tuple[int, int, int, int]:
    """Vùng làm việc (trừ taskbar) của màn hình chính, điểm ảnh vật lý (agent đã bật DPI awareness)."""
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    user32 = ctypes.windll.user32
    if not user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):   # SPI_GETWORKAREA
        raise OSError("SPI_GETWORKAREA thất bại")
    left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
    # Chạy hết chiều ngang màn hình (vùng làm việc có thể hẹp hơn nếu có thanh công cụ tùy biến chiếm hai bên) và
    # đứng trên mép trên của thanh taskbar gốc của Windows (Shell_TrayWnd) khi nó nằm ở đáy màn hình.
    screen_w, screen_h = int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    left, right = 0, max(right, screen_w)
    tray = user32.FindWindowW("Shell_TrayWnd", None)
    tray_rect = wintypes.RECT()
    if tray and user32.IsWindowVisible(tray) and user32.GetWindowRect(tray, ctypes.byref(tray_rect)):
        if tray_rect.top > screen_h // 2 and tray_rect.right - tray_rect.left > screen_w // 2:
            bottom = tray_rect.top
    return left, top, right, bottom


def _dpi_scale() -> float:
    try:
        import ctypes

        return max(1.0, int(ctypes.windll.user32.GetDpiForSystem()) / 96)
    except (AttributeError, OSError):
        return 1.0


def _animations_enabled() -> bool:
    """Windows "Hiệu ứng hoạt ảnh" (SPI_GETCLIENTAREAANIMATION); tắt = giảm chuyển động."""
    try:
        import ctypes
        from ctypes import wintypes

        value = wintypes.BOOL(True)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0):
            return bool(value.value)
    except (AttributeError, OSError):
        pass
    return True


def _make_tool_window(hwnd: int) -> None:
    """WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE: không có nút trên taskbar, không cướp focus."""
    import ctypes

    user32 = ctypes.windll.user32
    get = user32.GetWindowLongPtrW
    put = user32.SetWindowLongPtrW
    get.restype = put.restype = ctypes.c_ssize_t
    get.argtypes = (ctypes.c_void_p, ctypes.c_int)
    put.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t)
    style = get(hwnd, -20)                                                # GWL_EXSTYLE
    style = (style | 0x00000080 | 0x08000000) & ~0x00040000               # TOOLWINDOW | NOACTIVATE, bỏ APPWINDOW
    put(hwnd, -20, style)
    user32.SetWindowPos.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_uint)
    user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0020)  # TOPMOST, giữ chỗ


def _foreground() -> int:
    import ctypes

    return int(ctypes.windll.user32.GetForegroundWindow() or 0)


def _restore_foreground(hwnd: int) -> None:
    if hwnd:
        import ctypes

        ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(hwnd))


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

    @staticmethod
    def _config_stamp() -> tuple[int, int] | None:
        try:
            info = os.stat(data_dir() / "config.json")
        except OSError:
            return None
        return info.st_mtime_ns, info.st_size

    def _poll(self) -> None:
        """Theo dõi cấu hình mỗi ``_POLL_MS`` (dự phòng cho tín hiệu ``config_changed``)."""
        self._apply_config(force=self._stamp is None)
        if self._enabled and self._window is not None:
            self._place_bounds()                      # đổi độ phân giải / dời taskbar
        if not self._broken:
            self._root.after(_POLL_MS, lambda: self._safe(self._poll))

    def _apply_config(self, force: bool = False) -> None:
        stamp = self._config_stamp()
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
        if cfg["mascot_enabled"] and not self._enabled:
            self._show()
        elif not cfg["mascot_enabled"] and self._enabled:
            self._hide()
        self._sync_pin()

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
                poses = tuple(img for img, _ in _source_poses())
            self._incoming = (colors, poses)

        threading.Thread(target=work, name="chotto-mascot-paint", daemon=True).start()

    def _show(self) -> None:
        if not supported():
            _LOG.info("Nhân vật taskbar không khả dụng trên máy này (cần Windows + Pillow), bỏ qua")
            self._broken = True
            return
        self._enabled = True
        previous = _foreground()                      # lấy TRƯỚC khi dựng cửa sổ (dựng xong có thể đã thành foreground)
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
                self._canvas.create_text(width / 2, 9, text="\u25c0  \u25b6", fill="#d4a24a", font=("Segoe UI", 9, "bold"), tags="hint")
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
        from .service.app import save_settings

        try:
            save_settings({"mascot_pos": round(self._pos, 4)})
        except OSError:
            _LOG.exception("Không lưu được vị trí nhân vật")
        self._stamp = self._config_stamp()

    def _give_back_focus(self, previous: int) -> None:
        if previous and previous != self._hwnd and _foreground() == self._hwnd:
            _restore_foreground(previous)

    def _hide(self) -> None:
        self._enabled = False
        if self._window is not None:
            self._window.withdraw()
        _LOG.info("Ẩn nhân vật taskbar")

    def _build(self) -> None:
        import tkinter as tk

        dpi = _dpi_scale()
        self._scale = _BASE_SCALE * dpi
        self._unit = self._scale / _DESIGN_SCALE
        width = int(259 * self._scale * 1.12 + 60 * self._unit)
        height = int(488 * self._scale * 1.03 + 30 * self._unit + 4)
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
        hwnd = int(window.winfo_id())
        import ctypes

        self._hwnd = int(ctypes.windll.user32.GetParent(hwnd) or hwnd)
        _make_tool_window(self._hwnd)
        self._window, self._canvas = window, canvas
        self._size = (width, height)
        self._brain = MascotBrain(0, 1, unit=self._unit, reduced_motion=not _animations_enabled())

    def _place_bounds(self) -> None:
        self._area = _work_area()
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
        from .service.app import save_settings

        self._hide()
        try:
            save_settings({"mascot_enabled": False})
        except OSError:
            _LOG.exception("Không lưu được cấu hình khi ẩn nhân vật")
        self._stamp = self._config_stamp()

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
        w = max(1, round(src.width * self._scale * key[2] / 100))
        h = max(1, round(src.height * self._scale * key[3] / 100))
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
