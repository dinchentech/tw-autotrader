"""測試：notify_order_failure — 交易失敗 TG 警示（每日每檔一次）"""
import unittest
from unittest.mock import MagicMock

from core.live_utils import notify_order_failure


class TestNotifyOrderFailure(unittest.TestCase):
    def test_sends_once_per_symbol_per_day(self):
        sent = []
        notified = {}
        notified = notify_order_failure("2330", "test error", notified, "2026-08-23", sent.append, action="買入")
        notified = notify_order_failure("2330", "test error 2", notified, "2026-08-23", sent.append, action="買入")
        self.assertEqual(len(sent), 1, '同檔同日只發一次')
        self.assertEqual(notified, {"2330": "2026-08-23"})
        self.assertIn("2330", sent[0])
        self.assertIn("買入失敗", sent[0])

    def test_sends_again_next_day(self):
        sent = []
        notified = {}
        notified = notify_order_failure("2330", "e1", notified, "2026-08-23", sent.append)
        notified = notify_order_failure("2330", "e2", notified, "2026-08-24", sent.append)
        self.assertEqual(len(sent), 2, '次日重新警示')

    def test_different_symbols_independent(self):
        sent = []
        notified = {}
        notify_order_failure("2330", "e", notified, "2026-08-23", sent.append)
        notify_order_failure("2317", "e", notified, "2026-08-23", sent.append)
        self.assertEqual(len(sent), 2)

    def test_buy_hint(self):
        sent = []
        notify_order_failure("2330", "e", {}, "2026-08-23", sent.append, action="買入")
        self.assertIn("自動重試至收盤", sent[0])

    def test_sell_hint(self):
        sent = []
        notify_order_failure("2330", "e", {}, "2026-08-23", sent.append, action="清倉賣出")
        self.assertIn("下一個交易日 09:00", sent[0])

    def test_custom_hint(self):
        sent = []
        notify_order_failure("2330", "e", {}, "2026-08-23", sent.append, action="交易", retry_hint="請檢查券商帳戶。")
        self.assertIn("請檢查券商帳戶", sent[0])

    def test_notify_fn_exception_safe(self):
        bad = MagicMock(side_effect=Exception("tg down"))
        notified = notify_order_failure("2330", "e", {}, "2026-08-23", bad)
        self.assertEqual(notified, {"2330": "2026-08-23"}, 'TG 失敗不影響去重狀態')


if __name__ == '__main__':
    unittest.main()
