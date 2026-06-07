import pandas as pd
from FinMind.strategies import BackTest

class BreakoutStrategy(BackTest):
    def __init__(self, lookback=20, atr_period=14, atr_threshold=0.01):
        self.lookback = lookback
        self.atr_period = atr_period
        self.atr_threshold = atr_threshold
    
    def trade(self, stock_price):
        if len(stock_price) < self.lookback + 1:
            return 0
            
        high = stock_price['high']
        low = stock_price['low']
        close = stock_price['close']
        current_price = close.iloc[-1]

        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(self.atr_period).mean()
        current_atr_ratio = atr.iloc[-1] / current_price
        is_volatile_enough = current_atr_ratio >= self.atr_threshold
        
        # 使用前一日的 Donchian 通道
        donchian_high = high.rolling(self.lookback).max().iloc[-2]
        donchian_low = low.rolling(self.lookback).min().iloc[-2]
        
        if current_price > donchian_high and is_volatile_enough:
            return 1
        elif current_price < donchian_low and is_volatile_enough:
            return -1
        else:
            return 0