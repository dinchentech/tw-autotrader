from FinMind.strategies import BackTest

class BreakoutStrategy(BackTest):
    def __init__(self, lookback=20):
        self.lookback = lookback
    
    def trade(self, stock_price):
        if len(stock_price) < self.lookback + 1:
            return 0
            
        high = stock_price['high']
        low = stock_price['low']
        current_price = stock_price['close'].iloc[-1]
        
        # 使用前一日的 Donchian 通道
        donchian_high = high.rolling(self.lookback).max().iloc[-2]
        donchian_low = low.rolling(self.lookback).min().iloc[-2]
        
        if current_price > donchian_high:
            return 1
        elif current_price < donchian_low:
            return -1
        else:
            return 0