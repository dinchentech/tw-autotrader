import os
import time
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 核心組態：在此定義您的【小資零股投資組合】與【策略配置】
# ==========================================
MY_PORTFOLIO = {
    "0050": "bollinger",  # 市值型 ETF -> 搭配布林反轉（恐慌抄底）
    "2330": "ma_cross",   # 台積電 -> 搭配均線交叉（順勢抱大波段）
    "2382": "breakout",   # 廣達 AI 股 -> 搭配唐奇安突破（抓主力發動）
    "2881": "vwap"        # 富邦金金融股 -> 搭配 VWAP 偏離（低於法人成本安心存）
}

# 選擇 API（真實或模擬）
USE_REAL_API = os.getenv("USE_REAL_API", "false").lower() == "true"

if USE_REAL_API:
    from data.kgi_real import KGIRealAPI as BrokerAPI
    print("🚀 【正式上線】使用真實凱基 API 進行自動化零股下單")
else:
    from data.kgi_mock import KGIMockAPI as BrokerAPI
    print("🧪 【模擬測試】使用凱基 API 模擬器（發送 TG 通知而不動用真錢）")

# 匯入策略
from strategies.vwap_strategy import VWAPDeviationStrategy
from strategies.ma_cross_strategy import MACrossStrategy
from strategies.bollinger_strategy import BollingerReverseStrategy
from strategies.breakout_strategy import BreakoutStrategy

# 匯入工具與風控
from utils.telegram import send_trade_alert
from core.risk_manager import RiskManager

def main():
    print("🚀 啟動 TW AutoTrader 多股多策略分流系統")
    
    # 初始化經紀商 API
    broker = BrokerAPI()
    
    # 初始化風險控管模組 (讀取環境變數)
    risk_manager = RiskManager(
        max_risk_per_trade=float(os.getenv("MAX_RISK_PER_TRADE", 0.01)),
        max_daily_loss=float(os.getenv("MAX_DAILY_LOSS", 0.05)),
        max_daily_trades=int(os.getenv("MAX_DAILY_TRADES", 10)) # 多股同步，放寬每日上限
    )
    
    # 預先初始化所有策略實例與各自的最佳參數配置
    strategy_instances = {
        "vwap": VWAPDeviationStrategy(sigma_mult=1.5, rsi_period=5),
        "ma_cross": MACrossStrategy(fast_period=9, slow_period=21),
        "bollinger": BollingerReverseStrategy(window=20, std_dev=2.0),
        "breakout": BreakoutStrategy(lookback=20)
    }
    
    # 建立一個字典，用來存放每檔股票獨立的累積歷史 K 線資料
    portfolio_history = {}
    
    print("\n⏳ 正在下載初始化歷史資料...")
    for symbol, strat_name in MY_PORTFOLIO.items():
        if USE_REAL_API:
            df_init = broker.get_minute_bars(symbol, minutes=60)
        else:
            df_init = broker.get_historical_data(symbol, days=30)
        
        if df_init.empty:
            print(f"❌ 無法取得 {symbol} 的初始資料，系統跳過該標的")
            continue
            
        portfolio_history[symbol] = df_init
        print(f"✅ {symbol} 初始化成功 -> 配置策略: [{strat_name.upper()}]")
    
    print("\n🎯 系統初始化完成，正式進入每分鐘輪詢監控...")
    
    while True:
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{current_time_str}] 正在掃描投資組合中...")
        
        # 【核心改動】：使用 for 迴圈逐一掃描 my_portfolio 裡面的每一檔股票
        for symbol, strategy_name in MY_PORTFOLIO.items():
            if symbol not in portfolio_history:
                continue
                
            try:
                # 取得這檔股票綁定的策略物件
                strategy = strategy_instances[strategy_name]
                accumulated_data = portfolio_history[symbol]
                
                # 1. 獲取最新的一分鐘價格資料並塞入歷史表格中
                if USE_REAL_API:
                    new_data = broker.get_minute_bars(symbol, minutes=1)
                    if not new_data.empty:
                        accumulated_data = pd.concat([accumulated_data, new_data])
                else:
                    # 模擬即時最新報價
                    current_price = broker.get_current_price(symbol)
                    new_row = pd.DataFrame({
                        'open': [current_price * 0.999],
                        'high': [current_price * 1.001],
                        'low': [current_price * 0.998],
                        'close': [current_price],
                        'volume': [5000] # 模擬小額交易量
                    }, index=[pd.Timestamp.now()])
                    accumulated_data = pd.concat([accumulated_data, new_row])
                
                # 保持 DataFrame 長度，避免記憶體因時間拉長而溢出（DigitalOcean $6 方案必備優化）
                if len(accumulated_data) > 100:
                    accumulated_data = accumulated_data.iloc[-100:]
                
                # 回存更新後的資料表
                portfolio_history[symbol] = accumulated_data
                
                # 2. 讓策略對最新資料進行即時運算
                signal = strategy.trade(accumulated_data)
                current_price = accumulated_data['close'].iloc[-1]
                
                # 3. 檢查是否有買賣訊號觸發 (1=買進, -1=賣出)
                if signal != 0:
                    action = "BUY" if signal == 1 else "SELL"
                    print(f"🔍 {symbol} 偵測到 {strategy_name.upper()} 觸發 {action} 訊號！價格: {current_price:.2f}")
                    
                    # 風險控管模組審查
                    if not risk_manager.check_trade_allowed(symbol, signal, current_price):
                        print(f"🛑 {symbol} 的交易要求因違反風控規則（如今日虧損過大或次數過多）被攔截。")
                        continue
                    
                    # 風控自動計算部位大小（傳回應下單的零股股數）
                    position_size = risk_manager.calculate_position_size(symbol, current_price)
                    if position_size <= 0:
                        print(f"⚠️ {symbol} 計算出的下單股數為 0，取消下單。")
                        continue
                    
                    # 4. 執行下單動作
                    if USE_REAL_API:
                        # 實盤下單：此處傳入的是算好的「零股股數」
                        order_result = broker.place_order(symbol, action.lower(), position_size)
                        if "error" in order_result:
                            print(f"❌ {symbol} 券商下單失敗: {order_result['error']}")
                            continue
                    else:
                        # 模擬下單紀錄
                        broker.place_order(symbol, action, position_size)
                    
                    # 5. 成功下單後更新風控日誌並發送 Telegram 通報
                    risk_manager.log_trade(symbol, signal, current_price, position_size)
                    send_trade_alert(symbol, action, current_price, position_size, strategy_name.upper())
                    print(f"💰 成功送出訂單: {action} {symbol} 共 {position_size} 股！")
                    
            except Exception as e:
                print(f"❌ 處理股票 {symbol} 時發生錯誤: {e}")
                
        # 每一分鐘執行一次批次掃描
        time.sleep(60)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()  # 載入主機中的 .env 設定檔
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 交易系統已被手動停止。")
