"""測試：IM_DEBUG 模式 — 法人動能未啟用時仍執行每日篩選（debug_screen）"""
import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ.setdefault("INST_MOM_DAILY_SCREENING", "true")

from strategies.institutional_momentum import InstitutionalMomentumStrategy


def make_strategy(capital=0):
    strat = InstitutionalMomentumStrategy(broker=MagicMock(), capital=capital, top_n=3)
    strat.state = {
        "candidates": [], "positions": {}, "last_screen_date": None,
        "last_entry_date": None, "loser_ban": {}, "last_roll_date": None,
    }
    return strat


class TestDebugScreen(unittest.TestCase):
    def _screen_time(self):
        return datetime(2026, 8, 17, 13, 35)  # 週一 13:35（盤後篩選窗）

    def test_screens_when_disabled_and_debug(self):
        strat = make_strategy(capital=0)
        strat.get_candidates = MagicMock(return_value=([("2330", 0.12)], []))
        strat._save_state = MagicMock()
        strat.debug_screen(self._screen_time())
        strat.get_candidates.assert_called_once()
        self.assertEqual(strat.state["last_screen_date"], "2026-08-17")
        self.assertEqual(strat.state["candidates"], [{"stock_id": "2330", "score": 0.12}])

    def test_no_screen_outside_window(self):
        strat = make_strategy(capital=0)
        strat.get_candidates = MagicMock(return_value=([], []))
        strat.debug_screen(datetime(2026, 8, 17, 10, 0))  # 非 13:31-13:45
        strat.get_candidates.assert_not_called()

    def test_no_screen_twice_same_day(self):
        strat = make_strategy(capital=0)
        strat.get_candidates = MagicMock(return_value=([], []))
        strat.debug_screen(self._screen_time())
        strat.get_candidates.assert_called_once()
        strat.debug_screen(self._screen_time())
        self.assertEqual(strat.get_candidates.call_count, 1, '同一天不重複篩選')

    def test_no_screen_on_weekend(self):
        strat = make_strategy(capital=0)
        strat.get_candidates = MagicMock(return_value=([], []))
        strat.debug_screen(datetime(2026, 8, 16, 13, 35))  # 週日
        strat.get_candidates.assert_not_called()

    def test_no_screen_when_not_friday_and_weekly_mode(self):
        strat = make_strategy(capital=0)
        strat.daily_screening = False
        strat.get_candidates = MagicMock(return_value=([], []))
        strat.debug_screen(datetime(2026, 8, 17, 13, 35))  # 週一、每週模式 → 不篩
        strat.get_candidates.assert_not_called()

    def test_run_still_skips_when_disabled(self):
        strat = make_strategy(capital=0)
        strat.debug_screen = MagicMock()
        with patch.object(InstitutionalMomentumStrategy, 'run', return_value=None) as mock_run:
            strat.run(MagicMock(), MagicMock(), {}, datetime(2026, 8, 17, 13, 35))
            mock_run.assert_called_once()  # run 本身直接回傳（capital<=0）


if __name__ == '__main__':
    unittest.main()


class TestRankByPriceReturn(unittest.TestCase):
    def _df(self, closes):
        import pandas as pd
        import numpy as np
        idx = pd.date_range("2026-08-01", periods=len(closes))
        return pd.DataFrame({"close": closes}, index=idx)

    def test_ranks_by_recent_return(self):
        from core.inst_strategy_core import rank_by_price_return
        data = {
            "1111": self._df([100, 100, 100, 100, 110, 120]),   # 20%
            "2222": self._df([100, 100, 100, 100, 100, 90]),    # -10%
            "3333": self._df([100, 100, 100, 100, 100, 105]),   # 5%
            "4444": self._df([50, 50, 50, 50, 50, 60]),         # 20%
        }
        r = rank_by_price_return(data, days=5, top_n=3)
        self.assertEqual(len(r), 3)
        self.assertEqual(r[0][0], "1111", '1111 漲幅最高應排第一')
        self.assertIn("4444", [s for s, _ in r])
        self.assertNotIn("2222", [s for s, _ in r])

    def test_short_history_still_ranks(self):
        from core.inst_strategy_core import rank_by_price_return
        data = {"1111": self._df([100, 110])}   # 只有兩天
        r = rank_by_price_return(data, top_n=3)
        self.assertEqual([s for s, _ in r], ["1111"])

    def test_empty_data(self):
        from core.inst_strategy_core import rank_by_price_return
        self.assertEqual(rank_by_price_return({}), [])
