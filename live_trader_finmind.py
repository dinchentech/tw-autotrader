# live_trader_finmind.py (更新版)
import os
import time
import argparse
import pandas as pd
from datetime import datetime

# 選擇 API（真實或模擬）
USE_REAL_API = os.getenv("USE_REAL_API", "false").lower() == "true"

if USE_REAL_API:
    from data.kgi_real import KGIRealAPI as BrokerAPI
    print("🚀 使用真實凱基 API")
else:
    from data.kgi_mock import KGIMockAPI as BrokerAPI
    print("🧪 使用凱基 API 模擬器")

# 匯入策略
from strategies.vwap_strategy import VWAPDeviationStrategy
from strategies.ma_cross_strategy import MACrossStrategy
from strategies.bollinger_strategy import BollingerReverseStrategy
from strategies.breakout_strategy import BreakoutStrategy

# 匯入工具
from utils.telegram import send_trade_alert
from core.risk_manager import RiskManager

def run_live_trading(symbol: str = "2330", strategy_name: str = "vwap"):
    """實盤交易（含風險控管 + Telegram 通知）"""
    print(f"🚀 啟動 FinMind 實盤交易: {symbol} ({strategy_name})")
    
    # 初始化
    broker = BrokerAPI()
    risk_manager = RiskManager(
        max_risk_per_trade=float(os.getenv("MAX_RISK_PER_TRADE", 0.01)),
        max_daily_loss=float(os.getenv("MAX_DAILY_LOSS", 0.05)),
        max_daily_trades=int(os.getenv("MAX_DAILY_TRADES", 3))
    )
    
    # 選擇策略（從 .env 讀取參數，未設定則使用預設值）
    strategy_map = {
        "vwap": VWAPDeviationStrategy(
            sigma_mult=float(os.getenv("VWAP_SIGMA_MULT", 1.5)),
            rsi_period=int(os.getenv("VWAP_RSI_PERIOD", 5)),
        ),
        "ma_cross": MACrossStrategy(
            fast_period=int(os.getenv("MA_CROSS_FAST_PERIOD", 9)),
            slow_period=int(os.getenv("MA_CROSS_SLOW_PERIOD", 21)),
            atr_threshold=float(os.getenv("MA_CROSS_ATR_THRESHOLD", 0.005)),
        ),
        "bollinger": BollingerReverseStrategy(
            window=int(os.getenv("BOLLINGER_WINDOW", 20)),
            std_dev=float(os.getenv("BOLLINGER_STD_DEV", 2.0)),
            rsi_period=int(os.getenv("BOLLINGER_RSI_PERIOD", 5)),
        ),
        "breakout": BreakoutStrategy(
            lookback=int(os.getenv("BREAKOUT_LOOKBACK", 20)),
        )
    }
    
    if strategy_name not in strategy_map:
        raise ValueError(f"未知策略: {strategy_name}")
    
    strategy = strategy_map[strategy_name]
    
    # 獲取初始歷史資料
    if USE_REAL_API:
        accumulated_data = broker.get_minute_bars(symbol, minutes=60)
    else:
        accumulated_data = broker.get_historical_data(symbol, days=30)
    
    if accumulated_data.empty:
        print("❌ 無法取得初始資料，退出")
        return
    
    print("✅ 系統初始化完成，開始監控...")
    
    while True:
        try:
            # 取得最新資料
            if USE_REAL_API:
                new_data = broker.get_minute_bars(symbol, minutes=1)
                if not new_data.empty:
                    accumulated_data = pd.concat([accumulated_data, new_data])
                    if len(accumulated_data) > 100:
                        accumulated_data = accumulated_data.iloc[-100:]
            else:
                # 模擬新增資料
                current_price = broker.get_current_price(symbol)
                current_time = pd.Timestamp.now()
                new_row = pd.DataFrame({
                    'open': [current_price * 0.999],
                    'high': [current_price * 1.001],
                    'low': [current_price * 0.998],
                    'close': [current_price],
                    'volume': [100000]
                }, index=[current_time])
                accumulated_data = pd.concat([accumulated_data, new_row])
                if len(accumulated_data) > 100:
                    accumulated_data = accumulated_data.iloc[-100:]
            
            # 產生交易訊號
            signal = strategy.trade(accumulated_data)
            current_price = accumulated_data['close'].iloc[-1]
            
            if signal != 0:
                # 風險控管檢查
                if not risk_manager.check_trade_allowed(symbol, signal, current_price):
                    print(f"🛑 {symbol} 交易被風險控管攔截")
                    continue
                
                # 計算部位大小
                position_size = risk_manager.calculate_position_size(symbol, current_price)
                
                # 執行交易
                action = "BUY" if signal == 1 else "SELL"
                print(f"🔔 {action} 訊號: {symbol} @ {current_price:.2f} ({position_size} 股)")
                
                # 下單
                if USE_REAL_API:
                    order_result = broker.place_order(symbol, action.lower(), position_size)
                    if "error" in order_result:
                        continue
                else:
                    broker.place_order(symbol, action, position_size)
                
                # 記錄交易
                risk_manager.log_trade(symbol, signal, current_price, position_size)
                
                # Telegram 通知
                send_trade_alert(symbol, action, current_price, position_size, strategy_name.upper())
            
            time.sleep(60)  # 每分鐘檢查一次
            
        except KeyboardInterrupt:
            print("\n🛑 交易系統停止")
            break
        except Exception as e:
            print(f"❌ 系統錯誤: {e}")
            time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="2330", help="股票代號")
    parser.add_argument("--strategy", default="vwap", 
                       choices=["vwap", "ma_cross", "bollinger", "breakout"],
                       help="策略名稱")
    args = parser.parse_args()
    
    # 載入環境變數
    from dotenv import load_dotenv
    load_dotenv()
    
    run_live_trading(args.symbol, args.strategy)