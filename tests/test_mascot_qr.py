"""Quét QR của nhân vật taskbar: thanh chọn 2 ô, cắt/giải mã, xử lý kết quả. Không mở cửa sổ, không chụp màn hình thật."""

import time
import unittest
from typing import Any
from unittest.mock import patch

from chotto.engine import Result
from chotto.mascot import TaskbarMascot, panel, qr, scan

try:
    import zxingcpp
    from PIL import Image
except ImportError:                                                  # pragma: no cover - máy không có thư viện
    zxingcpp = None


def make_qr(text: str, size: int = 240) -> Any:
    code = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.QRCode)
    bitmap = zxingcpp.write_barcode_to_image(code, scale=1, add_quiet_zones=False)
    view = memoryview(bitmap)
    height, width = view.shape[:2]
    small = Image.frombytes("L", (width, height), view.tobytes())
    step = size // width
    return small.resize((width * step, height * step), Image.Resampling.NEAREST).convert("RGB")


def result(level: str, tier: int = 2) -> Result:
    reasons = [] if level == "SAFE" else ["Đuôi tên miền rẻ tiền"]
    signals = [] if level == "SAFE" else [{"code": "bad_tld", "points": 50, "reason": reasons[0], "brand": ""}]
    return Result(url="u", final_url="https://vi-du.top/", host="vi-du.top", score=0, level=level, reasons=reasons,
                  signals=signals, tier_reached=tier, display_domain="vi-du.top")


class SelectionTest(unittest.TestCase):
    def test_any_drag_direction_is_normalized_and_clamped(self) -> None:
        self.assertEqual(qr.selection_box(300, 200, 100, 50, 1920, 1080), (100, 50, 300, 200))
        self.assertEqual(qr.selection_box(-40, -5, 5000, 90, 800, 600), (0, 0, 800, 90))

    def test_a_stray_click_is_not_a_selection(self) -> None:
        self.assertIsNone(qr.selection_box(10, 10, 12, 200, 800, 600))


@unittest.skipIf(zxingcpp is None, "cần zxing-cpp + Pillow")
class DecodeTest(unittest.TestCase):
    def test_crop_from_a_screenshot_then_decode_even_without_quiet_zone(self) -> None:
        code = make_qr("https://vi-du.top/nhan-qua")
        screen = Image.new("RGB", (900, 700), (30, 30, 40))
        screen.paste(code, (400, 250))
        box = qr.selection_box(400, 250, 400 + code.width, 250 + code.height, *screen.size)
        assert box is not None
        self.assertEqual(qr.decode(qr.crop(screen, box)), ["https://vi-du.top/nhan-qua"])     # kéo sát mép mã

    def test_blank_area(self) -> None:
        self.assertEqual(qr.decode(Image.new("RGB", (300, 300), "white")), [])
        self.assertEqual(qr.scan(Image.new("RGB", (60, 60), "white"), "vi").status, "none")


class ReportTest(unittest.TestCase):
    def test_only_http_links_are_links(self) -> None:
        self.assertEqual(qr.as_link(" https://a.vn/x "), "https://a.vn/x")
        self.assertEqual(qr.as_link("www.a.vn"), "https://www.a.vn")
        self.assertEqual(qr.as_link("zalo-qua.xyz/nhan"), "https://zalo-qua.xyz/nhan")
        for value in ("xin chào", "javascript:alert(1)", "file:///c:/x", "tel:0900000000", "WIFI:S:a;P:b;;", "a@b.com",
                      "00020101021238", "https://a.vn/ two"):
            self.assertEqual(qr.as_link(value), "", value)

    def test_plain_text_is_never_inspected(self) -> None:
        def boom(_link: str) -> Result:
            raise AssertionError("không được thẩm định văn bản thường")

        report = qr.analyze(["mật khẩu wifi\u202e: 123"], "vi", boom)
        self.assertEqual((report.status, report.link, report.payload), ("text", "", "mật khẩu wifi\u202e: 123"))
        self.assertNotIn("\u202e", report.message)                       # ký tự đảo chiều chữ không lên màn hình

    def test_levels(self) -> None:
        for level, kind, word in (("SAFE", "normal", "chưa chắc"), ("WARN", "alert", "đáng ngờ"),
                                  ("HIGH", "alert", "Nguy hiểm"), ("BLOCKED", "alert", "danh sách")):
            report = qr.analyze(["https://vi-du.top/"], "vi", lambda _link, lv=level: result(lv))
            self.assertEqual((report.status, report.kind, report.level), ("link", kind, level))
            self.assertIn(word, report.message)
            self.assertIn("https://vi-du.top/", report.message)
        english = qr.analyze(["https://vi-du.top/"], "en", lambda _link: result("HIGH"))
        self.assertTrue(english.message.startswith("Dangerous!"))

    def test_failed_inspection_is_never_safe(self) -> None:
        def boom(_link: str) -> Result:
            raise RuntimeError("engine hỏng")

        with self.assertLogs("chotto", "ERROR"):
            report = qr.analyze(["https://vi-du.top/"], "vi", boom)
        self.assertEqual((report.level, report.kind), ("WARN", "alert"))
        unreadable = qr.analyze(["https://vi-du.top/"], "vi", lambda _link: result("WARN", tier=0))
        self.assertIn("chưa kiểm tra được", unreadable.message)


class PanelLayoutTest(unittest.TestCase):
    def test_two_boxes_and_close_are_clickable_and_do_not_overlap(self) -> None:
        for u in (1.0, 1.5, 2.0):
            buttons = [panel.Button("scan", "Quét QR", True), panel.Button("ask", "Hỏi Chotto")]
            image, areas = panel.render_panel("normal", "Bạn cần tui làm gì nè?", buttons, u, big=True)
            self.assertEqual(set(areas), {"scan", "ask", panel.CLOSE})
            for key, (left, top, right, bottom) in areas.items():
                self.assertTrue(0 <= left < right <= image.width and 0 <= top < bottom <= image.height, key)
                self.assertEqual(panel.hit(areas, (left + right) // 2, (top + bottom) // 2), key)
            self.assertLessEqual(areas["scan"][2], areas["ask"][0])
            self.assertIsNone(panel.hit(areas, 0, 0))

    def test_long_link_wraps_inside_the_bubble(self) -> None:
        text = "Nguy hiểm!\nhttps://" + "a" * 150 + ".top"
        image, _areas = panel.render_panel("alert", text, [panel.Button("copy", "Sao chép")], 1.0)
        self.assertLess(image.width, 520)


class FakeRoot:
    def __init__(self) -> None:
        self.jobs: list[Any] = []
        self.clipboard = ""

    def after(self, ms: int, fn: Any = None) -> str:
        self.jobs.append(fn)
        return "job"

    def after_cancel(self, ident: str) -> None:
        pass

    def clipboard_clear(self) -> None:
        self.clipboard = ""

    def clipboard_append(self, value: str) -> None:
        self.clipboard += value

    def run(self) -> None:
        jobs, self.jobs = self.jobs, []
        for job in jobs:
            job()


class FakePanel:
    def __init__(self) -> None:
        self.visible = False
        self.shown: list[tuple[str, list[str]]] = []
        self.action: Any = None

    def show(self, kind: str, text: str, buttons: Any, on_action: Any, big: bool = False, modal: bool = False) -> None:
        self.visible = True
        self.shown.append((text, [b.key for b in buttons]))
        self.action = on_action

    def close(self) -> None:
        self.visible = False


class FakeBubble:
    chatting = False
    visible = False

    def __init__(self) -> None:
        self.calls: list[str] = []

    def open_chat(self) -> None:
        self.calls.append("open_chat")

    def close_chat(self) -> None:
        pass

    def hide(self) -> None:
        pass

    def say(self, kind: str, text: str, keep: bool = False) -> None:
        self.calls.append("say:" + text)


class FakeScan:
    def __init__(self) -> None:
        self.capturing = False
        self.started: list[str] = []
        self.cancelled = 0

    def start(self, lang: str) -> None:
        self.started.append(lang)

    def cancel(self) -> None:
        self.cancelled += 1


class MascotFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.opened: list[str] = []
        self.root = FakeRoot()
        self.mascot = TaskbarMascot(self.root, lambda: None, self.opened.append)  # type: ignore[arg-type]
        self.panel, self.bubble, self.scan = FakePanel(), FakeBubble(), FakeScan()
        self.mascot._panel, self.mascot._bubble, self.mascot._scan = self.panel, self.bubble, self.scan  # type: ignore[assignment]
        self.mascot._enabled, self.mascot._lang = True, "vi"
        qr_on = patch("chotto.platforms.overlay.QR_SUPPORTED", True)   # luồng quét QR (Windows) kiểm được trên mọi máy
        qr_on.start()
        self.addCleanup(qr_on.stop)

    def test_without_qr_double_click_opens_chat_directly(self) -> None:
        with patch("chotto.platforms.overlay.QR_SUPPORTED", False):    # macOS: không có quét QR
            with patch.object(self.mascot, "_open_chat") as open_chat:
                self.mascot._open_choices()
        open_chat.assert_called_once()
        self.assertEqual(self.panel.shown, [])

    def test_double_click_offers_two_boxes_and_does_not_open_chat_yet(self) -> None:
        self.mascot._open_choices()
        self.assertEqual(self.panel.shown[-1][1], ["scan", "ask"])
        self.assertEqual(self.bubble.calls, [])

    def test_scan_box_closes_panel_and_starts_scanning(self) -> None:
        self.mascot._open_choices()
        self.panel.action("scan")
        self.assertFalse(self.panel.visible)
        self.assertEqual(self.scan.started, ["vi"])

    def test_ask_box_opens_chat(self) -> None:
        self.mascot._open_choices()
        self.panel.action("ask")
        self.assertFalse(self.panel.visible)
        self.assertEqual(self.bubble.calls, ["open_chat"])
        self.assertEqual(self.scan.started, [])

    def test_nothing_happens_while_hidden_or_placing(self) -> None:
        self.mascot._placing = True
        self.mascot._open_choices()
        self.mascot._start_scan()
        self.assertEqual((self.panel.shown, self.scan.started), ([], []))

    def test_link_result_can_be_copied_and_is_only_opened_on_request(self) -> None:
        report = qr.QrReport("link", "Cẩn thận", "alert", "vi-du.top", "https://vi-du.top", "WARN")
        self.mascot._on_qr_report(report)
        self.assertEqual(self.panel.shown[-1][1], ["copy", "open"])
        self.assertEqual(self.opened, [])
        self.panel.action("copy")
        self.assertEqual(self.root.clipboard, "vi-du.top")
        self.panel.action("open")
        self.assertEqual(self.opened, ["https://vi-du.top"])
        self.assertFalse(self.panel.visible)

    def test_text_result_has_no_open_button(self) -> None:
        self.mascot._on_qr_report(qr.QrReport("text", "Mã QR ghi là: a", payload="a"))
        self.assertEqual(self.panel.shown[-1][1], ["copy"])

    def test_not_found_is_just_a_speech_bubble(self) -> None:
        self.mascot._on_qr_report(qr.QrReport("none", "Không thấy"))
        self.assertEqual((self.panel.shown, self.bubble.calls), ([], ["say:Không thấy"]))


class ScanPipelineTest(unittest.TestCase):
    def _scan(self) -> tuple[scan.QrScan, FakeRoot, list[Any]]:
        root, events = FakeRoot(), []
        job = scan.QrScan(root, 1.0, lambda fn: fn(), lambda on: events.append(on),  # type: ignore[arg-type]
                          lambda: events.append("reading"), events.append)
        return job, root, events

    def _drain(self, root: FakeRoot) -> None:
        for _ in range(200):
            if not root.jobs:
                return
            root.run()
            time.sleep(0.005)
        self.fail("lượt quét không kết thúc")

    def test_hides_before_capture_then_decodes_off_thread(self) -> None:
        job, root, events = self._scan()
        order: list[str] = []

        def overlay(_root: Any, _image: Any, _origin: Any, _hint: str, _u: float, done: Any, _scale: float) -> object:
            order.append("overlay")
            done("cropped")
            return object()

        with patch.object(scan.snip, "grab_screen", side_effect=lambda: (order.append("grab"), ("img", (0, 0), 1.0))[1]), \
                patch.object(scan.snip, "SnipOverlay", side_effect=overlay), \
                patch.object(scan.qr, "scan", return_value=qr.QrReport("none", "x")):
            job.start("vi")
            self.assertEqual((events, order), ([True], []))              # giấu trước, chụp ở nhịp sau
            self._drain(root)
        self.assertEqual(order, ["grab", "overlay"])
        self.assertEqual(events, [True, False, "reading", qr.QrReport("none", "x")])

    def test_cancel_drops_the_pending_capture(self) -> None:
        job, root, events = self._scan()
        with patch.object(scan.snip, "grab_screen", side_effect=AssertionError("đã hủy thì không chụp")):
            job.start("vi")
            job.cancel()
            self._drain(root)
        self.assertEqual(events, [True, False])

    def test_capture_error_is_reported(self) -> None:
        job, root, events = self._scan()
        with patch.object(scan.snip, "grab_screen", side_effect=OSError("màn hình khóa")), self.assertLogs("chotto", "ERROR"):
            job.start("vi")
            self._drain(root)
        self.assertFalse(job.capturing)
        self.assertEqual(events[-1].status, "failed")

    def test_other_permission_errors_are_plain_failures(self) -> None:
        job, root, events = self._scan()                                   # Windows: không hiện câu nhắc quyền của Mac
        with patch.object(scan.snip, "grab_screen", side_effect=PermissionError("khác")), self.assertLogs("chotto", "ERROR"):
            job.start("vi")
            self._drain(root)
        self.assertEqual(events[-1], qr.QrReport("failed", qr.texts("vi")["failed"]))

    def test_missing_screen_permission_is_explained(self) -> None:
        job, root, events = self._scan()
        with patch.object(scan.snip, "grab_screen", side_effect=scan.snip.ScreenPermissionError("macOS")):
            job.start("vi")
            self._drain(root)
        self.assertFalse(job.capturing)
        self.assertEqual(events[-1], qr.QrReport("failed", qr.texts("vi")["permission"]))


if __name__ == "__main__":
    unittest.main()
