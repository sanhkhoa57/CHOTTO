"""Kiểm thử nhân vật taskbar: cấu hình, state machine, tô màu (chạy headless, không cần Tk/màn hình)."""
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ.setdefault("CHOTTO_DATA_DIR", tempfile.mkdtemp(prefix="chotto-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from chotto import mascot  # noqa: E402
from chotto.config import DEFAULTS, MASCOT_DEFAULT_COLORS, load_config, save_config, validate_config  # noqa: E402
from chotto.mascot import ALERT_SECONDS, REST_SECONDS, RUN_SECONDS, MascotBrain, load_palette, normalize_colors, recolor_pixels  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OTHER = ["#6b3e26", "#3f7fbf", "#7c5239", "#2e4a7d", "#e58fa8", "#7bc6a4"]


class ConfigTest(unittest.TestCase):
    """Khóa ``mascot_enabled`` / ``mascot_colors`` trong ``config.json``."""

    def tearDown(self) -> None:
        save_config(DEFAULTS)

    def test_defaults(self) -> None:
        cfg = validate_config({})
        self.assertFalse(cfg["mascot_enabled"])
        self.assertEqual(cfg["mascot_colors"], list(MASCOT_DEFAULT_COLORS))

    def test_pin_defaults_and_validation(self) -> None:
        cfg = validate_config({})
        self.assertFalse(cfg["mascot_pinned"])
        self.assertEqual(cfg["mascot_pos"], 0.85)
        self.assertEqual(validate_config({"mascot_pos": 7})["mascot_pos"], 1.0)
        self.assertEqual(validate_config({"mascot_pos": -2})["mascot_pos"], 0.0)
        self.assertEqual(validate_config({"mascot_pos": "x"})["mascot_pos"], 0.85)
        self.assertFalse(validate_config({"mascot_pinned": 1})["mascot_pinned"])
        from chotto.service.app import save_settings

        save_settings({"mascot_pinned": True, "mascot_pos": 0.25})
        cfg = load_config()
        self.assertTrue(cfg["mascot_pinned"])
        self.assertEqual(cfg["mascot_pos"], 0.25)

    def test_save_and_load(self) -> None:
        save_config(dict(DEFAULTS, mascot_enabled=True, mascot_colors=[c.upper() for c in OTHER]))
        cfg = load_config()
        self.assertTrue(cfg["mascot_enabled"])
        self.assertEqual(cfg["mascot_colors"], OTHER)               # viết thường lại

    def test_invalid_values_fall_back(self) -> None:
        for bad in (["#fff"] * 6, OTHER[:5], OTHER + ["#000000"], "red", [1, 2, 3, 4, 5, 6], ["#gggggg"] * 6):
            self.assertEqual(validate_config({"mascot_colors": bad})["mascot_colors"], list(MASCOT_DEFAULT_COLORS), bad)
        self.assertFalse(validate_config({"mascot_enabled": "yes"})["mascot_enabled"])

    def test_save_settings_accepts_mascot_keys(self) -> None:
        from chotto.service.app import save_settings

        save_settings({"mascot_enabled": True, "mascot_colors": OTHER, "browser_command": "evil.exe"})
        cfg = load_config()
        self.assertTrue(cfg["mascot_enabled"])
        self.assertEqual(cfg["mascot_colors"], OTHER)
        self.assertEqual(cfg["browser_command"], "")               # khóa không được phép thì không đổi

    def test_defaults_match_assets_and_design(self) -> None:
        self.assertEqual(load_palette().default, MASCOT_DEFAULT_COLORS)
        design = ROOT / "design" / "chotto_mascot_customizer.html"
        if design.exists():                                          # design/ không nằm trong git
            match = re.search(r'"def":(\[[^\]]*\])', design.read_text("utf-8"))
            assert match is not None
            self.assertEqual(tuple(json.loads(match.group(1))), MASCOT_DEFAULT_COLORS)

    def test_normalize_colors(self) -> None:
        self.assertEqual(normalize_colors(OTHER), tuple(OTHER))
        self.assertEqual(normalize_colors(None), MASCOT_DEFAULT_COLORS)


class BrainTest(unittest.TestCase):
    """State machine ``sleep`` / ``run`` / ``alert`` / ``stop``."""

    def brain(self, **kw: Any) -> MascotBrain:
        return MascotBrain(100, 900, rng=random.Random(7), nap_range=(2.0, 2.0), **kw)

    def run_for(self, brain: MascotBrain, seconds: float, step: float = 0.05) -> None:
        for _ in range(round(seconds / step)):
            brain.tick(step)

    def test_idle_then_patrol_in_bursts(self) -> None:
        b = self.brain()
        self.assertEqual((b.state, b.animating), ("sleep", False))
        self.run_for(b, 1.9)
        self.assertEqual(b.state, "sleep")                           # ngủ đủ 2 giây (nap_range của test) mới chạy
        self.run_for(b, 0.2)
        self.assertEqual(b.state, "run")
        self.run_for(b, RUN_SECONDS - 0.2)
        self.assertEqual(b.state, "run")
        self.run_for(b, 0.3)
        self.assertEqual(b.state, "sleep")                           # chạy 3 giây thì ngủ
        self.run_for(b, REST_SECONDS - 0.2)
        self.assertEqual(b.state, "sleep")
        self.run_for(b, 0.4)
        self.assertEqual(b.state, "run")                             # ngủ xong chạy tiếp

    def test_runs_to_the_end_turns_around_and_keeps_going(self) -> None:
        b = MascotBrain(0, 100, unit=1.0, rng=random.Random(2), nap_range=(0.0, 0.0))   # 300 px/s, mỗi nhịp 900 px
        b.drag_to(60)
        b.tick(0.01)
        self.assertEqual(b.state, "run")
        self.assertEqual(b.direction, -1)                            # về mép xa hơn (trái)
        b.tick(0.25)
        self.assertEqual((b.x, b.direction), (0, 1))                 # chạm mép trái thì quay đầu
        for _ in range(4):
            b.tick(0.1)
        self.assertEqual((b.x, b.direction), (100, -1))              # chạm mép phải thì quay đầu

    def test_patrol_covers_both_edges_and_stays_in_bounds(self) -> None:
        b = self.brain()
        seen, flips = [], set()
        for _ in range(2000):
            b.tick(0.05)
            self.assertTrue(100 <= b.x <= 900)
            if b.state == "run":
                seen.append(b.x)
                flips.add(b.direction)
                self.assertEqual(b.frame().flip, b.direction > 0)
        self.assertEqual(flips, {-1, 1})
        self.assertEqual((min(seen), max(seen)), (100, 900))         # có chạm cả hai điểm cuối

    def test_warning_stops_patrol_and_idle_nap_returns(self) -> None:
        b = self.brain()
        self.run_for(b, 2.5)
        self.assertEqual(b.state, "run")
        b.warning_opened()
        self.assertFalse(b.patrol)
        self.run_for(b, ALERT_SECONDS + 0.1)
        b.warning_closed()
        self.assertEqual(b.state, "sleep")
        self.run_for(b, 1.9)
        self.assertEqual(b.state, "sleep")                           # lại ngủ nghỉ dài như lúc rảnh, rồi mới chạy
        self.run_for(b, 0.3)
        self.assertEqual(b.state, "run")

    def test_pinned_never_runs_but_still_reacts_to_warning(self) -> None:
        b = self.brain()
        b.set_pinned(True)
        x = b.x
        self.run_for(b, 100)
        self.assertEqual((b.state, b.x), ("sleep", x))
        b.warning_opened()
        self.run_for(b, ALERT_SECONDS + 0.1)
        self.assertEqual(b.state, "stop")
        b.warning_closed()
        self.assertEqual(b.state, "sleep")
        self.assertEqual(b.x, x)

    def test_pinning_while_running_stops_and_unpin_resumes(self) -> None:
        b = self.brain()
        self.run_for(b, 2.5)
        self.assertEqual(b.state, "run")
        b.set_pinned(True)
        self.assertEqual(b.state, "sleep")
        b.set_pinned(False)
        self.run_for(b, 2.1)
        self.assertEqual(b.state, "run")

    def test_drag_is_clamped(self) -> None:
        b = self.brain()
        b.drag_to(-500)
        self.assertEqual(b.x, 100)
        b.drag_to(5000)
        self.assertEqual(b.x, 900)
        b.drag_to(400)
        self.assertEqual(b.x, 400)

    def test_warning_flow(self) -> None:
        b = self.brain()
        self.run_for(b, 2.5)                                         # đang chạy
        b.warning_opened()
        self.assertEqual(b.state, "alert")
        self.assertEqual(b.frame().pose, 1)
        self.run_for(b, ALERT_SECONDS + 0.05)
        self.assertEqual(b.state, "stop")
        self.run_for(b, 60)                                          # giữ "Khoan đã!" suốt lúc cảnh báo còn mở
        self.assertEqual(b.state, "stop")
        self.assertEqual(b.frame().pose, 3)
        b.warning_closed()
        self.assertEqual(b.state, "sleep")

    def test_closed_during_alert_returns_to_sleep(self) -> None:
        b = self.brain()
        b.warning_opened()
        b.tick(0.2)
        b.warning_closed()
        self.assertEqual(b.state, "alert")                           # diễn nốt cú giật mình
        self.run_for(b, ALERT_SECONDS)
        self.assertEqual(b.state, "sleep")

    def test_second_warning_restarts_alert(self) -> None:
        b = self.brain()
        b.warning_opened()
        self.run_for(b, 2)
        b.warning_opened()
        self.assertEqual((b.state, b.t), ("alert", 0.0))

    def test_reduced_motion(self) -> None:
        b = self.brain(reduced_motion=True)
        x = b.x
        self.run_for(b, 30)
        self.assertEqual(b.state, "sleep")                           # không chạy qua lại
        self.assertEqual(b.x, x)
        b.warning_opened()
        b.tick(0.1)
        frame = b.frame()
        self.assertEqual((frame.dx, frame.dy, frame.sx, frame.sy), (0.0, 0.0, 1.0, 1.0))


class RecolorTest(unittest.TestCase):
    """Thuật toán tô màu liên tục (port từ bản thiết kế)."""

    P = load_palette()

    @staticmethod
    def px(*rgba: int) -> bytes:
        return bytes(rgba)

    def one(self, rgba: tuple[int, int, int, int], mask: tuple[int, int, int, int], colors: list[str]) -> tuple[int, ...]:
        return tuple(recolor_pixels(bytes(rgba), bytes(mask), colors, self.P))

    def test_default_colors_keep_original(self) -> None:
        data = bytes(random.Random(3).randrange(256) for _ in range(4000))
        mask = bytes((i % 7, 0, 0, 255)[i % 4] for i in range(4000))
        self.assertEqual(recolor_pixels(data, mask, list(MASCOT_DEFAULT_COLORS), self.P), data)

    def test_group_pixel_takes_new_color(self) -> None:
        colors = list(MASCOT_DEFAULT_COLORS)
        colors[3] = "#2e4a7d"                                        # áo choàng xanh
        r, g, b, a = self.one((70, 55, 52, 255), (4, 0, 0, 255), colors)
        self.assertGreater(b, r)
        self.assertEqual(a, 255)

    def test_only_changed_group_is_touched(self) -> None:
        colors = list(MASCOT_DEFAULT_COLORS)
        colors[0] = "#e58fa8"
        self.assertEqual(self.one((70, 55, 52, 255), (4, 0, 0, 255), colors), (70, 55, 52, 255))

    def test_dark_outline_protected(self) -> None:
        self.assertEqual(self.one((8, 6, 7, 255), (1, 0, 0, 255), OTHER), (8, 6, 7, 255))

    def test_protected_mask_and_transparent_pixels(self) -> None:
        self.assertEqual(self.one((120, 90, 160, 255), (2, 255, 0, 255), OTHER), (120, 90, 160, 255))
        self.assertEqual(self.one((120, 90, 160, 0), (2, 0, 0, 255), OTHER), (120, 90, 160, 0))
        self.assertEqual(self.one((120, 90, 160, 255), (0, 0, 0, 255), OTHER), (120, 90, 160, 255))

    def test_eye_highlight_stays_white(self) -> None:
        self.assertEqual(self.one((250, 248, 252, 255), (2, 0, 0, 255), OTHER), (250, 248, 252, 255))

    def test_skin_keeps_blush(self) -> None:
        colors = list(MASCOT_DEFAULT_COLORS)
        colors[2] = "#e3b18a"
        plain = self.one((248, 213, 192, 255), (3, 0, 0, 255), colors)
        blush = self.one((248, 180, 180, 255), (3, 0, 0, 255), colors)
        self.assertGreater(plain[1] - blush[1], 15)                  # chỗ má hồng vẫn hồng hơn da thường

    def test_poses_cached_and_shape_preserved(self) -> None:
        first = mascot.recolored_poses(tuple(OTHER))
        self.assertIs(first, mascot.recolored_poses(tuple(OTHER)))
        for (src, _), out in zip(mascot.recolor.source_poses(), first):
            self.assertEqual(src.size, out.size)
            self.assertEqual(src.getchannel("A").tobytes(), out.getchannel("A").tobytes())

    @unittest.skipUnless(shutil.which("node"), "cần Node.js")
    def test_matches_javascript_preview(self) -> None:
        """Bản JavaScript (chotto/web/mascot.js, dùng để xem trước) phải cho đúng từng điểm ảnh như Python."""
        rng = random.Random(11)
        n = 3000
        src = bytes(rng.randrange(256) if i % 4 != 3 else rng.choice((0, 255)) for i in range(n * 4))
        mask = bytes(x for _ in range(n) for x in (rng.randrange(8), rng.choice((0, 0, 0, 255)), 0, 255))
        script = (
            "const vm=require('vm'),fs=require('fs');const ctx={window:{}};vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(ROOT / 'chotto/web/mascot.js'))},'utf8'),ctx);"
            "const d=JSON.parse(fs.readFileSync(0,'utf8'));const out=new Uint8ClampedArray(d.src.length);"
            "ctx.window.CHOTTO_MASCOT.recolor(Uint8ClampedArray.from(d.src),Uint8ClampedArray.from(d.mask),out,d.colors,d.P);"
            "process.stdout.write(JSON.stringify(Array.from(out)));"
        )
        palette = json.loads((ROOT / "chotto/mascot/assets/palette.json").read_text("utf-8"))
        payload = json.dumps({"src": list(src), "mask": list(mask), "colors": OTHER, "P": palette})
        done = subprocess.run(["node", "-e", script], input=payload, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), list(recolor_pixels(src, mask, OTHER, self.P)))


class HandlerEventsTest(unittest.TestCase):
    """``LinkHandler`` báo sự kiện cảnh báo cho nhân vật; lỗi ở người nghe không đổi quyết định."""

    def harness(self, **kw: Any) -> Any:
        from test_main import Harness

        h = Harness(**kw)
        h.events = []
        h.handler.notify = lambda event, level: h.events.append((event, level))
        return h

    def test_warning_open_then_closed(self) -> None:
        from test_main import DANGEROUS

        h = self.harness()
        self.assertEqual(h.handler.handle(DANGEROUS, force=True), "cancel")
        self.assertEqual([e for e, _ in h.events], ["warning_open", "warning_closed"])
        self.assertIn(h.events[0][1], ("WARN", "HIGH", "BLOCKED"))

    def test_safe_link_sends_nothing(self) -> None:
        from test_main import SAFE

        h = self.harness()
        self.assertEqual(h.handler.handle(SAFE, force=True), "auto_open")
        self.assertEqual(h.events, [])

    def test_ui_failure_still_closes(self) -> None:
        from test_main import DANGEROUS

        h = self.harness(present_error=True)
        self.assertEqual(h.handler.handle(DANGEROUS, force=True), "ui_failed_blocked")
        self.assertEqual([e for e, _ in h.events], ["warning_open", "warning_closed"])

    def test_broken_listener_never_changes_decision(self) -> None:
        from test_main import DANGEROUS, Harness

        h = Harness(proceed=True)

        def boom(event: str, level: str) -> None:
            raise RuntimeError("mascot hỏng")

        h.handler.notify = boom
        self.assertEqual(h.handler.handle(DANGEROUS, force=True), "proceed")
        self.assertEqual(len(h.opened), 1)


class FakeRoot:
    """Thay cho Tk: chỉ ghi lại lịch ``after``."""

    def __init__(self) -> None:
        self.scheduled: list[int] = []

    def after(self, ms: int, fn: Any = None) -> str:
        self.scheduled.append(ms)
        return f"after#{len(self.scheduled)}"

    def after_cancel(self, ident: str) -> None:
        pass


class TaskbarMascotFailSafeTest(unittest.TestCase):
    """Cửa sổ nhân vật: không bao giờ ném lỗi ra agent."""

    def tearDown(self) -> None:
        save_config(DEFAULTS)

    def test_disabled_by_default_creates_nothing(self) -> None:
        save_config(DEFAULTS)
        m = mascot.TaskbarMascot(FakeRoot(), lambda: None)  # type: ignore[arg-type]
        m.start()
        self.assertIsNone(m._window)
        m.notify("warning_open", "HIGH")                             # chỉ xếp hàng, không cần Tk
        m.request_reload()
        m.stop()

    def test_unsupported_machine_is_skipped_quietly(self) -> None:
        save_config(dict(DEFAULTS, mascot_enabled=True))
        m = mascot.TaskbarMascot(FakeRoot(), lambda: None)  # type: ignore[arg-type]
        with patch.object(mascot.taskbar, "supported", return_value=False):
            m.start()
        self.assertTrue(m._broken)
        self.assertIsNone(m._window)

    def test_window_error_disables_for_session(self) -> None:
        save_config(dict(DEFAULTS, mascot_enabled=True))
        m = mascot.TaskbarMascot(FakeRoot(), lambda: None)  # type: ignore[arg-type]
        with patch.object(mascot.taskbar, "supported", return_value=True), \
                patch.object(mascot.TaskbarMascot, "_build", side_effect=RuntimeError("không có màn hình")),                 self.assertLogs("chotto", "ERROR"):
            m.start()                                                # không ném lỗi, chỉ ghi log
        self.assertTrue(m._broken)

    def _start_with(self, **cfg: Any) -> tuple[Any, list[str]]:
        save_config(dict(DEFAULTS, **cfg))
        m = mascot.TaskbarMascot(FakeRoot(), lambda: None)  # type: ignore[arg-type]
        calls: list[str] = []
        m._show = lambda: (calls.append("show"), setattr(m, "_enabled", True))  # type: ignore[method-assign,assignment]
        m._hide = lambda: (calls.append("hide"), setattr(m, "_enabled", False))  # type: ignore[method-assign,assignment]
        return m, calls

    def test_startup_zalo_follows_zalo_process(self) -> None:
        m, calls = self._start_with(mascot_enabled=True, mascot_startup="zalo")
        running = [False]
        with patch.object(mascot.taskbar, "any_process_running", side_effect=lambda names: running[0]):
            m._poll()
            self.assertEqual(calls, [])                              # Zalo chưa mở: chưa hiện
            running[0] = True
            m._poll()
            self.assertEqual(calls, ["show"])
            running[0] = False
            m._poll()
            self.assertEqual(calls, ["show", "hide"])
        m.stop()

    def test_startup_login_ignores_zalo(self) -> None:
        m, calls = self._start_with(mascot_enabled=True, mascot_startup="login")
        with patch.object(mascot.taskbar, "any_process_running", return_value=False):
            m._poll()
        self.assertEqual(calls, ["show"])
        m.stop()

    def test_fps_setting_is_validated(self) -> None:
        self.assertEqual(validate_config({})["mascot_fps"], 60)
        for ok in (10, 15, 30, 59, 60, 90, 144, 240):                  # thanh kéo: số nguyên bất kỳ trong khoảng
            self.assertEqual(validate_config({"mascot_fps": ok})["mascot_fps"], ok)
        self.assertEqual(validate_config({"mascot_fps": 1})["mascot_fps"], 10)      # ngoài khoảng thì kẹp lại
        self.assertEqual(validate_config({"mascot_fps": 9999})["mascot_fps"], 240)
        for bad in ("60", 60.0, True, None, [60]):                     # sai kiểu thì về mặc định
            self.assertEqual(validate_config({"mascot_fps": bad})["mascot_fps"], 60, bad)
        from chotto.config import SETTINGS_KEYS

        self.assertIn("mascot_fps", SETTINGS_KEYS)                  # cửa sổ ứng dụng được phép sửa

    def test_fps_setting_sets_the_frame_interval(self) -> None:
        for fps in (10, 15, 37, 60, 144, 240):
            m, _calls = self._start_with(mascot_enabled=True, mascot_fps=fps)
            with patch.object(mascot.taskbar, "any_process_running", return_value=False):
                m._poll()
            self.assertAlmostEqual(m._frame_s, 1 / fps)
            m.stop()

    def test_sleep_and_run_time_settings(self) -> None:
        from chotto.config import SETTINGS_KEYS

        for key, default, high in (("mascot_sleep_s", 3, 300), ("mascot_run_s", 3, 60)):
            self.assertIn(key, SETTINGS_KEYS)
            self.assertEqual(validate_config({})[key], default)  # type: ignore[literal-required]
            self.assertEqual(validate_config({key: 0})[key], 1)  # type: ignore[literal-required]
            self.assertEqual(validate_config({key: 9999})[key], high)  # type: ignore[literal-required]
        m, _calls = self._start_with(mascot_enabled=True, mascot_sleep_s=40, mascot_run_s=12)
        with patch.object(mascot.taskbar, "any_process_running", return_value=False):
            m._poll()
        self.assertEqual(m._timing, (40.0, 12.0))
        m.stop()

    def test_brain_follows_sleep_and_run_time(self) -> None:
        brain = mascot.MascotBrain(0, 100000)
        brain.set_timing(2.0, 5.0)
        seen: list[tuple[str, float]] = []
        for _ in range(200):                                     # 20 giây, bước 0,1 giây
            state, t = brain.state, brain.t
            brain.tick(0.1)
            if brain.state != state:
                seen.append((state, round(t + 0.1, 1)))
        self.assertEqual([s for s, _ in seen[:4]], ["sleep", "run", "sleep", "run"])
        for state, lasted in seen[:4]:
            self.assertAlmostEqual(lasted, 2.0 if state == "sleep" else 5.0, delta=0.11)
        brain.set_timing(1.0, 1.0)                               # đổi giữa chừng: giấc/lượt đang dở theo số mới
        before = brain.state
        for _ in range(11):
            brain.tick(0.1)
        self.assertNotEqual(brain.state, before)

    def test_startup_validation(self) -> None:
        self.assertEqual(validate_config({})["mascot_startup"], "login")
        self.assertEqual(validate_config({"mascot_startup": "bogus"})["mascot_startup"], "login")
        self.assertEqual(validate_config({"mascot_startup": "zalo"})["mascot_startup"], "zalo")
        self.assertEqual(validate_config({"mascot_startup": "off"})["mascot_startup"], "login")   # "Thủ công" đã bỏ

    def test_headless_has_no_support_off_windows(self) -> None:
        with patch.object(mascot.taskbar.ov, "SUPPORTED", False):
            self.assertFalse(mascot.supported())


class MacPortTest(unittest.TestCase):
    """Phần macOS chạy được kiểm tra trên mọi máy (không cần AppKit)."""

    def test_runner_uses_main_root_on_mac(self) -> None:
        from chotto.mascot import runner as runner_mod

        root = object()
        with patch.object(runner_mod.sys, "platform", "darwin"),                 patch.object(runner_mod, "TaskbarMascot") as fake, patch.object(runner_mod.threading, "Thread") as thread:
            runner = runner_mod.MascotRunner(lambda: None, None, root)
            runner.start()
            runner.stop()
        fake.assert_called_once()
        self.assertIs(fake.call_args.args[0], root)               # không tạo tk.Tk ở luồng phụ (macOS sẽ sập)
        thread.assert_not_called()
        fake.return_value.stop.assert_called_once()

    def test_runner_ignores_main_root_on_windows(self) -> None:
        from chotto.mascot import runner as runner_mod

        with patch.object(runner_mod.sys, "platform", "win32"):
            self.assertIsNone(runner_mod.MascotRunner(lambda: None, None, object())._main_root)

    def test_zalo_detection_on_mac(self) -> None:
        from chotto import platforms
        from chotto.platforms import cocoa_overlay

        with patch.object(platforms.sys, "platform", "darwin"),                 patch.object(cocoa_overlay, "running_app_names", return_value={"zalo", "finder"}):
            self.assertTrue(platforms.any_process_running(["zalo.exe"]))
            self.assertFalse(platforms.any_process_running(["telegram.exe"]))

    def test_work_area_converts_to_top_left_origin(self) -> None:
        from types import SimpleNamespace

        from chotto.platforms import cocoa_overlay

        def rect(x: float, y: float, w: float, h: float) -> SimpleNamespace:
            return SimpleNamespace(origin=SimpleNamespace(x=x, y=y), size=SimpleNamespace(width=w, height=h))

        screen = SimpleNamespace(frame=lambda: rect(0, 0, 1512, 982), visibleFrame=lambda: rect(0, 70, 1512, 875))
        appkit = SimpleNamespace(NSScreen=SimpleNamespace(screens=lambda: [screen]))
        with patch.object(cocoa_overlay, "_appkit", return_value=appkit):
            self.assertEqual(cocoa_overlay.work_area(), (0, 37, 1512, 912))   # menu 37 pt, Dock 70 pt


class WiringTest(unittest.TestCase):
    """Tín hiệu ``config_changed`` (cửa sổ ứng dụng → agent) và dữ liệu xem trước."""

    def test_webui_forwards_config_changed(self) -> None:
        from chotto.service.webui import WebUI

        web = WebUI()
        calls: list[int] = []
        web.on_config_changed = lambda: calls.append(1)
        web._on_message({"op": "config_changed"})
        self.assertEqual(calls, [1])
        web.on_config_changed = lambda: (_ for _ in ()).throw(RuntimeError("x"))
        with self.assertLogs("chotto", "ERROR"):
            web._on_message({"op": "config_changed"})                # người nghe lỗi không làm đứt kênh

    def test_app_save_signals_agent_and_mascot_assets(self) -> None:
        from chotto.webhost import AppApi

        class FakeHost:
            changed = 0

            def config_changed(self) -> None:
                FakeHost.changed += 1

        api = AppApi(FakeHost())  # type: ignore[arg-type]
        try:
            reply = api.save({"mascot_enabled": True, "mascot_colors": OTHER})
            self.assertTrue(reply["ok"])
            self.assertEqual(reply["settings"]["mascot_colors"], OTHER)
            self.assertEqual(FakeHost.changed, 1)
        finally:
            save_config(DEFAULTS)
        data = api.mascot()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["poses"]), 4)
        self.assertTrue(data["poses"][0]["img"].startswith("data:image/png;base64,"))
        self.assertEqual(data["palette"]["default"], list(MASCOT_DEFAULT_COLORS))

    def test_place_flag_file_channel(self) -> None:
        from chotto.webhost import AppApi

        class FakeHost:
            pass

        mascot.set_place_flag(False)
        self.assertFalse(mascot.place_flag_set())
        AppApi(FakeHost()).mascot_place(True)  # type: ignore[arg-type]
        self.assertTrue(mascot.place_flag_set())                     # cờ sống ngoài tiến trình: agent khác vẫn thấy
        AppApi(FakeHost()).mascot_place(False)  # type: ignore[arg-type]
        self.assertFalse(mascot.place_flag_set())

    def test_agent_follows_flag(self) -> None:
        m = mascot.TaskbarMascot(FakeRoot(), lambda: None)  # type: ignore[arg-type]
        m._enabled = m._pinned = True
        try:
            mascot.set_place_flag(True)
            m._watch_flag()
            self.assertTrue(m._placing)
            mascot.set_place_flag(False)
            m._watch_flag()
            self.assertFalse(m._placing)
            m._pinned = False                                        # bỏ cố định thì cờ không có hiệu lực
            mascot.set_place_flag(True)
            m._watch_flag()
            self.assertFalse(m._placing)
        finally:
            mascot.set_place_flag(False)

    def test_start_clears_stale_flag(self) -> None:
        mascot.set_place_flag(True)
        m = mascot.TaskbarMascot(FakeRoot(), lambda: None)  # type: ignore[arg-type]
        m.start()
        self.assertFalse(mascot.place_flag_set())
        m.stop()

    def test_place_requires_enabled_and_pinned(self) -> None:
        m = mascot.TaskbarMascot(FakeRoot(), lambda: None)  # type: ignore[arg-type]
        m._set_placing(True)                                         # chưa hiện, chưa cố định: bỏ qua
        self.assertFalse(m._placing)
        m._enabled = m._pinned = True
        m._set_placing(True)
        self.assertTrue(m._placing)

    def test_i18n_has_both_languages(self) -> None:
        text = (ROOT / "chotto/web/i18n.js").read_text("utf-8")
        en, vi = text.split("\n    vi: {", 1)
        keys = ["set.buddy", "set.buddyOn", "tip.buddy", "buddy.custom", "buddy.preview", "buddy.random", "buddy.reset",
                "buddy.default", "buddy.pick", "buddy.unsupported", "set.buddyPin", "tip.buddyPin", "buddy.place",
                "buddy.placeBtn", "buddy.placeDone", "buddy.placeHint"] + [f"buddy.g{i}" for i in range(6)] \
            + [f"buddy.p{i}" for i in range(4)]
        for key in keys:
            self.assertIn(f'"{key}":', en, key)
            self.assertIn(f'"{key}":', vi, key)
        html = (ROOT / "chotto/web/app.html").read_text("utf-8")
        for key in re.findall(r'data-i18n(?:-tip)?="((?:set\.buddy|tip\.buddy|buddy\.)[^"]*)"', html):
            self.assertIn(f'"{key}":', vi, key)

    def test_packaging_includes_assets(self) -> None:
        bat = (ROOT / "platforms/PC/windows/build_windows.bat").read_bytes()
        self.assertIn(b"chotto\\mascot\\assets;chotto\\mascot\\assets", bat)
        self.assertNotIn(b"\x08", bat)
        for n in range(4):
            self.assertTrue((ROOT / f"chotto/mascot/assets/pose_{n}.png").exists())
            self.assertTrue((ROOT / f"chotto/mascot/assets/mask_{n}.png").exists())


if __name__ == "__main__":
    unittest.main()
