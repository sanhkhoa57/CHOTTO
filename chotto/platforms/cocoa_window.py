"""Thủ thuật cửa sổ trên macOS (AppKit qua PyObjC) cho giao diện pywebview. Chỉ được gọi trên macOS.

AppKit chỉ được gọi từ luồng chính, nên mọi thao tác đi qua ``AppHelper.callAfter``.
"""
from __future__ import annotations

import logging
from typing import Any

__all__ = ["activate", "center_on_screen", "reload_on_show"]

_LOG = logging.getLogger("chotto")


def reload_on_show(window: Any, url: str) -> None:
    """Cửa sổ tạo sau khi vòng lặp GUI chạy sẽ ra đen nếu chỉ tải trang lúc tạo: tải lại khi cửa sổ đã hiện."""
    window.events.shown += lambda: window.load_url(url)


def activate(window: Any) -> None:
    """Đưa ứng dụng và cửa sổ lên trước; lỗi thì bỏ qua."""
    try:
        from AppKit import NSApplication  # type: ignore[import-untyped,import-not-found,unused-ignore]
        from PyObjCTools import AppHelper  # type: ignore[import-untyped,import-not-found,unused-ignore]

        def front() -> None:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            if window.native is not None:
                window.native.makeKeyAndOrderFront_(None)

        AppHelper.callAfter(front)
    except Exception:  # noqa: BLE001 - chỉ là tiện ích hiển thị
        _LOG.debug("Không đưa cửa sổ lên trước được (macOS)", exc_info=True)


def center_on_screen(window: Any, width: int, max_height: int, margin: int = 24) -> None:
    """Đặt cửa sổ giữa vùng nhìn thấy (đã trừ thanh menu và Dock) của màn hình chứa con trỏ chuột (đơn vị point)."""
    import AppKit  # type: ignore[import-untyped,import-not-found,unused-ignore]
    from PyObjCTools import AppHelper  # type: ignore[import-untyped,import-not-found,unused-ignore]

    def place() -> None:
        ns_window = window.native
        if ns_window is None:
            return
        mouse = AppKit.NSEvent.mouseLocation()
        screen = next((s for s in AppKit.NSScreen.screens() if AppKit.NSMouseInRect(mouse, s.frame(), False)),
                      None) or ns_window.screen() or AppKit.NSScreen.mainScreen()
        visible = screen.visibleFrame()
        w = min(width, visible.size.width - 2 * margin)
        h = min(max_height, visible.size.height - 2 * margin)
        x = visible.origin.x + (visible.size.width - w) / 2
        y = visible.origin.y + (visible.size.height - h) / 2           # gốc tọa độ macOS ở góc dưới
        ns_window.setFrame_display_(AppKit.NSMakeRect(x, y, w, h), True)

    AppHelper.callAfter(place)
