# strategies/ma_cross.py
import pandas as pd

def ma_cross_strategy(df: pd.DataFrame, fast_period=9, slow_period=21) -> pd.DataFrame:
    """
    均線交叉策略：
    - 當快線（MA9）上穿慢線（MA21）→ 買進
    - 當快線下穿慢線 → 賣出
    """
    df = df.copy()
    
    # 計算均線
    df['MA_Fast'] = df['close'].rolling(window=fast_period, min_periods=1).mean()
    df['MA_Slow'] = df['close'].rolling(window=slow_period, min_periods=1).mean()
    
    # 訊號：1=買, -1=賣
    df['signal'] = 0
    df['prev_fast'] = df['MA_Fast'].shift(1)
    df['prev_slow'] = df['MA_Slow'].shift(1)
    
    # 金叉：今日快 > 慢，昨日快 <= 慢
    golden_cross = (df['MA_Fast'] > df['MA_Slow']) & (df['prev_fast'] <= df['prev_slow'])
    # 死叉：今日快 < 慢，昨日快 >= 慢
    death_cross = (df['MA_Fast'] < df['MA_Slow']) & (df['prev_fast'] >= df['prev_slow'])
    
    df.loc[golden_cross, 'signal'] = 1
    df.loc[death_cross, 'signal'] = -1
    
    # 清理臨時欄位
    df.drop(['prev_fast', 'prev_slow'], axis=1, inplace=True)
    
    return df