"""tools/build_community_leaves.py: thêm lá mới, lá rụng khi tên miền rời danh sách, xóa sau 2 ngày."""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

TOOL = Path(__file__).resolve().parent.parent / "tools" / "build_community_leaves.py"


def load_tool(root: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_community_leaves", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    setattr(module, "ROOT", root)
    setattr(module, "OUT_DIR", root / "community-data")
    setattr(module, "REGISTRY", root / "data" / "community-registry.tsv.gz")
    return module


class CommunityLeavesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.tool = load_tool(self.root)
        self.base = [f"site{n:04d}.example.com" for n in range(1500)]

    def tearDown(self) -> None:
        self.dir.cleanup()

    def run_day(self, domains: list[str], now: int) -> None:
        with mock.patch.object(self.tool, "cached_source", return_value="\n".join(domains)), \
                mock.patch.object(self.tool.time, "time", return_value=now), \
                mock.patch.object(sys, "argv", ["build"]):
            self.tool.main()

    def meta(self) -> dict[str, object]:
        text = (self.root / "community-leaves.js").read_text(encoding="utf-8")
        result: dict[str, object] = json.loads(text.split("=", 1)[1].strip().rstrip(";"))
        return result

    def alive(self) -> list[str]:
        names: list[str] = []
        for pack in sorted((self.root / "community-data").glob("leaves-*.txt.gz")):
            names += gzip.decompress(pack.read_bytes()).decode("utf-8").split("\n")
        return names

    def fallen(self) -> list[list[object]]:
        data = json.loads((self.root / "community-data" / "fallen.json").read_text(encoding="utf-8"))
        result: list[list[object]] = data["leaves"]
        return result

    def test_new_dead_and_purge(self) -> None:
        day = 86400
        self.run_day(self.base, 1000 * day)
        self.assertEqual(self.meta()["count"], 1500)
        self.assertEqual(self.meta()["fresh"], 0)  # lần đầu: không coi cả cây là "mới"

        # Ngày 2: 10 tên miền chết, 5 tên miền mới -> lá mới nằm cuối thứ tự.
        new = [f"new{n}.example.org" for n in range(5)]
        self.run_day(self.base[10:] + new, 1001 * day)
        self.assertEqual(self.meta()["count"], 1495)
        self.assertEqual(self.meta()["fresh"], 5)
        self.assertEqual(self.alive()[-5:], sorted(new))
        self.assertEqual(sorted(d for d, _ in self.fallen()), sorted(self.base[:10]))
        self.assertTrue(all(t == 1001 * day for _, t in self.fallen()))

        # Ngày 3: lá rụng vẫn nằm đất (chưa quá 2 ngày); một lá rụng sống lại.
        self.run_day([self.base[0]] + self.base[10:] + new, 1002 * day)
        self.assertEqual(len(self.fallen()), 9)
        self.assertIn(self.base[0], self.alive())

        # Ngày 4 + 1 giây: quá 2 ngày kể từ lúc rụng -> xóa hẳn.
        self.run_day([self.base[0]] + self.base[10:] + new, 1003 * day + 1)
        self.assertEqual(self.fallen(), [])

    def test_broken_source_keeps_old_data(self) -> None:
        self.run_day(self.base, 86400)
        with self.assertRaises(SystemExit):
            self.run_day(self.base[:600], 2 * 86400)  # cụt hơn một nửa
        self.assertEqual(self.meta()["count"], 1500)
        self.assertEqual(self.fallen(), [])


if __name__ == "__main__":
    unittest.main()
