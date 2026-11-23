"""Nhân vật đồng hành trên thanh taskbar: ngủ khi rảnh, chạy dọc taskbar, giật mình và giơ tay "Khoan đã!" khi có
link đáng ngờ.

- ``recolor``: tô màu sprite theo bộ màu người dùng chọn (thuần Pillow, kiểm thử headless được).
- ``brain``: state machine ``sleep`` / ``alert`` / ``run`` / ``stop`` (thuần Python).
- ``taskbar``: cửa sổ overlay trên luồng Tk của agent (Windows; Win32 nằm trong ``chotto.platforms.win32_window``).
- ``assets/``: 4 sprite + mask và ``palette.json`` (trích bằng ``tools/extract_mascot.py``).
"""
from __future__ import annotations

from .brain import ALERT_SECONDS, REST_SECONDS, RUN_SECONDS, Frame, MascotBrain
from .recolor import Palette, load_palette, normalize_colors, recolor_image, recolor_pixels, recolored_poses
from .taskbar import PLACE_FLAG, TaskbarMascot, place_flag_set, set_place_flag, supported

__all__ = [
    "ALERT_SECONDS",
    "PLACE_FLAG",
    "REST_SECONDS",
    "RUN_SECONDS",
    "Frame",
    "MascotBrain",
    "Palette",
    "TaskbarMascot",
    "load_palette",
    "normalize_colors",
    "place_flag_set",
    "recolor_image",
    "recolor_pixels",
    "recolored_poses",
    "set_place_flag",
    "supported",
]
