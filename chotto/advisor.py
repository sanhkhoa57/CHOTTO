"""AI's Advices (chế độ riêng tư 100%): lời khuyên sinh cục bộ từ các tín hiệu, KHÔNG gửi dữ liệu ra ngoài.

Hiện là bộ tư vấn dựa trên luật. Lời khuyên ưu tiên theo **tổ hợp** dấu hiệu (ví dụ mạo danh + hối thúc là
một kịch bản cụ thể, cần lời khuyên cụ thể), rồi mới đến từng dấu hiệu riêng lẻ. Có thể thay bằng mô hình
ngôn ngữ chạy cục bộ bằng cách giữ nguyên chữ ký ``advise(result) -> str``.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from .engine import Result

__all__ = ["COMBOS", "COMBOS_EN", "GENERAL", "GENERAL_EN", "TIPS", "TIPS_EN", "advise", "advise_signals"]

_BRAND_PLACEHOLDER: Final[str] = "{brand}"
_DEFAULT_BRAND: Final[str] = "thương hiệu này"
_MAX_TIPS: Final[int] = 2

TIPS: Final[dict[str, str]] = {
    "blacklist": "Trang này đã bị cộng đồng báo cáo là lừa đảo. Đừng nhập bất kỳ thông tin nào và hãy báo cho người gửi biết.",
    "combosquat": "Đừng đăng nhập qua link trong tin nhắn. Hãy tự mở ứng dụng hoặc gõ địa chỉ chính thức của {brand}.",
    "homoglyph": "Địa chỉ này giả dạng {brand} bằng ký tự nhìn giống nhau. Hãy kiểm tra từng chữ cái trong tên miền.",
    "typosquat": "Tên miền gần giống {brand} nhưng sai vài ký tự, đây là chiêu giả mạo phổ biến.",
    "lure": "Các từ như “khóa tài khoản”, “phạt nguội”, “hoàn thuế” thường dùng để tạo cảm giác khẩn cấp. "
            "Hãy bình tĩnh và xác minh qua kênh chính thức.",
    "tld": "Đuôi tên miền giá rẻ thường được kẻ lừa đảo đăng ký hàng loạt.",
    "raw_ip": "Dịch vụ thật hiếm khi dùng địa chỉ IP trần. Không nhập thông tin cá nhân vào trang này.",
    "at_sign": "Phần đứng trước ký tự @ không phải trang đích thật. Đừng mở link này.",
    "shortener": "Link rút gọn che đích đến thật. Hãy hỏi người gửi địa chỉ đầy đủ.",
    "nested_redirect": "Liên kết được bọc nhiều lớp chuyển hướng để giấu trang đích. Đừng mở nếu không chắc chắn.",
    "redirect_via_trusted": "Liên kết mượn một trang uy tín để chuyển hướng bạn sang trang khác. Hãy xem kỹ trang đích.",
    "brand_in_path": "Tên ngân hàng/dịch vụ xuất hiện ở phần sau của địa chỉ chỉ để đánh lừa; trang thật nằm ở phần tên miền đứng trước.",
    "http": "Trang không mã hóa, thông tin nhập vào có thể bị đọc trộm.",
    "port": "Trang dùng cổng mạng lạ, dấu hiệu của máy chủ dựng tạm.",
    "idn": "Tên miền chứa ký tự Unicode có thể trông giống hệt chữ Latin. Hãy gõ tay địa chỉ chính thức.",
    "entropy": "Tên miền kiểu chuỗi ngẫu nhiên thường do công cụ tự sinh cho chiến dịch lừa đảo.",
    "hyphens": "Nhiều dấu gạch ngang là đặc điểm của tên miền ghép để giả mạo.",
    "digits": "Tên miền chứa nhiều chữ số ngẫu nhiên, thường thấy ở trang lừa đảo dựng hàng loạt.",
    "free_hosting": "Trang được dựng trên nền tảng miễn phí, ngân hàng và cơ quan nhà nước không dùng loại địa chỉ này.",
    "age": "Tên miền vừa được đăng ký gần đây; trang lừa đảo thường chỉ sống vài ngày.",
    "unparseable": "Liên kết có định dạng bất thường. Hãy hỏi lại người gửi trước khi mở.",
}
_IMPERSONATION: Final[frozenset[str]] = frozenset({"combosquat", "homoglyph", "typosquat"})
_REDIRECTS: Final[frozenset[str]] = frozenset({"redirect_via_trusted", "nested_redirect"})

# Tổ hợp theo thứ tự ưu tiên: (nhóm dấu hiệu phải có — mỗi nhóm cần ít nhất một mã —, lời khuyên).
COMBOS: Final[tuple[tuple[tuple[frozenset[str], ...], str], ...]] = (
    ((_IMPERSONATION, frozenset({"age"})),
     ("Trang giả {brand} trên một tên miền vừa đăng ký vài ngày: gần như chắc chắn là lừa đảo. "
      "Tuyệt đối không đăng nhập hay nhập mã OTP.")),
    ((_IMPERSONATION, frozenset({"lure"})),
     ("Đây là kịch bản quen thuộc: giả danh {brand} rồi hối thúc bạn xử lý gấp. {brand} không yêu cầu "
      "xác nhận hay mở khóa qua link; hãy gọi tổng đài in trên thẻ hoặc mở ứng dụng chính thức.")),
    ((_IMPERSONATION, frozenset({"free_hosting"})),
     "{brand} không bao giờ đặt trang đăng nhập trên nền tảng tạo web miễn phí. Đây là trang giả."),
    ((_IMPERSONATION, _REDIRECTS),
     "Liên kết đi vòng qua một trang uy tín rồi mới tới trang giả {brand}, để qua mặt bạn và bộ lọc."),
    ((frozenset({"shortener"}), frozenset({"lure"})),
     ("Link rút gọn đi kèm lời hối thúc: kẻ gian che địa chỉ thật để bạn không kịp nhận ra. "
      "Hãy hỏi người gửi địa chỉ đầy đủ qua một kênh khác.")),
    ((frozenset({"raw_ip", "port"}), frozenset({"lure", "http"})),
     "Trang đặt trên máy chủ dựng tạm (địa chỉ IP hoặc cổng lạ), không mã hóa. Không nhập bất kỳ thông tin nào."),
)

GENERAL: Final[str] = (
    "Ngân hàng, cơ quan nhà nước không yêu cầu cung cấp OTP, mật khẩu hay CCCD qua đường link trên Zalo. "
    "Nếu nghi ngờ, hãy gọi hotline chính thức hoặc hỏi người thân trước khi bấm."
)

# Bản tiếng Anh cho giao diện HTML (cùng mã, cùng thứ tự ưu tiên với bản tiếng Việt ở trên).
_DEFAULT_BRAND_EN: Final[str] = "this brand"
TIPS_EN: Final[dict[str, str]] = {
    "blacklist": "This page has been reported as a scam. Don't enter any information, and let the sender know.",
    "combosquat": "Don't sign in through a link in a message. Open the app yourself or type the official {brand} address.",
    "homoglyph": "This address imitates {brand} with look-alike characters. Check every letter of the domain.",
    "typosquat": "The domain is almost {brand} but a few characters off, a common impersonation trick.",
    "lure": "Words like “account locked”, “traffic fine” or “tax refund” are used to create panic. "
            "Stay calm and verify through an official channel.",
    "tld": "Cheap domain endings are often registered in bulk by scammers.",
    "raw_ip": "Real services rarely use a bare IP address. Don't enter personal details on this page.",
    "at_sign": "Everything before the @ sign is not the real destination. Don't open this link.",
    "shortener": "A short link hides where it really goes. Ask the sender for the full address.",
    "nested_redirect": "The link is wrapped in several redirects to hide the destination. Don't open it unless you're sure.",
    "redirect_via_trusted": "The link borrows a trusted site to send you somewhere else. Look closely at the destination.",
    "brand_in_path": "The bank or service name appears later in the address only to mislead you; the real site is the domain before it.",
    "http": "The page isn't encrypted, so anything you type can be read by others.",
    "port": "The page uses an unusual network port, a sign of a makeshift server.",
    "idn": "The domain contains Unicode characters that can look exactly like Latin letters. Type the official address yourself.",
    "entropy": "Random-looking domains are usually generated by tools for scam campaigns.",
    "hyphens": "Many hyphens are typical of domains stitched together to impersonate a brand.",
    "digits": "The domain has many random digits, common on scam pages built in bulk.",
    "free_hosting": "The page is built on a free platform; banks and government agencies never use addresses like this.",
    "age": "The domain was registered very recently; scam pages usually live only a few days.",
    "unparseable": "The link has an unusual format. Ask the sender before opening it.",
}
_COMBOS_EN_TEXT: Final[tuple[str, ...]] = (
    "A fake {brand} page on a domain registered a few days ago: almost certainly a scam. Never sign in or enter an OTP code.",
    "A familiar script: pretend to be {brand}, then rush you. {brand} never asks you to confirm or unlock anything "
    "through a link; call the number on your card or open the official app.",
    "{brand} never puts its sign-in page on a free website builder. This page is fake.",
    "The link detours through a trusted site before reaching a fake {brand} page, to fool you and the filters.",
    "A short link plus pressure to act fast: the scammer hides the real address so you don't notice. "
    "Ask the sender for the full address through another channel.",
    "The page runs on a makeshift server (bare IP or odd port) without encryption. Don't enter any information.",
)
COMBOS_EN: Final[tuple[tuple[tuple[frozenset[str], ...], str], ...]] = tuple(
    (groups, text) for (groups, _), text in zip(COMBOS, _COMBOS_EN_TEXT, strict=True)
)
GENERAL_EN: Final[str] = (
    "Banks and government agencies never ask for OTP codes, passwords or ID numbers through a link on Zalo. "
    "If in doubt, call the official hotline or ask someone you trust before tapping."
)


def _brand_of(signals: list[Mapping[str, Any]], codes: frozenset[str], default: str = _DEFAULT_BRAND) -> str:
    """Tên thương hiệu của dấu hiệu mạnh nhất thuộc ``codes`` (hoặc ``default``)."""
    for signal in signals:
        if str(signal.get("code", "")) in codes and signal.get("brand"):
            return str(signal["brand"])
    return default


def advise_signals(signals: Iterable[Mapping[str, Any]], lang: str = "vi") -> str:
    """Ghép tối đa 2 lời khuyên: tổ hợp dấu hiệu khớp trước, rồi tới dấu hiệu riêng lẻ mạnh nhất.

    Args:
        signals: Các tín hiệu có ``code``, ``points`` và tùy chọn ``brand``.
        lang: ``"vi"`` (mặc định, dùng chung với tiện ích trình duyệt) hoặc ``"en"`` (giao diện HTML).

    Returns:
        Đoạn lời khuyên, luôn kết thúc bằng lời khuyên chung.
    """
    english = lang == "en"
    combos, tips = (COMBOS_EN, TIPS_EN) if english else (COMBOS, TIPS)
    default_brand = _DEFAULT_BRAND_EN if english else _DEFAULT_BRAND
    ordered = sorted((s for s in signals if int(s.get("points", 0)) > 0), key=lambda s: -int(s.get("points", 0)))
    present = {str(s.get("code", "")) for s in ordered}
    covered: set[str] = set()
    parts: list[str] = []
    for groups, text in combos:
        if len(parts) == _MAX_TIPS:
            break
        if all(group & present for group in groups) and not all(group & present <= covered for group in groups):
            matched = frozenset().union(*(group & present for group in groups))
            parts.append(text.replace(_BRAND_PLACEHOLDER, _brand_of(ordered, matched, default_brand)))
            covered |= matched
    for signal in ordered:
        if len(parts) == _MAX_TIPS:
            break
        code = str(signal.get("code", ""))
        tip = tips.get(code)
        if tip is None or code in covered:
            continue
        covered.add(code)
        brand = str(signal.get("brand") or "") or default_brand
        parts.append(tip.replace(_BRAND_PLACEHOLDER, brand))
    parts.append(GENERAL_EN if english else GENERAL)
    return " ".join(parts)


def advise(result: Result) -> str:
    """Lời khuyên cục bộ cho một kết quả thẩm định."""
    return advise_signals(result.signals)
