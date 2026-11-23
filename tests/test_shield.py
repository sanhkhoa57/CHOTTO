"""Kiểm thử màn hình cảnh báo kiểu mới: cấu trúc hiển thị lũy tiến, bảng chữ đời thường, khớp với bản JavaScript."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("CHOTTO_DATA_DIR", tempfile.mkdtemp(prefix="chotto-test-"))
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import gen_view_vectors  # noqa: E402
import sync_extension_data  # noqa: E402

from chotto import advisor, plain  # noqa: E402
from chotto.config import DEFAULTS, load_rules  # noqa: E402
from chotto.engine import Engine, Result, analysis_failed_result  # noqa: E402
from chotto.shield import brand_hit, shield_details, shield_headline, shield_view  # noqa: E402

RULES = load_rules()
BANNED = re.compile(r"(tầng|heuristic|điểm|signal|combosquat|tld|rdap|punycode)", re.IGNORECASE)
VIETNAMESE_ONLY = "[ạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹđ]"


def inspect(url: str) -> Result:
    return Engine(dict(DEFAULTS), RULES, age_lookup=lambda h: None).inspect(url)


def view(url: str, lang: str = "vi", checking: bool = False) -> dict:
    return shield_view(inspect(url), checking, RULES, lang)


class SharedVectorsTest(unittest.TestCase):
    def test_python_reproduces_shared_view_vectors(self) -> None:
        self.assertEqual(
            (ROOT / "tests" / "data" / "view_vectors.json").read_text("utf-8"), gen_view_vectors.dump(gen_view_vectors.build()),
            "Chạy: python tools/gen_view_vectors.py")

    def test_vectors_are_wide_enough(self) -> None:
        vectors = json.loads((ROOT / "tests" / "data" / "view_vectors.json").read_text("utf-8"))["vectors"]
        self.assertGreater(len(vectors), 100)
        self.assertEqual({v["view"]["level"] for v in vectors}, {"WARN", "HIGH", "BLOCKED"})


class PlainTablesTest(unittest.TestCase):
    def test_combo_headlines_follow_advisor_combos(self) -> None:
        for lang in ("vi", "en"):
            self.assertEqual(len(plain.HEADLINES[lang]["combos"]), len(advisor.COMBOS))

    def test_every_advice_code_has_a_detail_line_in_both_languages(self) -> None:
        for lang in ("vi", "en"):
            self.assertEqual(set(plain.DETAILS[lang]), set(advisor.TIPS), lang)
        self.assertEqual(set(plain.DETAILS["vi"]), set(plain.DETAILS["en"]))

    def test_vietnamese_and_english_tables_have_the_same_keys(self) -> None:
        self.assertEqual(set(plain.LABELS["vi"]), set(plain.LABELS["en"]))
        self.assertEqual(set(plain.HEADLINES["vi"]["single"]), set(plain.HEADLINES["en"]["single"]))
        self.assertEqual(plain.LEVELS["vi"].keys(), plain.LEVELS["en"].keys())
        for code in plain.DETAILS["vi"]:
            self.assertEqual(plain.DETAILS["vi"][code]["icon"], plain.DETAILS["en"][code]["icon"], code)

    def test_no_technical_vocabulary_and_short_headlines(self) -> None:
        for lang in ("vi", "en"):
            texts = [*plain.HEADLINES[lang]["combos"], *plain.HEADLINES[lang]["single"].values(), *plain.HEADLINES[lang]["default"].values(),
                     *(d["text"] for d in plain.DETAILS[lang].values()), *(m["label"] for m in plain.LEVELS[lang].values()),
                     *(m["sub"] for m in plain.LEVELS[lang].values())]
            for text in texts:
                self.assertLessEqual(len(text.split()), 12, text)
                if lang == "vi":
                    self.assertIsNone(BANNED.search(text), text)

    def test_english_text_has_no_vietnamese_left(self) -> None:
        for lang_texts in (plain.HEADLINES["en"]["combos"], plain.HEADLINES["en"]["single"].values(),
                           (d["text"] for d in plain.DETAILS["en"].values()), plain.LABELS["en"].values()):
            for text in lang_texts:
                self.assertIsNone(re.search(VIETNAMESE_ONLY, text), text)

    def test_exported_plain_data_is_what_the_extension_ships(self) -> None:
        shipped = json.loads((ROOT / "platforms" / "extension" / "data" / "plain.json").read_text("utf-8"))
        self.assertEqual(shipped, json.loads(json.dumps(plain.plain_data("vi"), ensure_ascii=False)))
        self.assertEqual(shipped["max_details"], 3)

    def test_ui_files_shipped_to_the_extension_are_in_sync(self) -> None:
        for name, content in sync_extension_data.ui_outputs().items():
            self.assertEqual((ROOT / "platforms" / "extension" / "src" / "ui" / name).read_text("utf-8"), content,
                             "Chạy: python tools/sync_extension_data.py")


def _tokens(selector: str) -> dict[str, str]:
    """Các biến màu hex trong khối CSS ``selector`` của ``chotto/web/shield.css``."""
    css = (ROOT / "chotto" / "web" / "shield.css").read_text("utf-8")
    start = css.index(selector + " {")
    block = css[start:css.index("}", start)]
    return {name[2:]: value for name, value in re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", block)}


def _contrast(a: str, b: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, bl = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl

    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class ContrastTest(unittest.TestCase):
    """Chữ và biểu tượng của màn hình cảnh báo đạt tương phản WCAG AA (>= 4,5:1) ở cả chế độ tối và sáng."""

    def test_wcag_aa_in_both_themes(self) -> None:
        for name, selector in (("tối", ".sh"), ("sáng", '.sh[data-theme="light"]')):
            t = {**_tokens(".sh"), **_tokens(selector)}      # chế độ sáng kế thừa các biến không đổi (nút chính...)
            pairs = [("ink", "bg"), ("muted", "bg"), ("muted", "surface"), ("accent-ink", "accent"),
                     ("warn-ink", "bg"), ("high-ink", "bg"), ("blocked-ink", "bg"), ("blocked-on", "blocked-solid"),
                     ("ok", "surface"), ("warn-ink", "warn-chip"), ("high-ink", "high-chip")]
            for fg, bg in pairs:
                if fg not in t or bg not in t:
                    continue
                self.assertGreaterEqual(_contrast(t[fg], t[bg]), 4.5, f"{name}: {fg} trên {bg}")
            self.assertGreaterEqual(len([1 for fg, bg in pairs if fg in t and bg in t]), 8, name)


class ShieldViewTest(unittest.TestCase):
    def test_structure(self) -> None:
        v = view("https://vcb-digibanks.top/xac-nhan")
        self.assertEqual(set(v), {"lang", "level", "levelLabel", "headline", "reasonShort", "domain", "officialLine", "details",
                                  "checking", "actions", "labels"})
        self.assertEqual(v["headline"], "Giả danh Vietcombank và hối thúc bạn")
        self.assertEqual(v["level"], "HIGH")
        self.assertEqual(v["domain"]["registered"], "vcb-digibanks.top")
        self.assertEqual(v["domain"]["hit"], "vcb")
        self.assertEqual(v["domain"]["rest"], "/xac-nhan")
        self.assertEqual(v["officialLine"], "Trang chính thức của Vietcombank là vietcombank.com.vn")
        self.assertLessEqual(len(v["details"]), 3)
        self.assertEqual(v["actions"]["back"], "Quay lại an toàn")

    def test_no_score_or_tier_leaks_into_the_view(self) -> None:
        def strings(node: object) -> list[str]:        # chỉ các chuỗi người dùng nhìn thấy, không tính tên khóa
            if isinstance(node, str):
                return [node]
            items = node.values() if isinstance(node, dict) else node if isinstance(node, list) else []
            return [text for item in items for text in strings(item)]

        for text in strings(view("https://vcb-digibanks.top/xac-nhan")):
            self.assertIsNone(BANNED.search(text), text)

    def test_blacklist_is_blocked_with_its_own_sentence(self) -> None:
        v = view("https://phish-test.chotto.invalid/")
        self.assertEqual(v["level"], "BLOCKED")
        self.assertEqual(v["headline"], "Trang này nằm trong danh sách lừa đảo")
        self.assertEqual(v["domain"]["registered"], "chotto.invalid")
        self.assertEqual(v["domain"]["prefix"], "phish-test.")

    def test_brand_in_subdomain_is_a_decoy_and_real_domain_stays_separate(self) -> None:
        d = view("https://vietcombank.com.vn.xacthuc-tk.top/khoa-tai-khoan")["domain"]
        self.assertEqual((d["prefix"], d["decoyPrefix"], d["registered"]), ("vietcombank.com.vn.", True, "xacthuc-tk.top"))

    def test_idn_shows_readable_form_and_keeps_punycode_apart(self) -> None:
        d = view("https://xn--vietcmbank-y8a.com/")["domain"]
        self.assertEqual(d["punycode"], "xn--vietcmbank-y8a.com")
        self.assertNotIn("xn--", d["registered"])
        self.assertTrue(d["hit"])

    def test_homoglyph_digit_swap_is_highlighted(self) -> None:
        self.assertEqual(view("https://vietc0mbank.com.vn/")["domain"]["hit"], "vietc0mbank")

    def test_ip_userinfo_and_port(self) -> None:
        d = view("http://user@192.168.1.5:8080/x")["domain"]
        self.assertEqual((d["userinfo"], d["registered"], d["rest"], d["isIp"]), ("user@", "192.168.1.5", ":8080/x", True))

    def test_unparseable_link_is_one_plain_sentence(self) -> None:
        v = shield_view(analysis_failed_result("https://exa mple.com/%%"), False, RULES, "vi")
        self.assertEqual(v["headline"], "CHOTTO không đọc được link này")
        self.assertEqual(v["level"], "WARN")
        self.assertTrue(v["domain"]["registered"])

    def test_checking_flag_is_passed_through(self) -> None:
        self.assertTrue(view("https://vcb-digibanks.top/xac-nhan", checking=True)["checking"])

    def test_report_text_is_defanged_and_copy_text_is_the_full_address(self) -> None:
        v = view("https://vcb-digibanks.top/xac-nhan")
        self.assertEqual(v["actions"]["copyText"], "https://vcb-digibanks.top/xac-nhan")
        self.assertEqual(v["actions"]["reportText"], "Link này có vẻ lừa đảo, bạn đừng bấm nhé: vcb-digibanks[.]top")

    def test_english_view_has_no_vietnamese_except_quoted_keywords(self) -> None:
        for url in ("https://vcb-digibanks.top/xac-nhan", "https://bit.ly/3abc", "http://user@192.168.1.5:8080/x",
                    "https://phish-test.chotto.invalid/", "https://xn--vietcmbank-y8a.com/"):
            v = view(url, "en")
            self.assertEqual(v["lang"], "en")
            texts = [v["levelLabel"], v["headline"], v["reasonShort"], v["officialLine"], *(d["text"] for d in v["details"]),
                     *v["labels"].values(), *(x for k, x in v["actions"].items() if k not in ("copyText", "reportText"))]
            for text in texts:
                self.assertIsNone(re.search(VIETNAMESE_ONLY, re.sub(r"“[^”]*”", "", text)), f"{url}: {text}")

    def test_headline_priority_combo_beats_single_signal(self) -> None:
        # giả danh + hối thúc là kịch bản tổ hợp; "tld" riêng lẻ không bao giờ thành câu kết luận
        self.assertEqual(shield_headline(inspect("https://vcb-digibanks.top/xac-nhan"), "vi"), "Giả danh Vietcombank và hối thúc bạn")
        self.assertEqual(shield_headline(inspect("https://vietcombsnk.com/"), "vi"), "Tên gần giống Vietcombank, sai vài chữ")
        self.assertEqual(shield_headline(inspect("https://xk9q2v7z1p.xyz/"), "vi"), "Địa chỉ này trông khác thường")

    def test_details_are_at_most_three_with_icons(self) -> None:
        rows = shield_details(inspect("https://vietcombank.com.vn.xacthuc-tk.top/khoa-tai-khoan"), "vi")
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["icon"] and r["text"] for r in rows))

    def test_brand_hit_edge_cases(self) -> None:
        self.assertEqual(brand_hit("example.com", "Vietcombank", RULES), "")
        self.assertEqual(brand_hit("my-vietcombank-login.top", "Vietcombank", RULES), "vietcombank")
        self.assertEqual(brand_hit("vietcombank.top", "Không có", RULES), "")

    def test_hostile_text_is_sanitised(self) -> None:
        v = view("https://evil.top/%E2%80%AEgnp.exe")
        self.assertNotIn("‮", json.dumps(v, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
