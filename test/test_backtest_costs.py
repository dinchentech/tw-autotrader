"""回歸測試：每季全輪替回測 (backtest_selector) 必須計入交易成本。

Bug 背景：backtest_selector 買賣僅以收盤價計算 shares/市值，未扣
手續費 (0.1425%) 與證交稅 (0.3%)，導致回測績效高估；
成本只在 TWO_BY_TWO 模式有計入。
"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import stock_selector_grid as ssg


class TestBacktestTradingCosts(unittest.TestCase):

    def setUp(self):
        self._start, self._end = ssg.START_DATE, ssg.END_DATE
        ssg.START_DATE = "2023-07-01"
        ssg.END_DATE = "2024-06-30"
        self.params = dict(ssg.DEFAULT_PARAMS)
        self.params["use_ma_filter"] = False

    def tearDown(self):
        ssg.START_DATE, ssg.END_DATE = self._start, self._end

    def _price_df(self, first_half_close, second_half_close):
        """2024-03-29(含)前收 first_half_close，之後收 second_half_close。"""
        dates = pd.bdate_range("2023-07-01", "2024-06-30")
        closes = [first_half_close if d <= pd.Timestamp("2024-03-29")
                  else second_half_close for d in dates]
        return pd.DataFrame({
            "open": closes, "high": [x * 1.01 for x in closes],
            "low": [x * 0.99 for x in closes], "close": closes,
            "volume": [1_000_000] * len(dates),
        }, index=dates)

    def test_quarterly_backtest_deducts_costs(self):
        """100 → 110 單季漲 10%：應扣買進手續費 + 賣出(手續費+證交稅)。

        期望終值 = 500,000 × (110/100) / 1.001425 × 0.995575 ≈ 546,787，
        而非未扣成本的 550,000。
        """
        data = {"2330": self._price_df(100.0, 110.0)}
        bt = ssg.backtest_selector(data, self.params, top_n=1,
                                   quarter_months=(3, 6))
        final = bt["final_value"]
        self.assertLess(final, 550_000, "未扣交易成本的總額 550,000 不應出現")
        self.assertAlmostEqual(final, 546_787, delta=500)
        self.assertAlmostEqual(bt["total_return"], (546_787 - 500_000) / 500_000,
                               delta=0.001)


if __name__ == "__main__":
    unittest.main()
