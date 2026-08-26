"""測試：跨策略重疊防護 — 法人動能/全輪替選出的股票若已持有 → 通知+跳過

2026-08-25 規定：不同策略間的撞股才跳掉；全輪替自身（排程 A/B）撞股補足不變。
"""
import unittest
from unittest.mock import MagicMock

from core.live_utils import skip_if_overlap_held, should_skip_rotation_overlap


class TestSkipIfOverlapHeld(unittest.TestCase):
    """通用檢查：法人動能買入前，holdings 已持有 → 跳過"""

    def test_held_returns_true_and_notifies(self):
        """已持有 → 回傳 True（跳過）且發出通知"""
        notify = MagicMock()
        result = skip_if_overlap_held("2330", {"2330": 400, "2454": 100},
                                      notify, label="法人動能")
        self.assertTrue(result)
        notify.assert_called_once()
        msg = notify.call_args[0][0]
        self.assertIn("2330", msg)
        self.assertIn("400", msg)
        self.assertIn("法人動能", msg)

    def test_not_held_returns_false_no_notify(self):
        """未持有 → 回傳 False（可買）且不通知"""
        notify = MagicMock()
        result = skip_if_overlap_held("2330", {"2454": 100}, notify, label="法人動能")
        self.assertFalse(result)
        notify.assert_not_called()

    def test_zero_shares_treated_as_not_held(self):
        """holdings 中股數 0 → 視為未持有（可買）"""
        notify = MagicMock()
        result = skip_if_overlap_held("2330", {"2330": 0}, notify)
        self.assertFalse(result)
        notify.assert_not_called()

    def test_missing_symbol_returns_false(self):
        """holdings 中無此 symbol → 可買"""
        notify = MagicMock()
        result = skip_if_overlap_held("9999", {"2330": 100}, notify)
        self.assertFalse(result)

    def test_none_holdings_safe(self):
        """holdings 為 None → 不崩潰、視為未持有"""
        notify = MagicMock()
        result = skip_if_overlap_held("2330", None, notify)
        self.assertFalse(result)

    def test_notify_exception_safe(self):
        """通知失敗 → 不影響跳過判斷"""
        def boom(*a, **k):
            raise RuntimeError("TG down")
        result = skip_if_overlap_held("2330", {"2330": 5}, boom, label="法人動能")
        self.assertTrue(result, '通知失敗仍應跳過（防重疊優先）')


class TestShouldSkipRotationOverlap(unittest.TestCase):
    """全輪替買入檢查：同策略撞股補足不變，跨策略撞股才跳掉"""

    def test_own_rotation_position_kept(self):
        """pyramid_tracker 有記錄（全輪替自己持有）→ 不跳過（保留補足）"""
        notify = MagicMock()
        result = should_skip_rotation_overlap(
            "2330", {"2330": 400}, {"2330": {"buy_count": 1}}, notify)
        self.assertFalse(result, '全輪替自身撞股 → 維持補足')
        notify.assert_not_called()

    def test_rotation_managed_kept_even_tracker_empty(self):
        """全輪替管理的股票（max_entry_price=-1，is_rotation_managed=True）
        即使 pyramid_tracker 空（重啟後）→ 不跳過（2026-08-26 實盤 bug）"""
        notify = MagicMock()
        result = should_skip_rotation_overlap(
            "2395", {"2395": 121}, {}, notify, is_rotation_managed=True)
        self.assertFalse(result, '全輪替自己的倉位不應跳過')
        notify.assert_not_called()

    def test_other_strategy_held_skips(self):
        """無 tracker 記錄且非全輪替管理但 holdings 有 → 其他策略持有 → 跳過+通知"""
        notify = MagicMock()
        result = should_skip_rotation_overlap(
            "2330", {"2330": 400}, {}, notify)
        self.assertTrue(result, '跨策略撞股 → 跳過')
        notify.assert_called_once()

    def test_not_held_returns_false(self):
        """未持有 → 可買"""
        notify = MagicMock()
        result = should_skip_rotation_overlap("2330", {"2454": 100}, {}, notify)
        self.assertFalse(result)
        notify.assert_not_called()

    def test_tracker_zero_buy_count_treated_as_other(self):
        """tracker 有 entry 但 buy_count=0（已賣光）→ 視為其他策略持有 → 跳過"""
        notify = MagicMock()
        result = should_skip_rotation_overlap(
            "2330", {"2330": 100}, {"2330": {"buy_count": 0}}, notify)
        self.assertTrue(result)

    def test_none_tracker_safe(self):
        """pyramid_tracker 為 None → 不崩潰"""
        notify = MagicMock()
        result = should_skip_rotation_overlap("2330", {"2330": 5}, None, notify)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
