# user_strategies.py - 用戶自定義策略檔案
"""
此檔案供使用者定義 Group 1 和 Group 2 的備用策略。
使用者可自由修改此檔案，無需更動 live_trader_multi.py。

使用方式：
1. 修改下方的策略函式
2. 在 .env 中設定 G1_STRATEGY_1、G1_STRATEGY_2、G2_STRATEGY_1、G2_STRATEGY_2
3. 在 PORTFOLIO 設定中使用 g1_strategy_1、g1_strategy_2、g2_strategy_1、g2_strategy_2

例如：
PORTFOLIO=0050:g1_strategy_1,2330:g1_strategy_2
G1_STRATEGY_1=my_custom_ma_cross
G1_STRATEGY_2=my_custom_rsi
"""

import pandas as pd


# ==========================================
# Group 1 備用策略 1 (g1_strategy_1) — 價格區間策略
# ==========================================
def price_band(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    Group 1 備用策略 1 - 價格區間低接高賣策略

    當價格低於買入價時發出買進訊號，高於賣出價時發出賣出訊號。
    適用於基本面看好、設定固定價格區間來回操作的股票（如 十銓 250↓買/280↑賣）。

    Parameters:
    - df: 包含 OHLCV 資料的 DataFrame
    - kwargs: 策略參數
        - buy_price: 買進觸發價 (預設 250)，現價 ≤ buy_price 時 signal=1
        - sell_price: 賣出觸發價 (預設 280)，現價 ≥ sell_price 時 signal=-1

    Returns:
    - DataFrame with 'signal' column (1=BUY, -1=SELL, 0=HOLD)
    """
    buy_price = kwargs.get('buy_price', 250)
    sell_price = kwargs.get('sell_price', 280)

    signals = pd.Series(0, index=df.index)

    buy_signal = df['close'] <= buy_price
    sell_signal = df['close'] >= sell_price

    signals[buy_signal] = 1
    signals[sell_signal] = -1

    return pd.DataFrame({'signal': signals}, index=df.index)


# ==========================================
# Group 1 備用策略 2 (g1_strategy_2) — 週 KD 黃金交叉策略
# ==========================================
def weekly_kd_golden_cross(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    Group 1 備用策略 2 - 週 KD 黃金交叉策略

    將日線資料重新採樣為週線，計算週 KD(9,3,3)，在低檔黃金交叉時買進，
    死亡交叉時賣出。一年約 1~2 次訊號，適合中長期波段操作。

    Parameters:
    - df: 包含 OHLCV 資料的 DataFrame（日線）
    - kwargs: 策略參數
        - k_period: KD 週期 (預設 9)
        - k_threshold: K 值低檔門檻，低於此值才考慮買進 (預設 30)
        - d_period: K/D 平滑期數 (預設 3)

    Returns:
    - DataFrame with 'signal' column (1=BUY, -1=SELL, 0=HOLD)
    """
    import numpy as np

    k_period = kwargs.get('k_period', 9)
    k_threshold = kwargs.get('k_threshold', 30)
    d_period = kwargs.get('d_period', 3)

    signals = pd.Series(0, index=df.index)

    if len(df) < 60:
        return pd.DataFrame({'signal': signals}, index=df.index)

    # ── 日線 → 週線聚合（以最後交易日為週索引） ──
    df_copy = df.copy()
    df_copy['week_label'] = df_copy.index.to_period('W')

    weekly_records = []
    for week_label, group in df_copy.groupby('week_label'):
        if len(group) == 0:
            continue
        weekly_records.append({
            'last_day': group.index[-1],
            'open': group['open'].iloc[0],
            'high': group['high'].max(),
            'low': group['low'].min(),
            'close': group['close'].iloc[-1],
            'volume': group['volume'].sum(),
        })

    weekly = pd.DataFrame(weekly_records).set_index('last_day')

    if len(weekly) < k_period + d_period + 5:
        return pd.DataFrame({'signal': signals}, index=df.index)

    # ── 計算週 KD(9,3,3) ──
    low_n = weekly['low'].rolling(k_period).min()
    high_n = weekly['high'].rolling(k_period).max()

    rsv = pd.Series(50.0, index=weekly.index)
    mask = (high_n - low_n).abs() > 1e-8
    rsv[mask] = 100.0 * (weekly.loc[mask, 'close'] - low_n[mask]) / (high_n[mask] - low_n[mask])
    rsv = rsv.clip(0, 100)

    # K = SMA(RSV, d_period), D = SMA(K, d_period)
    k = rsv.rolling(d_period).mean()
    d = k.rolling(d_period).mean()

    # ── 週線訊號 ──
    buy_signal = (
        (k > d) &
        (k.shift(1) <= d.shift(1)) &
        (k < k_threshold)
    )
    sell_signal = (
        (k < d) &
        (k.shift(1) >= d.shift(1))
    )

    # ── 週線訊號映射回日線（放在該週最後一個交易日） ──
    for idx in weekly.index[buy_signal]:
        if idx in signals.index:
            signals.loc[idx] = 1

    for idx in weekly.index[sell_signal]:
        if idx in signals.index:
            signals.loc[idx] = -1

    df['signal'] = signals
    df.drop(columns=['week_label'], inplace=True, errors='ignore')
    return df


# ==========================================
# Group 2 備用策略 1 (g2_strategy_1)
# ==========================================
def my_custom_momentum(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    Group 2 備用策略 1 - 自訂動能策略

    預設：價格動能策略 - 基於過去 N 日的漲跌幅判斷

    Parameters:
    - df: 包含 OHLCV 資料的 DataFrame
    - kwargs: 策略參數
        - lookback: 回看天數 (預設 5)
        - threshold: 漲跌幅門檻百分比 (預設 3)

    Returns:
    - DataFrame with 'signal' column (1=BUY, -1=SELL, 0=HOLD)
    """
    lookback = kwargs.get('lookback', 5)
    threshold = kwargs.get('threshold', 3)  # 百分比

    signals = pd.Series(0, index=df.index)

    if len(df) >= lookback + 1:
        # 計算 N 日漲跌幅
        pct_change = df['close'].pct_change(lookback) * 100

        # 動能策略訊號
        signals[(pct_change >= threshold) & (pct_change.shift(1) < threshold)] = 1  # 動能轉正
        signals[(pct_change <= -threshold) & (pct_change.shift(1) > -threshold)] = -1  # 動能轉負

    return pd.DataFrame({'signal': signals}, index=df.index)


# ==========================================
# Group 2 備用策略 2 (g2_strategy_2)
# ==========================================
def my_custom_volume_price(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    Group 2 備用策略 2 - 自訂量價策略

    預設：量價配合策略 - 價格上漲 + 成交量放大 = 買進

    Parameters:
    - df: 包含 OHLCV 資料的 DataFrame
    - kwargs: 策略參數
        - ma_period: 價格均線週期 (預設 10)
        - volume_ma_period: 成交量均線週期 (預設 10)
        - volume_mult: 成交量放大倍數 (預設 1.5)

    Returns:
    - DataFrame with 'signal' column (1=BUY, -1=SELL, 0=HOLD)
    """
    ma_period = kwargs.get('ma_period', 10)
    volume_ma_period = kwargs.get('volume_ma_period', 10)
    volume_mult = kwargs.get('volume_mult', 1.5)

    signals = pd.Series(0, index=df.index)

    if len(df) >= ma_period:
        # 價格均線
        price_ma = df['close'].rolling(window=ma_period, min_periods=1).mean()
        # 成交量均線
        volume_ma = df['volume'].rolling(window=volume_ma_period, min_periods=1).mean()

        # 量價配合訊號
        # 價格站穩均線 + 成交量放大 = 買進
        buy_condition = (df['close'] > price_ma) & (df['volume'] >= volume_ma * volume_mult)
        buy_entry = buy_condition & (~buy_condition.shift(1).fillna(False))

        # 價格跌破均線 = 賣出
        sell_condition = df['close'] < price_ma
        sell_entry = sell_condition & (~sell_condition.shift(1).fillna(False))

        signals[buy_entry] = 1
        signals[sell_entry] = -1

    return pd.DataFrame({'signal': signals}, index=df.index)


# ==========================================
# 用戶策略映射表（請勿修改此行以下）
# ==========================================
# 此映射表讓 live_trader_multi.py 知道如何載入你的自訂策略
# 左邊是你在 .env 中使用的名稱，右邊是上方定義的函式名稱
USER_STRATEGY_MAP = {
    # Group 1 備用策略
    'g1_strategy_1': price_band,
    'g1_strategy_2': weekly_kd_golden_cross,

    # Group 2 備用策略
    'g2_strategy_1': my_custom_momentum,
    'g2_strategy_2': my_custom_volume_price,
}

# 若要自訂名稱映射，可在 .env 中設定：
# G1_STRATEGY_1=my_custom_ma_cross
# G1_STRATEGY_2=my_custom_rsi
# G2_STRATEGY_1=my_custom_momentum
# G2_STRATEGY_2=my_custom_volume_price