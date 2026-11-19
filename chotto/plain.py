"""Bảng chữ đời thường cho màn hình cảnh báo: **mã dấu hiệu → một câu ngắn** mà người không rành công nghệ hiểu ngay.

Hai việc:
  - ``headline``: MỘT câu kết luận (tối đa ~12 từ), chọn theo mức ưu tiên: danh sách đen, rồi kịch bản tổ hợp (cùng
    thứ tự và cùng nhóm mã với ``advisor.COMBOS``, ví dụ "giả danh thương hiệu + hối thúc"), rồi dấu hiệu riêng lẻ
    mạnh nhất, cuối cùng là câu mặc định theo mức.
  - ``details``: tối đa 3 gạch đầu dòng ngắn, mỗi dòng một ý và một biểu tượng, nằm trong mục "Xem vì sao".

Không dùng thuật ngữ (tầng, heuristic, điểm, signal, combosquat, TLD, RDAP...). Chỉ là dữ liệu chữ: không đổi
điểm số hay luật. ``tools/sync_extension_data.py`` xuất bản tiếng Việt sang ``extension/data/plain.json`` và
``extension/src/view.js`` đọc đúng bảng đó, nên hai nền tảng hiển thị CÙNG chữ (có test khớp từng ký tự).

Chi tiết động (từ khóa, đuôi tên miền, số ngày, cổng) lấy từ câu lý do tiếng Việt của engine bằng ``pattern``
(cú pháp dùng được ở cả Python ``re`` lẫn JavaScript ``RegExp``).
"""
from __future__ import annotations

from typing import Any, Final

from .advisor import COMBOS

__all__ = ["DETAILS", "HEADLINES", "LABELS", "LEVELS", "MAX_DETAILS", "plain_data"]

MAX_DETAILS: Final[int] = 3
BRAND: Final[str] = "{brand}"

# --- Mức độ -----------------------------------------------------------------------------------------------------
LEVELS: Final[dict[str, dict[str, dict[str, str]]]] = {
    "vi": {
        "WARN": {"label": "Khoan đã! Link đáng ngờ", "sub": "Hãy cẩn thận trước khi mở link này."},
        "HIGH": {"label": "Khoan đã! Link nguy hiểm", "sub": "Đừng đăng nhập hay nhập mã OTP vào trang này."},
        "BLOCKED": {"label": "Đã chặn! Link lừa đảo", "sub": "Đừng đăng nhập hay nhập bất cứ thông tin nào."},
    },
    "en": {
        "WARN": {"label": "Hold on! Suspicious link", "sub": "Be careful before you open this link."},
        "HIGH": {"label": "Hold on! Dangerous link", "sub": "Don't sign in or type any OTP code on this page."},
        "BLOCKED": {"label": "Blocked! Scam link", "sub": "Don't sign in or enter any information."},
    },
}

# --- Câu kết luận -----------------------------------------------------------------------------------------------
# Tổ hợp: cùng thứ tự với ``advisor.COMBOS`` (test kiểm tra số lượng khớp).
_COMBO_HEADLINES: Final[dict[str, tuple[str, ...]]] = {
    "vi": (
        "Trang giả {brand}, tên miền vừa mới lập",
        "Giả danh {brand} và hối thúc bạn",
        "Giả danh {brand} trên trang web miễn phí",
        "Giả danh {brand}, đi vòng qua trang uy tín",
        "Link rút gọn kèm lời hối thúc",
        "Trang dựng tạm, không an toàn",
    ),
    "en": (
        "Fake {brand} page on a brand-new domain",
        "Pretends to be {brand} and rushes you",
        "Pretends to be {brand} on a free website",
        "Pretends to be {brand}, via a trusted detour",
        "A short link with pressure to hurry",
        "A makeshift page that isn't safe",
    ),
}

# Dấu hiệu riêng lẻ (dấu hiệu nào không có ở đây thì không tự làm câu kết luận, chỉ nằm trong "Xem vì sao").
_SINGLE_HEADLINES: Final[dict[str, dict[str, str]]] = {
    "vi": {
        "blacklist": "Trang này nằm trong danh sách lừa đảo",
        "unparseable": "CHOTTO không đọc được link này",
        "homoglyph": "Giả dạng {brand} bằng ký tự lạ",
        "typosquat": "Tên gần giống {brand}, sai vài chữ",
        "combosquat": "Mượn tên {brand} nhưng không phải trang chính thức",
        "brand_in_path": "Chèn tên {brand} để đánh lừa",
        "shortener": "Link rút gọn che địa chỉ thật",
        "redirect_via_trusted": "Mượn trang uy tín để chuyển hướng",
        "nested_redirect": "Bị chuyển hướng qua nhiều lớp",
        "raw_ip": "Dùng dãy số thay cho tên trang",
        "at_sign": "Có dấu @ để giấu địa chỉ thật",
        "free_hosting": "Nằm trên nền tảng web miễn phí",
        "lure": "Có lời hối thúc, dọa dẫm",
        "idn": "Có ký tự lạ dễ nhầm với chữ thường",
        "age": "Tên miền vừa mới đăng ký",
    },
    "en": {
        "blacklist": "This page is on a scam list",
        "unparseable": "Chotto can't read this link",
        "homoglyph": "Imitates {brand} with odd characters",
        "typosquat": "Almost {brand}, but a few letters off",
        "combosquat": "Uses the name {brand} but isn't the official site",
        "brand_in_path": "Slips in the name {brand} to mislead you",
        "shortener": "A short link hides the real address",
        "redirect_via_trusted": "Borrows a trusted site to redirect you",
        "nested_redirect": "Bounced through many redirects",
        "raw_ip": "Uses a string of numbers, not a site name",
        "at_sign": "An @ sign hides the real address",
        "free_hosting": "Sits on a free website builder",
        "lure": "Uses pressure and scare words",
        "idn": "Has odd characters that pass for plain letters",
        "age": "The domain was only just registered",
    },
}

_DEFAULT_HEADLINES: Final[dict[str, dict[str, str]]] = {
    "vi": {"WARN": "Địa chỉ này trông khác thường", "HIGH": "Địa chỉ này giống trang lừa đảo",
           "BLOCKED": "Trang này nằm trong danh sách lừa đảo"},
    "en": {"WARN": "This address looks a bit odd", "HIGH": "This address looks like a scam page",
           "BLOCKED": "This page is on a scam list"},
}
_DEFAULT_BRAND: Final[dict[str, str]] = {"vi": "thương hiệu này", "en": "this brand"}

HEADLINES: Final[dict[str, dict[str, Any]]] = {
    lang: {"combos": _COMBO_HEADLINES[lang], "single": _SINGLE_HEADLINES[lang], "default": _DEFAULT_HEADLINES[lang],
           "brand": _DEFAULT_BRAND[lang]}
    for lang in ("vi", "en")
}

# --- Gạch đầu dòng "Xem vì sao" ----------------------------------------------------------------------------------
# code -> {icon, text, pattern?, fallback?}. ``pattern`` lấy nhóm {0} từ câu lý do tiếng Việt của engine; không khớp
# thì dùng ``fallback`` (không có ``fallback`` thì bỏ dòng này).
_DETAILS_VI: Final[dict[str, dict[str, str]]] = {
    "blacklist": {"icon": "shield", "text": "Nhiều người đã báo trang này là lừa đảo"},
    "unparseable": {"icon": "alert", "text": "Địa chỉ có định dạng bất thường"},
    "combosquat": {"icon": "badge", "text": "Có tên {brand} nhưng không phải trang chính thức"},
    "homoglyph": {"icon": "eye", "text": "Có chữ trông giống {brand} nhưng là ký tự khác"},
    "typosquat": {"icon": "eye", "text": "Gần giống {brand} nhưng sai vài chữ"},
    "lure": {"icon": "alert", "text": "Có từ hối thúc: “{0}”", "pattern": "“(.+?)”", "fallback": "Có từ ngữ hối thúc, dọa dẫm"},
    "brand_in_path": {"icon": "badge", "text": "Tên {brand} chỉ chèn phía sau để đánh lừa"},
    "tld": {"icon": "tag", "text": "Đuôi .{0} hay bị kẻ xấu lợi dụng", "pattern": "Đuôi \\.(\\S+)",
            "fallback": "Đuôi tên miền hay bị kẻ xấu lợi dụng"},
    "idn": {"icon": "eye", "text": "Có ký tự lạ dễ nhầm với chữ thường"},
    "entropy": {"icon": "shuffle", "text": "Tên miền như một chuỗi chữ ngẫu nhiên"},
    "hyphens": {"icon": "shuffle", "text": "Có nhiều dấu gạch ngang bất thường"},
    "digits": {"icon": "shuffle", "text": "Có nhiều chữ số ngẫu nhiên"},
    "free_hosting": {"icon": "server", "text": "Nằm trên nền tảng web miễn phí, ai cũng lập được"},
    "nested_redirect": {"icon": "route", "text": "Bị chuyển qua nhiều lớp để giấu nơi đến"},
    "redirect_via_trusted": {"icon": "route", "text": "Mượn trang uy tín để chuyển bạn sang trang khác"},
    "http": {"icon": "lock", "text": "Không mã hóa, thông tin nhập vào có thể bị đọc trộm"},
    "at_sign": {"icon": "alert", "text": "Có dấu @ để giấu địa chỉ thật"},
    "port": {"icon": "server", "text": "Dùng cổng mạng lạ"},
    "shortener": {"icon": "link", "text": "Link rút gọn che địa chỉ thật"},
    "raw_ip": {"icon": "server", "text": "Dùng dãy số thay cho tên trang"},
    "age": {"icon": "clock", "text": "Tên miền mới đăng ký {0} ngày trước", "pattern": "(\\d+) ngày",
            "fallback": "Tên miền mới đăng ký gần đây"},
}
_DETAILS_EN: Final[dict[str, dict[str, str]]] = {
    "blacklist": {"icon": "shield", "text": "Many people reported this page as a scam"},
    "unparseable": {"icon": "alert", "text": "The address has an unusual format"},
    "combosquat": {"icon": "badge", "text": "Has the name {brand} but isn't the official site"},
    "homoglyph": {"icon": "eye", "text": "Letters that look like {brand} but are other characters"},
    "typosquat": {"icon": "eye", "text": "Almost {brand}, but a few letters off"},
    "lure": {"icon": "alert", "text": "Has a pressure word: “{0}”", "pattern": "“(.+?)”", "fallback": "Has pressure or scare words"},
    "brand_in_path": {"icon": "badge", "text": "The name {brand} is slipped in later to mislead"},
    "tld": {"icon": "tag", "text": "The .{0} ending is often abused by scammers", "pattern": "Đuôi \\.(\\S+)",
            "fallback": "The domain ending is often abused by scammers"},
    "idn": {"icon": "eye", "text": "Has odd characters that pass for plain letters"},
    "entropy": {"icon": "shuffle", "text": "The domain looks like random letters"},
    "hyphens": {"icon": "shuffle", "text": "Has an unusual number of hyphens"},
    "digits": {"icon": "shuffle", "text": "Has many random digits"},
    "free_hosting": {"icon": "server", "text": "On a free website builder anyone can use"},
    "nested_redirect": {"icon": "route", "text": "Bounced through many redirects to hide the end"},
    "redirect_via_trusted": {"icon": "route", "text": "Borrows a trusted site to send you elsewhere"},
    "http": {"icon": "lock", "text": "Not encrypted, so what you type can be read"},
    "at_sign": {"icon": "alert", "text": "An @ sign hides the real address"},
    "port": {"icon": "server", "text": "Uses an unusual network port"},
    "shortener": {"icon": "link", "text": "A short link hides the real address"},
    "raw_ip": {"icon": "server", "text": "Uses a string of numbers, not a site name"},
    "age": {"icon": "clock", "text": "Domain registered only {0} day(s) ago", "pattern": "(\\d+) ngày",
            "fallback": "Domain registered very recently"},
}
DETAILS: Final[dict[str, dict[str, dict[str, str]]]] = {"vi": _DETAILS_VI, "en": _DETAILS_EN}

# --- Nhãn giao diện ---------------------------------------------------------------------------------------------
LABELS: Final[dict[str, dict[str, str]]] = {
    "vi": {
        "caption": "Link này thật sự dẫn tới",
        "official": "Trang chính thức của {brand} là {domain}",
        "why": "Xem vì sao",
        "checking": "Đang xác minh tuổi tên miền…",
        "back": "Quay lại an toàn",
        "proceed": "Vẫn mở link",
        "proceed_wait": "Vẫn mở link (mở khóa sau {n} giây)",
        "copy": "Sao chép địa chỉ",
        "copied": "Đã sao chép địa chỉ",
        "report": "Báo cho người gửi",
        "reported": "Đã chép lời nhắn, hãy dán vào Zalo",
        "hint": "Nhấn Esc để quay lại",
        "decoy": "phần ngụy trang",
        "report_text": "Link này có vẻ lừa đảo, bạn đừng bấm nhé: {domain}",
        "unknown": "(không xác định)",
        "ip": "dãy số, không phải tên trang",
    },
    "en": {
        "caption": "This link really goes to",
        "official": "The official {brand} site is {domain}",
        "why": "See why",
        "checking": "Checking how old the domain is…",
        "back": "Go back to safety",
        "proceed": "Open anyway",
        "proceed_wait": "Open anyway (unlocks in {n} s)",
        "copy": "Copy address",
        "copied": "Address copied",
        "report": "Tell the sender",
        "reported": "Message copied, paste it into Zalo",
        "hint": "Press Esc to go back",
        "decoy": "disguise",
        "report_text": "This link looks like a scam, please don't tap it: {domain}",
        "unknown": "(unknown)",
        "ip": "numbers, not a site name",
    },
}


def combo_groups() -> tuple[tuple[frozenset[str], ...], ...]:
    """Nhóm mã của từng tổ hợp, đúng thứ tự ưu tiên của ``advisor.COMBOS``."""
    return tuple(groups for groups, _ in COMBOS)


def plain_data(lang: str = "vi") -> dict[str, Any]:
    """Toàn bộ bảng chữ của một ngôn ngữ ở dạng JSON (nhóm tổ hợp đã sắp xếp), để xuất sang tiện ích.

    Args:
        lang: ``"vi"`` hoặc ``"en"``.
    """
    lang = "vi" if lang == "vi" else "en"
    headlines = HEADLINES[lang]
    return {
        "levels": LEVELS[lang],
        "combos": [{"groups": [sorted(group) for group in groups], "text": text}
                   for groups, text in zip(combo_groups(), headlines["combos"], strict=True)],
        "single": headlines["single"],
        "default": headlines["default"],
        "brand": headlines["brand"],
        "details": DETAILS[lang],
        "labels": LABELS[lang],
        "max_details": MAX_DETAILS,
    }
