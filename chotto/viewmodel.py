"""Chuyển ``Result`` của engine thành dữ liệu hiển thị cho giao diện HTML (thuần Python, không phụ thuộc GUI).

Phần quan trọng nhất là ``url_parts``: tách đường link thành các phần có nhãn để người dùng thấy ngay
**nơi link thật sự dẫn tới** (tên miền đăng ký được) và phần nào chỉ là ngụy trang (tên ngân hàng đặt
ở tên miền phụ, phần ``user@`` trước host...).

Hai ngôn ngữ (``"en"``, ``"vi"``). Engine luôn viết lý do bằng tiếng Việt (dùng chung với tiện ích trình
duyệt), nên bản tiếng Anh được dựng lại từ **mã dấu hiệu**; chi tiết động (từ khóa, đuôi tên miền, số
ngày...) lấy từ câu gốc. Mã chưa có bản dịch thì giữ câu tiếng Việt, không bao giờ làm mất lý do.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final

from .advisor import GENERAL, GENERAL_EN, advise_signals
from .core.url import URLParseError, domain_to_unicode, parse_url
from .util import registered_domain, sanitize_for_display

if TYPE_CHECKING:
    from .engine import Result

__all__ = ["brand_of", "friction_view", "official_domain", "reason_text", "tier_text", "url_parts"]

_PATH_LIMIT: Final[int] = 36
_RAW_LIMIT: Final[int] = 90
_MAX_REASONS: Final[int] = 4
_DANGER: Final[frozenset[str]] = frozenset({"HIGH", "BLOCKED"})

_TEXT: Final[dict[str, dict[str, str]]] = {
    "en": {
        "decoy_user": "decoy", "decoy": "disguise", "sub": "subdomain", "target": "where you actually go",
        "ip": "an IP address, not a domain", "port": "unusual port",
        "t0": "Chotto can't read this link.", "t0_sub": "Ask the sender before opening it.",
        "blocked": "This link is on a scam list.", "fake": "This is a fake page.",
        "high": "This link is very dangerous.", "warn": "This link looks suspicious.",
        "danger_sub": "Don't sign in or enter any OTP code on this page.",
        "checking_sub": "Chotto is checking how old the domain is.", "warn_sub": "Think carefully before opening it.",
        "src0": "Could not analyse the link", "src1": "Scam list", "src3": "Domain analysis and domain age",
        "src2": "Domain analysis",
    },
    "vi": {
        "decoy_user": "phần đánh lừa", "decoy": "phần ngụy trang", "sub": "tên miền phụ",
        "target": "nơi bạn thật sự tới", "ip": "địa chỉ IP, không phải tên miền", "port": "cổng lạ",
        "t0": "Chotto không đọc được link này.", "t0_sub": "Hãy hỏi lại người gửi trước khi mở.",
        "blocked": "Link có trong danh sách lừa đảo.", "fake": "Đây là trang giả.",
        "high": "Link này rất nguy hiểm.", "warn": "Link này đáng ngờ.",
        "danger_sub": "Đừng đăng nhập hay nhập mã OTP vào trang này.",
        "checking_sub": "Chotto đang tra thêm tuổi tên miền.", "warn_sub": "Hãy cân nhắc kỹ trước khi mở.",
        "src0": "Không phân tích được liên kết", "src1": "Danh sách lừa đảo",
        "src3": "Phân tích tên miền và tuổi tên miền", "src2": "Phân tích tên miền",
    },
}


def _t(lang: str) -> dict[str, str]:
    return _TEXT["vi" if lang == "vi" else "en"]


def _fill(template: str, pattern: str, fallback: str = "") -> Callable[[Mapping[str, Any], str], str]:
    """Bộ dịch dùng các nhóm của ``pattern`` (tìm trong câu gốc) và ``{brand}`` để điền ``template``.

    Câu gốc không khớp ``pattern`` thì trả ``fallback`` (rỗng = giữ câu tiếng Việt).
    """
    compiled = re.compile(pattern) if pattern else None

    def translate(signal: Mapping[str, Any], original: str) -> str:
        groups: tuple[str, ...] = ()
        if compiled is not None:
            found = compiled.search(original)
            if found is None:
                return fallback.format(brand=signal.get("brand", ""))
            groups = found.groups()
        return template.format(*groups, brand=signal.get("brand", ""))

    return translate


# Lý do tiếng Anh theo mã dấu hiệu; chi tiết động lấy từ câu tiếng Việt của engine.
_REASONS_EN: Final[dict[str, Callable[[Mapping[str, Any], str], str]]] = {
    "blacklist": _fill("This domain is on a scam list reported by the community", ""),
    "unparseable": _fill("Chotto could not analyse this link; check it carefully before opening", ""),
    "combosquat": _fill("The domain contains the name “{brand}” but is not the official site", ""),
    "homoglyph": _fill("Uses look-alike characters (0/o, 1/l, rn/m, Cyrillic…) to imitate {brand}", ""),
    "typosquat": _fill("Imitates the brand {brand} ({0} character(s) off)", r"sai lệch (\d+)",
                       "Imitates the brand {brand}"),
    "lure": _fill("Contains an alarming keyword: “{0}”", r"“(.+?)”", "Contains an alarming keyword"),
    "brand_in_path": _fill("The path inserts {0} to pose as {brand}", r"địa chỉ (\S+) để"),
    "tld": _fill("The .{0} ending is often abused for scams", r"Đuôi \.(\S+)"),
    "idn": _fill("The domain uses Unicode characters that are easy to fake", ""),
    "entropy": _fill("The domain looks like a random string of characters", ""),
    "hyphens": _fill("The domain has an unusual number of hyphens", ""),
    "digits": _fill("The domain contains many random digits", ""),
    "free_hosting": _fill("The page is on a free website builder anyone can use in minutes", ""),
    "nested_redirect": _fill("The link is wrapped in many redirects to hide where it goes", ""),
    "http": _fill("The link is not encrypted (http://)", ""),
    "at_sign": _fill("Contains an @ sign to hide the real domain", ""),
    "port": _fill("Uses an unusual network port (:{0})", r"\(:(\d+)\)", "Uses an unusual network port"),
    "shortener": _fill("A short link hides the real destination", ""),
    "raw_ip": _fill("Uses an IP address instead of a domain name", ""),
    "redirect_via_trusted": _fill("Goes through {0} to redirect to {1}", r"Đi qua (\S+) để chuyển hướng sang (\S+)"),
    "age": _fill("Domain registered only {0} day(s) ago", r"(\d+) ngày", "Domain registered very recently"),
}


def reason_text(signal: Mapping[str, Any], lang: str) -> str:
    """Lý do hiển thị của một dấu hiệu theo ngôn ngữ (thiếu bản dịch: giữ câu tiếng Việt của engine)."""
    original = str(signal.get("reason", ""))
    if lang != "en":
        return original
    translate = _REASONS_EN.get(str(signal.get("code", "")))
    return (translate(signal, original) if translate else "") or original


def _reasons(result: Result, lang: str) -> list[str]:
    """Tối đa 4 lý do, cùng thứ tự với ``Result.reasons`` (dấu hiệu có điểm dương và có câu lý do)."""
    if lang != "en" or not result.signals:
        return [sanitize_for_display(reason) for reason in result.reasons[:_MAX_REASONS]]
    picked = [s for s in result.signals if int(s.get("points", 0)) > 0 and s.get("reason")][:_MAX_REASONS]
    return [sanitize_for_display(reason_text(s, lang)) for s in picked]


def _truncate(text: str, limit: int) -> str:
    """Rút gọn ở giữa (giữ đầu và cuối) để không mất phần đuôi đáng ngờ."""
    if len(text) <= limit:
        return text
    head = (limit - 1) * 2 // 3
    return text[:head] + "…" + text[-(limit - 1 - head):]


def brand_of(signals: Sequence[Mapping[str, Any]]) -> str:
    """Thương hiệu bị giả danh (dấu hiệu đầu tiên có ``brand``), rỗng nếu không có."""
    for signal in signals:
        if signal.get("brand"):
            return str(signal["brand"])
    return ""


def official_domain(brand: str, rules: Mapping[str, Any]) -> str:
    """Tên miền chính thức đầu tiên của ``brand`` trong bộ luật, rỗng nếu không biết."""
    for entry in rules.get("brands", []):
        if str(entry.get("name", "")).casefold() == brand.casefold() and entry.get("domains"):
            return str(entry["domains"][0])
    return ""


def tier_text(result: Result, lang: str = "en") -> str:
    """Tầng đã phát hiện rủi ro, viết cho người dùng."""
    text = _t(lang)
    if result.tier_reached == 0:
        return text["src0"]
    if result.tier_reached == 1:
        return text["src1"]
    if result.tier_reached == 3 and result.domain_age_days is not None:
        return text["src3"]
    return text["src2"]


def _part(text: str, kind: str, label: str = "") -> dict[str, str]:
    return {"text": text, "kind": kind, "label": label}


def url_parts(result: Result, brand: str = "", lang: str = "en") -> list[dict[str, str]]:
    """Tách ``result.final_url`` thành các phần hiển thị.

    ``kind``: ``dim`` (phụ), ``decoy`` (ngụy trang, gạch đi), ``real`` (nơi thật sự tới, mức nguy hiểm)
    hoặc ``warnpart`` (nơi thật sự tới, mức đáng ngờ). Link không phân tích được: một phần ``dim``.
    """
    text = _t(lang)
    raw = sanitize_for_display(result.final_url or result.url)
    try:
        url = parse_url(result.final_url or result.url)
    except URLParseError:
        return [_part(_truncate(raw, _RAW_LIMIT), "dim")]
    target_kind = "real" if result.level in _DANGER else "warnpart"
    parts = [_part(f"{url.scheme}://", "dim")]
    if url.username:
        parts.append(_part(_truncate(sanitize_for_display(url.username), 30) + "@", "decoy", text["decoy_user"]))
    host = url.host
    if url.host_kind != "domain":
        parts.append(_part(host, target_kind, text["ip"]))
    else:
        domain = result.display_domain or registered_domain(host) or host
        prefix = host[: -len(domain)] if host.endswith("." + domain) else ""
        if prefix:
            shown = sanitize_for_display(domain_to_unicode(prefix.rstrip("."))) + "."
            parts.append(_part(shown, "decoy" if brand else "dim", text["decoy"] if brand else text["sub"]))
        readable = sanitize_for_display(domain_to_unicode(domain))
        label = text["target"] if readable == domain else f"{text['target']} ({domain})"
        parts.append(_part(readable, target_kind, label))
    if url.port is not None:
        parts.append(_part(f":{url.port}", "dim", text["port"]))
    rest = url.path + (f"?{url.query}" if url.query else "")
    if rest and rest != "/":
        parts.append(_part(_truncate(sanitize_for_display(rest), _PATH_LIMIT), "dim"))
    return parts


def _headline(result: Result, brand: str, checking: bool, lang: str) -> tuple[str, str]:
    """(dòng thứ hai của tiêu đề, câu phụ)."""
    text = _t(lang)
    if result.tier_reached == 0:
        return text["t0"], text["t0_sub"]
    if result.level == "BLOCKED":
        return text["blocked"], text["danger_sub"]
    if result.level == "HIGH":
        return (text["fake"] if brand else text["high"]), text["danger_sub"]
    return text["warn"], text["checking_sub"] if checking else text["warn_sub"]


def _advice(result: Result, checking: bool, lang: str) -> str:
    """Lời khuyên (chỉ khi engine đã sinh lời khuyên và Tầng 3 không còn chạy, như bản Tk)."""
    if not result.advice or checking:
        return ""
    return advise_signals(result.signals, "en") if lang == "en" else result.advice


def friction_view(result: Result, checking: bool, rules: Mapping[str, Any], lang: str = "en") -> dict[str, Any]:
    """Toàn bộ dữ liệu cho màn hình đệm.

    Args:
        result: Kết quả đang hiển thị.
        checking: Tầng 3 còn chạy nền (hiện dòng "đang tra" và ẩn lời khuyên như bản Tk).
        rules: Bộ luật (để tra tên miền chính thức của thương hiệu bị giả danh).
        lang: ``"en"`` hoặc ``"vi"``.
    """
    lang = "vi" if lang == "vi" else "en"
    brand = brand_of(result.signals)
    title, text = _headline(result, brand, checking, lang)
    return {
        "lang": lang,
        "level": result.level if result.level in ("WARN", "HIGH", "BLOCKED") else "WARN",
        "score": max(0, min(100, int(result.score))),
        "title": title,
        "text": text,
        "parts": url_parts(result, brand, lang),
        "brand": brand,
        "official": official_domain(brand, rules) if brand else "",
        "reasons": _reasons(result, lang),
        "checking": checking,
        "advice": _advice(result, checking, lang),
        "general": GENERAL_EN if lang == "en" else GENERAL,
        "source": tier_text(result, lang),
        "full_url": _truncate(sanitize_for_display(result.final_url or result.url), 160),
    }
