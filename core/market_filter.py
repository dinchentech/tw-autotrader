"""
大盤年線（MA200）過濾器
FinMind 為主要資料源，抓不到時安全跳過（不過濾）

用法：
    filter = MarketTrendFilter()
    if filter.is_above_ma200():
        # 可以買進
"""
import os
import pandas as pd
from datetime import datetime, timedelta

class MarketTrendFilter:
    def __init__(self):
        self.cache = None
        self.cache_date = None
    
    def is_above_ma200(self) -> bool:
        """回傳 True = 指數在年線之上（可以買），False = 指數跌破年線（跳過買進）"""
        try:
            index_data = self._fetch_tw_index()
            if index_data is None or len(index_data) < 200:
                print("⚠️  大盤過濾：資料不足 200 筆，跳過過濾")
                return True
            
            close = index_data['close']
            ma200 = close.rolling(200).mean().iloc[-1]
            current_close = close.iloc[-1]
            above = current_close > ma200
            
            if above:
                print(f"📈 大盤過濾：指數 {current_close:.0f} > MA200 {ma200:.0f}，允許買進")
            else:
                print(f"📉 大盤過濾：指數 {current_close:.0f} < MA200 {ma200:.0f}，跳過買進")
            
            return above
            
        except Exception as e:
            print(f"⚠️  大盤過濾異常 ({e})，跳過過濾")
            return True
    
    def _fetch_tw_index(self):
        """從 FinMind 抓取加權指數日線"""
        today = datetime.now()
        # 抓最近 1 年資料確保有足夠的 200 日線
        start_date = (today - timedelta(days=400)).strftime("%Y-%m-%d")
        
        try:
            from finmind.data_loader import FinMindDataLoader
            api = FinMindDataLoader()
            df = api.taiwan_stock_daily(stock_id="TX00", start_date=start_date)
            if df is not None and not df.empty and 'close' in df.columns:
                print(f"✅ 大盤過濾：成功取得 FinMind 加權指數 ({len(df)} 筆)")
                return df
        except ImportError:
            print("⚠️  大盤過濾：FinMind 套件未安裝，嘗試 FinMind API...")
        except Exception as e:
            print(f"⚠️  大盤過濾：FinMind 抓取失敗 ({e})")
        
        # 備援：直接呼叫 FinMind REST API
        try:
            import requests
            import json
            url = f"https://api.finmindtrade.com/api/v4/data"
            params = {
                "dataset": "TaiwanStockIndex",
                "data_id": "TX00",
                "start_date": start_date,
                "token": os.getenv("FINMIND_API_TOKEN", ""),
            }
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("data"):
                df = pd.DataFrame(data["data"])
                df.rename(columns={"index_value": "close"}, inplace=True)
                df['close'] = pd.to_numeric(df['close'], errors='coerce')
                print(f"✅ 大盤過濾：成功取得 FinMind REST 加權指數 ({len(df)} 筆)")
                return df
        except Exception as e2:
            print(f"⚠️  大盤過濾：FinMind REST 也失敗 ({e2})")
        
        return None
