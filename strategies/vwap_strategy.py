import pandas as pd
import numpy as np
from FinMind.strategies import BackTest

class VWAPDeviationStrategy(BackTest):
    def __init__(self, sigma_mult=1.5, rsi_period=5, rsi_low=30, rsi_high=70):
        self.sigma_mult = sigma_mult
        self.rsi_period = rsi_period
        self.rsi_low = rsi_low
        self.rsi_high = rsi_high
    
    def calculate_rsi(self, prices):
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def trade(self, stock_price: pd.DataFrame):
        if len(stock_price) < 20:
            return 0
            
        # 計算 VWAP（使用 close 近似）
        vwap = stock_price['close'].mean()
        current_price = stock_price['close'].iloc[-1]
        deviations = stock_price['close'] - vwap
        std = np.std(deviations)
        
        # 計算 RSI
        rsi_series = self.calculate_rsi(stock_price['close'])
        rsi = rsi_series.iloc[-1] if not rsi_series.empty else 50
        
        # 訊號邏輯
        if current_price < vwap - self.sigma_mult * std and rsi < self.rsi_low:
            return 1
        elif current_price > vwap + self.sigma_mult * std and rsi > self.rsi_high:
            return -1
        else:
            return 0