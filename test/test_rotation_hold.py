"""測試：core/rotation_hold.py — MIN_DRAW_BACK 實盤回撤保護邏輯"""
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from core.rotation_hold import (
    compute_equity, realized_pnl, should_hold, is_rotation_buy,
    PEAK_FILE, HOLD_FILE,
)


class TestIsRotationBuy(unittest.TestCase):
    ROT_CFG = {'strategy': 'keep_wait', 'max_entry_price': -1, 'alloc': 12.5}

    def test_rotation_day_keep_wait_mep_minus1(self):
        self.assertTrue(is_rotation_buy(self.ROT_CFG, True))

    def test_not_rotation_day(self):
        self.assertFalse(is_rotation_buy(self.ROT_CFG, False))

    def test_non_rotation_strategy(self):
        cfg = {'strategy': 'bollinger', 'max_entry_price': -1}
        self.assertFalse(is_rotation_buy(cfg, True))

    def test_keep_wait_without_mep_minus1(self):
        cfg = {'strategy': 'keep_wait', 'max_entry_price': 100}
        self.assertFalse(is_rotation_buy(cfg, True))
        self.assertFalse(is_rotation_buy({'strategy': 'keep_wait'}, True))

    def test_mep_bad_value_safe(self):
        self.assertFalse(is_rotation_buy({'strategy': 'keep_wait', 'max_entry_price': 'x'}, True))

    def test_explicit_strategy_override(self):
        self.assertTrue(is_rotation_buy(self.ROT_CFG, True, strategy='keep_wait'))
        self.assertFalse(is_rotation_buy(self.ROT_CFG, True, strategy='vwap'))


class TestShouldHold(unittest.TestCase):
    def test_disabled_never_holds(self):
        hold, state = should_hold(0, 800000, 1000000, {"extended": False})
        self.assertFalse(hold)
        self.assertFalse(state["extended"])

    def test_drawdown_below_threshold_first_time_holds(self):
        hold, state = should_hold(20, 790000, 1000000, {"extended": False})
        self.assertTrue(hold, '回撤 -21% > 20% 應延後換股')
        self.assertTrue(state["extended"])

    def test_drawdown_still_deep_second_time_forces_rotation(self):
        hold, state = should_hold(20, 780000, 1000000, {"extended": True})
        self.assertFalse(hold, '已延長一季仍超標 → 強制換股（最多延長一季）')
        self.assertFalse(state["extended"])

    def test_drawdown_recovered_rotates_normally(self):
        hold, state = should_hold(20, 850000, 1000000, {"extended": True})
        self.assertFalse(hold, '回撤恢復到門檻內 → 照常換股')
        self.assertFalse(state["extended"])

    def test_negative_equity_or_peak_safe(self):
        hold, _ = should_hold(20, -100, 1000000, {})
        self.assertFalse(hold)
        hold2, _ = should_hold(20, 800000, 0, {})
        self.assertFalse(hold2)


class TestEquity(unittest.TestCase):
    def test_realized_pnl(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write("timestamp,symbol,signal,price,quantity,action\n")
            f.write("2026-01-01,2330,buy,100,100,BUY\n")
            f.write("2026-01-02,2330,buy,110,50,BUY\n")
            f.write("2026-02-01,2330,sell,150,120,SELL\n")
            csv_path = f.name
        try:
            self.assertEqual(realized_pnl(csv_path), 150 * 120 - 100 * 100 - 110 * 50)
        finally:
            os.unlink(csv_path)

    def test_realized_pnl_missing_file(self):
        self.assertEqual(realized_pnl('/nonexistent/perf.csv'), 0.0)

    def test_compute_equity(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write("timestamp,symbol,signal,price,quantity,action\n")
            f.write("2026-01-01,2330,buy,100,100,BUY\n")
            csv_path = f.name
        try:
            holdings = {"2330": 100}
            prices = {"2330": 120}
            equity = compute_equity(500000, holdings, prices, csv_path)
            self.assertEqual(equity, 500000 - 100 * 100 + 100 * 120)
        finally:
            os.unlink(csv_path)


class TestCheckRotationHold(unittest.TestCase):
    def _tmp_env(self):
        tmp = tempfile.mkdtemp()
        peak = os.path.join(tmp, 'equity_peak.json')
        hold = os.path.join(tmp, 'rotation_hold.json')
        json.dump({'peak': 1000000, 'updated_at': '2026-01-01'}, open(peak, 'w'))
        return {'PEAK': peak, 'HOLD': hold}

    def test_first_skip_then_force_rotation(self):
        env = self._tmp_env()
        broker = MagicMock()
        broker.get_current_price.return_value = 100.0
        holdings = {"2330": 10, "2317": 10, "2454": 10, "2882": 10}

        from core.rotation_hold import check_rotation_hold
        with unittest.mock.patch('core.rotation_hold.PEAK_FILE', env['PEAK']), \
             unittest.mock.patch('core.rotation_hold.HOLD_FILE', env['HOLD']):
            hold, dd = check_rotation_hold(20, 500000, broker, holdings, '2026-08-31')
            # equity = 500000 + 0(無績效檔) + 40*100 = 504000 → dd ≈ -49.6% < -20%
            self.assertTrue(hold, '首次深回撤應延後換股')
            self.assertAlmostEqual(dd, 504000 / 1000000 - 1)
            self.assertTrue(json.load(open(env['HOLD']))['extended'], '狀態應記錄已延長')

        with unittest.mock.patch('core.rotation_hold.PEAK_FILE', env['PEAK']), \
             unittest.mock.patch('core.rotation_hold.HOLD_FILE', env['HOLD']):
            hold2, _ = check_rotation_hold(20, 500000, broker, holdings, '2026-09-30')
            self.assertFalse(hold2, '已延長一季仍超標 → 強制換股')
            self.assertFalse(json.load(open(env['HOLD']))['extended'], '強制換股後狀態重置')

    def test_recovered_after_skip_rotates_normally(self):
        env = self._tmp_env()
        broker = MagicMock()
        broker.get_current_price.return_value = 300.0  # 市值 12000 → equity 512000 → dd -48.8%... 仍深
        holdings = {"2330": 10, "2317": 10, "2454": 10, "2882": 10}

        from core.rotation_hold import check_rotation_hold
        with unittest.mock.patch('core.rotation_hold.PEAK_FILE', env['PEAK']), \
             unittest.mock.patch('core.rotation_hold.HOLD_FILE', env['HOLD']):
            hold, _ = check_rotation_hold(20, 500000, broker, holdings, '2026-08-31')
            self.assertTrue(hold)

        broker.get_current_price.return_value = 30000.0  # 市值 120萬 → equity 170萬 > peak → 恢復
        with unittest.mock.patch('core.rotation_hold.PEAK_FILE', env['PEAK']), \
             unittest.mock.patch('core.rotation_hold.HOLD_FILE', env['HOLD']):
            hold2, dd2 = check_rotation_hold(20, 500000, broker, holdings, '2026-09-30')
            self.assertFalse(hold2, '回撤恢復後照常換股')
            self.assertGreater(dd2, -0.20)
            self.assertFalse(json.load(open(env['HOLD']))['extended'])


if __name__ == '__main__':
    unittest.main()
