import pandas as pd
from FinMind.strategies import BackTest

class BollingerReverseStrategy(BackTest):
    def __init__(self, window=20, std_dev=2.0, rsi_period=5, rsi_low=30, rsi_high=70):
        self.window = window
        self.std_dev = std_dev
        self.rsi_period = rsi_period
        self.rsi_low = rsi_low
        self.rsi_high = rsi_high
    
    def calculate_rsi(self, prices):
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def trade(self, stock_price):
        if len(stock_price) < self.window:
            return 0
            
        close = stock_price['close']
        middle = close.rolling(self.window).mean().iloc[-1]
        std = close.rolling(self.window).std().iloc[-1]
        upper = middle + self.std_dev * std
        lower = middle - self.std_dev * std
        current_price = close.iloc[-1]
        
        rsi_series = self.calculate_rsi(close)
        rsi = rsi_series.iloc[-1] if not rsi_series.empty else 50
        
        if current_price < lower and rsi < self.rsi_low:
            return 1
        elif current_price > upper and rsi > self.rsi_high:
            return -1
        else:
            return 0