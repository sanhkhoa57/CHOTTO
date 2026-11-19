"""Dữ liệu cho màn hình cảnh báo kiểu mới ("shield"): hiển thị lũy tiến, một câu kết luận, tên miền thật là nhân vật chính.

Mặc định người dùng chỉ thấy ba thứ: (a) một câu kết luận, (b) tên miền thật được làm nổi bật, (c) hành động. Mọi
thứ khác (tối đa 3 gạch đầu dòng) nằm trong mục thu gọn "Xem vì sao". Không có điểm số, tên tầng hay thuật ngữ.

Cấu trúc trả về của ``shield_view``::

    {lang, level, levelLabel, headline, reasonShort,
     domain: {userinfo, prefix, decoyPrefix, registered, rest, hit, punycode, isIp, brand, official},
     officialLine, details: [{icon, text}], checking,
     actions: {back, proceed, copy, report, copied, reported, hint, copyText, reportText},
     labels: {caption, why, checking, proceedWait, decoy, ip}}

Cùng cấu trúc và cùng chữ với ``extension/src/view.js`` (bản tiếng Việt). ``tests/data/view_vectors.json`` do
``tools/gen_view_vectors.py`` sinh, cả Python lẫn JavaScript phải tái tạo đúng từng ký tự. Chữ nằm ở ``chotto/plain.py``.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final

from . import plain
from .core.url import URLParseError, domain_to_unicode, parse_url
from .util import sanitize_for_display
from .viewmodel import _truncate, brand_of, official_domain

if TYPE_CHECKING:
    from .engine import Result

__all__ = ["brand_hit", "shield_details", "shield_headline", "shield_view"]

_REST_LIMIT: Final[int] = 40
_RAW_LIMIT: Final[int] = 90
_USERINFO_LIMIT: Final[int] = 30
_IMPERSONATION: Final[frozenset[str]] = frozenset({"combosquat", "homoglyph", "typosquat"})
_MAX_EDIT: Final[int] = 2
_MIN_KEYWORD: Final[int] = 4
_LEVELS: Final[tuple[str, ...]] = ("WARN", "HIGH", "BLOCKED")


def _levenshtein(a: str, b: str) -> int:
    """Khoảng cách Levenshtein (thêm/xóa/thay một ký tự)."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            row.append(min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = row
    return previous[-1]


def brand_hit(registered: str, brand: str, rules: Mapping[str, Any]) -> str:
    """Phần của tên miền đăng ký giống tên thương hiệu nhất (để tô sáng), rỗng nếu không thấy.

    Thử từ khóa nguyên văn trước (tên có chứa thương hiệu), rồi tìm đoạn gần giống tối đa 2 ký tự (sai chính tả hoặc
    ký tự đánh lừa). Thứ tự duyệt cố định để bản JavaScript chọn đúng đoạn này.

    Args:
        registered: Tên miền đăng ký ở dạng đọc được (Unicode).
        brand: Tên thương hiệu bị giả danh.
        rules: Bộ luật (lấy từ khóa của thương hiệu).
    """
    keywords: list[str] = []
    for entry in rules.get("brands", []):
        if str(entry.get("name", "")).casefold() == brand.casefold():
            keywords = [str(k).casefold() for k in entry.get("keywords", [])]
            break
    keywords = sorted(keywords, key=len, reverse=True)
    lowered = registered.casefold()
    if len(lowered) != len(registered):          # casefold đổi độ dài (ß...) làm lệch vị trí: bỏ qua việc tô sáng
        return ""
    for keyword in keywords:
        at = lowered.find(keyword)
        if at >= 0:
            return registered[at:at + len(keyword)]
    best, best_distance = "", _MAX_EDIT + 1
    for keyword in keywords:
        if len(keyword) < _MIN_KEYWORD:
            continue
        for size in (len(keyword), len(keyword) - 1, len(keyword) + 1):
            for start in range(0, len(lowered) - size + 1):
                distance = _levenshtein(lowered[start:start + size], keyword)
                if distance < best_distance:
                    best, best_distance = registered[start:start + size], distance
    return best


def _domain(result: Result, brand: str, rules: Mapping[str, Any]) -> dict[str, Any]:
    """Tên miền thật tách thành các phần: tiền tố (nhạt), tên miền đăng ký (đậm), phần còn lại (nhạt)."""
    empty: dict[str, Any] = {"userinfo": "", "prefix": "", "decoyPrefix": False, "registered": "", "rest": "",
                             "hit": "", "punycode": "", "isIp": False}
    raw = result.final_url or result.url
    try:
        url = parse_url(raw)
    except URLParseError:
        return {**empty, "registered": _truncate(sanitize_for_display(raw), _RAW_LIMIT)}
    rest = (f":{url.port}" if url.port is not None else "") + url.path + (f"?{url.query}" if url.query else "")
    userinfo = _truncate(sanitize_for_display(url.username), _USERINFO_LIMIT) + "@" if url.username else ""
    base = {**empty, "userinfo": userinfo, "rest": "" if rest == "/" else _truncate(sanitize_for_display(rest), _REST_LIMIT)}
    if url.host_kind != "domain":
        return {**base, "registered": url.host, "isIp": True}
    domain = result.display_domain or url.host
    prefix = url.host[: -len(domain)] if url.host.endswith("." + domain) else ""
    registered = sanitize_for_display(domain_to_unicode(domain))
    codes = {str(s.get("code", "")) for s in result.signals}
    hit = brand_hit(registered, brand, rules) if brand and codes & _IMPERSONATION else ""
    return {**base, "registered": registered, "punycode": domain if registered != domain else "", "hit": hit,
            "prefix": sanitize_for_display(domain_to_unicode(prefix.rstrip("."))) + "." if prefix else "",
            "decoyPrefix": bool(prefix and brand)}


def _positive(signals: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Dấu hiệu có điểm dương, mạnh nhất trước (cùng điểm giữ thứ tự của engine)."""
    return sorted((s for s in signals if int(s.get("points", 0)) > 0), key=lambda s: -int(s.get("points", 0)))


def shield_headline(result: Result, lang: str = "vi") -> str:
    """MỘT câu kết luận: danh sách đen, kịch bản tổ hợp, dấu hiệu riêng mạnh nhất, rồi câu mặc định theo mức."""
    table = plain.HEADLINES["vi" if lang == "vi" else "en"]
    ordered = _positive(result.signals)
    present = {str(s.get("code", "")) for s in ordered}
    level = result.level if result.level in _LEVELS else "WARN"
    if result.tier_reached == 0:
        return str(table["single"]["unparseable"])
    if level == "BLOCKED" and "blacklist" in present:
        return str(table["single"]["blacklist"])
    for groups, text in zip(plain.combo_groups(), table["combos"], strict=True):
        if all(group & present for group in groups):
            matched = frozenset().union(*(group & present for group in groups))
            brand = next((str(s["brand"]) for s in ordered if str(s.get("code", "")) in matched and s.get("brand")),
                         table["brand"])
            return str(text).replace(plain.BRAND, brand)
    for signal in ordered:
        text = table["single"].get(str(signal.get("code", "")))
        if text is not None:
            return str(text).replace(plain.BRAND, str(signal.get("brand") or "") or table["brand"])
    return str(table["default"][level])


def shield_details(result: Result, lang: str = "vi") -> list[dict[str, str]]:
    """Tối đa ``plain.MAX_DETAILS`` gạch đầu dòng ngắn (biểu tượng + một câu) cho mục "Xem vì sao"."""
    lang = "vi" if lang == "vi" else "en"
    specs = plain.DETAILS[lang]
    default_brand = plain.HEADLINES[lang]["brand"]
    rows: list[dict[str, str]] = []
    for signal in _positive(result.signals):
        spec = specs.get(str(signal.get("code", "")))
        if spec is None:
            continue
        text = spec["text"]
        pattern = spec.get("pattern")
        if pattern:
            found = re.search(pattern, str(signal.get("reason", "")))
            if found is not None:
                text = text.replace("{0}", sanitize_for_display(found.group(1)))
            elif "fallback" in spec:
                text = spec["fallback"]
            else:
                continue
        brand = str(signal.get("brand") or "") or default_brand
        rows.append({"icon": spec["icon"], "text": text.replace(plain.BRAND, brand)})
        if len(rows) == plain.MAX_DETAILS:
            break
    return rows


def _defang(domain: str) -> str:
    """Viết tên miền để không thành link bấm được khi dán vào tin nhắn: ``a.top`` → ``a[.]top``."""
    return domain.replace(".", "[.]")


def shield_view(result: Result, checking: bool, rules: Mapping[str, Any], lang: str = "en") -> dict[str, Any]:
    """Dữ liệu cho màn hình cảnh báo kiểu mới.

    Args:
        result: Kết quả đang hiển thị.
        checking: Tầng 3 còn chạy nền (giao diện hiện dòng "Đang xác minh tuổi tên miền…").
        rules: Bộ luật (tra tên miền chính thức và từ khóa của thương hiệu bị giả danh).
        lang: ``"en"`` hoặc ``"vi"`` (tiện ích chỉ có ``"vi"``).
    """
    lang = "vi" if lang == "vi" else "en"
    labels = plain.LABELS[lang]
    level = result.level if result.level in _LEVELS else "WARN"
    brand = brand_of(result.signals)
    official = official_domain(brand, rules) if brand else ""
    domain = {**_domain(result, brand, rules), "brand": brand, "official": official}
    shown = str(domain["registered"]) or labels["unknown"]
    return {
        "lang": lang,
        "level": level,
        "levelLabel": plain.LEVELS[lang][level]["label"],
        "headline": shield_headline(result, lang),
        "reasonShort": plain.LEVELS[lang][level]["sub"],
        "domain": domain,
        "officialLine": labels["official"].replace("{brand}", brand).replace("{domain}", official) if official else "",
        "details": shield_details(result, lang),
        "checking": bool(checking),
        "actions": {
            "back": labels["back"], "proceed": labels["proceed"], "copy": labels["copy"], "report": labels["report"],
            "copied": labels["copied"], "reported": labels["reported"], "hint": labels["hint"],
            "copyText": sanitize_for_display(result.final_url or result.url),
            "reportText": labels["report_text"].replace("{domain}", _defang(shown)),
        },
        "labels": {"caption": labels["caption"], "why": labels["why"], "checking": labels["checking"],
                   "proceedWait": labels["proceed_wait"], "decoy": labels["decoy"], "ip": labels["ip"]},
    }
