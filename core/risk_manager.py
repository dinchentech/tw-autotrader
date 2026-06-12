# core/risk_manager.py
import os
import pandas as pd
from datetime import datetime, date

class RiskManager:
    def __init__(self, max_risk_per_trade=0.01, max_daily_loss=0.05, max_daily_trades=5):
        self.max_risk_per_trade = max_risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_daily_trades = max_daily_trades
        self.initial_capital = float(os.getenv("INITIAL_CAPITAL", 1000000))
        self.today = date.today()
        self.daily_loss = 0.0
        self.daily_trade_count = 0
        self.log_file = "logs/performance.csv"
        self._ensure_log_dir()
    
    def _ensure_log_dir(self):
        """確保日誌目錄存在"""
        import os
        if not os.path.exists("logs"):
            os.makedirs("logs")
    
    def _load_today_trades(self):
        """載入今日交易紀錄"""
        try:
            if not os.path.exists(self.log_file):
                self.daily_trade_count = 0
                self.daily_loss = 0.0
                return
            
            df = pd.read_csv(self.log_file)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            today_df = df[df['timestamp'].dt.date == self.today]
            self.daily_trade_count = len(today_df)
            
            # 計算今日累積虧損（簡化：假設每筆交易有 profit 欄位）
            # 實際應從真實部位計算
            if not today_df.empty:
                total_pnl = today_df.get('pnl', pd.Series([0])).sum()
                self.daily_loss = max(0.0, -total_pnl / self.initial_capital)
            else:
                self.daily_loss = 0.0
                
        except Exception as e:
            print(f"⚠️ 載入交易紀錄失敗: {e}")
            self.daily_trade_count = 0
            self.daily_loss = 0.0
    
    def check_trade_allowed(self, symbol: str, signal: int, current_price: float,
                            total_buy: float = 0, total_sell: float = 0) -> tuple:
        """檢查是否允許交易，回傳 (允許與否, 原因)

        total_buy: 累計買入總金額（用於判斷剩餘資金）
        total_sell: 累計賣出總金額
        """
        self._load_today_trades()
        
        # 資金充裕檢查：剩餘資金 > CAPITAL_CONTROL_LINE% 時，不限制交易次數
        capital_control_line = float(os.getenv("CAPITAL_CONTROL_LINE", "30"))
        remaining = self.initial_capital - total_buy + total_sell
        capital_ratio = remaining / self.initial_capital if self.initial_capital > 0 else 1.0
        
        if capital_ratio > capital_control_line / 100:
            pass  # 資金充裕，跳過交易次數檢查
        else:
            if self.daily_trade_count >= self.max_daily_trades:
                reason = "今日交易次數已達上限"
                print(f"⚠️ 風險控管：{reason} ({self.max_daily_trades})，剩餘資金 {capital_ratio:.1%}")
                return False, reason
        
        # 每日最大虧損
        if self.daily_loss >= self.max_daily_loss:
            reason = "今日虧損已達上限"
            print(f"⚠️ 風險控管：{reason} ({self.max_daily_loss:.1%})")
            return False, reason
        
        # 漲跌停過濾
        if self._is_limit_up_or_down(symbol, current_price):
            reason = f"{symbol} 已達漲跌停"
            print(f"⚠️ 風險控管：{reason}，跳過交易")
            return False, reason
        
        return True, ""
    
    def calculate_position_size(self, symbol: str, current_price: float) -> int:
        """動態計算部位大小"""
        risk_amount = self.initial_capital * self.max_risk_per_trade
        stop_loss_distance = current_price * 0.02  # 固定 2% 止損
        shares = risk_amount / stop_loss_distance
        lots = int(shares // 1000)
        position_size = max(1000, lots * 1000)  # 至少 1 張
        print(f"📊 部位計算：{symbol} → {position_size // 1000} 張 (風險: {self.max_risk_per_trade:.1%})")
        return position_size
    
    def _is_limit_up_or_down(self, symbol: str, price: float) -> bool:
        """檢查漲跌停（簡化版）"""
        # 實際應取得前日收盤價
        prev_close = price / 1.05
        limit_up = prev_close * 1.10
        limit_down = prev_close * 0.90
        return price >= limit_up or price <= limit_down
    
    def log_trade(self, symbol: str, signal: int, price: float, quantity: int):
        """記錄交易"""
        import csv
        from datetime import datetime
        
        action = "BUY" if signal == 1 else "SELL"
        timestamp = datetime.now().isoformat()
        
        # 確保 CSV 檔案有標頭
        file_exists = os.path.exists(self.log_file)
        with open(self.log_file, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists:
                writer.writerow(["timestamp", "symbol", "signal", "price", "quantity", "action"])
            writer.writerow([timestamp, symbol, signal, price, quantity, action])
        
        print(f"📝 已記錄交易: {action} {symbol} @ {price} ({quantity} 股)")