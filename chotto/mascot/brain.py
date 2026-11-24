"""Hành vi của nhân vật (state machine thuần ``sleep`` / ``alert`` / ``run`` / ``stop``), không đụng tới giao diện."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Final, Literal

from ..util import clamp as _clamp

__all__ = ["ALERT_SECONDS", "POSE_INDEX", "REST_SECONDS", "RUN_SECONDS", "WARNING_LEVELS", "Frame", "MascotBrain"]

State = Literal["sleep", "alert", "run", "stop"]
POSE_INDEX: Final[dict[str, int]] = {"sleep": 0, "alert": 1, "run": 2, "stop": 3}
ALERT_SECONDS: Final[float] = 0.8
RUN_SECONDS: Final[float] = 3.0       # mỗi nhịp chạy
REST_SECONDS: Final[float] = 3.0      # nghỉ (ngủ) giữa hai nhịp chạy
WARNING_LEVELS: Final[frozenset[str]] = frozenset({"WARN", "HIGH", "BLOCKED"})


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
    attending: bool = field(default=False, init=False)   # đang chat với người dùng: giơ tay đứng yên như khi có cảnh báo
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

    def attend(self, on: bool) -> None:
        """Bắt đầu/kết thúc chat: giật mình rồi giơ tay đứng yên; kết thúc thì về rảnh (đang có cảnh báo thì giữ nguyên)."""
        self.attending = on
        if on:
            self.patrol = False
            self._go("alert")
        elif self.state == "stop" and not self.warning:
            self._go("sleep")

    def warning_closed(self) -> None:
        """Màn hình cảnh báo đã đóng: về trạng thái rảnh (cú giật mình đang dở thì cho diễn nốt)."""
        self.warning = False
        if self.state == "stop" and not self.attending:
            self._go("sleep")

    # ---- thời gian ----
    def tick(self, dt: float) -> None:
        """Tiến ``dt`` giây."""
        dt = max(0.0, min(dt, 0.25))
        self.t += dt
        if self.state == "alert":
            if self.t >= self._until:
                self._go("stop" if self.warning or self.attending else "sleep")
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
        """Đang có chuyển động nhanh (cần khung hình dày). Ngủ có nhịp thở riêng (``TaskbarMascot`` tự lo);
        "Khoan đã!" lắc nhẹ mãi như trên web, trừ khi người dùng tắt hiệu ứng (khi đó đứng yên sau cú nảy)."""
        return self.state != "sleep" and not (self.state == "stop" and self.t > 0.4 and self.reduced_motion)

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
        wave = math.radians(1.6) * (1 - math.cos((t - 0.55) / 1.3 * math.tau)) / 2 if (m and t > 0.55) else 0.0   # tay lắc nhẹ như ma-wave trên web
        return Frame(pose, self.x, dy=rise * u, flip=flip, sx=scale, sy=scale, rot=wave)
