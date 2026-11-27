"""Dựng dải núi lặp liền mạch cho community/index.html từ tranh miệng núi lửa (cần Pillow).

Lấy phần giữa tranh (hai vách sát mép quá cao, không nối được). Trên đá, đường nối
đi theo nơi hai bên giống nhau nhất nên không chồng bóng; trên trời thì hòa dần.
Chạy lại khi đổi tranh: python community/tools/make_community_panorama.py
"""

from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / "assets"
CROP = (0.14, 0.86)
OVERLAP = 170
CLOUD_ROWS = 360  # trên hàng này chỉ có trời, mây
FEATHER = 4


def seam(head: Image.Image, tail: Image.Image) -> list[int]:
    """Đường dọc ít lệch màu nhất (quy hoạch động), mỗi hàng một cột."""
    width, height = head.size
    a: Any = head.load()
    b: Any = tail.load()
    assert a is not None and b is not None
    total: list[float] = [0.0] * width
    back: list[list[int]] = []
    for y in range(height):
        row, came = [], []
        for x in range(width):
            near = range(max(0, x - 1), min(width, x + 2))
            best = min(near, key=total.__getitem__)
            diff = sum((p - q) ** 2 for p, q in zip(a[x, y], b[x, y]))
            edge = x < FEATHER or x >= width - FEATHER
            row.append(total[best] + diff + (1e9 if edge else 0))
            came.append(best)
        total = row
        back.append(came)
    x = min(range(width), key=total.__getitem__)
    path = [0] * height
    for y in range(height - 1, -1, -1):
        path[y] = x
        x = back[y][x]
    return path


def rock_mask(head: Image.Image, tail: Image.Image) -> Image.Image:
    """255 ở nơi một trong hai bên là đá (không xanh như trời), nới và làm mềm mép."""
    width, height = head.size
    a: Any = head.load()
    b: Any = tail.load()
    mask = Image.new("L", head.size)
    pixels = mask.load()
    assert a is not None and b is not None and pixels is not None
    for y in range(CLOUD_ROWS, height):
        for x in range(width):
            if any(p[2] - p[0] < 55 for p in (a[x, y], b[x, y])):
                pixels[x, y] = 255
    return mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(2))


def sky_cut(image: Image.Image) -> Image.Image:
    """Trời (xanh hoặc mây trắng) phía trên đỉnh núi thành trong suốt; trang tự vẽ trời.

    Mỗi cột quét từ trên xuống, dừng ở điểm đá đầu tiên (nét viền tối của đỉnh núi),
    nên mảng sáng trên đá bên dưới không bị khoét.
    """
    width, height = image.size
    px: Any = image.load()
    alpha = Image.new("L", image.size, 255)
    ap: Any = alpha.load()
    for x in range(width):
        for y in range(height):
            r, g, b = px[x, y]
            if not (b - r > 45 or min(r, g, b) > 185):
                break
            ap[x, y] = 0
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    out = image.convert("RGBA")
    out.putalpha(alpha)
    return out


def main() -> None:
    art = Image.open(ASSETS / "community-crater.webp").convert("RGB")
    w, h = art.size
    strip = art.crop((round(w * CROP[0]), 0, round(w * CROP[1]), h))
    period = strip.width - OVERLAP
    out = strip.crop((0, 0, period, h))
    head = strip.crop((0, 0, OVERLAP, h))
    tail = strip.crop((period, 0, strip.width, h))
    path = seam(head, tail)
    rocks: Any = rock_mask(head, tail).load()
    assert rocks is not None
    mask = Image.new("L", (OVERLAP, h))
    pixels = mask.load()
    assert pixels is not None
    for y in range(h):
        for x in range(OVERLAP):
            rock = rocks[x, y] / 255
            soft = x / (OVERLAP - 1)
            soft = soft * soft * (3 - 2 * soft)
            hard = min(1.0, max(0.0, (x - path[y] + FEATHER) / (2 * FEATHER)))
            # 255 = đầu dải, 0 = đuôi dải (nối tiếp cột cuối cùng bên trái).
            pixels[x, y] = round(255 * (soft + (hard - soft) * rock))
    out.paste(Image.composite(head, tail, mask), (0, 0))
    target = ASSETS / "community-panorama.webp"
    sky_cut(out).save(target, quality=90, method=6)
    print(target.name, out.size)


if __name__ == "__main__":
    main()
