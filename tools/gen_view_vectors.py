#!/usr/bin/env python3
"""Sinh bộ test dùng chung ``tests/data/view_vectors.json``: URL → cấu trúc hiển thị của màn hình cảnh báo (tiếng Việt).

``tests/test_shield.py`` (Python) và ``platforms/extension/tests/view.test.mjs`` (JavaScript) cùng phải tái tạo đúng từng ký tự
cấu trúc ``{headline, domain{registered, rest, ...}, reasonShort, details[], actions}`` này, để Desktop và tiện ích
hiển thị CÙNG chữ, CÙNG thông điệp. URL lấy từ ``engine_vectors.json`` (đã được hai engine khớp nhau), chỉ giữ các
ca không an toàn vì màn hình cảnh báo chỉ hiện cho chúng. Nhãn tĩnh (nút, chú thích) và ``actions`` ngoài
``copyText``/``reportText`` không lặp lại ở từng vector; chúng đến từ ``plain.json`` và được test riêng.

Ví dụ:
  python tools/gen_view_vectors.py           # ghi lại tests/data/view_vectors.json
  python tools/gen_view_vectors.py --check   # chỉ kiểm tra file đang có còn khớp không
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chotto.config import DEFAULTS, load_rules  # noqa: E402
from chotto.engine import Engine  # noqa: E402
from chotto.shield import shield_view  # noqa: E402

ENGINE_VECTORS: Final[Path] = ROOT / "tests" / "data" / "engine_vectors.json"
OUT: Final[Path] = ROOT / "tests" / "data" / "view_vectors.json"


def comparable(view: dict[str, Any]) -> dict[str, Any]:
    """Phần của view đem so sánh từng vector (bỏ nhãn tĩnh lặp lại ở mọi vector)."""
    actions = view["actions"]
    return {**{k: v for k, v in view.items() if k not in ("labels", "actions", "lang")},
            "actions": {"copyText": actions["copyText"], "reportText": actions["reportText"]}}


def build() -> dict[str, Any]:
    """Dựng bộ vector từ ``engine_vectors.json`` bằng engine Python (Tầng 3 tắt, danh sách đen khởi tạo)."""
    rules = load_rules()
    engine = Engine(dict(DEFAULTS, tier3_enabled=False, ai_advice=True), rules=rules)
    try:
        urls = [v["url"] for v in json.loads(ENGINE_VECTORS.read_text("utf-8"))["vectors"] if v["level"] != "SAFE"]
        vectors = [{"url": url, "view": comparable(shield_view(engine.inspect(url), False, rules, "vi"))} for url in urls]
    finally:
        engine.release()
    return {"description": "Sinh bởi tools/gen_view_vectors.py; đừng sửa tay.", "vectors": vectors}


def dump(payload: dict[str, Any]) -> str:
    """JSON gọn, ổn định, giữ nguyên tiếng Việt."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Điểm vào dòng lệnh. Trả 0 nếu thành công/khớp, 1 nếu ``--check`` thấy lệch."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Chỉ kiểm tra, không ghi")
    args = parser.parse_args(argv)
    text = dump(build())
    if args.check:
        current = OUT.read_text("utf-8") if OUT.exists() else ""
        if current != text:
            print("view_vectors.json lệch. Chạy: python tools/gen_view_vectors.py", file=sys.stderr)
            return 1
        print("view_vectors.json khớp.")
        return 0
    OUT.write_text(text, "utf-8", newline="\n")
    print(f"Đã ghi {OUT} ({len(text) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
