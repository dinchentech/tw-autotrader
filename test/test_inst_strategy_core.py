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


if __name__ == "__main__":
    unittest.main()
