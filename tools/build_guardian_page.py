#!/usr/bin/env python3
"""Dựng ``guardian/index.html``: trang người giám hộ TĨNH, một file, không gọi mạng.

Trang gộp engine chấm điểm JS của tiện ích (``platforms/extension/src/engine/*``, ``view.js``) + mã mật mã/liên kết của Guardian
(``platforms/extension/src/guardian/codec.js``, ``share.js``) + dữ liệu (``platforms/extension/data/*``) + giao diện (``guardian/src/page.*``) vào MỘT
file HTML. Lý do một file: mở được trực tiếp từ đĩa (module ES bị chặn trên ``file://``), host tĩnh ở đâu cũng được, và có thể ghim
bằng băm SHA-256 trong CSP (``script-src 'sha256-…'``; không cần ``unsafe-inline``). CSP còn đặt ``connect-src 'none'``: trang không
gọi được mạng dù có lỗi.

Không có bước bundler ngoài: các module ES được viết lại thành hàm tự gọi (import → lấy từ bảng module, export → trả về đối tượng).
Chạy: ``python tools/build_guardian_page.py`` (ghi ``guardian/index.html`` và ``guardian/sw.js``);
``--check`` chỉ so sánh với file đang có (dùng trong test: file phải luôn khớp mã nguồn).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
EXT: Final[Path] = ROOT / "platforms" / "extension"
SRC: Final[Path] = ROOT / "guardian" / "src"
OUT_HTML: Final[Path] = ROOT / "guardian" / "index.html"
OUT_SW: Final[Path] = ROOT / "guardian" / "sw.js"

# Thứ tự phụ thuộc: module đứng sau chỉ import module đứng trước.
MODULES: Final[tuple[str, ...]] = (
    "src/engine/punycode.js", "src/engine/url.js", "src/engine/psl.js", "src/engine/util.js", "src/view.js",
    "src/engine/advisor.js", "src/engine/data.js", "src/engine/tier1.js", "src/engine/tier2.js", "src/engine/engine.js",
    "src/guardian/codec.js", "src/guardian/share.js",
)
DATA_FILES: Final[tuple[str, ...]] = (
    "rules.json", "psl.json", "confusables.json", "popular.json", "advice.json", "plain.json", "blacklist.seed.txt", "sync.json",
)

IMPORT_RE: Final = re.compile(r'^import\s+(?P<what>[^;]*?)\s+from\s+"(?P<path>[^"]+)";[ \t]*$', re.M | re.S)
EXPORT_RE: Final = re.compile(r"^export\s+(?:async\s+)?(?:function|class|const|let|var)\s+(?P<name>\w+)", re.M)
JSDOC_RE: Final = re.compile(r"^[ \t]*/\*\*.*?\*/[ \t]*\n", re.M | re.S)
LINE_COMMENT_RE: Final = re.compile(r"^[ \t]*//.*\n", re.M)

CSP_TEMPLATE: Final[str] = (
    "default-src 'none'; script-src 'sha256-{script}'; style-src 'sha256-{style}'; img-src data:; connect-src 'none'; "
    "worker-src 'self'; base-uri 'none'; form-action 'none'"
)


def _module_key(path: str) -> str:
    return Path(path).name.removesuffix(".js")


def convert_module(relative: str) -> str:
    """Viết lại một module ES thành hàm tự gọi gán vào ``__modules[<tên>]``.

    Raises:
        ValueError: Module dùng cú pháp mà bộ chuyển đổi không hiểu (``export default``, ``export {}``, ``import.meta``…).
    """
    text = (EXT / relative).read_text("utf-8").replace("\r\n", "\n")
    for banned in ("export default", "import.meta", "export {", "export *"):
        if banned in text:
            raise ValueError(f"{relative}: không hỗ trợ `{banned}`")
    text = text.replace("// @ts-check\n", "")

    def import_to_const(match: re.Match[str]) -> str:
        what, key = match["what"].strip(), _module_key(match["path"])
        if what.startswith("* as "):
            return f'const {what[5:].strip()} = __modules["{key}"];'
        if what.startswith("{") and what.endswith("}"):
            names = ", ".join(part.strip().replace(" as ", ": ") for part in what[1:-1].split(",") if part.strip())
            return f'const {{ {names} }} = __modules["{key}"];'
        raise ValueError(f"{relative}: import không hiểu được: {what}")

    text = IMPORT_RE.sub(import_to_const, text)
    names = EXPORT_RE.findall(text)
    text = re.sub(r"^export\s+", "", text, flags=re.M)
    text = JSDOC_RE.sub("", text)
    text = LINE_COMMENT_RE.sub("", text)
    body = "\n".join(line.rstrip() for line in text.split("\n") if line.strip())
    exports = ", ".join(names)
    return f'__modules["{_module_key(relative)}"] = (() => {{\n{body}\nreturn {{ {exports} }};\n}})();\n'


def _js_literal(value: str) -> str:
    """Chuỗi JS an toàn khi nhúng trong thẻ <script> (không bao giờ đóng thẻ sớm)."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def build_script() -> str:
    """Toàn bộ JavaScript của trang: bảng module + dữ liệu + giao diện."""
    parts = ['"use strict";', "const __modules = Object.create(null);"]
    parts += [convert_module(path) for path in MODULES]
    data = ",\n".join(f"  {json.dumps(name)}: {_js_literal((EXT / 'data' / name).read_text('utf-8'))}" for name in DATA_FILES)
    parts.append(f"const __data = {{\n{data}\n}};")
    parts.append((SRC / "page.js").read_text("utf-8").replace("\r\n", "\n"))
    return "\n".join(parts)


def sha256_b64(text: str) -> str:
    """Băm SHA-256 (base64) của đúng chuỗi UTF-8 nằm giữa thẻ, dùng cho CSP."""
    return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")


def build_html() -> tuple[str, str]:
    """Trả ``(nội dung index.html, băm script)``."""
    script = "\n" + build_script() + "\n"
    style = "\n" + (SRC / "page.css").read_text("utf-8").replace("\r\n", "\n").strip() + "\n"
    template = (SRC / "page.html").read_text("utf-8").replace("\r\n", "\n")
    csp = CSP_TEMPLATE.format(script=sha256_b64(script), style=sha256_b64(style))
    html = template.replace("__CSP__", csp).replace("__STYLE__", style).replace("__SCRIPT__", script)
    return html, sha256_b64(script)


def build_sw(script_hash: str) -> str:
    """Service worker nhỏ: lưu trang vào bộ nhớ đệm để mở được khi không có mạng (chỉ SW này gọi mạng, để cập nhật trang)."""
    version = re.sub(r"[^A-Za-z0-9]", "", script_hash)[:12]
    return (
        "// Sinh bởi tools/build_guardian_page.py. Chỉ để trang người giám hộ mở được khi mất mạng; không chạm vào localStorage.\n"
        f'const CACHE = "chotto-guardian-{version}";\n'
        "self.addEventListener('install', (event) => {\n"
        "  event.waitUntil(caches.open(CACHE).then((cache) => cache.add(new Request('./', {cache: 'reload'}))).then(() => self.skipWaiting()));\n"
        "});\n"
        "self.addEventListener('activate', (event) => {\n"
        "  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))"
        ".then(() => self.clients.claim()));\n"
        "});\n"
        "self.addEventListener('fetch', (event) => {\n"
        "  const request = event.request;\n"
        "  if (request.method !== 'GET' || request.mode !== 'navigate') return;\n"
        "  event.respondWith(caches.open(CACHE).then(async (cache) => {\n"
        "    const cached = await cache.match('./', {ignoreSearch: true});\n"
        "    const refresh = fetch(request).then((response) => { if (response.ok) cache.put('./', response.clone()); return response; });\n"
        "    if (cached) { refresh.catch(() => undefined); return cached; }\n"
        "    return refresh;\n"
        "  }));\n"
        "});\n"
    )


def main(argv: list[str] | None = None) -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="chỉ kiểm tra file đã dựng có khớp mã nguồn không")
    args = parser.parse_args(argv)
    html, script_hash = build_html()
    sw = build_sw(script_hash)
    if args.check:
        same = (OUT_HTML.read_bytes() == html.encode("utf-8") and OUT_SW.read_bytes() == sw.encode("utf-8"))
        if not same:
            print("guardian/index.html hoặc sw.js không khớp mã nguồn: chạy python tools/build_guardian_page.py", file=sys.stderr)
        return 0 if same else 1
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_bytes(html.encode("utf-8"))
    OUT_SW.write_bytes(sw.encode("utf-8"))
    print(f"Đã ghi {OUT_HTML} ({len(html) // 1024} KB) và {OUT_SW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
