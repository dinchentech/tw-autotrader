import os
import time
import requests
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 核心投資組合配置
# ==========================================
MY_PORTFOLIO = {
    "0050": "bollinger",  # 市值型 ETF -> 搭配布林反轉（恐慌抄底）
    "2330": "ma_cross",   # 台積電 -> 搭配均線交叉（順勢抱大波段）
    "2382": "breakout",   # 廣達 AI 股 -> 搭配唐奇安突破（抓主力發動）
    "2881": "vwap"        # 富邦金金融股 -> 搭配 VWAP 偏離（低於法人成本安心存）
}

USE_REAL_API = os.getenv("USE_REAL_API", "false").lower() == "true"

if USE_REAL_API:
    from data.kgi_real import KGIRealAPI as BrokerAPI
    print("🚀 【正式上線】使用真實凱基 API 進行自動化零股下單")
else:
    from data.kgi_mock import KGIMockAPI as BrokerAPI
    print("🧪 【模擬測試】使用凱基 API 模擬器（雙通知，不動用真錢）")

from strategies.vwap_strategy import VWAPDeviationStrategy
from strategies.ma_cross_strategy import MACrossStrategy
from strategies.bollinger_strategy import BollingerReverseStrategy
from strategies.breakout_strategy import BreakoutStrategy
from utils.telegram import send_trade_alert
from core.risk_manager import RiskManager

# ==========================================
# 2. 全新加入 LINE Notify 通知函式
# ==========================================
def send_line_notification(message):
    line_token = os.getenv("LINE_NOTIFY_TOKEN")
    if not line_token:
        return
    headers = {"Authorization": f"Bearer {line_token}"}
    payload = {"message": message}
    try:
        requests.post("https://line.me", headers=headers, data=payload, timeout=5)
    except Exception as e:
        print(f"❌ LINE 通知發送失敗: {e}")

def main():
    print("🚀 啟動 TW AutoTrader 多股多策略分流系統（全天候監控模式）")
    send_line_notification("\n🤖 TW AutoTrader 雲端主機已成功啟動！開始全天候監控台股...")
    
    broker = BrokerAPI()
    risk_manager = RiskManager(
        max_risk_per_trade=float(os.getenv("MAX_RISK_PER_TRADE", 0.01)),
        max_daily_loss=float(os.getenv("MAX_DAILY_LOSS", 0.05)),
        max_daily_trades=int(os.getenv("MAX_DAILY_TRADES", 10))
    )
    
    strategy_instances = {
        "vwap": VWAPDeviationStrategy(sigma_mult=1.5, rsi_period=5),
        "ma_cross": MACrossStrategy(fast_period=9, slow_period=21),
        "bollinger": BollingerReverseStrategy(window=20, std_dev=2.0),
        "breakout": BreakoutStrategy(lookback=20)
    }
    
    portfolio_history = {}
    
    # 初始化歷史資料
    for symbol, strat_name in MY_PORTFOLIO.items():
        df_init = broker.get_minute_bars(symbol, minutes=60) if USE_REAL_API else broker.get_historical_data(symbol, days=30)
        if df_init.empty:
            continue
        portfolio_history[symbol] = df_init
        print(f"✅ {symbol} 初始化成功 -> [{strat_name.upper()}]")
    
    while True:
        current_time = datetime.now()
        
        # 💡 判斷是否為台股開盤時間 (週一至週五 09:00 ~ 13:30)
        # 全天候執行時，非交易時間主機會自動靜音等待，不浪費運算資源
        is_trading_time = current_time.weekday() < 5 and (
            (current_time.hour == 9 and current_time.minute >= 0) or
            (9 < current_time.hour < 13) or
            (current_time.hour == 13 and current_time.minute <= 30)
        )
        
        if not is_trading_time and USE_REAL_API:
            # 實盤模式下，非非開盤時間每 10 分鐘檢查一次即可
            time.sleep(600)
            continue

        for symbol, strategy_name in MY_PORTFOLIO.items():
            if symbol not in portfolio_history:
                continue
                
            try:
                strategy = strategy_instances[strategy_name]
                accumulated_data = portfolio_history[symbol]
                
                if USE_REAL_API:
                    new_data = broker.get_minute_bars(symbol, minutes=1)
                    if not new_data.empty:
                        accumulated_data = pd.concat([accumulated_data, new_data])
                else:
                    current_price = broker.get_current_price(symbol)
                    new_row = pd.DataFrame({
                        'open': [current_price * 0.999], 'high': [current_price * 1.001],
                        'low': [current_price * 0.998], 'close': [current_price], 'volume': [5000]
                    }, index=[pd.Timestamp.now()])
                    accumulated_data = pd.concat([accumulated_data, new_row])
                
                if len(accumulated_data) > 100:
                    accumulated_data = accumulated_data.iloc[-100:]
                portfolio_history[symbol] = accumulated_data
                
                signal = strategy.trade(accumulated_data)
                current_price = accumulated_data['close'].iloc[-1]
                
                if signal != 0:
                    action = "BUY" if signal == 1 else "SELL"
                    
                    # ==========================================
                    # 【核心核心：自動化小資零股戰術】
                    # ==========================================
                    position_size = 0
                    
                    # 戰術 A & B：逆勢與均線（單筆大於 2000 元，自動算股數）
                    if strategy_name in ["bollinger", "vwap", "ma_cross"]:
                        target_amount = 2500 if strategy_name != "ma_cross" else 2200
                        position_size = int(target_amount // current_price)
                    
                    # 戰術 C：唐奇安突破（首次買 50 股，創高再追 50 股）
                    elif strategy_name == "breakout":
                        if action == "BUY":
                            position_size = 50  # 簡化風控，突破或創高皆自動追 50 股
                        else:
                            position_size = 100 # 賣出時出清部位
                    
                    if position_size <= 0:
                        continue
                        
                    if not risk_manager.check_trade_allowed(symbol, signal, current_price):
                        continue
                    
                    # 下單執行
                    if USE_REAL_API:
                        order_result = broker.place_order(symbol, action.lower(), position_size)
                        if "error" in order_result:
                            continue
                    else:
                        broker.place_order(symbol, action, position_size)
                    
                    risk_manager.log_trade(symbol, signal, current_price, position_size)
                    
                    # ==========================================
                    # 雙重同時通知（Telegram + LINE Notify）
                    # ==========================================
                    action_zh = "買進" if action == "BUY" else "賣出"
                    notice_msg = f"\n🔔 交易通知\n股票: {symbol}\n動作: {action_zh}\n價格: {current_price:.2f}\n股數: {position_size} 股\n策略: {strategy_name.upper()}"
                    
                    # 1. 發送 Telegram
                    send_trade_alert(symbol, action, current_price, position_size, strategy_name.upper())
                    # 2. 發送 LINE
                    send_line_notification(notice_msg)
                    
            except Exception as e:
                print(f"❌ {symbol} 錯誤: {e}")
                
        time.sleep(60)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()
