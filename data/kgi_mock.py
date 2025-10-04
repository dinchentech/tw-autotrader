import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class KGIMockAPI:
    def __init__(self):
        self.positions = {}
        self.order_count = 0
    
    def get_today_minute_data(self, symbol: str) -> pd.DataFrame:
        # 模擬：用 Yahoo 日線 + 隨機分鐘波動
        yf_symbol = symbol + (".TWO" if symbol == "00632R" else ".TW")
        today = datetime.now().strftime("%Y-%m-%d")
        df_daily = yf.download(yf_symbol, start=today, end=today, interval="1d")
        
        if df_daily.empty:
            # 若無今日資料，用昨日
            df_daily = yf.download(yf_symbol, period="1d")
        
        if df_daily.empty:
            return None
            
        open_price = df_daily['Open'].iloc[0]
        close_price = df_daily['Close'].iloc[0]
        high = df_daily['High'].iloc[0]
        low = df_daily['Low'].iloc[0]
        volume = int(df_daily['Volume'].iloc[0] / 390)  # 平均每分鐘
        
        # 生成 390 分鐘模擬資料
        minutes = 390
        prices = np.random.normal(loc=close_price, scale=(high-low)/10, size=minutes)
        prices = np.clip(prices, low, high)
        prices[0] = open_price
        prices[-1] = close_price
        
        df = pd.DataFrame({
            'timestamp': [datetime.now().replace(hour=9, minute=i) for i in range(minutes)],
            'open': prices,
            'high': prices * 1.001,
            'low': prices * 0.999,
            'close': prices,
            'volume': [volume] * minutes
        })
        df.set_index('timestamp', inplace=True)
        
        # 計算真實 VWAP（累積）
        df['cum_value'] = (df['close'] * df['volume']).cumsum()
        df['cum_volume'] = df['volume'].cumsum()
        df['VWAP'] = df['cum_value'] / df['cum_volume']
        return df
    
    def place_order(self, symbol: str, side: str, quantity: int):
        self.order_count += 1
        print(f"📦 模擬下單 #{self.order_count}: {side} {symbol} {quantity} 股")
        return {"order_id": self.order_count, "status": "filled"}