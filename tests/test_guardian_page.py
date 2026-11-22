"""Trang người giám hộ (``guardian/index.html``): file dựng phải khớp mã nguồn, CSP chặn mạng, không có API mạng, mã không dính bí mật."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_guardian_page as build  # noqa: E402

HTML = (ROOT / "guardian" / "index.html").read_text("utf-8")
VECTORS = json.loads((ROOT / "tests" / "data" / "guardian_vectors.json").read_text("utf-8"))


def _between(text: str, start: str, end: str) -> str:
    a = text.index(start) + len(start)
    return text[a:text.index(end, a)]


class BuildTests(unittest.TestCase):
    """File dựng sẵn và bộ dựng."""

    def test_built_files_match_sources(self) -> None:
        """``guardian/index.html`` và ``sw.js`` phải đúng là kết quả của bộ dựng (sửa nguồn thì phải dựng lại)."""
        html, script_hash = build.build_html()
        self.assertEqual(HTML, html, "chạy: python tools/build_guardian_page.py")
        self.assertEqual((ROOT / "guardian" / "sw.js").read_text("utf-8"), build.build_sw(script_hash))

    def test_csp_hashes_match_inline_blocks(self) -> None:
        csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', HTML)
        assert csp is not None
        policy = csp.group(1)
        script = _between(HTML, "<script>", "</script>")
        style = _between(HTML, "<style>", "</style>")
        for kind, body in (("script-src", script), ("style-src", style)):
            digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
            self.assertIn(f"{kind} 'sha256-{digest}'", policy)

    def test_csp_blocks_network_and_inline_loopholes(self) -> None:
        policy = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', HTML).group(1)  # type: ignore[union-attr]
        for required in ("default-src 'none'", "connect-src 'none'", "base-uri 'none'", "form-action 'none'"):
            self.assertIn(required, policy)
        for forbidden in ("unsafe-inline", "unsafe-eval", "http:", "https:", "*", "data: ", "frame-src", "child-src"):
            self.assertNotIn(forbidden, policy)
        self.assertEqual(HTML.count("<script"), 1, "đúng một khối script (băm trong CSP)")
        self.assertNotIn("<link", HTML)
        self.assertNotIn(" src=", HTML)
        self.assertNotRegex(HTML, r'\bstyle="')

    def test_no_network_apis_in_page_script(self) -> None:
        script = _between(HTML, "<script>", "</script>")
        for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "EventSource", "importScripts", "indexedDB",
                       "innerHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(banned, script, banned)

    def test_page_holds_no_secret(self) -> None:
        """Trang là mã công khai: không chứa bí mật HMAC thử nghiệm, và không có chỗ nhúng bí mật như ``make-html``."""
        self.assertNotIn(VECTORS["hmac_secret"], HTML)
        self.assertNotIn('"secret": ""', HTML)

    def test_fragment_format_is_documented_in_page_and_share_link(self) -> None:
        script = _between(HTML, "<script>", "</script>")
        self.assertIn("parseShareFragment", script)
        self.assertIn("v=${FRAGMENT_VERSION}&d=", script)

    def test_converter_rejects_unsupported_syntax(self) -> None:
        with self.assertRaises(ValueError):
            self._convert_bad()

    def _convert_bad(self) -> str:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            original = build.EXT
            try:
                build.EXT = Path(tmp)
                (Path(tmp) / "bad.js").write_text("export default 1;\n", "utf-8")
                return build.convert_module("bad.js")
            finally:
                build.EXT = original


if __name__ == "__main__":
    unittest.main()
