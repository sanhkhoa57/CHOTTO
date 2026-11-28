"""Guardian Mode ở backend: cấu hình, chốt mở link (agent + tiến trình giao diện) và chốt sửa cài đặt."""
from __future__ import annotations

import io
import json
import logging
import os
import sys
import tempfile
import unittest
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chotto import guardian  # noqa: E402
from chotto.config import DEFAULTS, load_config, save_config, validate_config  # noqa: E402
from chotto.engine import Result, analysis_failed_result  # noqa: E402
from chotto.service.app import build_handler  # noqa: E402
from chotto.service.handler import LinkHandler  # noqa: E402
from chotto.webhost import AppApi, FrictionApi, Wire  # noqa: E402

URL = "https://vi-du.test/dang-nhap"
PIN = "4829"


def setUpModule() -> None:
    logging.disable(logging.CRITICAL)


def tearDownModule() -> None:
    logging.disable(logging.NOTSET)


def result_of(level: str, tier: int = 2) -> Result:
    return replace(analysis_failed_result(URL), level=level, tier_reached=tier)


class _DataDir(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"CHOTTO_DATA_DIR": folder.name})
        env.start()
        self.addCleanup(env.stop)
        save_config(validate_config({}))                 # như bản đã cài: config.json có sẵn, Guardian tắt rõ ràng

    def enable(self, **changes: Any) -> None:
        if not guardian.has_pin():
            guardian.setup(PIN)
            guardian.confirm(PIN)
        save_config({**load_config(), "guardian_enabled": True, **changes})


class ConfigTests(unittest.TestCase):
    def test_defaults_and_validation(self) -> None:
        self.assertEqual((DEFAULTS["guardian_enabled"], DEFAULTS["guardian_warn_policy"], DEFAULTS["guardian_contact"]),
                         (False, "pin", ""))
        bad = validate_config({"guardian_enabled": "yes", "guardian_warn_policy": "mo", "guardian_contact": 5})
        self.assertEqual((bad["guardian_enabled"], bad["guardian_warn_policy"], bad["guardian_contact"]),
                         (False, "pin", ""))
        good = validate_config({"guardian_enabled": True, "guardian_warn_policy": "lock",
                                "guardian_contact": "  Mẹ\n0901 " + "x" * 200})
        self.assertEqual(good["guardian_warn_policy"], "lock")
        self.assertTrue(good["guardian_contact"].startswith("Mẹ0901"))
        self.assertLessEqual(len(good["guardian_contact"]), 80)

    def test_needs_pin(self) -> None:
        on = {**DEFAULTS, "guardian_enabled": True, "friction_seconds": 8}
        self.assertTrue(guardian.needs_pin(DEFAULTS, on))
        self.assertTrue(guardian.needs_pin(on, DEFAULTS))
        for change in ({"guardian_warn_policy": "lock"}, {"guardian_contact": "ai đó"}, {"friction_seconds": 3},
                       {"agent_enabled": False}, {"log_decisions": False}, {"tier3_enabled": False},
                       {"unknown_caller_policy": "forward"}):
            with self.subTest(change=change):
                self.assertTrue(guardian.needs_pin(on, {**on, **change}))
                self.assertFalse(guardian.needs_pin(DEFAULTS, {**DEFAULTS, **change}))
        for harmless in ({"friction_seconds": 15}, {"ui_language": "vi"}, {"ui_theme": "dark"}, {}):
            self.assertFalse(guardian.needs_pin(on, {**on, **harmless}))


class HandlerGateTests(_DataDir):
    def run_link(self, level: str, cfg: dict[str, Any], authorized: bool = False, tier: int = 2,
                 present: Any = None) -> tuple[str, list[str]]:
        """Giao diện (giả) luôn bảo "mở": backend phải tự quyết."""
        opened: list[str] = []
        engine = MagicMock()
        engine.inspect_fast.return_value = (result_of(level, tier), None)

        def say_yes(result: Result, _s: Callable[[str], int], _p: Future[Result] | None) -> tuple[bool, int, Result]:
            return True, 1, result

        handler = LinkHandler(
            cfg=validate_config(cfg), engine_factory=lambda: engine, present=present or say_yes,
            open_url=lambda u: opened.append(u) is None, alert=lambda _m: None, record=lambda *_a: True,
            authorize=lambda: authorized)
        return handler.handle(URL, force=True), opened

    def test_high_and_blocked_are_refused_even_with_pin(self) -> None:
        for level in ("HIGH", "BLOCKED"):
            for warn in ("pin", "lock"):
                outcome, opened = self.run_link(level, {"guardian_enabled": True, "guardian_warn_policy": warn},
                                                authorized=True)
                self.assertEqual((outcome, opened), ("guardian_blocked", []), (level, warn))

    def test_warn_needs_valid_pin(self) -> None:
        cfg = {"guardian_enabled": True}
        self.assertEqual(self.run_link("WARN", cfg, authorized=False), ("guardian_blocked", []))
        outcome, opened = self.run_link("WARN", cfg, authorized=True)
        self.assertEqual((outcome, len(opened)), ("proceed", 1))

    def test_warn_lock_policy_ignores_pin(self) -> None:
        cfg = {"guardian_enabled": True, "guardian_warn_policy": "lock"}
        self.assertEqual(self.run_link("WARN", cfg, authorized=True), ("guardian_blocked", []))

    def test_off_keeps_old_behaviour(self) -> None:
        for level in ("WARN", "HIGH", "BLOCKED"):
            self.assertEqual(self.run_link(level, {})[0], "proceed")

    def test_broken_ui_does_not_open_unparsed_link(self) -> None:
        def broken(*_a: Any) -> Any:
            raise RuntimeError("không có giao diện")

        self.assertEqual(self.run_link("WARN", {"guardian_enabled": True}, tier=0, present=broken),
                         ("ui_failed_blocked", []))
        self.assertEqual(self.run_link("WARN", {}, tier=0, present=broken)[0], "ui_failed_open")


class BuildHandlerTests(_DataDir):
    """``build_handler`` thật: PIN đi kèm quyết định phải được agent kiểm lại."""

    def decide_with(self, level: str, pin: str) -> tuple[str, list[str], dict[str, Any]]:
        opened: list[str] = []
        seen: dict[str, Any] = {}
        engine = MagicMock()
        engine.inspect_fast.return_value = (result_of(level), None)
        web = MagicMock()

        def present(view_of: Any, result: Result, _s: Any, _p: Any, _pump: Any, on_pin: Any = None) -> Any:
            seen.update(view_of(result, False))
            if pin:
                on_pin(pin)
            return True, 1, result

        web.present.side_effect = present
        handler = build_handler(load_config(), None, web)
        handler.engine_factory = lambda: engine
        handler.open_url = lambda u: opened.append(u) is None
        handler.record = lambda *_a: True
        return handler.handle(URL, force=True), opened, seen

    def test_wrong_missing_and_right_pin(self) -> None:
        self.enable(guardian_contact="Mẹ 0901")
        for pin in ("", "0000"):
            self.assertEqual(self.decide_with("WARN", pin)[:2], ("guardian_blocked", []))
        outcome, opened, view = self.decide_with("WARN", PIN)
        self.assertEqual((outcome, len(opened)), ("proceed", 1))
        self.assertEqual(view["guardian"]["policy"], "pin")
        self.assertIn("Mẹ 0901", view["guardian"]["message"])
        self.assertEqual(view["actions"]["copyText"], "")
        self.assertEqual(self.decide_with("HIGH", PIN)[:2], ("guardian_blocked", []))

    def test_no_guardian_view_when_off(self) -> None:
        outcome, _, view = self.decide_with("HIGH", "")
        self.assertEqual(outcome, "proceed")
        self.assertNotIn("guardian", view)
        self.assertNotEqual(view["actions"]["copyText"], "")


class FrictionApiTests(_DataDir):
    def api(self, level: str) -> tuple[FrictionApi, io.StringIO]:
        out = io.StringIO()
        payload = {"view": {"level": level}, "lock_s": 0, "theme": "light"}
        return FrictionApi(1, payload, 0, Wire(out), lambda _i: None), out

    def test_deny(self) -> None:
        self.enable()
        for level in ("HIGH", "BLOCKED"):
            api, out = self.api(level)
            reply = api.decide(True, PIN)
            self.assertEqual((reply["ok"], reply["guardian"]["policy"]), (False, "deny"))
            self.assertEqual(out.getvalue(), "")
            self.assertTrue(api.decide(False)["ok"])

    def test_warn_pin_flow(self) -> None:
        self.enable()
        api, out = self.api("WARN")
        first = api.decide(True)
        self.assertEqual((first["ok"], first["need_pin"], first["guardian"]["policy"]), (False, True, "pin"))
        wrong = api.decide(True, "0000")
        self.assertEqual((wrong["ok"], wrong["auth"]["error"], wrong["auth"]["attempts_left"]), (False, "wrong", 4))
        self.assertEqual(out.getvalue(), "")
        self.assertTrue(api.decide(True, PIN)["ok"])
        message = json.loads(out.getvalue())
        self.assertEqual((message["proceed"], message["pin"]), (True, PIN))

    def test_guardian_turned_on_after_window_opened(self) -> None:
        api, out = self.api("WARN")                      # màn hình mở khi Guardian còn tắt (payload không có guardian)
        self.enable()
        reply = api.decide(True)
        self.assertEqual((reply["ok"], reply.get("need_pin"), reply["guardian"]["policy"]), (False, True, "pin"))
        self.assertEqual(out.getvalue(), "")
        self.assertTrue(api.decide(True, PIN)["ok"])

    def test_decision_carries_shown_level(self) -> None:
        api, out = self.api("WARN")
        self.assertTrue(api.decide(True)["ok"])
        self.assertEqual(json.loads(out.getvalue())["level"], "WARN")

    def test_open_screen_picks_up_guardian(self) -> None:
        api, _out = self.api("WARN")
        api._payload["view"]["actions"] = {"copyText": URL}  # noqa: SLF001
        self.enable()
        api.refresh_guardian()
        view = api.initial()["view"]
        self.assertEqual((view["guardian"]["policy"], view["actions"]["copyText"]), ("pin", ""))

    def test_copy_rechecks_live_policy(self) -> None:
        api, _out = self.api("WARN")
        self.assertTrue(api.copy_allowed()["ok"])
        self.enable()
        denied = api.copy_allowed()
        self.assertEqual((denied["ok"], denied["payload"]["view"]["guardian"]["policy"]), (False, "pin"))
        self.assertEqual(api.initial()["view"]["guardian"]["policy"], "pin")

    def test_partly_broken_policy_while_on_locks(self) -> None:
        self.enable()
        config = Path(os.environ["CHOTTO_DATA_DIR"]) / "config.json"
        raw = json.loads(config.read_text("utf-8"))
        raw["guardian_warn_policy"] = 7
        config.write_text(json.dumps(raw), "utf-8")
        self.assertEqual(load_config()["guardian_warn_policy"], "lock")

    def test_warn_lockout(self) -> None:
        self.enable()
        api, out = self.api("WARN")
        for _ in range(guardian.MAX_FAILURES):
            api.decide(True, "0000")
        reply = api.decide(True, PIN)
        self.assertEqual(reply["auth"]["error"], "locked")
        self.assertEqual(out.getvalue(), "")


class SettingsGateTests(_DataDir):
    def setUp(self) -> None:
        super().setUp()
        self.api = AppApi(MagicMock())

    def test_cannot_enable_without_pin(self) -> None:
        self.assertTrue(self.api.save({"guardian_enabled": True})["need_setup"])
        self.assertFalse(load_config()["guardian_enabled"])

    def test_first_time_flow(self) -> None:
        made = self.api.guardian_setup(PIN)
        self.assertRegex(made["recovery_key"], r"^CHOTTO-")
        self.assertTrue(self.api.save({"guardian_enabled": True}, PIN)["need_setup"])    # chưa tick "đã lưu"
        self.assertTrue(self.api.guardian_confirm(PIN)["ok"])
        self.assertTrue(self.api.save({"guardian_enabled": True}).get("need_pin"))
        self.assertTrue(self.api.save({"guardian_enabled": True}, PIN)["ok"])
        self.assertTrue(load_config()["guardian_enabled"])
        self.assertNotIn(PIN, json.dumps(load_config()))

    def test_protected_changes_need_pin(self) -> None:
        self.enable(friction_seconds=8)
        for patch_values in ({"guardian_enabled": False}, {"guardian_warn_policy": "lock"},
                             {"guardian_contact": "người lạ"}, {"friction_seconds": 3}, {"log_decisions": False},
                             {"guardian_enabled": "rác"}, {"friction_seconds": "rác"}):
            with self.subTest(values=patch_values):
                before = load_config()
                self.assertTrue(self.api.save(patch_values).get("need_pin"))
                self.assertEqual(load_config(), before)
        self.assertFalse(self.api.save({"friction_seconds": 3}, "0000")["ok"])
        self.assertTrue(self.api.save({"friction_seconds": 3}, PIN)["ok"])
        self.assertTrue(self.api.save({"ui_theme": "dark"})["ok"])
        self.assertTrue(self.api.save({"guardian_enabled": False}, PIN)["ok"])

    def test_actions_need_pin(self) -> None:
        self.enable()
        with patch("chotto.service.app.uninstall_action", return_value="đã gỡ") as uninstall, \
                patch("chotto.service.app.clear_log_action", return_value="đã xóa") as clear:
            for name in ("uninstall", "clear_log"):
                self.assertTrue(self.api.action(name).get("need_pin"))
                self.assertTrue(self.api.action(name, "0000").get("need_pin"))
            uninstall.assert_not_called()
            clear.assert_not_called()
            self.assertTrue(self.api.action("uninstall", PIN)["ok"])
            self.assertTrue(self.api.action("clear_log", PIN)["ok"])

    def test_corrupt_file_while_off_can_be_replaced(self) -> None:
        guardian.setup(PIN)
        guardian.confirm(PIN)
        (Path(os.environ["CHOTTO_DATA_DIR"]) / "guardian.bin").write_bytes(b"hong")
        self.assertFalse(self.api.state()["guardian"]["has_pin"])
        self.assertTrue(self.api.save({"guardian_enabled": True}, PIN).get("need_setup"))
        self.assertTrue(self.api.guardian_setup("1111")["ok"])
        self.assertTrue(self.api.guardian_confirm("1111")["ok"])
        self.assertTrue(self.api.save({"guardian_enabled": True}, "1111")["ok"])

    def test_corrupt_file_while_on_stays_locked(self) -> None:
        self.enable()
        (Path(os.environ["CHOTTO_DATA_DIR"]) / "guardian.bin").write_bytes(b"hong")
        self.assertFalse(self.api.guardian_setup("1111")["ok"])
        self.assertFalse(self.api.save({"guardian_enabled": False}, PIN)["ok"])
        self.assertTrue(load_config()["guardian_enabled"])

    def test_corrupt_config_keeps_guardian_on(self) -> None:
        self.enable()
        config = Path(os.environ["CHOTTO_DATA_DIR"]) / "config.json"
        for broken in ("{hỏng", "[]", json.dumps({**json.loads(config.read_text("utf-8")), "guardian_enabled": "no"})):
            with self.subTest(content=broken[:12]):
                config.write_text(broken, "utf-8")
                self.assertTrue(load_config()["guardian_enabled"])
                self.assertEqual(guardian.open_policy(load_config(), "HIGH"), "deny")
        config.write_text("{hỏng", "utf-8")
        (Path(os.environ["CHOTTO_DATA_DIR"]) / "guardian.bin").unlink()
        self.assertFalse(load_config()["guardian_enabled"])       # chưa từng đặt PIN: mặc định như cũ

    def test_save_rechecks_live_config(self) -> None:
        from chotto.service.app import save_settings

        self.enable()                                    # cửa sổ khác vừa bật Guardian: bản chụp cũ không được tắt nó
        self.assertFalse(save_settings({"guardian_enabled": False, "tier3_enabled": False}))
        self.assertTrue(load_config()["guardian_enabled"])
        self.assertTrue(load_config()["tier3_enabled"])
        self.assertTrue(save_settings({"ui_theme": "dark"}))
        self.assertTrue(save_settings({"tier3_enabled": False}, pin_verified=True))

    def test_export_refuses_data_dir(self) -> None:
        from chotto.service.app import export_action

        data = Path(os.environ["CHOTTO_DATA_DIR"])
        before = (data / "config.json").read_bytes()
        for target in (data / "config.json", data / "guardian.bin", data / "sub" / ".." / "x.csv",
                       Path(str(data).upper()) / "config.json"):          # khác chữ hoa/thường (NTFS, APFS)
            with self.subTest(target=str(target)[-20:]), self.assertRaises(OSError):
                export_action(str(target))
        self.assertEqual((data / "config.json").read_bytes(), before)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        with patch("chotto.logdb.export_csv", return_value=0):
            self.assertIn("0", export_action(str(Path(outside.name) / "log.csv"), "en"))

    def test_missing_config_with_pin_keeps_guardian_on(self) -> None:
        self.enable()
        (Path(os.environ["CHOTTO_DATA_DIR"]) / "config.json").unlink()
        self.assertTrue(load_config()["guardian_enabled"])
        self.assertTrue(self.api.save({"guardian_enabled": False}).get("need_pin"))

    def test_setup_writes_config_first(self) -> None:
        (Path(os.environ["CHOTTO_DATA_DIR"]) / "config.json").unlink()
        self.assertTrue(self.api.guardian_setup(PIN)["ok"])
        self.assertTrue(self.api.guardian_confirm(PIN)["ok"])
        self.assertFalse(load_config()["guardian_enabled"])      # đặt PIN chưa phải là bật

    def test_cannot_make_new_pin_after_data_file_is_deleted(self) -> None:
        self.enable()
        (Path(os.environ["CHOTTO_DATA_DIR"]) / "guardian.bin").unlink()
        self.assertFalse(self.api.guardian_setup("1111")["ok"])
        self.assertFalse(self.api.save({"guardian_enabled": False}, "1111")["ok"])
        self.assertTrue(load_config()["guardian_enabled"])


if __name__ == "__main__":
    unittest.main()
