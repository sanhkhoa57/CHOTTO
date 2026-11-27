"""Quét QR của nhân vật taskbar, phần KHÔNG đụng Tk: cắt vùng chọn, giải mã, thẩm định link, soạn câu báo (EN/VI).

Nội dung mã QR là dữ liệu lạ: luôn qua ``sanitize_for_display`` trước khi hiện, và chỉ ``http``/``https`` mới được coi là link.
Link luôn đi qua ``Engine`` của Chotto; module này không bao giờ mở link.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from ..util import sanitize_for_display
from . import speech

if TYPE_CHECKING:
    from PIL import Image

    from ..engine import Result

__all__ = ["TEXT", "QrReport", "analyze", "as_link", "crop", "decode", "scan", "selection_box"]

_LOG = logging.getLogger("chotto")

MIN_SELECTION: Final[int] = 12                 # cạnh nhỏ hơn chừng này (điểm ảnh) coi như bấm nhầm, không phải kéo chọn
_SHOWN_CHARS: Final[int] = 160                 # bong bóng chỉ hiện chừng này ký tự; nút Sao chép vẫn lấy đủ
Box = tuple[int, int, int, int]

TEXT: Final[dict[str, dict[str, str]]] = {
    "en": {
        "choose": "What can I do for you?", "scan": "Scan QR", "ask": "Ask Chotto",
        "copy": "Copy", "copied": "Copied", "open": "Open link",
        "hint": "Drag around the QR code · Esc to cancel",
        "reading": "Reading the QR code...",
        "none": "I couldn't find a QR code there. Try selecting a bit wider!",
        "failed": "I couldn't capture or read the screen. Please try again.",
        "missing": "QR scanning isn't available in this install (missing the zxing-cpp library).",
        "text": "The QR code says:",
        "SAFE": "No warning signs found for {domain}, but that isn't a guarantee.",
        "WARN": "Careful, {domain} looks suspicious!",
        "HIGH": "Dangerous! Stay away from {domain}.",
        "BLOCKED": "Dangerous! {domain} is on the scam list.",
        "unchecked": "I couldn't check this link. Don't open it unless you trust the source.",
        "many": "(Several QR codes found; this is the first one.)",
    },
    "vi": {
        "choose": "Bạn cần tui làm gì nè?", "scan": "Quét QR", "ask": "Hỏi Chotto",
        "copy": "Sao chép", "copied": "Đã chép", "open": "Mở link",
        "hint": "Kéo chọn vùng chứa mã QR · Nhấn Esc để hủy",
        "reading": "Đang đọc mã QR...",
        "none": "Tui không thấy mã QR nào trong vùng đó. Thử kéo rộng hơn chút nha!",
        "failed": "Tui chưa chụp hoặc đọc được màn hình. Bạn thử lại nha!",
        "missing": "Bản cài này chưa quét được QR (thiếu thư viện zxing-cpp).",
        "text": "Mã QR ghi là:",
        "SAFE": "Tui chưa thấy dấu hiệu lừa đảo ở {domain}, nhưng chưa chắc 100% đâu nha.",
        "WARN": "Cẩn thận, {domain} đáng ngờ đó!",
        "HIGH": "Nguy hiểm! Né {domain} ra nha.",
        "BLOCKED": "Nguy hiểm! {domain} nằm trong danh sách lừa đảo.",
        "unchecked": "Tui chưa kiểm tra được link này. Không chắc nguồn gửi thì đừng mở nha.",
        "many": "(Có nhiều mã QR, đây là mã đầu tiên.)",
    },
}


@dataclass(frozen=True)
class QrReport:
    """Kết quả một lần quét, đủ để vẽ bong bóng.

    ``status``: ``missing`` | ``none`` | ``failed`` (chỉ có câu báo) | ``text`` | ``link``.
    ``payload``: nội dung đầy đủ để sao chép. ``link``: link http/https để người dùng xác nhận mở (rỗng nếu không phải link).
    """

    status: str
    message: str
    kind: speech.Kind = "normal"
    payload: str = ""
    link: str = ""
    level: str = ""


def texts(lang: str) -> dict[str, str]:
    return TEXT.get(lang, TEXT["en"])


def selection_box(x0: int, y0: int, x1: int, y1: int, width: int, height: int) -> Box | None:
    """Vùng chọn (kéo theo hướng nào cũng được) kẹp trong ảnh ``width`` x ``height``; ``None`` nếu quá nhỏ."""
    left, right = sorted((max(0, min(width, x0)), max(0, min(width, x1))))
    top, bottom = sorted((max(0, min(height, y0)), max(0, min(height, y1))))
    if right - left < MIN_SELECTION or bottom - top < MIN_SELECTION:
        return None
    return left, top, right, bottom


def crop(image: Image.Image, box: Box) -> Image.Image:
    return image.crop(box)


def decode(image: Image.Image) -> list[str]:
    """Nội dung các mã QR trong ảnh. Không thấy thì thử lại với viền trắng (người dùng hay kéo sát mép) và phóng to.

    Raises:
        ImportError: Thiếu ``zxing-cpp``.
    """
    import zxingcpp
    from PIL import Image as PILImage
    from PIL import ImageOps

    formats = zxingcpp.BarcodeFormats([zxingcpp.BarcodeFormat.QRCode, zxingcpp.BarcodeFormat.MicroQRCode,
                                        zxingcpp.BarcodeFormat.RMQRCode])

    def read(candidate: Image.Image) -> list[str]:
        return list(dict.fromkeys(str(b.text) for b in zxingcpp.read_barcodes(candidate, formats=formats) if b.text))

    rgb = image.convert("RGB")
    found = read(rgb)
    if found:
        return found
    padded = ImageOps.expand(rgb, border=max(16, min(rgb.size) // 8), fill=(255, 255, 255))
    found = read(padded)
    if found or max(padded.size) > 1600:                  # ảnh đã lớn thì phóng nữa vô ích
        return found
    return read(padded.resize((padded.width * 3, padded.height * 3), PILImage.Resampling.LANCZOS))


_BARE_DOMAIN: Final[re.Pattern[str]] = re.compile(r"(?:[a-z0-9-]+\.)+(?:xn--[a-z0-9-]+|[a-z]{2,24})(?::\d{1,5})?(?:[/?#]\S*)?", re.I)


def as_link(payload: str) -> str:
    """Link http/https mà mã QR chứa, hoặc rỗng nếu là văn bản thường (kể cả ``tel:``, ``wifi:``...: không bao giờ mở)."""
    value = payload.strip()
    if not value or any(ch.isspace() for ch in value):
        return ""
    if value.lower().startswith(("http://", "https://")):
        return value
    return "https://" + value if _BARE_DOMAIN.fullmatch(value) else ""


def _shorten(value: str) -> str:
    clean = sanitize_for_display(value)
    return clean if len(clean) <= _SHOWN_CHARS else clean[:_SHOWN_CHARS - 1] + "…"


def _inspect(link: str) -> Result:
    """Thẩm định bằng đúng cấu hình của người dùng, như một link vừa được bấm."""
    from ..engine import Engine

    engine = Engine()
    try:
        return engine.inspect(link)
    finally:
        engine.release()


def analyze(payloads: list[str], lang: str, inspect: Callable[[str], Result] = _inspect) -> QrReport:
    """Câu báo cho các nội dung đọc được (chỉ xét mã đầu tiên)."""
    t = texts(lang)
    if not payloads:
        return QrReport("none", t["none"])
    payload = payloads[0]
    extra = "\n" + t["many"] if len(payloads) > 1 else ""
    link = as_link(payload)
    if not link:
        return QrReport("text", f"{t['text']} {_shorten(payload)}{extra}", payload=payload)
    try:
        result = inspect(link)
        message = _verdict(result, link, t, lang)
        level = str(result.level)
    except Exception:  # noqa: BLE001 - không thẩm định được thì cảnh giác, không bao giờ coi là an toàn
        _LOG.exception("Không thẩm định được link trong mã QR")
        message, level = t["unchecked"], "WARN"
    kind: speech.Kind = "normal" if level == "SAFE" else "alert"
    return QrReport("link", f"{message}\n{_shorten(link)}{extra}", kind, payload, link, level)


def _verdict(result: Result, link: str, t: Mapping[str, str], lang: str) -> str:
    if result.tier_reached == 0:
        return t["unchecked"]
    domain = sanitize_for_display(result.display_domain or result.host or link)
    head = t.get(str(result.level), t["WARN"]).format(domain=domain)
    if result.level == "SAFE":
        return head
    from ..config import load_rules
    from ..viewmodel import friction_view

    reasons: list[Any] = friction_view(result, False, load_rules(), lang)["reasons"]
    why = str(reasons[0]).rstrip(".") + "." if reasons else ""
    return f"{head} {why}".strip()


def scan(image: Image.Image, lang: str) -> QrReport:
    """Giải mã + thẩm định (chạy trên luồng nền). Không ném lỗi."""
    t = texts(lang)
    try:
        return analyze(decode(image), lang)
    except ImportError:
        _LOG.warning("Thiếu zxing-cpp, không quét được QR", exc_info=True)
        return QrReport("missing", t["missing"])
    except Exception:  # noqa: BLE001 - nhân vật không được làm chết agent
        _LOG.exception("Quét QR lỗi")
        return QrReport("failed", t["failed"])
