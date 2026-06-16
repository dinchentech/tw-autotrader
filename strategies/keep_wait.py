"""
Keep & Wait Strategy — function-based version

此策略不做技術分析，signal 永遠為 0。
實際的 DCA 低接 / 停利邏輯完全由 live_trader_multi.py 的 pyramid_tracker 管理。
"""

import pandas as pd


def keep_wait_strategy(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    Keep & Wait — signal 固定為 0。

    買賣時機由主程式根據 pyramid_tracker 狀態決定，
    此函式僅保留供未來擴充（如追蹤市場情緒）。
    """
    df = df.copy()
    df['signal'] = 0
    return df
