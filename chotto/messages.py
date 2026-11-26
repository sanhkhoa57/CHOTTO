"""Câu thông báo EN/VI của cửa sổ ứng dụng và các tác vụ (cài, gỡ, cập nhật, xuất nhật ký): một bảng duy nhất.

Thiếu bản tiếng Việt thì dùng bản tiếng Anh. Riêng cài/gỡ bằng tiếng Việt dùng câu chi tiết theo hệ điều hành do
``chotto.platforms`` trả về (hướng dẫn cụ thể cho Windows/macOS), nên không có khóa ``installed``/``uninstalled``
tiếng Việt ở đây.
"""
from __future__ import annotations

from typing import Final

__all__ = ["MESSAGES", "msg"]

MESSAGES: Final[dict[str, dict[str, str]]] = {
    "en": {
        "never": "Built-in scam list, not updated online yet",
        "today": "Scam list updated at {time} today", "yesterday": "Scam list updated at {time} yesterday",
        "date": "Scam list updated on {date}",
        "save_failed": "Couldn't save settings: {error}", "empty": "Paste a link first",
        "check_failed": "Chotto couldn't check this link", "not_link": "This doesn't look like a link",
        "installed": "Done. Chotto now checks links you open from Zalo.",
        "uninstalled": "Done. Links now open directly. Pick your default browser again in system settings.",
        "updated": "Added {count} entries to the scam list.",
        "unchanged": "No new data; the current scam list is kept.",
        "exported": "Exported {count} rows to {path}.",
        "cleared": "Activity log cleared.",
        "failed": "Couldn't finish: {error}", "unknown": "Unknown action",
        "bad_key": "That doesn't look like an API key (no spaces, up to 400 characters)",
        "friction_title": "Chotto · Hold on!",
    },
    "vi": {
        "never": "Danh sách lừa đảo khởi tạo, chưa cập nhật qua mạng",
        "today": "Danh sách lừa đảo cập nhật lúc {time} hôm nay",
        "yesterday": "Danh sách lừa đảo cập nhật lúc {time} hôm qua", "date": "Danh sách lừa đảo cập nhật ngày {date}",
        "save_failed": "Không lưu được cài đặt: {error}", "empty": "Hãy dán một link",
        "check_failed": "Chotto không kiểm tra được link này", "not_link": "Đây không giống một link",
        "updated": "Đã nạp {count} mục vào danh sách đen.",
        "unchanged": ("Không có dữ liệu mới (các nguồn không đổi hoặc không tải được); danh sách hiện tại vẫn được giữ. "
                      "Xem chotto.log để biết chi tiết."),
        "exported": "Đã xuất {count} dòng ra {path}.",
        "cleared": "Đã xóa nhật ký.",
        "failed": "Không thực hiện được: {error}", "unknown": "Tác vụ không hợp lệ",
        "bad_key": "Khóa API không hợp lệ (không có khoảng trắng, tối đa 400 ký tự)",
        "friction_title": "Chotto · Khoan đã!",
    },
}


def msg(lang: str, key: str, **values: object) -> str:
    """Câu thông báo theo ngôn ngữ (thiếu bản tiếng Việt thì dùng bản tiếng Anh)."""
    table = MESSAGES["vi" if lang == "vi" else "en"]
    return table.get(key, MESSAGES["en"][key]).format(**values)
