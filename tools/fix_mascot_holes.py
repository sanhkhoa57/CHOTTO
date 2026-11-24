"""Vá các lỗ trong suốt li ti NẰM GIỮA ảnh nhân vật (chotto/mascot/assets/pose_*.png).

    python tools/fix_mascot_holes.py

Ảnh gốc có vài điểm ảnh alpha = 0 lọt giữa mặt/tóc (sót lại khi tách nền). Viền tối vẽ quanh nhân vật lấp vào đó nên thành
"hai chấm đen" trên mặt. Công cụ tìm các vùng trong suốt KHÔNG nối ra ngoài và rộng tối đa MAX_AREA điểm ảnh rồi tô bằng màu
trung bình của các điểm ảnh đặc xung quanh. Chạy lại nhiều lần vẫn an toàn (không còn lỗ thì không làm gì). Nếu chạy lại
``tools/extract_mascot.py`` thì phải chạy tool này sau đó. Mask không đổi (lỗ vốn không thuộc nhóm màu nào).
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "chotto" / "mascot" / "assets"
MAX_AREA = 12                      # lỗ lớn hơn vậy là khe hở thật của hình (giữa tay và thân...), giữ nguyên
SOLID = 128                        # alpha tối thiểu coi là điểm ảnh đặc


def holes(image: Image.Image) -> list[list[tuple[int, int]]]:
    """Các vùng trong suốt kín (không chạm mép và không nối ra nền) có diện tích <= ``MAX_AREA``."""
    w, h = image.size
    alpha = image.getchannel("A").load()
    seen = [[False] * w for _ in range(h)]
    found: list[list[tuple[int, int]]] = []
    for sy in range(h):
        for sx in range(w):
            if seen[sy][sx] or alpha[sx, sy] >= SOLID:
                continue
            region: list[tuple[int, int]] = []
            queue = deque([(sx, sy)])
            seen[sy][sx] = True
            touches_edge = False
            while queue:
                x, y = queue.popleft()
                region.append((x, y))
                if x in (0, w - 1) or y in (0, h - 1):
                    touches_edge = True
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and alpha[nx, ny] < SOLID:
                        seen[ny][nx] = True
                        queue.append((nx, ny))
            if not touches_edge and len(region) <= MAX_AREA:
                found.append(region)
    return found


def fix(image: Image.Image) -> int:
    """Tô các lỗ kín trong ``image`` (RGBA, sửa tại chỗ); trả về số điểm ảnh đã vá."""
    pixels = image.load()
    patched = 0
    for region in holes(image):
        members = set(region)
        ring = 1
        while True:
            samples = [
                pixels[nx, ny]
                for x, y in region
                for nx in range(x - ring, x + ring + 1)
                for ny in range(y - ring, y + ring + 1)
                if (nx, ny) not in members and 0 <= nx < image.width and 0 <= ny < image.height and pixels[nx, ny][3] >= 250
            ]
            if samples or ring > 6:
                break
            ring += 1
        if not samples:
            continue
        colour = tuple(round(sum(p[i] for p in samples) / len(samples)) for i in range(3))
        for x, y in region:
            pixels[x, y] = (*colour, 255)
            patched += 1
    return patched


def main() -> None:
    for path in sorted(ASSETS.glob("pose_*.png")):
        image = Image.open(path).convert("RGBA")
        patched = fix(image)
        if patched:
            image.save(path, optimize=True)
        print(f"{path.relative_to(ROOT)}: vá {patched} điểm ảnh")


if __name__ == "__main__":
    main()
