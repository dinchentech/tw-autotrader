from FinMind.strategies import BackTest

class MACrossStrategy(BackTest):
    def __init__(self, fast_period=9, slow_period=21):
        self.fast_period = fast_period
        self.slow_period = slow_period
    
    def trade(self, stock_price):
        if len(stock_price) < self.slow_period:
            return 0
            
        ma_fast = stock_price['close'].rolling(self.fast_period).mean()
        ma_slow = stock_price['close'].rolling(self.slow_period).mean()
        
        if ma_fast.iloc[-2] <= ma_slow.iloc[-2] and ma_fast.iloc[-1] > ma_slow.iloc[-1]:
            return 1
        elif ma_fast.iloc[-2] >= ma_slow.iloc[-2] and ma_fast.iloc[-1] < ma_slow.iloc[-1]:
            return -1
        else:
            return 0