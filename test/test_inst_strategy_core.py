import unittest

import pandas as pd

import core.inst_strategy_core as ic


def make_df(days=40, closes=None, inst_buys=None, inst_sells=None, volumes=None):
    dates = pd.date_range("2025-01-01", periods=days, freq="B")
    closes = closes or [100.0] * days
    inst_buys = inst_buys or [100000] * days
    inst_sells = inst_sells or [100000] * days
    volumes = volumes or [3000000] * days
    df = pd.DataFrame({
        "date": dates,
        "open": closes, "high": [c * 1.02 for c in closes],
        "low": [c * 0.98 for c in closes], "close": closes,
        "volume": volumes,
        "inst_buy": inst_buys, "inst_sell": inst_sells,
        "ma20": [99.0] * days, "ma10": [99.0] * days,
    })
    return df


class TestMarkupConfirmation(unittest.TestCase):

    def setUp(self):
        self._saved = {k: getattr(ic, k) for k in (
            "LOOKBACK", "MIN_VOLUME_SHARES", "BUY_RATIO_THRESHOLD",
            "MAX_DIST_FROM_ACCUM", "MIN_BREAKOUT_FROM_ACCUM",
            "BUY_STREAK_DAYS", "VOLUME_CONFIRM")}
        ic.LOOKBACK = 10
        ic.MIN_VOLUME_SHARES = 2000
        ic.BUY_RATIO_THRESHOLD = 0.08
        ic.MAX_DIST_FROM_ACCUM = 0.15
        ic.MIN_BREAKOUT_FROM_ACCUM = 0.02
        ic.BUY_STREAK_DAYS = 2
        ic.VOLUME_CONFIRM = 1.3

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(ic, k, v)

    def _markup_df(self, **kw):
        days = 40
        closes = [100.0] * (days - 5) + [101, 102, 103, 104, 105]
        kw.setdefault("closes", closes)
        buys = [100000] * (days - 3) + [1000000] * 3
        kw.setdefault("inst_buys", buys)
        vols = [3000000] * (days - 1) + [4500000]
        kw.setdefault("volumes", vols)
        return make_df(days=days, **kw)

    def test_markup_confirmed_pass(self):
        """真拉抬：離成本 +5%、連續 3 日買超、放量 1.5x → 通過"""
        df = self._markup_df()
        ok, score = ic.check_momentum_entry({"2330": df}, "2330",
                                            pd.Timestamp(df["date"].iloc[-1]),
                                            accum_price=100.0)
        self.assertTrue(ok)

    def test_min_breakout_rejects_support(self):
        """護盤：貼著成本 +1%（未離開成本區）→ 拒絕"""
        df = make_df(days=40, closes=[100.0] * 35 + [100.5, 100.6, 100.7, 100.8, 101.0])
        ok, _ = ic.check_momentum_entry({"2330": df}, "2330",
                                        pd.Timestamp(df["date"].iloc[-1]),
                                        accum_price=100.0)
        self.assertFalse(ok)

    def test_buy_streak_rejects_single_day(self):
        """護盤：僅當日買超、前一日賣超（不連續）→ 拒絕"""
        days = 40
        closes = [100.0] * (days - 5) + [101, 102, 103, 104, 105]
        buys = [100000] * (days - 2) + [1000000, 100000]
        sells = [100000] * (days - 2) + [100000, 1500000]
        df = make_df(days=days, closes=closes, inst_buys=buys, inst_sells=sells)
        ok, _ = ic.check_momentum_entry({"2330": df}, "2330",
                                        pd.Timestamp(df["date"].iloc[-1]),
                                        accum_price=100.0)
        self.assertFalse(ok)

    def test_volume_confirm_rejects_low_vol(self):
        """護盤：量能不足（縮量防守）→ 拒絕"""
        days = 40
        closes = [100.0] * (days - 5) + [101, 102, 103, 104, 105]
        vols = [3000000] * (days - 1) + [2000000]
        df = make_df(days=days, closes=closes, volumes=vols)
        ok, _ = ic.check_momentum_entry({"2330": df}, "2330",
                                        pd.Timestamp(df["date"].iloc[-1]),
                                        accum_price=100.0)
        self.assertFalse(ok)

    def test_filters_disabled_returns_old_behavior(self):
        """三訊號全設 0（停用）→ 貼成本 1% 的護盤情境可通過（回舊版行為）"""
        ic.MIN_BREAKOUT_FROM_ACCUM = 0
        ic.BUY_STREAK_DAYS = 0
        ic.VOLUME_CONFIRM = 0
        days = 40
        closes = [100.0] * 35 + [100.5, 100.6, 100.7, 100.8, 101.0]
        buys = [100000] * (days - 5) + [1000000] * 5
        sells = [100000] * days
        df = make_df(days=days, closes=closes, inst_buys=buys, inst_sells=sells)
        ok, _ = ic.check_momentum_entry({"2330": df}, "2330",
                                        pd.Timestamp(df["date"].iloc[-1]),
                                        accum_price=100.0)
        self.assertTrue(ok)

    def test_no_accum_price_skips_markup(self):
        """無法人成本（一般模式）→ 拉抬確認不套用"""
        df = self._markup_df()
        ok, _ = ic.check_momentum_entry({"2330": df}, "2330",
                                        pd.Timestamp(df["date"].iloc[-1]),
                                        accum_price=None)
        self.assertTrue(ok)

    def test_market_filter_rejects(self):
        """大盤濾網不過（market_ok=False）→ 拒絕進場"""
        df = self._markup_df()
        ok, _ = ic.check_momentum_entry({"2330": df}, "2330",
                                        pd.Timestamp(df["date"].iloc[-1]),
                                        accum_price=100.0, market_ok=False)
        self.assertFalse(ok)

    def test_market_filter_default_allows(self):
        """未帶 market_ok（預設 True）→ 不影響既有行為"""
        df = self._markup_df()
        ok, _ = ic.check_momentum_entry({"2330": df}, "2330",
                                        pd.Timestamp(df["date"].iloc[-1]),
                                        accum_price=100.0)
        self.assertTrue(ok)


class TestExitDistributionSignals(unittest.TestCase):
    """方案 B：法人出貨前兆出場（買超反轉 / 高檔放量滯漲），與 MA10 並行"""

    def setUp(self):
        self._saved = {k: getattr(ic, k) for k in (
            "STOP_LOSS", "SELL_COST", "EXIT_REVERSAL", "EXIT_STALL_VOL",
            "EXIT_STALL_MIN_GAIN", "EXIT_STALL_MAX_CHG")}
        ic.STOP_LOSS = 0.10
        ic.SELL_COST = 0.004425
        ic.EXIT_REVERSAL = 0
        ic.EXIT_STALL_VOL = 0
        ic.EXIT_STALL_MIN_GAIN = 0.05
        ic.EXIT_STALL_MAX_CHG = 0.005

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(ic, k, v)

    def _call(self, price_info, close=110.0, buy_price=100.0):
        positions = {"2330": {"buy_price": buy_price, "shares": 1000,
                              "last_roll_date": None}}
        info = {"close": close, "ma10": 108.0, "volume": 1000000,
                "vol_avg20": 1000000, "chg": 0.01, "inst_net5": 0,
                "inst_buy": 0, "inst_sell": 0}
        info.update(price_info)
        trade_log = []
        proceeds, cost_basis, _ = ic.check_position_exit(
            "2330", positions, info, pd.Timestamp("2026-01-15"), 0, trade_log)
        return proceeds, trade_log

    def test_reversal_exit(self):
        """近5日累計淨買超但當日淨賣超（法人轉折第一天）→ 反轉出場"""
        ic.EXIT_REVERSAL = 1
        proceeds, log = self._call({"inst_net5": 50000, "inst_buy": 100, "inst_sell": 1000})
        self.assertGreater(proceeds, 0)
        self.assertIn("反轉", log[0]["reason"])

    def test_stall_exit(self):
        """獲利 10%、放量 2x、當日漲幅 0（高檔滯漲）→ 出場"""
        ic.EXIT_STALL_VOL = 1.3
        proceeds, log = self._call({"volume": 2000000, "chg": 0.0})
        self.assertGreater(proceeds, 0)
        self.assertIn("滯漲", log[0]["reason"])

    def test_no_distribution_signal_holds(self):
        """當日仍買超 + 量能正常 + 站上 MA10 → 續抱"""
        ic.EXIT_REVERSAL = 1
        ic.EXIT_STALL_VOL = 1.3
        proceeds, log = self._call({"inst_net5": 50000, "inst_buy": 1000,
                                    "inst_sell": 100, "volume": 800000})
        self.assertEqual(proceeds, 0)
        self.assertEqual(log, [])

    def test_reversal_disabled_holds(self):
        """反轉訊號停用（0）→ 回舊版行為：續抱"""
        proceeds, log = self._call({"inst_net5": 50000, "inst_buy": 100, "inst_sell": 1000})
        self.assertEqual(proceeds, 0)

    def test_stall_below_min_gain_holds(self):
        """獲利僅 2%（<5% 高檔門檻）→ 滯漲訊號不啟用（且站上 MA10 → 續抱）"""
        ic.EXIT_STALL_VOL = 1.3
        proceeds, log = self._call({"volume": 2000000, "chg": 0.0, "ma10": 101.0}, close=102.0)
        self.assertEqual(proceeds, 0)

    def test_stall_rising_day_holds(self):
        """放量但當日上漲 2%（非滯漲）→ 續抱"""
        ic.EXIT_STALL_VOL = 1.3
        proceeds, log = self._call({"volume": 2000000, "chg": 0.02})
        self.assertEqual(proceeds, 0)

    def test_ma10_trailing_still_works(self):
        """無出貨訊號但跌破 MA10 → 原移動停利仍生效"""
        proceeds, log = self._call({}, close=107.0)
        self.assertGreater(proceeds, 0)
        self.assertIn("MA10", log[0]["reason"])

    def test_hard_stop_takes_priority(self):
        """虧損 -11% → 硬性停損優先於出貨訊號"""
        ic.EXIT_REVERSAL = 1
        ic.EXIT_STALL_VOL = 1.3
        proceeds, log = self._call({"volume": 2000000, "chg": 0.0}, close=89.0)
        self.assertGreater(proceeds, 0)
        self.assertIn("停損", log[0]["reason"])


if __name__ == "__main__":
    unittest.main()
