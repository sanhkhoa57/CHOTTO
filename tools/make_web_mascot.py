"""Dựng ảnh mascot CÓ VIỀN cho trang giới thiệu (index.html), giống hệt viền của nhân vật trên taskbar.

    python tools/make_web_mascot.py

Ghi ``chotto/mascot/assets/web/pose_{0..3}.png`` từ sprite gốc (màu mặc định) bằng đúng ``taskbar.outline_sprite`` +
``taskbar.body_seed`` (chỉ viền phần thân, hiệu ứng zZ / dấu ! / vệt bụi không bị viền). Độ dày viền tính theo cỡ ảnh hiện trên
trang để ra khoảng ``TARGET_PX`` điểm ảnh CSS như trên taskbar. Sửa viền trong ``chotto/mascot/taskbar.py`` thì chạy lại tool này.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from chotto.config import MASCOT_DEFAULT_COLORS  # noqa: E402
from chotto.mascot.recolor import recolored_poses  # noqa: E402
from chotto.mascot.taskbar import _OUTLINE_PX, body_seed, outline_sprite  # noqa: E402

TARGET_PX = _OUTLINE_PX                                 # độ dày viền nhìn thấy trên trang (điểm ảnh CSS), như taskbar ở 100%
DISPLAY_H = {0: 200, 1: 200, 2: 190, 3: 172}            # chiều cao CSS của từng tư thế ở khung "mascot" trong index.html (.ma-img)
TARGET_SCALE = 3.0                                      # ảnh dựng cao gấp ngần này lần chiều cao CSS (đủ cho màn hình 2-3x)
OUT = ROOT / "chotto" / "mascot" / "assets" / "web"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for pose, source in enumerate(recolored_poses(tuple(MASCOT_DEFAULT_COLORS))):
        # Ảnh gốc nhỏ (tư thế "Khoan đã" chỉ ~1,5 lần chỗ hiện) nên trên màn hình DPI cao bị trình duyệt phóng ra, nhòe răng cưa.
        # Phóng lên TARGET_SCALE lần chiều cao hiện (LANCZOS, alpha nhân trước) rồi mới viền: trình duyệt chỉ còn thu nhỏ, cạnh mịn.
        factor = max(1.0, TARGET_SCALE * DISPLAY_H[pose] / source.height)
        size = (round(source.width * factor), round(source.height * factor))
        image = source.resize(size, Image.Resampling.LANCZOS) if factor > 1.0 else source
        width_px = TARGET_PX * image.height / DISPLAY_H[pose]     # ảnh to hơn chỗ hiện: viền phải dày tương ứng
        framed, pad = outline_sprite(image, width_px, body_seed(pose, image.size))
        path = OUT / f"pose_{pose}.png"
        framed.save(path, optimize=True)
        print(f"{path.relative_to(ROOT)}  {framed.width}x{framed.height}  viền {width_px:.1f}px  lề {pad}px")


if __name__ == "__main__":
    main()
