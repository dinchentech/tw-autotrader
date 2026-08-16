"""回歸測試：跨排程重複 symbol 的權重合併（撞股加倍，與回測一致）。

背景：dotenv 對重複 PC_ key 採後者覆蓋，兩個排程選中同一支股票時
權重會遺失（實盤資金留空）。load_portfolio_config 讀 .env 檔計算
出現次數，把 alloc 乘以次數（如 12.5×2=25），買入端依合併權重補足。
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config_loader import load_portfolio_config

_PC_TMPL = ('PC_{sym}={"strategy": "keep_wait", "alloc": 12.5, '
            '"max_entry_price": -1, "initial_buy_pct": 1.0}')


def pc(sym):
    return _PC_TMPL.replace("{sym}", sym)


class TestLoadPortfolioConfigDuplicates(unittest.TestCase):

    def _run(self, tmp: Path, pc_lines: list) -> dict:
        env = tmp / ".env"
        env.write_text("\n".join(pc_lines), encoding="utf-8")
        env_vars = {}
        for line in pc_lines:
            stripped = line.strip()
            if stripped.startswith("PC_") and "=" in stripped:
                sym, val = stripped[3:].split("=", 1)
                env_vars["PC_" + sym] = val
        with patch.dict(os.environ, env_vars, clear=False), \
             patch("core.config_loader.os.getenv", return_value=str(env)):
            return load_portfolio_config()

    def test_duplicate_symbol_alloc_multiplied(self):
        lines = [
            "# ── 排程 A ──",
            pc("2357"),
            pc("3231"),
            "",
            "# ── 排程 B ──",
            pc("2357"),
            pc("2395"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._run(Path(tmp), lines)
        self.assertAlmostEqual(cfg["2357"]["alloc"], 25.0)
        self.assertAlmostEqual(cfg["3231"]["alloc"], 12.5)
        self.assertAlmostEqual(cfg["2395"]["alloc"], 12.5)

    def test_no_duplicate_unchanged(self):
        lines = [
            "# ── 排程 A ──",
            pc("2357"),
            pc("3231"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._run(Path(tmp), lines)
        self.assertAlmostEqual(cfg["2357"]["alloc"], 12.5)
        self.assertAlmostEqual(cfg["3231"]["alloc"], 12.5)

    def test_duplicate_after_schedule_leave_reverts(self):
        lines = [
            "# ── 排程 A ──",
            pc("3653"),
            "",
            "# ── 排程 B ──",
            pc("2357"),
            pc("2880"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._run(Path(tmp), lines)
        self.assertAlmostEqual(cfg["2357"]["alloc"], 12.5)
        self.assertAlmostEqual(cfg["3653"]["alloc"], 12.5)

    def test_three_way_duplicate(self):
        lines = [
            "# ── 排程 A ──",
            pc("2357"),
            "",
            "# ── 排程 B ──",
            pc("2357"),
            pc("2395"),
            "",
            "# ── 排程 A 下季 ──",
            pc("2357"),
            pc("3653"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._run(Path(tmp), lines)
        self.assertAlmostEqual(cfg["2357"]["alloc"], 37.5)


if __name__ == "__main__":
    unittest.main()
