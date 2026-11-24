"""Kiểm thử lời thoại/hỏi đáp của nhân vật taskbar: bộ lọc đầu vào, hạn mức theo ngày, gọi máy chủ, vẽ bong bóng (headless)."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("CHOTTO_DATA_DIR", tempfile.mkdtemp(prefix="chotto-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chotto.mascot import speech  # noqa: E402
from chotto.mascot.brain import MascotBrain  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

CASES = [
    ("https://vietcombank.com.vn.xacthuc-tk.top/dang-nhap", True),
    ("shopee-khuyenmai247.com", True),
    ("Chotto có miễn phí không?", True),
    ("link này có lừa đảo không", True),
    ("viết code python cho tôi link", False),
    ("hôm nay trời đẹp quá", False),
    ("program machine", False),
    ("abc", False),
    ("mac", False),
    ("chạy trên mac được không", True),
    ("x" * 151 + " link", False),
    ("tóm tắt link https://a.com", False),
]


class InputFilterTests(unittest.TestCase):
    def test_cases(self) -> None:
        for text, want in CASES:
            with self.subTest(text=text):
                self.assertEqual(speech.check_input(text), want)

    def test_keyword_lists_match_the_web_and_server_copies(self) -> None:
        """Bộ lọc nằm ở ba nơi (Python, index.html, api/mascot-chat.js): danh sách từ khóa phải giống hệt nhau."""
        for rel in ("index.html", "api/mascot-chat.js"):
            src = (ROOT / rel).read_text("utf-8")
            kw = re.search(r"(?:var|const) KEYWORDS = \[(.*?)\];", src, re.S)
            bl = re.search(r"(?:var|const) BLACKLIST = \[(.*?)\];", src, re.S)
            assert kw is not None and bl is not None, rel
            self.assertEqual(re.findall(r"'([^']*)'", kw.group(1)), list(speech._KEYWORDS), rel)
            self.assertEqual(re.findall(r"'([^']*)'", bl.group(1)), list(speech._BLACKLIST), rel)


class QuotaTests(unittest.TestCase):
    def test_daily_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"CHOTTO_DATA_DIR": tmp}):
            self.assertEqual(speech.quota_left(), speech.DAILY_LIMIT)
            for _ in range(speech.DAILY_LIMIT):
                speech.quota_use()
            self.assertEqual(speech.quota_left(), 0)
            (Path(tmp) / "mascot_chat.json").write_text(json.dumps({"d": "2000-01-01", "n": 99}), "utf-8")
            self.assertEqual(speech.quota_left(), speech.DAILY_LIMIT)       # sang ngày mới thì có lại


class AskTests(unittest.TestCase):
    def _response(self, body: object) -> MagicMock:
        resp = MagicMock()
        resp.read.return_value = json.dumps(body).encode("utf-8")
        resp.__enter__.return_value = resp
        return resp

    def test_reply_and_bubble_type(self) -> None:
        with patch("urllib.request.urlopen", return_value=self._response({"reply": " Né ngay nha ", "bubbleType": "alert"})):
            self.assertEqual(speech.ask("link"), ("Né ngay nha", "alert"))
        with patch("urllib.request.urlopen", return_value=self._response({"reply": "Ổn", "bubbleType": "weird"})):
            self.assertEqual(speech.ask("link"), ("Ổn", "normal"))

    def test_failures_fall_back_to_the_canned_line(self) -> None:
        canned = (str(speech.LINES["fail"]), "normal")
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertEqual(speech.ask("link"), canned)
        with patch("urllib.request.urlopen", return_value=self._response({"oops": 1})):
            self.assertEqual(speech.ask("link"), canned)
        with patch("urllib.request.urlopen", return_value=self._response({"reply": "  "})):
            self.assertEqual(speech.ask("link"), canned)

    def test_endpoint_can_be_overridden(self) -> None:
        with patch.dict(os.environ, {"CHOTTO_MASCOT_API": "http://127.0.0.1:5400/api/mascot-chat"}), \
                patch("urllib.request.urlopen", return_value=self._response({"reply": "ok"})) as opened:
            speech.ask("link")
        self.assertEqual(opened.call_args.args[0].full_url, "http://127.0.0.1:5400/api/mascot-chat")


class BubbleRenderTests(unittest.TestCase):
    def test_every_kind_renders_with_ink_and_transparency(self) -> None:
        for kind in ("normal", "thought", "alert"):
            with self.subTest(kind=kind):
                w, h, tx, ty = speech.layout(kind, 300, 60, 1.0)
                img = speech.render_bubble(kind, w, h, 1.0)
                self.assertEqual(img.size, (w, h))
                alpha = img.getchannel("A")
                self.assertEqual(alpha.getpixel((0, h - 1)), 0)                 # góc ngoài trong suốt
                self.assertEqual(img.getpixel((w // 2, h // 2))[:3], (255, 255, 255))   # ruột trắng (nơi đặt chữ)
                self.assertTrue(tx < w // 2 and ty < h // 2)

    def test_text_area_is_inside_the_body(self) -> None:
        for kind in ("normal", "thought", "alert"):
            w, h, tx, ty = speech.layout(kind, 300, 60, 2.0)
            img = speech.render_bubble(kind, w, h, 2.0)
            for x, y in ((tx, ty), (tx + 300, ty), (tx, ty + 60), (tx + 300, ty + 60)):
                self.assertEqual(img.getpixel((x, y))[:3], (255, 255, 255), (kind, x, y))


class AttendTests(unittest.TestCase):
    def test_chat_keeps_the_raised_hand_until_it_ends(self) -> None:
        b = MascotBrain(0, 100, unit=1.0)
        b.attend(True)
        for _ in range(40):
            b.tick(0.1)
        self.assertEqual(b.state, "stop")                       # đứng yên giơ tay suốt lúc chat
        b.attend(False)
        self.assertEqual(b.state, "sleep")

    def test_chat_end_does_not_cancel_a_real_warning(self) -> None:
        b = MascotBrain(0, 100, unit=1.0)
        b.warning_opened()
        b.attend(True)
        b.attend(False)
        for _ in range(20):
            b.tick(0.1)
        self.assertEqual(b.state, "stop")


class StopWaveTests(unittest.TestCase):
    def test_raised_hand_keeps_waving_like_the_web(self) -> None:
        b = MascotBrain(0, 100, unit=1.0)
        b.warning_opened()
        rots = []
        for _ in range(60):                                      # 3 giây: qua cú nảy rồi lắc
            b.tick(0.05)
            rots.append(b.frame().rot)
        self.assertEqual(b.state, "stop")
        self.assertTrue(b.animating)                             # còn chuyển động nên vòng vẽ không tụt xuống nhịp thưa
        late = rots[-30:]
        self.assertGreater(max(late) - min(late), 0.02)          # lắc thật sự (biên độ ~1,6 độ)
        self.assertLess(max(abs(r) for r in rots), 0.03)         # nhẹ: không quá ~1,7 độ

    def test_reduced_motion_stands_still(self) -> None:
        b = MascotBrain(0, 100, unit=1.0, reduced_motion=True)
        b.warning_opened()
        for _ in range(60):
            b.tick(0.05)
        self.assertFalse(b.animating)
        self.assertEqual(b.frame().rot, 0.0)


class OutlineTests(unittest.TestCase):
    def test_body_gets_dark_outline_but_loose_effects_do_not(self) -> None:
        from PIL import Image

        from chotto.mascot.taskbar import _OUTLINE_RGB, outline_sprite

        img = Image.new("RGBA", (60, 40), (0, 0, 0, 0))
        img.paste((230, 60, 60, 255), (10, 10, 30, 30))          # "thân"
        img.paste((240, 220, 40, 255), (48, 18, 51, 21))         # hiệu ứng nhỏ tách rời (như dấu !)
        seed = Image.new("L", img.size, 0)
        seed.paste(255, (10, 10, 30, 30))                        # chỉ thân được viền
        out, pad = outline_sprite(img, 2.0, seed)
        self.assertEqual(out.size, (img.width + 2 * pad, img.height + 2 * pad))
        self.assertEqual(out.getpixel((pad + 20, pad + 20))[:3], (230, 60, 60))       # ruột giữ nguyên màu
        ring = out.getpixel((pad + 9, pad + 20))                                        # ngay ngoài mép thân
        self.assertGreaterEqual(ring[3], 240)                                           # viền đặc (cạnh làm mềm nên có thể 254)
        self.assertLess(sum(ring[:3]), sum(_OUTLINE_RGB) + 60)                          # tối như viền
        beside_effect = out.getpixel((pad + 47, pad + 19))                              # ngay cạnh hiệu ứng
        self.assertEqual(beside_effect[3], 0)                                           # không bị viền thành cục đen
        dot = out.getpixel((pad + 49, pad + 19))                                        # hiệu ứng vẫn là chấm vàng (được làm nét), không bị phủ đen
        self.assertTrue(dot[3] == 255 and dot[0] > 200 and dot[1] > 180 and dot[2] < 120, dot)

    def test_body_seed_excludes_effect_pixels(self) -> None:
        from chotto.mascot.recolor import source_poses
        from chotto.mascot.taskbar import body_seed

        img, _mask = source_poses()[0]
        seed = body_seed(0, img.size)
        self.assertEqual(seed.size, img.size)
        solid = sum(1 for v in img.getchannel("A").getdata() if v >= 96)
        body = sum(1 for v in seed.getdata() if v)
        self.assertTrue(0.6 * solid < body < solid)              # gần hết phần đặc là thân, nhưng không phải tất cả (zZ bị loại)


if __name__ == "__main__":
    unittest.main()
