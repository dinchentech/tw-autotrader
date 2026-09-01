"""回歸測試：睡前/啟動持倉報告的參考市價必須反映真實收盤價。

背景：_build_holdings_message 以 performance.csv 最後一筆成交價當市價，
未平倉部位的最後一筆成交就是買進 → 參考市價永遠 = 成本均價、未實現損益 +0。
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class TestHoldingsMessagePrices(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_cwd = os.getcwd()
        os.chdir(self._tmp.name)
        logs = Path("logs")
        logs.mkdir()
        (logs / "holdings.json").write_text(
            json.dumps({"2357": 93}), encoding="utf-8")
        (logs / "stock_allocation.json").write_text(
            json.dumps({"2357": {"total_buy_cost": 798 * 93,
                                 "total_buy_shares": 93}}), encoding="utf-8")
        pd.DataFrame([
            {"timestamp": "2026-08-03 09:00:00", "symbol": "2357",
             "signal": "BUY", "price": 798.0, "quantity": 93, "action": "BUY"},
        ]).to_csv(logs / "performance.csv", index=False)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def _fake_twse(self, stock_id, start, end):
        return pd.DataFrame([
            {"date": pd.Timestamp("2026-08-13"), "open": 950.0, "high": 970.0,
             "low": 940.0, "close": 955.0, "volume": 100},
            {"date": pd.Timestamp("2026-08-14"), "open": 990.0, "high": 1000.0,
             "low": 985.0, "close": 996.0, "volume": 200},
        ])

    def test_sleep_report_uses_real_market_price(self):
        from core.live_notifications import _build_holdings_message
        with patch("core.inst_data._fetch_price_twse",
                   side_effect=self._fake_twse):
            msg = _build_holdings_message(pd, "3.9", "💤", "睡前持倉報告")
        # 市價應為 996（修復前顯示 798 = 成本），未實現損益 +18,414（修復前 +0）
        self.assertIn("參考市價 996", msg)
        self.assertIn("未實現損益 +18,414", msg)

    def test_closing_summary_uses_real_market_price(self):
        from core.live_notifications import send_closing_summary
        captured = {}
        with patch("core.inst_data._fetch_price_twse",
                   side_effect=self._fake_twse), \
             patch("core.live_notifications.notify_all",
                   side_effect=lambda m: captured.setdefault("msg", m)):
            send_closing_summary(pd, "3.9")
        self.assertIn("參考市價 996", captured["msg"])
        self.assertIn("未實現損益 +18,414", captured["msg"])

    def test_sleep_report_fallback_when_fetch_fails(self):
        from core.live_notifications import _build_holdings_message
        with patch("core.inst_data._fetch_price_twse",
                   return_value=pd.DataFrame()):
            msg = _build_holdings_message(pd, "3.9", "💤", "睡前持倉報告")
        # 抓價失敗時回退 CSV 最後成交價（既有行為），不中斷報告
        self.assertIn("參考市價 798", msg)


if __name__ == "__main__":
    unittest.main()


class TestRotationCapitalEstimate(unittest.TestCase):

    def _est(self, pc_lines, total_capital, stock_alloc):
        from core.live_notifications import estimate_rotation_capital
        return estimate_rotation_capital(pc_lines, total_capital, stock_alloc)

    def test_sufficient_capital(self):
        pc_lines = [
            'PC_3017={"strategy":"keep_wait","alloc":16.7,"max_entry_price":-1,"initial_buy_pct":1.0}',
            'PC_3653={"strategy":"keep_wait","alloc":16.7,"max_entry_price":-1,"initial_buy_pct":1.0}',
            'PC_2059={"strategy":"keep_wait","alloc":16.7,"max_entry_price":-1,"initial_buy_pct":1.0}',
        ]
        # 總資金 120 萬，已投入 50 萬 → 可用 70 萬 > 所需 60.1 萬
        r = self._est(pc_lines, 1200000, {'3017': {'total_buy_cost': 300000}})
        self.assertAlmostEqual(r['need'], 601200)
        self.assertAlmostEqual(r['available'], 900000)
        self.assertTrue(r['sufficient'])
        self.assertEqual(r['shortfall'], 0)

    def test_shortfall_after_rotation_release(self):
        pc_lines = [
            'PC_3017={"strategy":"keep_wait","alloc":16.7,"max_entry_price":-1,"initial_buy_pct":1.0}',
            'PC_3653={"strategy":"keep_wait","alloc":16.7,"max_entry_price":-1,"initial_buy_pct":1.0}',
            'PC_2059={"strategy":"keep_wait","alloc":16.7,"max_entry_price":-1,"initial_buy_pct":1.0}',
        ]
        # 已投入 90 萬（含 40 萬舊輪替股 3008，換股日將清倉回籠）
        stock_alloc = {
            '3017': {'total_buy_cost': 500000},
            '3008': {'total_buy_cost': 400000},
        }
        r = self._est(pc_lines, 1200000, stock_alloc)
        # 可用 = 120-90 = 30 萬；回籠 = 40 萬 → 合計 70 萬 > 60.1 萬
        self.assertAlmostEqual(r['available'], 300000)
        self.assertAlmostEqual(r['released'], 400000)
        self.assertTrue(r['sufficient'])
        self.assertEqual(r['shortfall'], 0)

    def test_insufficient_even_with_release(self):
        pc_lines = [
            'PC_3017={"strategy":"keep_wait","alloc":26.7,"max_entry_price":-1,"initial_buy_pct":1.0}',
            'PC_3653={"strategy":"keep_wait","alloc":16.7,"max_entry_price":-1,"initial_buy_pct":1.0}',
            'PC_2059={"strategy":"keep_wait","alloc":21.7,"max_entry_price":-1,"initial_buy_pct":1.0}',
        ]
        stock_alloc = {
            '3017': {'total_buy_cost': 700000},
            '3008': {'total_buy_cost': 100000},
        }
        r = self._est(pc_lines, 1200000, stock_alloc)
        # 所需 = 26.7+16.7+21.7 = 65.1% × 120萬 = 781,200
        self.assertAlmostEqual(r['need'], 781200)
        # 可用 = 120-80 = 40 萬；回籠 = 10 萬 → 合計 50 萬 < 78.1 萬
        self.assertFalse(r['sufficient'])
        self.assertAlmostEqual(r['shortfall'], 281200)

    def test_released_excludes_new_selection(self):
        # 舊持股若也在新選清單內（續抱），不計入回籠
        pc_lines = [
            'PC_3017={"strategy":"keep_wait","alloc":16.7,"max_entry_price":-1,"initial_buy_pct":1.0}',
            'PC_3653={"strategy":"keep_wait","alloc":16.7,"max_entry_price":-1,"initial_buy_pct":1.0}',
        ]
        stock_alloc = {
            '3017': {'total_buy_cost': 200000},
            '3653': {'total_buy_cost': 200000},
        }
        r = self._est(pc_lines, 1200000, stock_alloc)
        self.assertAlmostEqual(r['released'], 0, '續抱股不計入回籠')
        self.assertAlmostEqual(r['available'], 800000)
        self.assertTrue(r['sufficient'])

    def test_empty_pc_lines(self):
        r = self._est([], 1200000, {})
        self.assertEqual(r['need'], 0)
        self.assertAlmostEqual(r['available'], 1200000)
        self.assertTrue(r['sufficient'])
