import pandas as pd
from FinMind.strategies import BackTest

class MACrossStrategy(BackTest):
    def __init__(self, fast_period=9, slow_period=21, atr_period=14, atr_threshold=0.005):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.atr_period = atr_period
        self.atr_threshold = atr_threshold
    
    def trade(self, stock_price):
        if len(stock_price) < self.slow_period:
            return 0
            
        ma_fast = stock_price['close'].rolling(self.fast_period).mean()
        ma_slow = stock_price['close'].rolling(self.slow_period).mean()
        
        # 計算 ATR（平均真實波動幅度）— 用來過濾盤整期假訊號
        high = stock_price['high']
        low = stock_price['low']
        close = stock_price['close']
        
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(self.atr_period).mean()
        
        # ATR 波動度過濾：ATR / 股價 < 門檻值 => 視為盤整，跳過訊號
        current_atr_ratio = atr.iloc[-1] / close.iloc[-1]
        is_volatile_enough = current_atr_ratio >= self.atr_threshold
        
        if ma_fast.iloc[-2] <= ma_slow.iloc[-2] and ma_fast.iloc[-1] > ma_slow.iloc[-1]:
            if is_volatile_enough:
                return 1
            else:
                return 0  # 波動不足，跳過
        
        elif ma_fast.iloc[-2] >= ma_slow.iloc[-2] and ma_fast.iloc[-1] < ma_slow.iloc[-1]:
            if is_volatile_enough:
                return -1
            else:
                return 0  # 波動不足，跳過
        
        else:
            return 0