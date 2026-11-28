"""Tạo mọi biểu tượng của CHOTTO từ logo chính: ``assets/logo.png``.

Logo được vẽ cho nền trắng (nét mực đen chìm trên nền tối, mảng trắng bán trong suốt), nên được ép lên nền trắng rồi
đặt vào ô bo góc. Công cụ sinh:

- ``platforms/PC/windows/chotto.ico``      biểu tượng Windows (exe, bộ cài, shortcut Desktop)
- ``platforms/PC/macos/chotto.icns``     biểu tượng macOS (py2app, chừa lề theo lưới biểu tượng của Apple)
- ``chotto/web/icon.png``       logo trong giao diện HTML của bản Desktop
- ``platforms/extension/icons/icon*.png`` biểu tượng tiện ích trình duyệt (16/32/48/128)
- ``platforms/extension/src/ui/icon.png`` logo trong trang cài đặt / cảnh báo của tiện ích
- ``platforms/extension/src/ui/icon-data.js`` cùng logo dạng data URI cho hộp thoại trên trang Zalo (không lộ URL tài nguyên)
- ``icon.png``, ``favicon.png``  logo và biểu tượng thẻ của trang web
- ``platforms/android/app/src/main/res/mipmap-*`` biểu tượng ứng dụng Android

Cần Pillow (chỉ khi chạy công cụ này, không cần khi chạy CHOTTO): pip install pillow
Dùng: python tools/make_icon.py
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "logo.png"
INK_MAX = 232         # kênh nhỏ nhất dưới ngưỡng này (sau khi ép lên nền trắng) thì là nét vẽ, dùng để cắt sát logo
WHITE = (255, 255, 255, 255)
SS = 4                # vẽ mặt nạ bo góc ở gấp 4 cho viền mịn


def load_logo(path: Path) -> Image.Image:
    """Ép logo lên nền trắng và cắt sát phần có nét vẽ."""
    src = Image.open(path).convert("RGBA")
    flat = Image.new("RGBA", src.size, WHITE)
    flat.alpha_composite(src)
    r, g, b = flat.convert("RGB").split()
    darkest = ImageChops.darker(ImageChops.darker(r, g), b)
    box = darkest.point([255 if v < INK_MAX else 0 for v in range(256)]).getbbox()
    assert box is not None, "Logo trống"
    return flat.crop(box)


def placed(logo: Image.Image, size: int, fill: float) -> Image.Image:
    """Ảnh vuông trong suốt ``size`` x ``size``, logo ở giữa, cạnh dài bằng ``fill`` x ``size``."""
    scale = size * fill / max(logo.size)
    small = logo.resize((round(logo.width * scale), round(logo.height * scale)), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(small, ((size - small.width) // 2, (size - small.height) // 2))
    return out


def tile(logo: Image.Image, size: int = 1024, margin: float = 0.0, radius: float = 0.22,
         fill: float = 0.92) -> Image.Image:
    """Ô trắng bo góc chứa logo. ``margin``: lề trong suốt mỗi bên; ``radius``: bo góc so với cạnh ô (0.5 = tròn)."""
    inner = size - 2 * round(size * margin)
    mask = Image.new("L", (inner * SS, inner * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, inner * SS - 1, inner * SS - 1), radius=inner * SS * radius, fill=255)
    card = Image.new("RGBA", (inner, inner), WHITE)
    card.alpha_composite(placed(logo, inner, fill))
    card.putalpha(mask.resize((inner, inner), Image.Resampling.LANCZOS))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(card, ((size - inner) // 2, (size - inner) // 2))
    return out


def sized(img: Image.Image, size: int) -> Image.Image:
    """Thu nhỏ về ``size`` x ``size`` bằng LANCZOS."""
    return img.resize((size, size), Image.Resampling.LANCZOS)


def png_bytes(img: Image.Image) -> bytes:
    """Mã hóa ảnh thành PNG."""
    buffer = io.BytesIO()
    img.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def main() -> None:
    """Sinh mọi biểu tượng từ ``assets/logo.png``."""
    logo = load_logo(SOURCE)
    base = big = tile(logo)
    targets: list[Path] = []

    ico = ROOT / "platforms" / "PC" / "windows" / "chotto.ico"
    big.save(ico, format="ICO", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    targets.append(ico)

    icns = ROOT / "platforms" / "PC" / "macos" / "chotto.icns"
    tile(logo, margin=0.1).save(icns, format="ICNS")
    targets.append(icns)

    web = ROOT / "chotto" / "web" / "icon.png"
    web.write_bytes(png_bytes(sized(base, 256)))
    targets.append(web)

    for size in (16, 32, 48, 128):
        path = ROOT / "platforms" / "extension" / "icons" / f"icon{size}.png"
        path.write_bytes(png_bytes(sized(base, size)))
        targets.append(path)

    page = ROOT / "platforms" / "extension" / "src" / "ui" / "icon.png"
    page.write_bytes(png_bytes(sized(base, 128)))
    targets.append(page)

    data = base64.b64encode(png_bytes(sized(base, 96))).decode("ascii")
    js = ROOT / "platforms" / "extension" / "src" / "ui" / "icon-data.js"
    js.write_text(
        "// Sinh bởi tools/make_icon.py, đừng sửa tay. Logo dạng data URI để hộp thoại trên trang Zalo\n"
        "// không phải tải tài nguyên của tiện ích (tránh để lộ URL của tiện ích cho trang).\n"
        f'globalThis.CHOTTO_ICON = "data:image/png;base64,{data}";\n',
        encoding="utf-8", newline="\n")
    targets.append(js)

    for name, size in (("icon.png", 256), ("favicon.png", 48)):
        path = ROOT / name
        path.write_bytes(png_bytes(sized(base, size)))
        targets.append(path)

    res = ROOT / "platforms" / "android" / "app" / "src" / "main" / "res"
    legacy = tile(logo, margin=0.04)
    rounded = tile(logo, margin=0.04, radius=0.5, fill=0.88)
    foreground = placed(logo, 1024, 0.62)      # lớp trước của adaptive icon: logo nằm trong vùng an toàn 66/108
    for density, factor in (("mdpi", 1.0), ("hdpi", 1.5), ("xhdpi", 2.0), ("xxhdpi", 3.0), ("xxxhdpi", 4.0)):
        for name, image, dp in (("ic_launcher", legacy, 48), ("ic_launcher_round", rounded, 48),
                                ("ic_launcher_foreground", foreground, 108)):
            path = res / f"mipmap-{density}" / f"{name}.png"
            path.write_bytes(png_bytes(sized(image, round(dp * factor))))
            targets.append(path)

    for path in targets:
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size} byte")


if __name__ == "__main__":
    main()
