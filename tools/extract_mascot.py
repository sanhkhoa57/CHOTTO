"""Trích 4 sprite + mask và tham số tô màu từ ``design/chotto_mascot_customizer.html`` vào ``chotto/mascot_assets``.

Chạy lại khi bản thiết kế thay đổi: ``python tools/extract_mascot.py``.
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "design" / "chotto_mascot_customizer.html"
OUT = ROOT / "chotto" / "mascot_assets"


def main() -> int:
    html = SRC.read_text("utf-8")
    match = re.search(r"var D=(\{.*?\});\s*\n", html, re.S)
    if not match:
        print("Không tìm thấy biến D trong", SRC)
        return 1
    data = json.loads(match.group(1))
    rpar = re.search(r"var RPAR=(\[.*?\]);", html, re.S)
    groups = re.search(r"var GROUPS=(\[.*?\]);", html, re.S)
    if not rpar or not groups:
        print("Không tìm thấy RPAR/GROUPS")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for n, pose in enumerate(data["poses"]):
        for key, name in (("img", "pose"), ("mask", "mask")):
            raw = pose[key].split(",", 1)[1]
            (OUT / f"{name}_{n}.png").write_bytes(base64.b64decode(raw))
    swatches = json.loads(groups.group(1).replace("'", '"'))
    palette = {
        "default": data["def"],
        "pivot": data["cm"],
        "params": json.loads(rpar.group(1)),
        "swatches": [g[2] for g in swatches],
    }
    (OUT / "palette.json").write_text(json.dumps(palette, indent=1) + "\n", "utf-8", newline="\n")
    print("Đã ghi", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
