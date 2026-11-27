"""Dựng dữ liệu lá cho community.html: mỗi lá = một tên miền đang hoạt động của Phishing.Database.

Chạy hằng ngày (GitHub Actions, .github/workflows/community-leaves.yml) để cây sống theo danh sách:
- Tên miền mới xuất hiện trong danh sách ACTIVE -> thêm lá (lá mới nằm cuối thứ tự).
- Tên miền rời danh sách ACTIVE (Phishing.Database kiểm tra lại và thấy đã chết) -> lá rụng,
  ghi thời điểm; lá rụng nằm trên mặt đất 2 ngày rồi bị xóa hẳn.
Sổ ghi giữa các lần chạy: data/community-registry.tsv.gz (tên miền, lúc thêm, lúc rụng), KHÔNG đăng web.

Ghi ra:
- community-leaves.js: số lá, số lá mới trong 24 giờ, thời điểm dựng, nguồn.
- community-data/leaves-NNN.txt.gz: tên miền đang sống, theo thứ tự thêm vào (cũ trước).
- community-data/fallen.json: tên miền rụng trong 2 ngày qua kèm thời điểm rụng.
Chỉ dùng Phishing.Database (danh sách mở); KHÔNG đăng lại dữ liệu PhishTank/ChongLuaDao.

    python tools/build_community_leaves.py [--download]
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_NAME = "Phishing.Database"
SOURCE_URL = "https://raw.githubusercontent.com/mitchellkrogza/Phishing.Database/master/phishing-domains-ACTIVE.txt"
SOURCE_PAGE = "https://github.com/mitchellkrogza/Phishing.Database"
SHARD = 4000
FALLEN_DAYS = 2
OUT_DIR = ROOT / "community-data"
REGISTRY = ROOT / "data" / "community-registry.tsv.gz"
DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}\.)+[a-z0-9-]{2,63}$")


def cached_source() -> str | None:
    """Bản danh sách app CHOTTO đã tải trên máy này, tìm theo URL trong file .json đi kèm."""
    sys.path.insert(0, str(ROOT))
    from chotto.config import data_dir

    for meta in (data_dir() / "sources").glob("*.json"):
        try:
            if json.loads(meta.read_text(encoding="utf-8")).get("url") == SOURCE_URL:
                return meta.with_suffix(".txt").read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
    return None


def download() -> str:
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "chotto-build"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data: bytes = response.read()
    return data.decode("utf-8", errors="replace")


def load_registry() -> dict[str, tuple[int, int]] | None:
    """tên miền -> (lúc thêm, lúc rụng hoặc 0). None nếu chưa có sổ (lần chạy đầu)."""
    if not REGISTRY.exists():
        return None
    entries: dict[str, tuple[int, int]] = {}
    for line in gzip.decompress(REGISTRY.read_bytes()).decode("utf-8").splitlines():
        domain, added, died = line.split("\t")
        entries[domain] = (int(added), int(died))
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="tải mới thay vì dùng bản app đã tải")
    args = parser.parse_args()
    text = None if args.download else cached_source()
    if text is None:
        print("Tải", SOURCE_URL)
        text = download()
    active = {line.strip().lower() for line in text.splitlines() if DOMAIN.match(line.strip().lower())}
    now = int(time.time())
    registry = load_registry()
    first_run = registry is None
    entries: dict[str, tuple[int, int]] = registry or {}
    alive_before = sum(1 for _, died in entries.values() if not died)
    # Chặn lỗi nguồn: danh sách rỗng/cụt sẽ làm rụng cả cây trong một đêm.
    if len(active) < 1000 or (alive_before and len(active) < alive_before * 0.5):
        raise SystemExit(f"Danh sách bất thường ({len(active)} so với {alive_before}), giữ nguyên dữ liệu cũ.")

    for domain in active:
        added, died = entries.get(domain, (0 if first_run else now, 0))
        entries[domain] = (added, 0)  # mới, hoặc sống lại sau khi rụng
    for domain, (added, died) in list(entries.items()):
        if domain not in active and not died:
            entries[domain] = (added, now)
        elif died and now - died > FALLEN_DAYS * 86400:
            del entries[domain]  # rụng quá 2 ngày: xóa hẳn

    alive = sorted((d for d, (_, died) in entries.items() if not died), key=lambda d: (entries[d][0], d))
    fallen = sorted(((d, died) for d, (_, died) in entries.items() if died), key=lambda item: -item[1])
    new_count = sum(1 for d in alive if entries[d][0] and now - entries[d][0] <= 86400)

    OUT_DIR.mkdir(exist_ok=True)
    for old in OUT_DIR.glob("leaves-*.txt.gz"):
        old.unlink()
    shards = (len(alive) + SHARD - 1) // SHARD
    for n in range(shards):
        body = "\n".join(alive[n * SHARD:(n + 1) * SHARD]).encode("utf-8")
        # mtime=0 giữ file giống hệt nhau giữa các lần dựng cùng dữ liệu.
        (OUT_DIR / f"leaves-{n:03d}.txt.gz").write_bytes(gzip.compress(body, 9, mtime=0))
    (OUT_DIR / "fallen.json").write_text(
        json.dumps({"leaves": [[d, t] for d, t in fallen]}, separators=(",", ":")), encoding="utf-8", newline="\n")
    meta = {
        "count": len(alive), "fresh": new_count, "shard": SHARD, "source": SOURCE_NAME, "page": SOURCE_PAGE,
        "built": now, "date": datetime.datetime.fromtimestamp(now, datetime.UTC).date().isoformat(),
    }
    (ROOT / "community-leaves.js").write_text(
        "// Sinh bởi tools/build_community_leaves.py — đừng sửa tay.\n"
        f"const leafSource = {json.dumps(meta, ensure_ascii=False)};\n",
        encoding="utf-8", newline="\n")
    REGISTRY.parent.mkdir(exist_ok=True)
    rows = "\n".join(f"{d}\t{a}\t{t}" for d, (a, t) in sorted(entries.items()))
    REGISTRY.write_bytes(gzip.compress(rows.encode("utf-8"), 9, mtime=0))
    print(f"{len(alive):,} lá sống ({new_count:,} mới), {len(fallen):,} lá rụng trong {FALLEN_DAYS} ngày, {shards} gói")


if __name__ == "__main__":
    main()
