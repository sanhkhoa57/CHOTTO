"""Kiểm thử tools/zero_day_gap.py bằng feed giả (file://), không gọi mạng thật."""
import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("CHOTTO_DATA_DIR", tempfile.mkdtemp(prefix="chotto-test-"))
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import zero_day_gap as zd  # noqa: E402
from chotto.config import load_rules  # noqa: E402

H = 3600
T0 = 1_800_000_000
PHISH = "https://vietcombank-xacthuc-taikhoan.top/login"   # Tầng 2 phải cảnh báo
PHISH_B = "https://zalo-nhan-qua-mienphi.xyz/"
CLEAN = "https://example.com/"                              # miền phổ biến: không cảnh báo


class ZeroDayGapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.con = zd.open_db(self.dir / "zd.sqlite3")
        self.addCleanup(self.con.close)
        self.rules = load_rules()

    def feed(self, name: str, lines: list[str]) -> str:
        path = self.dir / f"{name}.txt"
        path.write_text("\n".join(lines) + "\n", "utf-8")
        return path.as_uri()

    def run_collect(self, sources: dict[str, str], now: int) -> dict[str, dict]:
        return {o["source"]: o for o in zd.collect(self.con, sources, self.rules, now)}

    def scored(self) -> dict[str, tuple]:
        return {r[0]: r for r in self.con.execute("SELECT domain, score, level, grp FROM scores")}

    # --- đọc feed ---------------------------------------------------------------------------

    def test_parse_feed_domains_urls_hosts_and_junk(self) -> None:
        text = "# comment\n\nhttp://a.example.org/x\nb.example.net\n0.0.0.0 c.example.com\nnot a domain\n\"d.example.io\"\n"
        got = zd.parse_feed(text)
        self.assertEqual(got["example.org"], "http://a.example.org/x")
        self.assertIn("example.net", got)
        self.assertIn("example.com", got)
        self.assertIn("example.io", got)

    def test_parse_feed_json_and_html(self) -> None:
        got = zd.parse_feed(json.dumps([{"url": "https://x.test-site.top/a"}, "y.test-site2.top"]))
        self.assertEqual(set(got), {"test-site.top", "test-site2.top"})
        with self.assertRaises(ValueError):
            zd.parse_feed("<!DOCTYPE html><html>410 Gone</html>")

    # --- baseline và chấm điểm --------------------------------------------------------------

    def test_first_run_is_baseline_and_not_scored(self) -> None:
        src = {"A": self.feed("a", [PHISH])}
        out = self.run_collect(src, T0)
        self.assertTrue(out["A"]["baseline"])
        self.assertEqual(self.scored(), {})
        self.assertEqual(self.con.execute("SELECT baseline FROM sightings").fetchone()[0], 1)

    def test_new_domain_scored_at_first_sight(self) -> None:
        src = {"A": self.feed("a", [CLEAN])}
        self.run_collect(src, T0)
        src = {"A": self.feed("a", [CLEAN, PHISH, "https://shop.example.vn/"])}
        out = self.run_collect(src, T0 + H)
        self.assertFalse(out["A"]["baseline"])
        self.assertEqual(out["A"]["new"], 2)
        scored = self.scored()
        self.assertEqual(set(scored), {"vietcombank-xacthuc-taikhoan.top", "example.vn"})
        self.assertGreaterEqual(scored["vietcombank-xacthuc-taikhoan.top"][1], 30)
        self.assertEqual(scored["example.vn"][3], "vn")
        self.assertEqual(self.con.execute("SELECT first_seen FROM scores LIMIT 1").fetchone()[0], T0 + H)

    def test_domain_already_in_other_baseline_is_not_new(self) -> None:
        a, b = self.dir / "a.txt", self.dir / "b.txt"
        a.write_text(PHISH + "\n", "utf-8")
        b.write_text(CLEAN + "\n", "utf-8")
        sources = {"A": a.as_uri(), "B": b.as_uri()}
        self.run_collect(sources, T0)
        b.write_text(CLEAN + "\n" + PHISH + "\n", "utf-8")     # B thêm tên miền A đã có từ trước nghiên cứu
        self.run_collect(sources, T0 + H)
        self.assertEqual(self.scored(), {})

    # --- nguồn lỗi --------------------------------------------------------------------------

    def test_failing_source_does_not_break_run(self) -> None:
        good = self.feed("good", [CLEAN])
        sources = {"Good": good, "Dead": (self.dir / "missing.txt").as_uri(), "Html": self.feed("html", ["<html>x</html>"])}
        out = self.run_collect(sources, T0)
        self.assertTrue(out["Good"]["ok"])
        self.assertFalse(out["Dead"]["ok"])
        self.assertFalse(out["Html"]["ok"])
        info = zd.status(self.con)
        rates = {s["source"]: s["success_rate"] for s in info["sources"]}
        self.assertEqual(rates, {"Good": 1.0, "Dead": 0.0, "Html": 0.0})
        # Nguồn lỗi chưa từng thành công thì lần thành công đầu sau này vẫn là baseline.
        Path(self.dir / "missing.txt").write_text(PHISH + "\n", "utf-8")
        sources["Html"] = self.feed("html", [CLEAN])
        out = self.run_collect(sources, T0 + H)
        self.assertTrue(out["Dead"]["baseline"])
        self.assertEqual(self.scored(), {})

    # --- báo cáo ----------------------------------------------------------------------------

    def test_report_gaps_between_sources(self) -> None:
        pa, pb = self.dir / "a.txt", self.dir / "b.txt"
        pa.write_text(CLEAN + "\n", "utf-8")
        pb.write_text(CLEAN + "\n", "utf-8")
        sources = {"A": pa.as_uri(), "B": pb.as_uri()}
        self.run_collect(sources, T0)                               # baseline cả hai
        pa.write_text(f"{CLEAN}\n{PHISH}\n{PHISH_B}\nhttps://khong-ai-bao.top/\n", "utf-8")
        self.run_collect(sources, T0 + H)                           # A thấy 3 tên miền mới; B chưa
        pb.write_text(f"{CLEAN}\n{PHISH}\nhttps://khong-ai-bao.top/\n", "utf-8")
        self.run_collect(sources, T0 + 5 * H)                       # B liệt kê 2 tên miền sau 4 giờ
        report = zd.build_report(self.con, self.rules)
        self.assertEqual(report["new_domains"], 3)
        a, b = report["sources"]["A"], report["sources"]["B"]
        self.assertEqual((a["domains"], a["same_time"], a["later"], a["not_listed"]), (3, 3, 0, 0))
        self.assertEqual((b["domains"], b["later"], b["not_listed"], b["same_time"]), (3, 2, 1, 0))
        # Chỉ tên miền CHOTTO cảnh báo được mới tính vào số giờ sớm hơn.
        self.assertEqual(b["flagged_later"], len([h for h in report["lead_hours"]["B"]]))
        self.assertTrue(all(h == 4.0 for h in report["lead_hours"]["B"]))
        self.assertGreaterEqual(report["flagged"], 1)
        self.assertEqual(report["groups"]["vn"]["total"] + report["groups"]["global"]["total"], 3)

    def test_late_baseline_source_is_censored_for_that_domain(self) -> None:
        pa, pb = self.dir / "a.txt", self.dir / "b.txt"
        pa.write_text(CLEAN + "\n", "utf-8")
        self.run_collect({"A": pa.as_uri()}, T0)
        pa.write_text(f"{CLEAN}\n{PHISH}\n", "utf-8")
        pb.write_text(f"{PHISH}\n", "utf-8")
        self.run_collect({"A": pa.as_uri(), "B": pb.as_uri()}, T0 + H)   # B xuất hiện muộn: lần đầu của B là baseline
        report = zd.build_report(self.con, self.rules)
        self.assertEqual(report["new_domains"], 1)
        self.assertEqual(report["sources"]["B"]["excluded_baseline"], 1)
        self.assertEqual(report["sources"]["B"]["domains"], 0)

    def test_report_empty_database_and_rendering(self) -> None:
        report = zd.build_report(self.con, self.rules)
        self.assertEqual(report["new_domains"], 0)
        self.assertIsNone(report["rate"])
        md = zd.render_md(report)
        self.assertIn("CẦN CẬP NHẬT SỐ LIỆU", md)
        json.dumps(report)

    def test_quartiles(self) -> None:
        self.assertIsNone(zd.quartiles([]))
        self.assertEqual(zd.quartiles([2.0]), (2.0, 2.0, 2.0))
        self.assertEqual(zd.quartiles([1.0, 2.0, 3.0, 4.0, 5.0]), (2.0, 3.0, 4.0))

    def test_engine_has_no_blacklist_or_tier3(self) -> None:
        engine = zd.make_engine(self.rules)
        result = engine.inspect(PHISH)
        self.assertEqual(result.tier_reached, 2)
        self.assertNotIn("blacklist", [s["code"] for s in result.signals])

    def test_main_collect_status_report(self) -> None:
        db = self.dir / "cli.sqlite3"
        feed = self.feed("cli", [CLEAN])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(zd.main(["x", "--db", str(db), "collect", "--source", f"A={feed}"]), 0)
            self.assertEqual(zd.main(["x", "--db", str(db), "collect", "--source", f"A={(self.dir / 'no.txt').as_uri()}"]), 1)
            self.assertEqual(zd.main(["x", "--db", str(db), "status"]), 0)
            self.assertEqual(zd.main(["x", "--db", str(db), "report", "--md", str(self.dir / "r.md"),
                                      "--json", str(self.dir / "r.json")]), 0)
        self.assertTrue((self.dir / "r.md").read_text("utf-8").startswith("# Khoảng trống zero-day"))
        with contextlib.closing(sqlite3.connect(db)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 2)

    def test_main_collect_fails_when_all_sources_fail(self) -> None:
        db = self.dir / "fail.sqlite3"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(zd.main(["x", "--db", str(db), "collect", "--source",
                                      f"A={(self.dir / 'no.txt').as_uri()}"]), 1)


if __name__ == "__main__":
    unittest.main()
