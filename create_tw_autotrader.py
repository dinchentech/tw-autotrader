import os

# 專案結構與檔案內容
PROJECT_STRUCTURE = {
    "config": {
        "symbols.py": '''STOCKS = ["2330", "2454", "2317", "2881"]
INDEX_ETFS = ["0050", "0056", "00632R", "00646"]
ALL_SYMBOLS = STOCKS + INDEX_ETFS

def get_yahoo_suffix(symbol: str) -> str:
    if symbol == "00632R":
        return ".TWO"
    return ".TW"
''',
        "settings.py": '''# 全域設定
INITIAL_CAPITAL = 1000000  # 初始資金（台幣）
LOT_SIZE = 1000           # 每張股數
COMMISSION_RATE = 0.001425  # 手續費 0.1425%
'''
    },
    "data": {
        "yahoo_loader.py": '''import yfinance as yf
import pandas as pd

def load_historical_data(symbol: str, start: str = "2023-01-01"):
    """從 Yahoo Finance 載入資料（自動處理除權息）"""
    df = yf.download(symbol, start=start, auto_adjust=True)
    if df.empty:
        return df
    df = df.rename(columns={
        "Open": "open", "High": "high", 
        "Low": "low", "Close": "close", 
        "Volume": "volume"
    })
    return df
''',
        "kgi_mock.py": '''import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

class KGIMockAPI:
    def __init__(self):
        self.positions = {}
        self.order_count = 0
    
    def get_today_minute_data(self, symbol: str) -> pd.DataFrame:
        yf_symbol = symbol + (".TWO" if symbol == "00632R" else ".TW")
        today = datetime.now().strftime("%Y-%m-%d")
        df_daily = yf.download(yf_symbol, start=today, end=today, interval="1d")
        
        if df_daily.empty:
            df_daily = yf.download(yf_symbol, period="1d")
        if df_daily.empty:
            return None
            
        open_price = df_daily['Open'].iloc[0] if 'Open' in df_daily else df_daily['Close'].iloc[0]
        close_price = df_daily['Close'].iloc[0]
        high = df_daily['High'].iloc[0] if 'High' in df_daily else close_price * 1.02
        low = df_daily['Low'].iloc[0] if 'Low' in df_daily else close_price * 0.98
        volume = int(df_daily['Volume'].iloc[0] / 390) if 'Volume' in df_daily and not pd.isna(df_daily['Volume'].iloc[0]) else 1000
        
        minutes = 390
        prices = np.random.normal(loc=close_price, scale=(high-low)/10, size=minutes)
        prices = np.clip(prices, low, high)
        prices[0] = open_price
        prices[-1] = close_price
        
        df = pd.DataFrame({
            'timestamp': [datetime.now().replace(hour=9, minute=i, second=0, microsecond=0) for i in range(minutes)],
            'open': prices,
            'high': np.maximum(prices * 1.001, prices + 0.1),
            'low': np.minimum(prices * 0.999, prices - 0.1),
            'close': prices,
            'volume': [max(1, volume)] * minutes
        })
        df.set_index('timestamp', inplace=True)
        
        df['cum_value'] = (df['close'] * df['volume']).cumsum()
        df['cum_volume'] = df['volume'].cumsum()
        df['VWAP'] = df['cum_value'] / df['cum_volume']
        return df
    
    def place_order(self, symbol: str, side: str, quantity: int):
        self.order_count += 1
        print(f"📦 模擬下單 #{self.order_count}: {side} {symbol} {quantity} 股")
        return {"order_id": self.order_count, "status": "filled"}
'''
    },
    "strategies": {
        "__init__.py": "",
        "vwap_deviation.py": '''import pandas as pd
import numpy as np

def calculate_rsi(series, period=5):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def vwap_deviation_strategy(df: pd.DataFrame, sigma_mult=1.5, rsi_period=5, rsi_low=30, rsi_high=70) -> pd.DataFrame:
    df = df.copy()
    if 'VWAP' not in df.columns:
        df['VWAP'] = df['close']
    
    df['RSI'] = calculate_rsi(df['close'], rsi_period)
    df['Deviation'] = df['close'] - df['VWAP']
    df['Std'] = df['Deviation'].rolling(window=20, min_periods=1).std().fillna(0)
    
    df['signal'] = 0
    long_condition = (df['close'] < df['VWAP'] - sigma_mult * df['Std']) & (df['RSI'] < rsi_low)
    short_condition = (df['close'] > df['VWAP'] + sigma_mult * df['Std']) & (df['RSI'] > rsi_high)
    df.loc[long_condition, 'signal'] = 1
    df.loc[short_condition, 'signal'] = -1
    return df
''',
        "ma_cross.py": '''import pandas as pd

def ma_cross_strategy(df: pd.DataFrame, fast_period=9, slow_period=21) -> pd.DataFrame:
    df = df.copy()
    df['MA_Fast'] = df['close'].rolling(window=fast_period, min_periods=1).mean()
    df['MA_Slow'] = df['close'].rolling(window=slow_period, min_periods=1).mean()
    df['signal'] = 0
    df['prev_fast'] = df['MA_Fast'].shift(1)
    df['prev_slow'] = df['MA_Slow'].shift(1)
    golden_cross = (df['MA_Fast'] > df['MA_Slow']) & (df['prev_fast'] <= df['prev_slow'])
    death_cross = (df['MA_Fast'] < df['MA_Slow']) & (df['prev_fast'] >= df['prev_slow'])
    df.loc[golden_cross, 'signal'] = 1
    df.loc[death_cross, 'signal'] = -1
    df.drop(['prev_fast', 'prev_slow'], axis=1, inplace=True)
    return df
''',
        "bollinger.py": '''import pandas as pd

def bollinger_reverse_strategy(df: pd.DataFrame, window=20, std_dev=2.0, rsi_period=5, rsi_low=30, rsi_high=70) -> pd.DataFrame:
    df = df.copy()
    df['BB_Middle'] = df['close'].rolling(window=window, min_periods=1).mean()
    df['BB_Std'] = df['close'].rolling(window=window, min_periods=1).std()
    df['BB_Upper'] = df['BB_Middle'] + (std_dev * df['BB_Std'])
    df['BB_Lower'] = df['BB_Middle'] - (std_dev * df['BB_Std'])
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period, min_periods=1).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    df['signal'] = 0
    buy_condition = (df['close'] < df['BB_Lower']) & (df['RSI'] < rsi_low)
    sell_condition = (df['close'] > df['BB_Upper']) & (df['RSI'] > rsi_high)
    df.loc[buy_condition, 'signal'] = 1
    df.loc[sell_condition, 'signal'] = -1
    return df
''',
        "breakout.py": '''import pandas as pd

def breakout_strategy(df: pd.DataFrame, lookback=20, atr_period=14, atr_mult=1.5) -> pd.DataFrame:
    df = df.copy()
    df['Donchian_High'] = df['high'].rolling(window=lookback, min_periods=1).max()
    df['Donchian_Low'] = df['low'].rolling(window=lookback, min_periods=1).min()
    df['TR'] = df['high'] - df['low']
    df['TR'] = df[['TR', 'high', 'close']].apply(
        lambda row: max(row['TR'], abs(row['high'] - row['close']), abs(row['low'] - row['close'])), axis=1
    )
    df['ATR'] = df['TR'].rolling(window=atr_period, min_periods=1).mean()
    df['signal'] = 0
    buy_condition = (df['close'] > df['Donchian_High'].shift(1)) & (df['ATR'] > df['close'] * 0.01)
    sell_condition = (df['close'] < df['Donchian_Low'].shift(1)) & (df['ATR'] > df['close'] * 0.01)
    df.loc[buy_condition, 'signal'] = 1
    df.loc[sell_condition, 'signal'] = -1
    return df
'''
    },
    "core": {
        "strategy_engine.py": '''import pandas as pd

class StrategyEngine:
    def __init__(self, strategy_func, **strategy_params):
        self.strategy_func = strategy_func
        self.params = strategy_params

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.strategy_func(df, **self.params)
'''
    },
    "utils": {
        "telegram.py": '''import os
import requests

def send_telegram_message(message: str):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("⚠️ Telegram 未設定，跳過通知")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": f"🤖 TW AutoTrader\\n{message}", "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"❌ Telegram 發送失敗: {e}")
''',
        "logger.py": '''import os
import pandas as pd
from datetime import datetime

LOG_FILE = "logs/performance.csv"

def init_log():
    if not os.path.exists("logs"):
        os.makedirs("logs")
    if not os.path.exists(LOG_FILE):
        pd.DataFrame(columns=["timestamp", "symbol", "signal", "price", "action"]).to_csv(LOG_FILE, index=False)

def log_trade(symbol: str, signal: int, price: float):
    init_log()
    action = "BUY" if signal == 1 else "SELL"
    new_row = {"timestamp": datetime.now().isoformat(), "symbol": symbol, "signal": signal, "price": price, "action": action}
    df = pd.DataFrame([new_row])
    df.to_csv(LOG_FILE, mode='a', header=False, index=False)
    print(f"📝 已記錄交易: {action} {symbol} @ {price}")
'''
    },
    "": {
        "backtest.py": '''from config.symbols import ALL_SYMBOLS, get_yahoo_suffix
from core.strategy_engine import StrategyEngine
from strategies.vwap_deviation import vwap_deviation_strategy
from data.yahoo_loader import load_historical_data

def main():
    engine = StrategyEngine(vwap_deviation_strategy, sigma_mult=1.5, rsi_period=5)
    for symbol in ALL_SYMBOLS:
        yf_symbol = symbol + get_yahoo_suffix(symbol)
        print(f"📊 回測 {symbol} ({yf_symbol})...")
        df = load_historical_data(yf_symbol, start="2023-01-01")
        if df.empty:
            print("  → 資料為空，跳過")
            continue
        df = engine.run(df)
        total_trades = (df['signal'] != 0).sum()
        if total_trades == 0:
            print("  → 無交易訊號")
            continue
        win_trades = ((df['signal'] == 1) & (df['close'].shift(-1) > df['close'])).sum() + \\
                     ((df['signal'] == -1) & (df['close'].shift(-1) < df['close'])).sum()
        win_rate = win_trades / total_trades
        print(f"  → 交易次數: {total_trades}, 勝率: {win_rate:.1%}\\n")

if __name__ == "__main__":
    main()
''',
        "live_trader.py": '''import time
from config.symbols import ALL_SYMBOLS
from core.strategy_engine import StrategyEngine
from strategies.vwap_deviation import vwap_deviation_strategy
from data.kgi_mock import KGIMockAPI
from utils.telegram import send_telegram_message
from utils.logger import log_trade

def main():
    print("🚀 啟動 TW AutoTrader（模擬模式）")
    engine = StrategyEngine(vwap_deviation_strategy, sigma_mult=1.5, rsi_period=5)
    kgi = KGIMockAPI()
    while True:
        for symbol in ALL_SYMBOLS:
            try:
                df = kgi.get_today_minute_data(symbol)
                if df is None or len(df) < 10:
                    continue
                df = engine.run(df)
                last_signal = df['signal'].iloc[-1]
                last_price = df['close'].iloc[-1]
                if last_signal != 0:
                    action = "買進" if last_signal == 1 else "賣出"
                    msg = f"{action} {symbol}！\\n價格: {last_price:.2f}\\n策略: VWAP ±1.5σ + RSI"
                    print(f"🔔 {msg}")
                    send_telegram_message(msg)
                    log_trade(symbol, last_signal, last_price)
            except Exception as e:
                print(f"❌ {symbol} 處理錯誤: {e}")
        print("⏳ 等待下一分鐘...")
        time.sleep(60)

if __name__ == "__main__":
    main()
''',
        "requirements.txt": '''yfinance==0.2.37
pandas==2.2.1
numpy==1.26.4
python-telegram-bot==20.7
requests==2.31.0
''',
        "Dockerfile": '''FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "live_trader.py"]
''',
        "docker-compose.yml": '''version: '3.8'
services:
  tw-autotrader:
    build: .
    volumes:
      - ./logs:/app/logs
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
    restart: unless-stopped
''',
        ".env.example": '''TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
''',
        "README.md": '''# TW AutoTrader

台灣股市自動交易系統，支援個股與指數。

## 功能
- 四種策略：VWAP偏離、均線交叉、布林反轉、突破交易
- Telegram 通知
- 績效日誌
- 凱基 API 模擬器（無需真實 API）
- Docker 部署

## 快速開始
```bash
pip install -r requirements.txt
cp .env.example .env  # 填入 Telegram 設定
python backtest.py    # 回測
python live_trader.py # 模擬實盤