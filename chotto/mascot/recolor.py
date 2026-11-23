"""Tô màu nhân vật: thuật toán tô màu liên tục chép từ ``design/chotto_mascot_customizer.html`` (Pillow, có cache).

Bản JavaScript để xem trước trong cửa sổ ứng dụng là ``chotto/web/mascot.js``: hai bản phải cho ra đúng từng điểm
ảnh như nhau (có test so bằng Node).
"""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Final

from ..config import MASCOT_DEFAULT_COLORS, resource_path
from ..util import clamp as _clamp

if TYPE_CHECKING:
    from PIL import Image

__all__ = [
    "GROUPS",
    "Palette",
    "load_palette",
    "normalize_colors",
    "recolor_image",
    "recolor_pixels",
    "recolored_poses",
    "source_poses",
]

GROUPS: Final[int] = 6                     # Tóc, Mắt, Da, Áo choàng, Váy, Giày/phụ kiện
POSES: Final[int] = 4                      # sleep, alert, run, stop
_HEX: Final[re.Pattern[str]] = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class Palette:
    """Tham số tô màu (``chotto/mascot/assets/palette.json``, trích từ bản thiết kế)."""

    default: tuple[str, ...]
    pivot: tuple[float, ...]                                     # độ sáng "giữa" của từng nhóm trong ảnh gốc
    params: tuple[tuple[float, float, float, float], ...]        # (ngưỡng viền thấp, cao, gamma tối, mức nâng sáng)
    swatches: tuple[tuple[str, ...], ...]


@lru_cache(maxsize=1)
def load_palette() -> Palette:
    """Đọc bảng tham số đóng gói kèm."""
    raw = json.loads(resource_path("mascot", "assets", "palette.json").read_text("utf-8"))
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
def source_poses() -> tuple[tuple[Image.Image, Image.Image], ...]:
    """4 cặp (sprite, mask) gốc."""
    from PIL import Image as PILImage

    pairs = []
    for n in range(POSES):
        with PILImage.open(resource_path("mascot", "assets", f"pose_{n}.png")) as img, \
                PILImage.open(resource_path("mascot", "assets", f"mask_{n}.png")) as msk:
            pairs.append((img.convert("RGBA"), msk.convert("RGBA")))
    return tuple(pairs)


@lru_cache(maxsize=4)
def recolored_poses(colors: tuple[str, ...]) -> tuple[Image.Image, ...]:
    """4 tư thế đã tô theo ``colors`` (cache theo bộ màu: tính một lần, hoạt ảnh chỉ dùng lại)."""
    palette = load_palette()
    return tuple(recolor_image(img, msk, colors, palette) for img, msk in source_poses())
