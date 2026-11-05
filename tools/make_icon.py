"""Tạo mọi biểu tượng của CHOTTO từ một ảnh gốc duy nhất: ``assets/anime.png``.

Ảnh gốc là sticker nền trắng. Công cụ tách nền (loang từ mép ảnh qua vùng gần trắng, dừng ở đường viền xám của sticker),
cắt vuông rồi sinh:

- ``packaging/chotto.ico``      biểu tượng Windows (exe, bộ cài, shortcut Desktop)
- ``packaging/chotto.icns``     biểu tượng macOS (py2app)
- ``chotto/web/icon.png``       logo trong giao diện HTML của bản Desktop (và icon cửa sổ)
- ``extension/icons/icon*.png`` biểu tượng tiện ích trình duyệt (16/32/48/128)
- ``extension/src/ui/icon.png`` logo trong trang cài đặt / cảnh báo của tiện ích
- ``extension/src/ui/icon-data.js`` cùng logo dạng data URI cho hộp thoại trên trang Zalo (không lộ URL tài nguyên)

Cần Pillow (chỉ khi chạy công cụ này, không cần khi chạy CHOTTO): pip install pillow
Dùng: python tools/make_icon.py
"""
from __future__ import annotations

import base64
import io
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "anime.png"
BG_MIN = 244          # kênh nhỏ nhất của điểm ảnh >= ngưỡng này (và nối với mép ảnh) thì là nền
WORK = 1024           # xử lý ở kích thước này cho nhanh


def cutout(path: Path) -> Image.Image:
    """Tách nền sticker, cắt sát nhân vật và đệm thành ảnh vuông trong suốt."""
    img = Image.open(path).convert("RGB").resize((WORK, WORK), Image.Resampling.LANCZOS)
    px = img.load()
    assert px is not None
    seen = bytearray(WORK * WORK)
    queue: deque[tuple[int, int]] = deque()
    for i in range(WORK):
        queue.extend([(i, 0), (i, WORK - 1), (0, i), (WORK - 1, i)])
    while queue:
        x, y = queue.popleft()
        if not (0 <= x < WORK and 0 <= y < WORK) or seen[y * WORK + x]:
            continue
        if min(px[x, y]) < BG_MIN:
            continue
        seen[y * WORK + x] = 1
        queue.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])
    mask = Image.frombytes("L", (WORK, WORK), bytes(0 if v else 255 for v in seen))
    mask = mask.filter(ImageFilter.GaussianBlur(1.2))             # viền mịn, không răng cưa
    out = img.convert("RGBA")
    out.putalpha(mask)
    box = out.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    assert box is not None, "Không tách được nhân vật khỏi nền"
    out = out.crop(box)
    side = max(out.size)
    pad = round(side * 0.04)
    square = Image.new("RGBA", (side + 2 * pad, side + 2 * pad), (0, 0, 0, 0))
    square.paste(out, ((square.width - out.width) // 2, (square.height - out.height) // 2))
    return square


def sized(img: Image.Image, size: int) -> Image.Image:
    """Thu nhỏ về ``size`` x ``size`` bằng LANCZOS."""
    return img.resize((size, size), Image.Resampling.LANCZOS)


def png_bytes(img: Image.Image) -> bytes:
    """Mã hóa ảnh thành PNG."""
    buffer = io.BytesIO()
    img.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def main() -> None:
    """Sinh mọi biểu tượng từ ``assets/anime.png``."""
    base = cutout(SOURCE)
    big = sized(base, 1024)
    targets: list[Path] = []

    ico = ROOT / "packaging" / "chotto.ico"
    big.save(ico, format="ICO", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    targets.append(ico)

    icns = ROOT / "packaging" / "chotto.icns"
    big.save(icns, format="ICNS")
    targets.append(icns)

    web = ROOT / "chotto" / "web" / "icon.png"
    web.write_bytes(png_bytes(sized(base, 256)))
    targets.append(web)

    for size in (16, 32, 48, 128):
        path = ROOT / "extension" / "icons" / f"icon{size}.png"
        path.write_bytes(png_bytes(sized(base, size)))
        targets.append(path)

    page = ROOT / "extension" / "src" / "ui" / "icon.png"
    page.write_bytes(png_bytes(sized(base, 128)))
    targets.append(page)

    data = base64.b64encode(png_bytes(sized(base, 96))).decode("ascii")
    js = ROOT / "extension" / "src" / "ui" / "icon-data.js"
    js.write_text(
        "// Sinh bởi tools/make_icon.py, đừng sửa tay. Logo dạng data URI để hộp thoại trên trang Zalo\n"
        "// không phải tải tài nguyên của tiện ích (tránh để lộ URL của tiện ích cho trang).\n"
        f'globalThis.CHOTTO_ICON = "data:image/png;base64,{data}";\n',
        encoding="utf-8", newline="\n")
    targets.append(js)

    for path in targets:
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size} byte")


if __name__ == "__main__":
    main()
