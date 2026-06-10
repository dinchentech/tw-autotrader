import unittest
import pandas as pd
import numpy as np
from strategies.vwap_strategy import VWAPDeviationStrategy
from strategies.ma_cross_strategy import MACrossStrategy
from strategies.bollinger_strategy import BollingerReverseStrategy
from strategies.breakout_strategy import BreakoutStrategy

class TestStrategies(unittest.TestCase):
    
    def setUp(self):
        """建立測試資料"""
        np.random.seed(42)  # 確保結果可重現
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        prices = 100 + np.random.randn(100).cumsum()
        
        self.test_data = pd.DataFrame({
            'open': prices * 0.995,
            'high': prices * 1.005,
            'low': prices * 0.990,
            'close': prices,
            'volume': np.random.randint(1000000, 5000000, 100)
        }, index=dates)
    
    def test_vwap_strategy(self):
        """測試 VWAP 策略"""
        strategy = VWAPDeviationStrategy(sigma_mult=1.0, rsi_period=5)
        signal = strategy.trade(self.test_data)
        self.assertIn(signal, [-1, 0, 1])
    
    def test_ma_cross_strategy(self):
        """測試均線交叉策略"""
        strategy = MACrossStrategy(fast_period=5, slow_period=10)
        signal = strategy.trade(self.test_data)
        self.assertIn(signal, [-1, 0, 1])
    
    def test_bollinger_strategy(self):
        """測試布林通道策略"""
        strategy = BollingerReverseStrategy(window=10, std_dev=1.5)
        signal = strategy.trade(self.test_data)
        self.assertIn(signal, [-1, 0, 1])
    
    def test_breakout_strategy(self):
        """測試突破策略"""
        strategy = BreakoutStrategy(lookback=10)
        signal = strategy.trade(self.test_data)
        self.assertIn(signal, [-1, 0, 1])
    
    def test_empty_data(self):
        """測試空資料"""
        empty_data = pd.DataFrame()
        strategy = VWAPDeviationStrategy()
        signal = strategy.trade(empty_data)
        self.assertEqual(signal, 0)

if __name__ == '__main__':
    unittest.main()