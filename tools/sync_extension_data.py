#!/usr/bin/env python3
"""Đồng bộ dữ liệu dùng chung từ ``chotto/data`` sang ``platforms/extension/data`` để Desktop và tiện ích cho cùng kết quả.

Sinh ra:
  - ``rules.json``: bản sao nguyên văn bộ luật (một nguồn sự thật cho cả hai nền tảng);
  - ``psl.json``: Public Suffix List đã tách sẵn thành ba bảng luật (thường, ``*.``, ``!``) với cờ PRIVATE,
    nhãn Unicode đã chuyển sang punycode bằng chính bộ phân tích của bản Desktop;
  - ``popular.json``: tên miền .vn phổ biến (CrUX) đã chuẩn hóa như ``config.load_popular_domains``;
  - ``advice.json``: lời khuyên cục bộ (``chotto.advisor``: TIPS, COMBOS, GENERAL);
  - ``plain.json``: bảng chữ đời thường cho màn hình cảnh báo (``chotto.plain``, bản tiếng Việt);
  - ``src/ui/shield.js`` và ``src/ui/shield-css.js``: giao diện cảnh báo dùng chung với Desktop (``chotto/web/shield.js|css``);
  - ``confusables.json`` và ``blacklist.seed.txt``: bản sao nguyên văn;
  - ``sync.json``: SHA-256 của từng file nguồn, để ``--check`` (và CI) phát hiện dữ liệu tiện ích bị lệch.

Ví dụ:
  python tools/sync_extension_data.py           # ghi lại platforms/extension/data
  python tools/sync_extension_data.py --check   # chỉ kiểm tra, mã thoát 1 nếu lệch
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chotto import __version__, advisor, plain  # noqa: E402
from chotto.config import load_popular_domains, resource_path  # noqa: E402
from chotto.core.psl import PublicSuffixList  # noqa: E402

SOURCES: Final[tuple[str, ...]] = (
    "rules.json",
    "public_suffix_list.dat",
    "popular_vn.txt",
    "confusables_ascii.json",
    "blacklist.seed.txt",
)
DEFAULT_OUT: Final[Path] = ROOT / "platforms" / "extension" / "data"


def _sha256(path: Path) -> str:
    """SHA-256 dạng hex của một file, không phụ thuộc kiểu xuống dòng (CRLF/LF) để Windows và Linux cho cùng kết quả.

    Raises:
        OSError: Không đọc được file.
    """
    crlf, lf = bytes([13, 10]), bytes([10])
    return hashlib.sha256(path.read_bytes().replace(crlf, lf)).hexdigest()


def _dump(data: Any) -> str:
    """JSON gọn, ổn định (khóa sắp xếp) và giữ nguyên tiếng Việt."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def advice_data() -> dict[str, Any]:
    """Lời khuyên cục bộ của ``chotto.advisor`` ở dạng JSON (nhóm mã dấu hiệu đã sắp xếp)."""
    return {
        "tips": dict(advisor.TIPS),
        "combos": [{"groups": [sorted(group) for group in groups], "text": text} for groups, text in advisor.COMBOS],
        "general": advisor.GENERAL,
    }


def ui_outputs() -> dict[str, str]:
    """File giao diện dùng chung với Desktop, ghi vào ``platforms/extension/src/ui`` (nội dung đã chuẩn hóa về xuống dòng LF).

    Returns:
        ``{tên file: nội dung UTF-8}``: ``shield.js`` (bản chép) và ``shield-css.js`` (CSS nhúng thành chuỗi JavaScript,
        vì content script không đọc được file CSS của tiện ích mà không lộ URL tài nguyên cho trang).

    Raises:
        OSError: Thiếu file nguồn.
    """
    web = ROOT / "chotto" / "web"
    script = _read_lf(web / "shield.js")
    css = _read_lf(web / "shield.css")
    header = "// Sinh bởi tools/sync_extension_data.py từ chotto/web/shield.css. Đừng sửa tay.\n"
    css_js = f"globalThis.CHOTTO_SHIELD_CSS = {json.dumps(css, ensure_ascii=False)};\n"
    return {"shield.js": script, "shield-css.js": header + css_js, "app.css": app_css()}


def app_css() -> str:
    """CSS của cửa sổ ứng dụng Desktop (``style.css`` + khối ``<style>`` của ``app.html``) cho trang cài đặt của tiện ích.

    Bỏ phần chỉ Desktop có: mép kéo giãn cửa sổ (``.rz``), tùy chỉnh nhân vật taskbar (``.buddy*``, ``.fold``) và cỡ riêng
    của cửa sổ rộng. Phần riêng của tiện ích (khung điện thoại, Guardian) nằm ở ``options.css`` viết tay.

    Raises:
        OSError: Thiếu file nguồn.
        ValueError: ``app.html`` không còn khối ``<style>``.
    """
    web = ROOT / "chotto" / "web"
    base = _read_lf(web / "style.css")
    match = re.search(r"<style>\n(.*?)</style>", _read_lf(web / "app.html"), re.S)
    if match is None:
        raise ValueError("app.html thiếu khối <style>")
    block = re.sub(r"@media \(prefers-reduced-motion: no-preference\) \{\n  \.fold.*?\n\}\n", "", match.group(1), flags=re.S)
    # Luật Desktop-only có thể trải nhiều dòng: xóa cả khối {...}, không xóa theo từng dòng (dòng lẻ làm hỏng luật kế tiếp).
    block = re.sub(r"^(?:\.rz|\.buddy|#buddyPlaceRow|\.fold)[^{\n]*\{[^}]*\}\n?", "", block, flags=re.M)
    block = re.sub(r" ?\.rz[^{\n]*\{[^}]*\}", "", block)         # các luật .rz còn lại nằm chung một dòng
    block = "\n".join(line for line in block.split("\n")
                      if not re.match(r"@media \(min-width: 560px\)|@media \(prefers-reduced-motion: no-preference\) \{ \.buddy", line))
    header = "/* Sinh bởi tools/sync_extension_data.py từ chotto/web/style.css + app.html. Đừng sửa tay (sửa options.css). */\n"
    return header + base + "\n" + block


def _read_lf(path: Path) -> str:
    """Đọc file UTF-8 và đổi xuống dòng CRLF thành LF (Windows và Linux cho cùng kết quả)."""
    return path.read_bytes().replace(bytes([13, 10]), bytes([10])).decode("utf-8")


def build_outputs() -> dict[str, str]:
    """Nội dung từng file dữ liệu của tiện ích, sinh từ ``chotto/data``.

    Returns:
        ``{tên file: nội dung UTF-8}``.

    Raises:
        OSError: Thiếu file nguồn.
        ValueError: File nguồn hỏng (JSON sai, PSL rỗng).
    """
    data_dir = resource_path("data")
    rules_text = (data_dir / "rules.json").read_text("utf-8")
    rules = json.loads(rules_text)
    if not isinstance(rules, dict):
        raise ValueError("rules.json phải là JSON object")
    psl = PublicSuffixList((data_dir / "public_suffix_list.dat").read_text("utf-8"))
    tables = {
        "exact": {rule: int(private) for rule, private in psl._exact.items()},          # noqa: SLF001
        "wildcard": {rule: int(private) for rule, private in psl._wildcard.items()},    # noqa: SLF001
        "exception": {rule: int(private) for rule, private in psl._exception.items()},  # noqa: SLF001
    }
    confusables = json.loads((data_dir / "confusables_ascii.json").read_text("utf-8"))
    if not isinstance(confusables, dict):
        raise ValueError("confusables_ascii.json phải là JSON object")
    sync_info = {
        "chotto_version": __version__,
        "sources": {name: _sha256(data_dir / name) for name in SOURCES},
    }
    return {
        "rules.json": _dump(rules),
        "psl.json": _dump(tables),
        "popular.json": _dump(sorted(load_popular_domains())),
        "confusables.json": _dump(confusables),
        "advice.json": _dump(advice_data()),
        "plain.json": _dump(plain.plain_data("vi")),
        "blacklist.seed.txt": (data_dir / "blacklist.seed.txt").read_text("utf-8"),
        "sync.json": _dump(sync_info),
    }


def main(argv: list[str] | None = None) -> int:
    """Điểm vào dòng lệnh.

    Returns:
        0 nếu thành công (hoặc dữ liệu đã khớp khi ``--check``), 1 nếu lệch, 2 nếu lỗi đọc/ghi.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Thư mục dữ liệu của tiện ích")
    parser.add_argument("--check", action="store_true", help="Chỉ kiểm tra dữ liệu tiện ích có khớp nguồn không")
    args = parser.parse_args(argv)
    try:
        outputs = build_outputs()
        ui = ui_outputs()
    except (OSError, ValueError) as exc:
        print(f"Lỗi đọc dữ liệu nguồn: {exc}", file=sys.stderr)
        return 2
    out_dir: Path = args.out
    ui_dir = out_dir.parent / "src" / "ui"
    targets = [(out_dir / name, content) for name, content in outputs.items()]
    targets += [(ui_dir / name, content) for name, content in ui.items()]
    if args.check:
        stale = []
        for path, content in targets:
            name = path.name
            try:
                current = path.read_text("utf-8")
            except OSError:
                current = None
            if current != content:
                stale.append(name)
        if stale:
            print("Dữ liệu tiện ích lệch với chotto/data: " + ", ".join(stale), file=sys.stderr)
            print("Chạy: python tools/sync_extension_data.py", file=sys.stderr)
            return 1
        print("Dữ liệu tiện ích khớp với chotto/data.")
        return 0
    try:
        for path, content in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, "utf-8", newline="\n")
    except OSError as exc:
        print(f"Không ghi được {out_dir}: {exc}", file=sys.stderr)
        return 2
    print(f"Đã đồng bộ {len(targets)} file vào {out_dir} và {ui_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
