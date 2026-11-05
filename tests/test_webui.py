"""Kiểm thử giao diện HTML: dữ liệu hiển thị, giao thức agent ↔ ui-host, host (với pywebview giả) và đường lùi về Tk."""
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ.setdefault("CHOTTO_DATA_DIR", tempfile.mkdtemp(prefix="chotto-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chotto import logdb  # noqa: E402
from chotto.config import DEFAULTS, friction_seconds_for, load_rules  # noqa: E402
from chotto.engine import Engine, Result, analysis_failed_result  # noqa: E402
from chotto.service.webui import WebUI, WebUIError  # noqa: E402
from chotto.viewmodel import friction_view, reason_text, url_parts  # noqa: E402
from chotto.webhost import FrictionApi, Host, Wire, _blacklist_text  # noqa: E402

RULES = load_rules()


def inspect(url: str) -> Result:
    return Engine(dict(DEFAULTS), RULES, age_lookup=lambda h: None).inspect(url)


def seconds_for(level: str) -> int:
    return friction_seconds_for(level, 5)


def no_pump() -> None:
    return None


def view_of(result: Result, checking: bool) -> dict[str, Any]:
    return friction_view(result, checking, RULES)


def view_of_vi(result: Result) -> dict[str, Any]:
    return friction_view(result, False, RULES, "vi")


class LanguageConfigTests(unittest.TestCase):
    def test_default_and_validation(self) -> None:
        from chotto.config import validate_config

        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.assertEqual(DEFAULTS["ui_language"], "en")
        self.assertEqual(validate_config({"ui_language": "vi"})["ui_language"], "vi")
        self.assertEqual(validate_config({"ui_language": "fr"})["ui_language"], "en")
        self.assertEqual(validate_config({"ui_language": 1})["ui_language"], "en")


class ViewModelTests(unittest.TestCase):
    def test_brand_on_subdomain_is_marked_as_decoy(self) -> None:
        view = friction_view(inspect("https://vietcombank.com.vn.xacthuc-tk.top/dang-nhap"), False, RULES, "vi")
        kinds = [(p["text"], p["kind"]) for p in view["parts"]]
        self.assertIn(("vietcombank.com.vn.", "decoy"), kinds)
        self.assertIn(("xacthuc-tk.top", "real"), kinds)
        self.assertEqual(view["brand"], "Vietcombank")
        self.assertEqual(view["official"], "vietcombank.com.vn")
        self.assertEqual(view["title"], "Đây là trang giả.")
        self.assertEqual(view["lang"], "vi")

    def test_english_is_the_default(self) -> None:
        view = friction_view(inspect("https://vietcombank.com.vn.xacthuc-tk.top/khoa-tai-khoan"), False, RULES)
        self.assertEqual(view["lang"], "en")
        self.assertEqual(view["title"], "This is a fake page.")
        self.assertIn("disguise", [p["label"] for p in view["parts"]])
        self.assertIn("Contains an alarming keyword: “khóa tài khoản”", view["reasons"])
        self.assertIn("The .top ending is often abused for scams", view["reasons"])
        self.assertTrue(view["advice"].startswith("A familiar script: pretend to be Vietcombank"))
        self.assertTrue(view["general"].startswith("Banks and government agencies"))

    def test_english_reasons_follow_engine_order_and_count(self) -> None:
        for url in ("http://user@192.168.1.5:8080/x", "https://vcbdigibank.weebly.com/", "https://bit.ly/3abc",
                    "https://vcb-digibanks.top/xac-nhan", "https://xn--vietcmbank-y8a.com/"):
            result = inspect(url)
            english = friction_view(result, False, RULES, "en")["reasons"]
            vietnamese = friction_view(result, False, RULES, "vi")["reasons"]
            self.assertEqual(vietnamese, result.reasons, url)
            self.assertEqual(len(english), len(vietnamese), url)
            for text in english:     # không lẫn tiếng Việt, trừ từ khóa trích nguyên văn trong “ ” (từ có trong link)
                unquoted = re.sub(r"“[^”]*”", "", text)
                self.assertNotRegex(unquoted, "[ạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹđ]", url)

    def test_untranslated_code_keeps_engine_text(self) -> None:
        self.assertEqual(reason_text({"code": "new_signal", "reason": "Lý do mới"}, "en"), "Lý do mới")
        self.assertEqual(reason_text({"code": "tld", "reason": "định dạng lạ"}, "en"), "định dạng lạ")

    def test_english_advice_tables_cover_vietnamese_ones(self) -> None:
        from chotto import advisor

        self.assertEqual(set(advisor.TIPS_EN), set(advisor.TIPS))
        self.assertEqual([groups for groups, _ in advisor.COMBOS_EN], [groups for groups, _ in advisor.COMBOS])
        signals = [{"code": "shortener", "points": 20}, {"code": "lure", "points": 15}]
        self.assertTrue(advisor.advise_signals(signals).startswith("Link rút gọn"))        # mặc định vẫn tiếng Việt
        self.assertTrue(advisor.advise_signals(signals, "en").startswith("A short link plus pressure"))

    def test_userinfo_ip_and_port_are_labelled(self) -> None:
        parts = url_parts(inspect("http://user@192.168.1.5:8080/x"), lang="vi")
        self.assertEqual([p["kind"] for p in parts], ["dim", "decoy", "real", "dim", "dim"])
        self.assertEqual(parts[2]["label"], "địa chỉ IP, không phải tên miền")
        self.assertEqual(url_parts(inspect("http://user@192.168.1.5:8080/x"))[2]["label"], "an IP address, not a domain")

    def test_idn_shows_both_forms(self) -> None:
        parts = url_parts(inspect("https://xn--vietcmbank-y8a.com/"))
        target = next(p for p in parts if p["kind"] in ("real", "warnpart"))
        self.assertIn("xn--vietcmbank-y8a.com", target["label"])
        self.assertNotIn("xn--", target["text"])

    def test_unparseable_link_is_one_plain_part(self) -> None:
        view = friction_view(analysis_failed_result("https://exa mple.com/%%"), False, RULES, "vi")
        self.assertEqual(view["title"], "Chotto không đọc được link này.")
        self.assertEqual(len(view["parts"]), 1)
        self.assertEqual(view["level"], "WARN")

    def test_checking_hides_advice_like_the_tk_screen(self) -> None:
        result = inspect("https://vcb-digibanks.top/xac-nhan")
        self.assertTrue(result.advice)
        self.assertEqual(friction_view(result, True, RULES)["advice"], "")
        self.assertTrue(friction_view(result, True, RULES)["checking"])


FAKE_HOST = textwrap.dedent("""
    import json, sys, time
    mode = sys.argv[1]
    if mode == "exit":
        sys.exit(3)
    print(json.dumps({"op": "ready", "pid": 1}), flush=True)
    for line in sys.stdin:
        msg = json.loads(line)
        if msg["op"] == "quit":
            break
        if mode == "die":
            sys.exit(1)
        if msg["op"] == "friction" and msg["payload"]["view"]["checking"]:
            continue                                   # chờ bản cập nhật Tầng 3 rồi mới quyết định
        if msg["op"] in ("friction", "update"):
            proceed = msg["op"] == "update"
            print(json.dumps({"op": "decision", "id": msg["id"], "proceed": proceed, "dwell_ms": 1234}), flush=True)
        if msg["op"] == "settings":
            print(json.dumps({"op": "settings_closed"}), flush=True)
""")


class WebUIProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.script = Path(tmp.name) / "fake_host.py"
        self.script.write_text(FAKE_HOST, "utf-8")

    def web(self, mode: str) -> WebUI:
        web = WebUI(argv=lambda: [sys.executable, str(self.script), mode], ready_timeout=10)
        self.addCleanup(web.stop)
        return web

    def test_decision_comes_back(self) -> None:
        result = inspect("https://vcb-digibanks.top/xac-nhan")
        proceed, dwell_ms, shown = self.web("ok").present(view_of, result, seconds_for, None, no_pump)
        self.assertFalse(proceed)
        self.assertEqual(dwell_ms, 1234)
        self.assertIs(shown, result)

    def test_tier3_result_is_pushed_and_returned(self) -> None:
        preliminary = inspect("https://vcb-digibanks.top/xac-nhan")
        final = inspect("https://vietcombank.com.vn.xacthuc-tk.top/dang-nhap")
        pending: Future[Result] = Future()
        threading.Timer(0.3, lambda: pending.set_result(final)).start()
        proceed, _, shown = self.web("ok").present(view_of, preliminary, seconds_for, pending, no_pump)
        self.assertTrue(proceed)
        self.assertIs(shown, final)

    def test_host_that_cannot_start_raises_and_gives_up(self) -> None:
        web = self.web("exit")
        result = inspect("https://vcb-digibanks.top/xac-nhan")
        for _ in range(3):
            with self.assertRaises(WebUIError):
                web.present(view_of, result, seconds_for, None, no_pump)
        self.assertFalse(web.start())             # sau 3 lần chết liên tiếp: dùng Tk cho phiên này

    def test_host_dying_mid_screen_raises(self) -> None:
        with self.assertRaises(WebUIError):
            self.web("die").present(view_of, inspect("https://vcb-digibanks.top/x"), seconds_for, None, no_pump)

    def test_settings_window_state(self) -> None:
        web = self.web("ok")
        self.assertTrue(web.open_settings(no_pump))
        deadline = time.monotonic() + 5
        while web.settings_open and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(web.settings_open)

    def test_build_handler_falls_back_to_tk(self) -> None:
        from chotto.service.app import build_handler

        result = inspect("https://vcb-digibanks.top/xac-nhan")
        handler = build_handler(dict(DEFAULTS), root=object(), web=self.web("exit"))  # type: ignore[arg-type]
        with patch("chotto.ui.show_friction", return_value=(False, 7, result)) as tk_screen:
            self.assertEqual(handler.present(result, seconds_for, None), (False, 7, result))
        tk_screen.assert_called_once()


class _Events:
    def __init__(self) -> None:
        self.handlers: list[Any] = []

    def __iadd__(self, handler: Any) -> "_Events":
        self.handlers.append(handler)
        return self

    def fire(self) -> None:
        for handler in self.handlers:
            handler()


class _Window:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.destroyed = False
        self.native = None
        self.js: list[str] = []
        self.events = type("E", (), {})()
        self.events.closed = _Events()
        self.events.shown = _Events()
        self.events.loaded = _Events()

    def destroy(self) -> None:
        if not self.destroyed:
            self.destroyed = True
            self.events.closed.fire()

    def evaluate_js(self, script: str) -> None:
        self.js.append(script)


class _FakeWebview:
    screens: list[Any] = []

    def __init__(self) -> None:
        self.windows: list[_Window] = []

    def create_window(self, title: str, **kwargs: Any) -> _Window:
        window = _Window(title=title, **kwargs)
        self.windows.append(window)
        return window


class _Out:
    def __init__(self) -> None:
        self.lines: list[dict[str, Any]] = []

    def write(self, text: str) -> None:
        self.lines.extend(json.loads(line) for line in text.splitlines() if line)

    def flush(self) -> None:
        return None


class HostTests(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.out = _Out()
        self.webview = _FakeWebview()
        self.host = Host(Wire(self.out), self.webview, lambda: "")  # type: ignore[arg-type]
        self.payload = {"view": view_of(inspect("https://vcb-digibanks.top/x"), False), "lock_s": 5}

    def api(self) -> FrictionApi:
        api = self.webview.windows[-1].kwargs["js_api"]
        assert isinstance(api, FrictionApi)
        return api

    def decisions(self) -> list[dict[str, Any]]:
        return [line for line in self.out.lines if line["op"] == "decision"]

    def test_open_is_refused_while_locked(self) -> None:
        self.host.dispatch({"op": "friction", "id": 4, "payload": self.payload})
        self.assertEqual(self.api().decide(True), {"ok": False})
        self.assertEqual(self.decisions(), [])
        self.assertEqual(self.api().decide(False), {"ok": True})
        self.assertEqual(len(self.decisions()), 1)
        self.assertFalse(self.decisions()[0]["proceed"])
        self.assertTrue(self.webview.windows[-1].destroyed)
        self.assertEqual(len(self.decisions()), 1)          # sự kiện closed sau quyết định không gửi thêm

    def test_open_allowed_after_lock(self) -> None:
        self.host.dispatch({"op": "friction", "id": 5, "payload": dict(self.payload, lock_s=0)})
        self.assertEqual(self.api().decide(True), {"ok": True})
        self.assertTrue(self.decisions()[0]["proceed"])

    def test_update_extends_lock_and_closing_window_means_cancel(self) -> None:
        self.host.dispatch({"op": "friction", "id": 6, "payload": dict(self.payload, lock_s=0)})
        self.host.dispatch({"op": "update", "id": 6, "payload": dict(self.payload, lock_s=8)})
        self.assertEqual(self.api().decide(True), {"ok": False})
        self.assertIn("CHOTTO.update", self.webview.windows[-1].js[0])
        self.webview.windows[-1].events.closed.fire()       # nút X / Alt+F4
        self.assertFalse(self.decisions()[0]["proceed"])

    def test_quit_cancels_open_screens(self) -> None:
        self.host.dispatch({"op": "friction", "id": 7, "payload": self.payload})
        self.assertFalse(self.host.dispatch({"op": "quit"}))
        self.host.quit()
        self.assertEqual([d["proceed"] for d in self.decisions()], [False])

    def test_blacklist_text(self) -> None:
        now = datetime(2026, 11, 5, 9, 0)
        self.assertIn("hôm nay", _blacklist_text(datetime(2026, 11, 5, 7, 42).timestamp(), now, "vi"))
        self.assertIn("hôm qua", _blacklist_text(datetime(2026, 11, 4, 7, 42).timestamp(), now, "vi"))
        self.assertIn("02/11/2026", _blacklist_text(datetime(2026, 11, 2, 7, 42).timestamp(), now, "vi"))
        self.assertIn("chưa cập nhật", _blacklist_text(None, now, "vi"))
        self.assertEqual(_blacklist_text(datetime(2026, 11, 5, 7, 42).timestamp(), now), "Scam list updated at 07:42 today")

    def test_window_title_follows_language(self) -> None:
        self.host.dispatch({"op": "friction", "id": 8, "payload": self.payload})
        self.assertEqual(self.webview.windows[-1].kwargs["title"], "Chotto · Hold on!")
        vi = {"view": view_of_vi(inspect("https://vcb-digibanks.top/x")), "lock_s": 5}
        self.host.dispatch({"op": "friction", "id": 9, "payload": vi})
        self.assertEqual(self.webview.windows[-1].kwargs["title"], "Chotto · Khoan đã!")


class LogSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {"CHOTTO_DATA_DIR": tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_summary_and_recent(self) -> None:
        safe, high = inspect("https://vnexpress.net/"), inspect("https://vcb-digibanks.top/x")
        logdb.record(safe, "auto_open", 0, "desktop")
        logdb.record(high, "cancel", 900, "desktop")
        logdb.record(high, "proceed", 9000, "desktop")
        logdb.record(high, "cancel", 900, "extension")       # nguồn tiện ích không tính vào Desktop
        self.assertEqual(logdb.summary(7), {"total": 3, "safe": 1, "warned": 2, "closed": 1, "blocked": 0})
        rows = logdb.recent(2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["decision"], "cancel")
        self.assertGreaterEqual(float(rows[0]["ts"]), float(rows[1]["ts"]))  # type: ignore[arg-type]

    def test_broken_database_gives_empty_values(self) -> None:
        with patch("chotto.logdb._connect", side_effect=sqlite3.OperationalError("locked")):
            self.assertEqual(logdb.summary()["total"], 0)
            self.assertEqual(logdb.recent(), [])


if __name__ == "__main__":
    unittest.main()
