"""
Keep & Wait Strategy — DCA 低接策略

不分析技術指標，只做三件事：
1. 初始進場（買入 KW_INITIAL_SHARES 股）
2. 跌 X% 就加碼 KW_ADD_SHARES 股（最多 KW_MAX_ADDITIONS 次）
3. 漲 Y% 就全部賣出（停利）

所有狀態追蹤由 live_trader_multi.py 的 pyramid_tracker 管理，
此 class 僅負責提供配置常數與停利訊號檢查。
"""
from FinMind.strategies import BackTest


class KeepWaitStrategy(BackTest):
    def __init__(self, take_profit_pct=0.15):
        self.take_profit_pct = take_profit_pct

    def trade(self, stock_price):
        """
        此策略的買賣時機由主程式根據 pyramid_tracker 狀態決定。
        這裡只保留供未來擴充（如追蹤市場情緒）。
        """
        return 0  # 訊號完全由主程式的 DCA 邏輯控制
