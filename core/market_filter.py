"""
大盤年線（MA200）過濾器
資料源：TWSE 公開 API（FMTQIK），免 token、免套件
抓不到時安全跳過（不過濾）

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
        """從 TWSE 公開 API 抓取加權指數日線（免 token、免套件）"""
        today = datetime.now()
        start_date = (today - timedelta(days=400)).strftime("%Y%m%d")
        
        try:
            import requests
            url = "https://www.twse.com.tw/en/exchangeReport/FMTQIK"
            params = {"response": "json", "date": start_date}
            resp = requests.get(url, params=params, headers={
                "User-Agent": "Mozilla/5.0",
            }, timeout=10)
            data = resp.json()
            rows = data.get("data", [])
            
            if rows and len(rows) >= 200:
                df = pd.DataFrame(rows, columns=[
                    "date", "volume", "value", "trades", "TAIEX", "change"
                ])
                df["close"] = pd.to_numeric(
                    df["TAIEX"].str.replace(",", ""), errors="coerce"
                )
                df = df.dropna(subset=["close"])
                print(f"✅ 大盤過濾：成功取得 TWSE 加權指數 ({len(df)} 筆)")
                return df
            else:
                print(f"⚠️  大盤過濾：TWSE 回傳 {len(rows)} 筆，不足 200")
        except Exception as e:
            print(f"⚠️  大盤過濾：TWSE 抓取失敗 ({e})")
        
        return None
