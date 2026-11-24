"""Lời thoại và hỏi đáp của nhân vật taskbar (phần thuần, không đụng Tk; Pillow chỉ nạp khi vẽ).

- Lời thoại theo ngữ cảnh (0 token): chào, cảnh báo link, đóng cảnh báo, rảnh rỗi.
- Hỏi đáp: bộ lọc đầu vào + hạn mức theo ngày, rồi gọi ``/api/mascot-chat`` của trang chotto.id.vn. Khóa API chỉ nằm ở máy chủ,
  app không bao giờ giữ khóa. ``CHOTTO_MASCOT_API`` ghi đè địa chỉ (thử nội bộ: ``node tools/mascot_dev.js`` → ``http://127.0.0.1:5400/api/mascot-chat``).
- ``check_input`` PHẢI khớp bộ lọc trong ``index.html`` và ``api/mascot-chat.js``.
- ``render_bubble`` vẽ bong bóng kiểu truyện tranh (trắng, viền đen, bóng chấm bi) ra ảnh RGBA.
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import re
import urllib.request
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from ..config import data_dir

if TYPE_CHECKING:
    from PIL import Image

__all__ = ["DAILY_LIMIT", "LINES", "Kind", "ask", "check_input", "layout", "pick", "quota_left", "quota_use", "render_bubble"]

_LOG = logging.getLogger("chotto")

Kind = Literal["normal", "thought", "alert"]
DEFAULT_API: Final[str] = "https://chotto.id.vn/api/mascot-chat"
DAILY_LIMIT: Final[int] = 6
MIN_LEN: Final[int] = 4
MAX_LEN: Final[int] = 150

LINES: Final[dict[str, str | tuple[str, ...]]] = {
    "hello": "Chào đằng ấy! Tui là Chotto. Bấm đúp vào tui nếu muốn soi link lạ hay hỏi gì về app nha!",
    "warn": "KHOAN ĐÃ! Link này nhìn sai sai, đọc kỹ cảnh báo trước khi bấm nha!",
    "closed": "Ổn áp! Lần sau có link lạ cứ bấm đúp vào tui, tui soi giùm.",
    "idle": ("Đang soi code xem uy tín không đúng hông? Sạch 100%, không giấu malware đâu mà lo...",
             'Không biết hôm nay có ai suýt chuyển khoản nhầm cho "shipper" nữa không ta...'),
    "open": "Dán link nghi ngờ vào đây, tui soi cho!",
    "loading": "Đang soi...",
    "refuse": ("HỎI LẠC ĐỀ RỒI! Tui là vệ sĩ chống scam của Chotto, không phải trợ lý làm bài tập hay chém gió đâu nha!",
               "Khoan! Câu này không liên quan tới Chotto hay link lừa đảo. Dán thử một đường link nghi ngờ vào đây tui soi cho!",
               "Từ chối tiếp nhận! Tui chỉ rành bóc phốt link bẩn với giải đáp về app Chotto thôi."),
    "quota": "Nay tui tư vấn hết công suất rồi! Mai quay lại hỏi tiếp nha.",
    "fail": "Hôm nay tui soi nhiều link quá nên hơi lag não, lát nữa bạn hỏi lại nha!",
}


def pick(key: str) -> str:
    """Một câu của ``key`` (nếu là danh sách thì chọn ngẫu nhiên)."""
    value = LINES[key]
    return random.choice(value) if isinstance(value, tuple) else value


# ---- bộ lọc đầu vào (khớp index.html và api/mascot-chat.js) ----
_DOMAIN = re.compile(r"(https?://|www\.)\S+|[a-z0-9-]+\.(vn|com|top|xyz|net|org|info|click|site|online|tk|me|io|app)(?![a-z0-9])", re.I)
_KEYWORDS: Final[tuple[str, ...]] = (
    "chotto", "scam", "lừa đảo", "giả mạo", "phishing", "link", "url", "tên miền", "domain", "mã độc", "virus", "trojan", "hack",
    "mất nick", "chiếm quyền", "zalo", "messenger", "facebook", "telegram", "ngân hàng", "vietcombank", "mbbank", "techcombank",
    "momo", "shopee", "shipper", "sinh trắc", "cài đặt", "tải về", "download", "windows", "macos", "mac", "arm", "x86", "extension",
    "tiện ích", "trình duyệt", "miễn phí", "free", "nhẹ", "ram", "bảo mật", "an toàn", "chặn")
_BLACKLIST: Final[tuple[str, ...]] = ("viết code", "giải bài", "dịch sang", "tóm tắt", "viết văn", "làm thơ", "kể chuyện",
                                      "sql", "python", "javascript", "bài tập")


def _has_keyword(text: str, word: str) -> bool:
    if re.fullmatch(r"[a-z0-9 ]+", word):                         # từ ASCII ngắn phải khớp nguyên từ ("mac" không khớp "machine")
        return re.search(rf"(^|[^a-z0-9]){word}([^a-z0-9]|$)", text) is not None
    return word in text


def check_input(raw: str) -> bool:
    """Câu hỏi có đủ điều kiện gửi lên máy chủ không (độ dài, chủ đề link/Chotto, không xin việc ngoài lề)."""
    text = raw.strip()
    if not MIN_LEN <= len(text) <= MAX_LEN:
        return False
    low = text.lower()
    if any(b in low for b in _BLACKLIST):
        return False
    return _DOMAIN.search(text) is not None or any(_has_keyword(low, k) for k in _KEYWORDS)


# ---- hạn mức theo ngày (lưu trong thư mục dữ liệu, không phải cấu hình) ----
def _quota_path() -> Path:
    return data_dir() / "mascot_chat.json"


def _quota_used() -> int:
    try:
        data = json.loads(_quota_path().read_text("utf-8"))
        return int(data["n"]) if data.get("d") == date.today().isoformat() else 0
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def quota_left() -> int:
    """Số lượt hỏi còn lại hôm nay."""
    return max(0, DAILY_LIMIT - _quota_used())


def quota_use() -> None:
    """Ghi nhận một lượt hỏi (lỗi ghi đĩa chỉ ghi log)."""
    try:
        _quota_path().write_text(json.dumps({"d": date.today().isoformat(), "n": _quota_used() + 1}), "utf-8")
    except OSError:
        _LOG.warning("Không ghi được hạn mức hỏi đáp của nhân vật", exc_info=True)


def ask(message: str, timeout: float = 20.0) -> tuple[str, Kind]:
    """Hỏi máy chủ; mọi lỗi (mạng, quá hạn, trả lời lạ) đều trả câu chữa cháy, không ném lỗi."""
    url = os.environ.get("CHOTTO_MASCOT_API") or DEFAULT_API
    try:
        request = urllib.request.Request(url, data=json.dumps({"message": message}).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "User-Agent": "CHOTTO-mascot"})
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - địa chỉ do cấu hình, https theo mặc định
            data = json.loads(response.read(8192).decode("utf-8"))
        reply = data["reply"]
        if isinstance(reply, str) and reply.strip():
            return re.sub(r"[`*_#]", "", reply).strip()[:400], ("alert" if data.get("bubbleType") == "alert" else "normal")
    except Exception:  # noqa: BLE001 - nhân vật không được làm chết agent
        _LOG.info("Hỏi đáp nhân vật thất bại", exc_info=True)
    return str(LINES["fail"]), "normal"


# ---- hình học + vẽ bong bóng ----
_PAD: Final[dict[str, tuple[int, int, int]]] = {"normal": (24, 16, 14), "thought": (36, 28, 26), "alert": (64, 52, 44)}   # ngang, trên, dưới
_M: Final[int] = 14                            # lề quanh thân (chứa nét viền, ngôi sao, bóng)
_SHADOW: Final[int] = 7
_TAIL: Final[int] = 26                         # chiều cao đuôi / bong bóng nhỏ dưới thân
_SS: Final[int] = 3                            # siêu mẫu để viền mịn
_INK: Final[tuple[int, int, int, int]] = (21, 16, 26, 255)
_WHITE: Final[tuple[int, int, int, int]] = (255, 255, 255, 255)
_LINE: Final[float] = 3.0


def layout(kind: str, text_w: int, text_h: int, u: float) -> tuple[int, int, int, int]:
    """(rộng ảnh, cao ảnh, x chữ, y chữ) cho khối chữ ``text_w`` x ``text_h`` (điểm ảnh màn hình, ``u`` = tỉ lệ DPI)."""
    pad_x, pad_top, pad_bottom = (round(p * u) for p in _PAD[kind])
    m = round(_M * u)
    width = text_w + 2 * pad_x + 2 * m + round(_SHADOW * u)
    height = text_h + pad_top + pad_bottom + 2 * m + round((_TAIL + _SHADOW) * u)
    return width, height, m + pad_x, m + pad_top


def _super(cx: float, cy: float, a: float, b: float, n: int, phase: float = -math.pi / 2) -> list[tuple[float, float]]:
    """Điểm trên hình chữ nhật bo tròn (siêu elip) theo chiều kim đồng hồ."""
    pts = []
    for i in range(n):
        t = i / n * math.tau + phase
        c, s = math.cos(t), math.sin(t)
        pts.append((cx + a * math.copysign(abs(c) ** (2 / 3), c), cy + b * math.copysign(abs(s) ** (2 / 3), s)))
    return pts


def _shape(kind: str, w: float, h: float, u: float) -> tuple[list[tuple[list[tuple[float, float]], bool]], list[tuple[float, float, float]]]:
    """(đa giác kèm cờ "có viền riêng", hình tròn) của bong bóng; toạ độ trên ảnh ``w`` x ``h``, ``u`` đã gồm siêu mẫu."""
    m, sh, tail = _M * u, _SHADOW * u, _TAIL * u
    x0, y0, x1, y1 = m, m, w - m - sh, h - m - sh - tail
    cx, cy, a, b = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    polys: list[tuple[list[tuple[float, float]], bool]] = []
    circles: list[tuple[float, float, float]] = []
    if kind == "thought":
        dense = _super(cx, cy, a - 8 * u, b - 8 * u, 720)
        seg = [math.hypot(dense[(i + 1) % 720][0] - dense[i][0], dense[(i + 1) % 720][1] - dense[i][1]) for i in range(720)]
        n = max(10, round(sum(seg) / (26 * u)))                                    # bướu cách đều nhau theo chu vi, cùng cỡ
        step, acc = sum(seg) / n, 0.0
        ring: list[tuple[float, float]] = []
        for i, length in enumerate(seg):
            while acc + length >= len(ring) * step and len(ring) < n:
                ring.append(dense[i])
            acc += length
        circles += [(p[0], p[1], step * 0.62) for p in ring]
        polys.append((_super(cx, cy, a - 14 * u, b - 14 * u, 48), False))          # ruột lấp đầy, không viền
        circles += [(x1 - 26 * u, y1 + 11 * u, 8 * u), (x1 - 8 * u, y1 + 23 * u, 5 * u)]
    elif kind == "alert":
        n = max(10, min(20, round((a + b) / (8.5 * u)))) * 2
        ring = _super(cx, cy, a + 6 * u, b + 6 * u, n)
        polys.append(([(cx + (p[0] - cx) * (0.8 if i % 2 else 1.04), cy + (p[1] - cy) * (0.8 if i % 2 else 1.04))
                       for i, p in enumerate(ring)], True))
        star = [(x0 + 12 * u + (6 if i % 2 else 15) * u * math.cos(i / 10 * math.tau - math.pi / 2),
                 y0 + (6 if i % 2 else 15) * u * math.sin(i / 10 * math.tau - math.pi / 2)) for i in range(10)]
        polys.append((star, True))
    else:
        r, tr, tl = 22 * u, x1 - 34 * u, x1 - 66 * u
        pts: list[tuple[float, float]] = []

        def arc(ax: float, ay: float, a0: float, a1: float) -> None:
            for k in range(9):
                t = math.radians(a0 + (a1 - a0) * k / 8)
                pts.append((ax + r * math.cos(t), ay + r * math.sin(t)))

        arc(x1 - r, y0 + r, -90, 0)
        arc(x1 - r, y1 - r, 0, 90)
        pts += [(tr, y1), (x1 - 22 * u, y1 + 22 * u), (tl, y1)]
        arc(x0 + r, y1 - r, 90, 180)
        arc(x0 + r, y0 + r, 180, 270)
        polys.append((pts, True))
    return polys, circles


def render_bubble(kind: str, width: int, height: int, u: float = 1.0, dot: tuple[int, int, int] = (85, 85, 85)) -> Image.Image:
    """Bong bóng ``width`` x ``height`` điểm ảnh (RGBA; ngoài hình là trong suốt). Viền, ngôi sao, đuôi/bong bóng nhỏ theo ``kind``."""
    from PIL import Image, ImageChops, ImageDraw

    s = _SS
    big_w, big_h, uu = width * s, height * s, u * s
    polys, circles = _shape(kind, big_w, big_h, uu)
    lw = max(2, round(_LINE * uu))

    def mask(dx: float = 0.0, dy: float = 0.0, grow: float = 0.0) -> Image.Image:
        """Hình bong bóng dời (dx, dy), nở ra ``grow`` (âm = co lại, chỉ áp dụng cho hình tròn)."""
        img = Image.new("L", (big_w, big_h), 0)
        d = ImageDraw.Draw(img)
        for pts, _outlined in polys:
            moved = [(x + dx, y + dy) for x, y in pts]
            d.polygon(moved, fill=255)
            if grow > 0:
                d.line(moved + [moved[0]], fill=255, width=round(2 * grow), joint="curve")
        for cx, cy, r in circles:
            d.ellipse((cx + dx - r - grow, cy + dy - r - grow, cx + dx + r + grow, cy + dy + r + grow), fill=255)
        return img

    def solid(color: tuple[int, ...]) -> Image.Image:
        return Image.new("RGBA", (big_w, big_h), color)

    # bóng: hình lệch (7,7) giao với lưới chấm bi (hàng le)
    off = _SHADOW * uu
    dots = Image.new("L", (big_w, big_h), 0)
    dd = ImageDraw.Draw(dots)
    step, rad = 5 * uu, 1.7 * uu
    for gy in range(-2, int(big_h / step) + 3):
        for gx in range(-2, int(big_w / step) + 3):
            px, py = (gx + (0.5 if gy % 2 else 0)) * step, gy * step
            dd.ellipse((px - rad, py - rad, px + rad, py + rad), fill=255)
    out = Image.new("RGBA", (big_w, big_h), (0, 0, 0, 0))
    out.paste(solid((*dot, 255)), mask=ImageChops.multiply(mask(off, off), dots))
    out.paste(solid(_INK), mask=mask(grow=lw / 2))                             # viền đen: hình nở nửa nét
    out.paste(solid(_WHITE), mask=mask(grow=-lw / 2))                          # ruột trắng
    draw = ImageDraw.Draw(out)
    for pts, outlined in polys:                                                # đa giác: nét viền đè lại lên ruột
        if outlined:
            draw.line(pts + [pts[0]], fill=_INK, width=lw, joint="curve")
    small = out.resize((width, height), Image.Resampling.LANCZOS)
    small.putalpha(small.getchannel("A").point(lambda v: 255 if v >= 110 else 0))
    return small
