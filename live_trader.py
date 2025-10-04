# live_trader.py
import os
import argparse
import time
from config.symbols import ALL_SYMBOLS
from core.strategy_engine import StrategyEngine
from core.risk_manager import risk_manager
from data.kgi_mock import KGIMockAPI
from utils.telegram import send_telegram_message
from utils.logger import log_trade

# 匯入所有策略
from strategies.vwap_deviation import vwap_deviation_strategy
from strategies.ma_cross import ma_cross_strategy
from strategies.bollinger import bollinger_reverse_strategy
from strategies.breakout import breakout_strategy

# 策略配置映射
STRATEGY_CONFIG = {
    "vwap": {
        "func": vwap_deviation_strategy,
        "params": {"sigma_mult": 1.5, "rsi_period": 5}
    },
    "ma_cross": {
        "func": ma_cross_strategy,
        "params": {"fast_period": 9, "slow_period": 21}
    },
    "bollinger": {
        "func": bollinger_reverse_strategy,
        "params": {"window": 20, "std_dev": 2.0, "rsi_period": 5}
    },
    "breakout": {
        "func": breakout_strategy,
        "params": {"lookback": 20, "atr_period": 14}
    }
}

def get_strategy_from_env_or_args():
    """從環境變數或命令列取得策略名稱"""
    parser = argparse.ArgumentParser(description='TW AutoTrader - Live Mode')
    parser.add_argument('--strategy', type=str, default=None,
                        help='選擇策略: vwap, ma_cross, bollinger, breakout')
    args = parser.parse_args()
    
    strategy_name = args.strategy or os.getenv("STRATEGY", "vwap")
    strategy_name = strategy_name.lower()
    
    if strategy_name not in STRATEGY_CONFIG:
        print(f"❌ 無效策略: {strategy_name}，使用預設 'vwap'")
        strategy_name = "vwap"
    
    return strategy_name

def main():
    strategy_name = get_strategy_from_env_or_args()
    config = STRATEGY_CONFIG[strategy_name]
    
    print("🚀 啟動 TW AutoTrader（模擬模式）")
    print(f"🎯 使用策略: {strategy_name}")
    print(f"⚙️  策略參數: {config['params']}")
    print(f"🛡️  風險控管: 單筆風險 {risk_manager.max_risk_per_trade:.1%} | 每日最大虧損 {risk_manager.max_daily_loss:.1%} | 每日最多 {risk_manager.max_daily_trades} 次")
    
    engine = StrategyEngine(config["func"], **config["params"])
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
                    # ===== 風險控管檢查 =====
                    if not risk_manager.check_trade_allowed(symbol, last_signal, last_price):
                        print(f"🛑 {symbol} 交易被風險控管攔截")
                        continue
                    
                    # 計算部位大小
                    position_size = risk_manager.calculate_position_size(symbol, last_price)
                    # =======================
                    
                    action = "買進" if last_signal == 1 else "賣出"
                    msg = f"{action} {symbol}！\n價格: {last_price:.2f}\n張數: {position_size // 1000}\n策略: {strategy_name.upper()}"
                    print(f"🔔 {msg}")
                    send_telegram_message(msg)
                    log_trade(symbol, last_signal, last_price)
                    
                    # ===== VWAP 視覺化 =====
                    if strategy_name == "vwap":
                        from utils.plotter import plot_vwap_chart
                        try:
                            plot_vwap_chart(df, symbol, last_signal)
                        except Exception as e:
                            print(f"❌ 繪圖失敗: {e}")
                    # =======================
                    
            except Exception as e:
                print(f"❌ {symbol} 處理錯誤: {e}")
        
        print("⏳ 等待下一分鐘...")
        time.sleep(60)

if __name__ == "__main__":
    main()