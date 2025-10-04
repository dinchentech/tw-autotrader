# core/risk_manager.py
import os
import pandas as pd
from datetime import datetime, date
from utils.logger import init_log

class RiskManager:
    def __init__(self, max_risk_per_trade=0.01, max_daily_loss=0.05, max_daily_trades=5):
        """
        風險控管模組
        :param max_risk_per_trade: 單筆交易最大風險（佔總資金比例，預設 1%）
        :param max_daily_loss: 每日最大可接受虧損（預設 5%）
        :param max_daily_trades: 每日最大交易次數（預設 5 次）
        """
        self.max_risk_per_trade = max_risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_daily_trades = max_daily_trades
        self.initial_capital = float(os.getenv("INITIAL_CAPITAL", 1000000))  # 預設 100 萬台幣
        self.today = date.today()
        self.daily_loss = 0.0
        self.daily_trade_count = 0
        self.log_file = "logs/performance.csv"
        init_log()
    
    def _load_today_trades(self):
        """載入今日交易紀錄"""
        try:
            df = pd.read_csv(self.log_file)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            today_df = df[df['timestamp'].dt.date == self.today]
            self.daily_trade_count = len(today_df)
            # 計算今日累積虧損（簡化：假設每筆交易報酬已記錄）
            # 實務上應從部位計算，此處用模擬值
            self.daily_loss = max(0.0, -0.02)  # 模擬今日虧損 2%
        except (FileNotFoundError, pd.errors.EmptyDataError):
            self.daily_trade_count = 0
            self.daily_loss = 0.0
    
    def check_trade_allowed(self, symbol: str, signal: int, current_price: float) -> bool:
        """
        檢查是否允許交易
        """
        # 重新載入今日交易狀態
        self._load_today_trades()
        
        # 1. 檢查每日交易次數上限
        if self.daily_trade_count >= self.max_daily_trades:
            print(f"⚠️ 風險控管：今日交易次數已達上限 ({self.max_daily_trades})")
            return False
        
        # 2. 檢查每日最大虧損
        if self.daily_loss >= self.max_daily_loss:
            print(f"⚠️ 風險控管：今日虧損已達上限 ({self.max_daily_loss:.1%})")
            return False
        
        # 3. 檢查個股異常波動（漲跌停過濾）
        if self._is_limit_up_or_down(symbol, current_price):
            print(f"⚠️ 風險控管：{symbol} 已達漲跌停，跳過交易")
            return False
        
        # 4. 檢查流動性（成交量過低過濾）
        if self._is_low_liquidity(symbol):
            print(f"⚠️ 風險控管：{symbol} 流動性不足，跳過交易")
            return False
        
        return True
    
    def calculate_position_size(self, symbol: str, current_price: float, atr: float = None) -> int:
        """
        動態計算部位大小（基於風險）
        :return: 股數（需為 1000 的倍數）
        """
        # 風險金額 = 總資金 × 單筆風險比例
        risk_amount = self.initial_capital * self.max_risk_per_trade
        
        # 止損距離（簡化：使用 ATR 或固定百分比）
        if atr and atr > 0:
            stop_loss_distance = atr * 2  # 2倍ATR
        else:
            stop_loss_distance = current_price * 0.02  # 固定 2% 止損
        
        # 股數 = 風險金額 / 止損距離
        shares = risk_amount / stop_loss_distance
        
        # 調整為 1000 股的倍數（台股一張 = 1000 股）
        lots = int(shares // 1000)
        position_size = max(1000, lots * 1000)  # 至少 1 張
        
        print(f"📊 部位計算：{symbol} → {position_size // 1000} 張 (風險: {self.max_risk_per_trade:.1%})")
        return position_size
    
    def _is_limit_up_or_down(self, symbol: str, price: float) -> bool:
        """
        檢查是否漲跌停（簡化版：用前日收盤價 ±10%）
        """
        # 實務上應取得前日收盤價，此處用模擬
        prev_close = price / 1.05  # 模擬前日收盤
        limit_up = prev_close * 1.10
        limit_down = prev_close * 0.90
        return price >= limit_up or price <= limit_down
    
    def _is_low_liquidity(self, symbol: str) -> bool:
        """
        檢查流動性（簡化：用固定門檻）
        """
        # 實務上應檢查即時成交量，此處用模擬
        return symbol in ["6543", "4980"]  # 假設這些是低流動性股票

# 全域風險管理器實例
risk_manager = RiskManager(
    max_risk_per_trade=float(os.getenv("MAX_RISK_PER_TRADE", 0.01)),
    max_daily_loss=float(os.getenv("MAX_DAILY_LOSS", 0.05)),
    max_daily_trades=int(os.getenv("MAX_DAILY_TRADES", 5))
)