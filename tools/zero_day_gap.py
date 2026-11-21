#!/usr/bin/env python3
"""Đo "khoảng trống zero-day": CHOTTO (chỉ Tầng 2) cảnh báo được bao nhiêu % tên miền lừa đảo mới
ngay lúc thấy lần đầu, và sớm hơn từng blacklist bao nhiêu giờ.

Ba lệnh (chỉ dùng thư viện chuẩn; ``plot`` cần thêm matplotlib):

  collect  Tải các feed, ghi vào SQLite thời điểm mỗi tên miền đăng ký xuất hiện lần đầu ở TỪNG nguồn và
           chấm điểm bằng Engine (tắt Tầng 1 và Tầng 3) ngay lần đầu thấy. Lần chạy thành công đầu tiên của
           mỗi nguồn là baseline: các tên miền trong đó bị loại khỏi phân tích (không biết chúng "mới" từ khi nào).
           Nguồn lỗi mạng thì bỏ qua, không làm hỏng cả lần chạy.
  status   Số lần chạy, số ngày, số tên miền mới, tỷ lệ tải thành công từng nguồn.
  report   Tỷ lệ cảnh báo và so sánh thời điểm với từng nguồn (--md, --json).
  plot     Vẽ CDF "số giờ CHOTTO sớm hơn" và cột tỷ lệ bắt theo nhóm vào thư mục --out.

Định nghĩa dùng trong báo cáo:
  * "Mới": tên miền mà lần xuất hiện đầu tiên (trên mọi nguồn) nằm ngoài baseline. Mốc T0 của nó là thời điểm
    của lần chạy ``collect`` phát hiện nó; điểm CHOTTO được tính ngay lúc đó.
  * "Được cảnh báo": điểm >= ``thresholds.friction`` trong rules.json (ngưỡng hiện màn hình đệm).
  * Với mỗi nguồn S: tên miền "chưa được liệt kê" (S chưa có), "liệt kê muộn hơn" (S có sau T0),
    hoặc "cùng lúc" (S có trong cùng lần chạy với T0; nguồn phát hiện đầu tiên luôn rơi vào nhóm này).
    Nếu tên miền nằm trong baseline của S thì S bị loại khỏi thống kê của riêng tên miền đó (không biết giờ thật).
  * "Số giờ CHOTTO sớm hơn" = (giờ S liệt kê) − T0, chỉ tính cho tên miền CHOTTO cảnh báo được và S liệt kê muộn hơn.

Độ phân giải thời gian bằng chu kỳ chạy ``collect`` (mặc định 30 phút): mọi thời điểm là thời điểm của lần chạy.

Ví dụ:
  python tools/zero_day_gap.py collect
  python tools/zero_day_gap.py status
  python tools/zero_day_gap.py report --md docs/zero-day-report.md --json docs/zero-day-report.json
  python tools/zero_day_gap.py plot --out docs
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import csv
import io
import json
import os
import sqlite3
import statistics
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

# Không bao giờ chạm vào dữ liệu thật của người dùng (config.json, danh sách đen) khi đo.
os.environ.setdefault("CHOTTO_DATA_DIR", tempfile.mkdtemp(prefix="chotto-zd-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chotto.config import DEFAULTS, load_rules  # noqa: E402
from chotto.core.url import URLParseError, parse_url  # noqa: E402
from chotto.engine import Engine  # noqa: E402
from chotto.tier1 import Blacklist  # noqa: E402
from chotto.util import is_private_suffix_host, registered_domain, tld_of  # noqa: E402

# Phishing.Database (mitchellkrogza) bị bỏ khỏi danh sách mặc định: kho ngừng cập nhật từ 02/10/2026, các
# feed NEW-last-hour luôn rỗng và ACTIVE không đổi. Phishing Army không dùng vì chỉ gộp lại PhishTank/OpenPhish/CERT.pl.
SOURCES: Final[dict[str, str]] = {
    "OpenPhish": "https://openphish.com/feed.txt",
    "PhishTank": "https://data.phishtank.com/data/online-valid.csv",
    "CERT-PL": "https://hole.cert.pl/domains/v2/domains.txt",
    "URLhaus": "https://urlhaus.abuse.ch/downloads/text_recent/",
    "ChongLuaDao": "https://api.chongluadao.vn/v1/blacklist",
}
# Nguồn giới hạn tần suất tải (PhishTank trả HTTP 429 khi tải mỗi 30 phút): khoảng cách tối thiểu giữa hai lần thử.
MIN_INTERVAL_SECONDS: Final[dict[str, int]] = {"PhishTank": 3600}
DEFAULT_DB: Final[Path] = Path(__file__).resolve().parent.parent / ".zero-day" / "zero_day.sqlite3"
_MAX_DOWNLOAD: Final[int] = 200 * 1024 * 1024
_USER_AGENT: Final[str] = "CHOTTO-zero-day-study (academic)"
_TOP_N: Final[int] = 15
_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS source_runs (
    run_id INTEGER NOT NULL REFERENCES runs(id),
    source TEXT NOT NULL,
    ok INTEGER NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    entries INTEGER NOT NULL DEFAULT 0,
    new_entries INTEGER NOT NULL DEFAULT 0,
    baseline INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, source)
);
CREATE TABLE IF NOT EXISTS sightings (
    domain TEXT NOT NULL,
    source TEXT NOT NULL,
    first_seen INTEGER NOT NULL,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    baseline INTEGER NOT NULL,
    url TEXT NOT NULL,
    PRIMARY KEY (domain, source)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS sightings_domain ON sightings(domain);
CREATE TABLE IF NOT EXISTS scores (
    domain TEXT PRIMARY KEY,
    first_seen INTEGER NOT NULL,
    discovered_by TEXT NOT NULL,
    url TEXT NOT NULL,
    grp TEXT NOT NULL,
    score INTEGER NOT NULL,
    level TEXT NOT NULL,
    signals TEXT NOT NULL
) WITHOUT ROWID;
"""

Fetcher = Callable[[str], str]


class NoBlacklist(Blacklist):
    """Tắt Tầng 1 khi đo (để đo năng lực với link chưa ai báo cáo)."""

    def __init__(self) -> None:
        """Không mở file nào."""
        self._fp = None
        self._fp_stamp = None
        self._checked = False

    def lookup(self, host: str, path: str = "") -> str | None:
        """Không bao giờ khớp."""
        return None


# ---------------------------------------------------------------------------------------------
# Tải và đọc feed
# ---------------------------------------------------------------------------------------------

def fetch_text(url: str, timeout: float = 90.0) -> str:
    """Tải một feed (http/https/file), giới hạn kích thước.

    Raises:
        OSError: Lỗi mạng/HTTP/đọc file (``urllib.error.URLError`` là con của ``OSError``).
        ValueError: URL không hợp lệ hoặc dữ liệu vượt giới hạn.
    """
    if not url.lower().startswith(("https://", "http://", "file://")):
        raise ValueError(f"Giao thức không được hỗ trợ: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - giao thức đã kiểm tra ở trên
        payload: bytes = response.read(_MAX_DOWNLOAD + 1)
    if len(payload) > _MAX_DOWNLOAD:
        raise ValueError(f"{url} vượt {_MAX_DOWNLOAD} byte")
    return payload.decode("utf-8", errors="replace")


def _iter_tokens(text: str) -> Iterable[str]:
    """Từng mục trong feed: JSON (list/dict), hoặc mỗi dòng một mục (hỗ trợ cả định dạng hosts)."""
    body = text.strip().lstrip("﻿")
    if not body:
        return
    if body[:15].lower().startswith(("<!doctype", "<html")):
        raise ValueError("Nguồn trả về trang HTML thay vì danh sách")
    if body[0] in "[{":
        try:
            data: Any = json.loads(body)
        except ValueError as exc:
            raise ValueError("Nguồn trông như JSON nhưng không đọc được") from exc
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        if not isinstance(data, list):
            return
        for item in data:
            if isinstance(item, str):
                yield item
            elif isinstance(item, dict):
                value = item.get("url") or item.get("domain") or item.get("host")
                if isinstance(value, str):
                    yield value
        return
    if body[:8].lower().startswith("phish_id"):          # CSV của PhishTank: cột "url"
        for row in csv.DictReader(io.StringIO(body)):
            value = row.get("url")
            if value:
                yield value
        return
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        parts = line.split()
        yield parts[-1] if len(parts) > 1 and parts[0].replace(".", "").isdigit() else parts[0]


def parse_feed(text: str) -> dict[str, str]:
    """Đọc feed thành ``{tên miền đăng ký được: URL đầu tiên của tên miền đó}``.

    Mục là URL đầy đủ thì giữ nguyên; mục chỉ là tên miền thì chấm điểm dưới dạng ``https://tên-miền/``.
    Mục không phân tích được bị bỏ qua.

    Raises:
        ValueError: Nội dung là HTML hoặc JSON hỏng (không phải danh sách).
    """
    entries: dict[str, str] = {}
    for token in _iter_tokens(text):
        raw = token.strip().strip('"\',')
        if not raw:
            continue
        url = raw if "://" in raw else f"https://{raw}/"
        if not url.lower().startswith(("http://", "https://")):
            continue
        try:
            host = parse_url(url).host
        except URLParseError:
            continue
        if not host or "." not in host:
            continue
        domain = registered_domain(host) or host
        entries.setdefault(domain, url)
    return entries


# ---------------------------------------------------------------------------------------------
# Chấm điểm
# ---------------------------------------------------------------------------------------------

def make_engine(rules: dict[str, Any]) -> Engine:
    """Engine với Tầng 1 và Tầng 3 tắt: chỉ còn Tầng 2 (không mạng, không blacklist)."""
    cfg = dict(DEFAULTS, tier3_enabled=False, ai_advice=False)
    return Engine(cfg, rules, blacklist=NoBlacklist(), age_lookup=lambda host: None)


def brand_keywords(rules: Mapping[str, Any]) -> list[str]:
    """Từ khóa thương hiệu VN (>= 4 ký tự) để xác định nhóm "nhắm VN", cùng tiêu chí với eval_accuracy."""
    return sorted({str(k).lower() for brand in rules["brands"] for k in brand["keywords"] if len(str(k)) >= 4})


def classify_group(url: str, keywords: Iterable[str]) -> str:
    """``vn`` nếu đuôi .vn hoặc URL chứa thương hiệu VN, ngược lại ``global``."""
    try:
        host = parse_url(url).host
    except URLParseError:
        host = ""
    lowered = url.lower()
    return "vn" if host.endswith(".vn") or any(k in lowered for k in keywords) else "global"


# ---------------------------------------------------------------------------------------------
# CSDL
# ---------------------------------------------------------------------------------------------

def open_db(path: Path) -> sqlite3.Connection:
    """Mở (và tạo nếu chưa có) CSDL SQLite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=60.0)
    con.executescript(_SCHEMA)
    return con


def collect(con: sqlite3.Connection, sources: Mapping[str, str], rules: dict[str, Any], now: int,
            fetcher: Fetcher = fetch_text, engine: Engine | None = None) -> list[dict[str, Any]]:
    """Một lần thu thập. Trả về kết quả từng nguồn (``ok``, ``entries``, ``new``, ``baseline``, ``error``).

    Mỗi nguồn được xử lý trong một giao dịch riêng nên nguồn lỗi không ảnh hưởng nguồn khác.
    """
    engine = engine or make_engine(rules)
    keywords = brand_keywords(rules)
    with con:
        run_id = int(con.execute("INSERT INTO runs (started_at) VALUES (?)", (now,)).lastrowid or 0)
    outcomes: list[dict[str, Any]] = []
    for name, url in sources.items():
        outcome: dict[str, Any] = {"source": name, "ok": False, "entries": 0, "new": 0, "baseline": False, "error": ""}
        outcomes.append(outcome)
        wait = MIN_INTERVAL_SECONDS.get(name, 0)
        last_try = con.execute("SELECT MAX(r.started_at) FROM source_runs s JOIN runs r ON r.id = s.run_id "
                               "WHERE s.source = ?", (name,)).fetchone()[0] if wait else None
        if last_try is not None and now - last_try < wait:
            outcome.update(skipped=True, error=f"bỏ qua: nguồn giới hạn tần suất, thử lại sau {wait // 60} phút")
            continue                  # không ghi source_runs: không tính vào tỷ lệ tải thành công
        try:
            entries = parse_feed(fetcher(url))
        except (OSError, ValueError) as exc:
            outcome["error"] = f"{type(exc).__name__}: {exc}"[:300]
            with con:
                con.execute("INSERT INTO source_runs (run_id, source, ok, error) VALUES (?, ?, 0, ?)",
                            (run_id, name, outcome["error"]))
            continue
        with con:
            baseline = con.execute("SELECT COUNT(*) FROM source_runs WHERE source = ? AND ok = 1",
                                   (name,)).fetchone()[0] == 0
            known = {row[0] for row in con.execute("SELECT domain FROM sightings WHERE source = ?", (name,))}
            fresh = [(domain, link) for domain, link in entries.items() if domain not in known]
            scored = 0
            for domain, link in fresh:
                if not baseline and _unseen_elsewhere(con, domain, name):
                    scored += _score_and_store(con, engine, keywords, domain, link, name, now)
            con.executemany(
                "INSERT INTO sightings (domain, source, first_seen, run_id, baseline, url) VALUES (?, ?, ?, ?, ?, ?)",
                ((domain, name, now, run_id, int(baseline), link) for domain, link in fresh),
            )
            con.execute("INSERT INTO source_runs (run_id, source, ok, entries, new_entries, baseline) "
                        "VALUES (?, ?, 1, ?, ?, ?)", (run_id, name, len(entries), len(fresh), int(baseline)))
        outcome.update(ok=True, entries=len(entries), new=len(fresh), baseline=baseline, scored=scored)
    return outcomes


def _unseen_elsewhere(con: sqlite3.Connection, domain: str, source: str) -> bool:
    """``True`` nếu chưa nguồn nào khác từng có tên miền này (kể cả baseline): tức tên miền thật sự mới."""
    return con.execute("SELECT 1 FROM sightings WHERE domain = ? AND source <> ? LIMIT 1",
                       (domain, source)).fetchone() is None


def _score_and_store(con: sqlite3.Connection, engine: Engine, keywords: list[str], domain: str, url: str,
                     source: str, now: int) -> int:
    """Chấm điểm một tên miền mới và ghi vào ``scores``. Trả về 1 nếu ghi được."""
    try:
        result = engine.inspect(url)
    except Exception as exc:  # noqa: BLE001 - một URL lạ không được làm hỏng cả lần thu thập
        print(f"  ! không chấm được {domain}: {exc}", file=sys.stderr)
        return 0
    signals = [{"code": str(s["code"]), "points": int(s["points"])} for s in result.signals]
    con.execute(
        "INSERT OR IGNORE INTO scores (domain, first_seen, discovered_by, url, grp, score, level, signals) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (domain, now, source, url, classify_group(url, keywords), result.score, result.level, json.dumps(signals)),
    )
    return 1


# ---------------------------------------------------------------------------------------------
# Thống kê
# ---------------------------------------------------------------------------------------------

def iso(ts: int | float | None) -> str:
    """Thời điểm UTC dạng ISO (rỗng nếu ``None``)."""
    if ts is None:
        return ""
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def quartiles(values: list[float]) -> tuple[float, float, float] | None:
    """(Q1, trung vị, Q3); ``None`` nếu không có mẫu. Một mẫu thì cả ba bằng giá trị đó."""
    if not values:
        return None
    if len(values) == 1:
        return values[0], values[0], values[0]
    q1, med, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return q1, med, q3


def status(con: sqlite3.Connection) -> dict[str, Any]:
    """Tình trạng thu thập."""
    first, last, runs = con.execute("SELECT MIN(started_at), MAX(started_at), COUNT(*) FROM runs").fetchone()
    per_source = []
    for name, total, ok, last_ok_run in con.execute(
            "SELECT source, COUNT(*), SUM(ok), MAX(CASE WHEN ok = 1 THEN run_id END) FROM source_runs "
            "GROUP BY source ORDER BY source"):
        last_ok = con.execute("SELECT started_at FROM runs WHERE id = ?", (last_ok_run,)).fetchone() if last_ok_run else None
        error = con.execute("SELECT error FROM source_runs WHERE source = ? AND ok = 0 ORDER BY run_id DESC LIMIT 1",
                            (name,)).fetchone()
        per_source.append({"source": name, "runs": total, "ok": int(ok or 0), "success_rate": (ok or 0) / total,
                           "last_ok": iso(last_ok[0]) if last_ok else "", "last_error": error[0] if error else ""})
    return {
        "runs": runs, "first_run": iso(first), "last_run": iso(last),
        "days": round((last - first) / 86400, 2) if runs else 0.0,
        "new_domains": con.execute("SELECT COUNT(*) FROM scores").fetchone()[0],
        "sources": per_source,
    }


def build_report(con: sqlite3.Connection, rules: Mapping[str, Any]) -> dict[str, Any]:
    """Toàn bộ số liệu cho báo cáo (JSON được)."""
    threshold = float(rules["thresholds"]["friction"])
    high = float(rules["thresholds"]["high"])
    rows = con.execute("SELECT domain, first_seen, discovered_by, url, grp, score, level, signals FROM scores "
                       "ORDER BY first_seen, domain").fetchall()
    sightings: dict[str, dict[str, tuple[int, int]]] = collections.defaultdict(dict)
    for domain, source, first_seen, baseline in con.execute("SELECT domain, source, first_seen, baseline FROM sightings "
                                                            "WHERE domain IN (SELECT domain FROM scores)"):
        sightings[domain][source] = (first_seen, baseline)
    source_names = [r[0] for r in con.execute("SELECT DISTINCT source FROM source_runs WHERE ok = 1 ORDER BY source")]

    groups: dict[str, dict[str, int]] = {g: {"total": 0, "flagged": 0, "high": 0} for g in ("vn", "global")}
    histogram = collections.Counter[str]()
    caught_signals = collections.Counter[str]()
    missed_signals = collections.Counter[str]()
    missed: list[dict[str, Any]] = []
    flagged_total = 0
    for domain, first_seen, _by, url, grp, score, level, signals_json in rows:
        flagged = score >= threshold
        groups[grp]["total"] += 1
        groups[grp]["flagged"] += int(flagged)
        groups[grp]["high"] += int(score >= high)
        histogram[_bucket(score)] += 1
        codes = sorted({s["code"] for s in json.loads(signals_json) if s["points"] > 0})
        flagged_total += int(flagged)
        (caught_signals if flagged else missed_signals).update(codes)
        if not flagged:
            missed.append({"domain": domain, "group": grp, "score": score, "signals": codes, "url": url,
                           "first_seen": iso(first_seen)})

    per_source: dict[str, Any] = {}
    lead_hours: dict[str, list[float]] = {}
    stale = _stale_sources(con)
    for name in source_names:
        if name in stale:
            continue            # nguồn đã tải được > 24 giờ mà không có mục mới nào: nghi ngừng cập nhật
        stats = {"domains": 0, "not_listed": 0, "later": 0, "same_time": 0, "excluded_baseline": 0,
                 "flagged_later": 0}
        hours: list[float] = []
        for domain, first_seen, _by, _url, _grp, score, _level, _sig in rows:
            seen = sightings[domain].get(name)
            if seen is not None and seen[1]:
                stats["excluded_baseline"] += 1
                continue
            stats["domains"] += 1
            if seen is None:
                stats["not_listed"] += 1
            elif seen[0] > first_seen:
                stats["later"] += 1
                if score >= threshold:
                    stats["flagged_later"] += 1
                    hours.append((seen[0] - first_seen) / 3600)
            else:
                stats["same_time"] += 1
        q = quartiles(hours)
        stats["lead_hours_q1"], stats["lead_hours_median"], stats["lead_hours_q3"] = q if q else (None, None, None)
        per_source[name] = stats
        lead_hours[name] = sorted(hours)

    return {
        "generated_at": iso(int(time.time())),
        "threshold_friction": threshold,
        "threshold_high": high,
        "status": status(con),
        "new_domains": len(rows),
        "flagged": flagged_total,
        "rate": flagged_total / len(rows) if rows else None,
        "groups": {g: dict(v, rate=(v["flagged"] / v["total"] if v["total"] else None)) for g, v in groups.items()},
        "score_histogram": {k: histogram[k] for k in _BUCKETS},
        "top_signals_caught": caught_signals.most_common(_TOP_N),
        "top_signals_missed": missed_signals.most_common(_TOP_N),
        "missed_total": len(missed),
        "missed_by_tld": collections.Counter(tld_of(m["domain"]) for m in missed).most_common(_TOP_N),
        "missed_by_platform": collections.Counter(
            m["domain"].split(".", 1)[1] for m in missed if is_private_suffix_host(m["domain"])
        ).most_common(_TOP_N),
        "missed_samples": {g: [m for m in missed if m["group"] == g][:30] for g in ("vn", "global")},
        "sources": per_source,
        "stale_sources": sorted(stale),
        "lead_hours": lead_hours,
    }


def _stale_sources(con: sqlite3.Connection, min_hours: float = 24.0) -> set[str]:
    """Nguồn tải được từ ``min_hours`` giờ trở lên (tính đến lần chạy cuối) mà không có mục mới nào ngoài baseline."""
    last = con.execute("SELECT MAX(started_at) FROM runs").fetchone()[0]
    result: set[str] = set()
    for (name,) in con.execute("SELECT DISTINCT source FROM source_runs WHERE ok = 1"):
        first_ok = con.execute("SELECT MIN(r.started_at) FROM source_runs s JOIN runs r ON r.id = s.run_id "
                               "WHERE s.source = ? AND s.ok = 1", (name,)).fetchone()[0]
        fresh = con.execute("SELECT 1 FROM sightings WHERE source = ? AND baseline = 0 LIMIT 1", (name,)).fetchone()
        if fresh is None and last is not None and (last - first_ok) / 3600 >= min_hours:
            result.add(name)
    return result


_BUCKETS: Final[tuple[str, ...]] = ("0-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60-79", "80-100")


def _bucket(score: int) -> str:
    """Nhóm điểm cho biểu đồ phân bố."""
    if score >= 80:
        return "80-100"
    if score >= 60:
        return "60-79"
    return f"{score // 10 * 10}-{score // 10 * 10 + 9}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _hours(value: float | None) -> str:
    return "–" if value is None else f"{value:.1f}"


def render_md(report: Mapping[str, Any]) -> str:
    """Báo cáo Markdown."""
    st = report["status"]
    lines = [
        "# Khoảng trống zero-day – số liệu thu thập",
        "",
        f"*Tạo lúc {report['generated_at']}. Thu thập {st['runs']} lần, từ {st['first_run'] or '–'} "
        f"đến {st['last_run'] or '–'} ({st['days']} ngày).*",
        "",
    ]
    if st["days"] < 3:
        lines += ["> **CẦN CẬP NHẬT SỐ LIỆU:** mới có dưới 3 ngày dữ liệu, các con số dưới đây chưa đủ tin cậy.", ""]
    lines += [
        "## Tỷ lệ cảnh báo ngay lúc thấy lần đầu (chỉ Tầng 2)",
        "",
        f"Cảnh báo = điểm ≥ {report['threshold_friction']:.0f}; HIGH = điểm ≥ {report['threshold_high']:.0f}.",
        "",
        "| Nhóm | Số tên miền mới | Cảnh báo | Tỷ lệ | HIGH |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| Tất cả | {report['new_domains']} | {report['flagged']} | {_pct(report['rate'])} | "
        f"{sum(g['high'] for g in report['groups'].values())} |",
    ]
    for key, label in (("vn", "Nhắm VN (.vn / thương hiệu VN)"), ("global", "Toàn cầu")):
        g = report["groups"][key]
        lines.append(f"| {label} | {g['total']} | {g['flagged']} | {_pct(g['rate'])} | {g['high']} |")
    lines += [
        "",
        "## So với từng nguồn blacklist",
        "",
        "| Nguồn | Tên miền xét | Chưa liệt kê | Liệt kê muộn hơn | Cùng lúc | Loại (baseline) | "
        "Số giờ sớm hơn Q1 | Trung vị | Q3 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, s in report["sources"].items():
        lines.append(f"| {name} | {s['domains']} | {s['not_listed']} | {s['later']} | {s['same_time']} | "
                     f"{s['excluded_baseline']} | {_hours(s['lead_hours_q1'])} | {_hours(s['lead_hours_median'])} | "
                     f"{_hours(s['lead_hours_q3'])} |")
    if not report["sources"]:
        lines.append("| *(chưa có nguồn nào tải thành công)* | | | | | | | | |")
    lines += [
        "",
        "Số giờ sớm hơn chỉ tính trên tên miền CHOTTO cảnh báo được và nguồn liệt kê muộn hơn. "
        "\"Cùng lúc\" gồm cả nguồn đã phát hiện tên miền đầu tiên. \"Chưa liệt kê\" có thể thành "
        "\"muộn hơn\" ở các lần đo sau (dữ liệu bị cắt phải).",
    ]
    if report["stale_sources"]:
        lines += ["", "Nguồn bị loại khỏi bảng vì tải được hơn 24 giờ mà không có mục mới nào (nghi ngừng cập nhật): "
                  + ", ".join(report["stale_sources"]) + "."]
    lines += [
        "",
        "## Phân bố điểm",
        "",
        "| Điểm | Số tên miền |",
        "| --- | ---: |",
    ]
    lines += [f"| {bucket} | {count} |" for bucket, count in report["score_histogram"].items()]
    lines += ["", "## Dấu hiệu (signal) hay gặp", "",
              "Ở tên miền bị bắt: " + (", ".join(f"`{c}` ({n})" for c, n in report["top_signals_caught"]) or "–"), "",
              "Ở tên miền bị bỏ sót (dấu hiệu có điểm nhưng không đủ ngưỡng): "
              + (", ".join(f"`{c}` ({n})" for c, n in report["top_signals_missed"]) or "–"), "",
              f"## Tên miền bị bỏ sót ({report['missed_total']})", "",
              "Theo đuôi: " + (", ".join(f".{t} ({n})" for t, n in report["missed_by_tld"]) or "–"), "",
              "Theo nền tảng hosting: " + (", ".join(f"{p} ({n})" for p, n in report["missed_by_platform"]) or "–")]
    for key, label in (("vn", "nhắm VN"), ("global", "toàn cầu")):
        samples = report["missed_samples"][key]
        if samples:
            lines += ["", f"### Mẫu bị bỏ sót – {label}", "", "| Tên miền | Điểm | Dấu hiệu |", "| --- | ---: | --- |"]
            lines += [f"| {m['domain']} | {m['score']} | {', '.join(m['signals']) or '–'} |" for m in samples]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------------
# Biểu đồ
# ---------------------------------------------------------------------------------------------

def plot(report: Mapping[str, Any], out: Path) -> list[Path]:
    """Vẽ hai biểu đồ PNG vào ``out``. Cần matplotlib.

    Raises:
        ImportError: Chưa cài matplotlib.
    """
    import matplotlib  # noqa: PLC0415 - chỉ cần khi vẽ

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    fig, ax = plt.subplots(figsize=(7, 4.2))
    drawn = False
    for name, hours in report["lead_hours"].items():
        if hours:
            ax.step(hours, [(i + 1) / len(hours) for i in range(len(hours))], where="post", label=f"{name} (n={len(hours)})")
            drawn = True
    if drawn:
        ax.set_xscale("symlog", linthresh=1)
        ax.legend(fontsize=8)
    else:
        ax.text(0.5, 0.5, "Chưa có tên miền nào được nguồn khác liệt kê muộn hơn", ha="center", va="center",
                transform=ax.transAxes)
    ax.set_xlabel("Số giờ CHOTTO cảnh báo sớm hơn blacklist")
    ax.set_ylabel("Tỷ lệ tên miền (CDF)")
    ax.set_title("CDF thời gian CHOTTO đi trước từng nguồn")
    ax.grid(alpha=0.3)
    path = out / "zero-day-cdf.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    written.append(path)

    fig, ax = plt.subplots(figsize=(6, 4.2))
    labels = ["Tất cả", "Nhắm VN", "Toàn cầu"]
    stats = [{"total": report["new_domains"], "flagged": report["flagged"]}, report["groups"]["vn"],
             report["groups"]["global"]]
    rates = [(s["flagged"] / s["total"] * 100) if s["total"] else 0.0 for s in stats]
    bars = ax.bar(labels, rates, color=["#6b7280", "#b45309", "#1d4ed8"])
    for bar, s in zip(bars, stats, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, f"n={s['total']}", ha="center", fontsize=9)
    ax.set_ylim(0, 110)
    ax.set_ylabel("% tên miền được cảnh báo (Tầng 2)")
    ax.set_title("Tỷ lệ bắt zero-day theo nhóm")
    path = out / "zero-day-rate-by-group.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    written.append(path)
    return written


# ---------------------------------------------------------------------------------------------
# Dòng lệnh
# ---------------------------------------------------------------------------------------------

def _parse_sources(items: list[str] | None) -> dict[str, str]:
    """``--source TÊN=URL`` (lặp được) thay cho danh sách mặc định."""
    if not items:
        return dict(SOURCES)
    result: dict[str, str] = {}
    for item in items:
        name, sep, url = item.partition("=")
        if not sep or not name or not url:
            raise ValueError(f"--source phải có dạng TÊN=URL, nhận được: {item!r}")
        result[name] = url
    return result


def _run_collect(con: sqlite3.Connection, sources: Mapping[str, str], rules: dict[str, Any], log: Path | None) -> int:
    """Chạy ``collect``, in kết quả và (nếu có ``log``) nối đuôi vào file log. Trả về mã thoát."""
    lines: list[str] = []
    code = 1
    started = time.perf_counter()
    now = int(time.time())
    try:
        outcomes = collect(con, sources, rules, now)
        lines.append(f"[{iso(now)}] collect xong sau {time.perf_counter() - started:.1f}s")
        for o in outcomes:
            if o["ok"]:
                tag = "baseline" if o["baseline"] else f"{o.get('scored', 0)} tên miền mới đã chấm"
                lines.append(f"  OK   {o['source']}: {o['entries']} mục, {o['new']} chưa từng thấy ({tag})")
            elif o.get("skipped"):
                lines.append(f"  BỎ   {o['source']}: {o['error']}")
            else:
                lines.append(f"  LỖI  {o['source']}: {o['error']}")
        code = 0 if any(o["ok"] or o.get("skipped") for o in outcomes) else 1
    except Exception as exc:  # noqa: BLE001 - chạy nền: lỗi nào cũng phải để lại dấu vết trong log
        lines.append(f"[{iso(now)}] collect THẤT BẠI: {type(exc).__name__}: {exc}")
    finally:
        text = "\n".join(lines)
        print(text)
        if log is not None:
            with contextlib.suppress(OSError):
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(text + f"\n  (mã thoát {code})\n")
    return code


def main(argv: list[str]) -> int:
    """Điểm vào."""
    for stream in (sys.stdout, sys.stderr):      # Windows: cp1252 khi chuyển hướng ra file/pipe
        with contextlib.suppress(AttributeError, ValueError, OSError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"file SQLite (mặc định {DEFAULT_DB})")
    sub = parser.add_subparsers(dest="command", required=True)
    p_collect = sub.add_parser("collect", help="tải feed và chấm điểm tên miền mới")
    p_collect.add_argument("--source", action="append", metavar="TÊN=URL", help="thay danh sách nguồn mặc định")
    p_collect.add_argument("--log", type=Path, help="ghi thêm kết quả (UTF-8, nối đuôi) vào file này; dùng khi chạy định kỳ")
    sub.add_parser("status", help="tình trạng thu thập")
    p_report = sub.add_parser("report", help="báo cáo số liệu")
    p_report.add_argument("--md", type=Path)
    p_report.add_argument("--json", type=Path)
    p_plot = sub.add_parser("plot", help="vẽ biểu đồ PNG")
    p_plot.add_argument("--out", type=Path, default=Path("docs"))
    args = parser.parse_args(argv[1:])

    try:
        rules = load_rules()
        if args.command == "collect":
            sources = _parse_sources(args.source)
        else:
            sources = {}
    except ValueError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
    with contextlib.closing(open_db(args.db)) as con:
        if args.command == "collect":
            return _run_collect(con, sources, rules, args.log)
        if args.command == "status":
            info = status(con)
            print(f"Số lần chạy: {info['runs']} ({info['first_run'] or '–'} → {info['last_run'] or '–'}, {info['days']} ngày)")
            print(f"Tên miền mới đã chấm điểm: {info['new_domains']}")
            for s in info["sources"]:
                print(f"  {s['source']}: {s['ok']}/{s['runs']} lần thành công ({s['success_rate']:.0%}), "
                      f"lần cuối {s['last_ok'] or '–'}" + (f", lỗi gần nhất: {s['last_error']}" if s["last_error"] else ""))
            return 0
        report = build_report(con, rules)
        if args.command == "report":
            md = render_md(report)
            print(md)
            if args.md:
                args.md.parent.mkdir(parents=True, exist_ok=True)
                args.md.write_text(md, "utf-8")
            if args.json:
                args.json.parent.mkdir(parents=True, exist_ok=True)
                args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
            return 0
        try:
            for path in plot(report, args.out):
                print(f"Đã ghi {path}")
        except ImportError:
            print("Cần cài matplotlib để vẽ biểu đồ: pip install matplotlib", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
