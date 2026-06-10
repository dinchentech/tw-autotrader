import os
import time
import requests
import pandas as pd
from datetime import datetime, date
import json
from pathlib import Path

# ==========================================
# 1. 核心投資組合配置（從 .env 讀取）
#    格式：PORTFOLIO=0050:bollinger,2330:ma_cross,2382:breakout,2881:vwap
#    未設定則使用下方預設值
# ==========================================
def load_portfolio() -> dict:
    raw = os.getenv("PORTFOLIO")
    if raw:
        portfolio = {}
        for pair in raw.split(","):
            pair = pair.strip()
            if ":" not in pair:
                continue
            symbol, strategy = pair.split(":", 1)
            portfolio[symbol.strip()] = strategy.strip().lower()
        if portfolio:
            return portfolio
    # 預設投資組合（.env 未設定時生效）
    return {
        "0050": "bollinger",
        "2330": "ma_cross",
        "2382": "breakout",
        "2881": "vwap",
    }

MY_PORTFOLIO = load_portfolio()

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
from utils.telegram import send_trade_alert, send_telegram_message
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
        requests.post("https://notify-api.line.me/api/notify", headers=headers, data=payload, timeout=5)
    except Exception as e:
        print(f"❌ LINE 通知發送失敗: {e}")

def main():
    print("🚀 啟動 TW AutoTrader 多股多策略分流系統（全天候監控模式）")
    send_line_notification("\n🤖 TW AutoTrader 雲端主機已成功啟動！開始全天候監控台股...")
    send_telegram_message("✅ *TW AutoTrader* 多股多策略系統已啟動\n📈 監控中: " + ", ".join(f"{s}[{p}]" for s, p in MY_PORTFOLIO.items()))

    # ==========================================
    # 股票數量上限檢查（GCP e2-micro 建議值）
    # 超過 15 支時提出警告，但不強制停止
    # ==========================================
    MAX_RECOMMENDED_STOCKS = 15
    if len(MY_PORTFOLIO) > MAX_RECOMMENDED_STOCKS:
        print(f"⚠️  警告：投資組合中有 {len(MY_PORTFOLIO)} 支股票，超過建議上限 {MAX_RECOMMENDED_STOCKS} 支。")
        print(f"   由於程式是順序處理，股票過多會導致每輪循環時間拉長，訊號失去即時性。")
        print(f"   建議將股票數降至 {MAX_RECOMMENDED_STOCKS} 支以下，或將程式改為非同步並行架構。")

    # ==========================================
    # 每月預算控管
    # ==========================================
    budget_file = Path("logs/monthly_budget.json")
    
    def load_monthly_budget() -> dict:
        """載入本月已使用預算"""
        current_month = datetime.now().strftime("%Y-%m")
        if budget_file.exists():
            try:
                data = json.loads(budget_file.read_text())
                if data.get("month") == current_month:
                    return data.get("spent", {})
            except:
                pass
        return {}
    
    def save_monthly_budget(spent: dict):
        """儲存本月已使用預算"""
        current_month = datetime.now().strftime("%Y-%m")
        budget_file.write_text(json.dumps({
            "month": current_month,
            "spent": spent
        }, indent=2))
    
    def check_monthly_budget(strategy_name: str, cost: float, spent: dict) -> bool:
        """檢查本月預算是否足夠，回傳 True = 可以下單"""
        budget_key = f"MONTHLY_BUDGET_{strategy_name.upper()}"
        monthly_limit = float(os.getenv(budget_key, 0))
        if monthly_limit <= 0:
            return True  # 0 = 不限制
        current_spent = spent.get(strategy_name, 0)
        if current_spent + cost > monthly_limit:
            print(f"⚠️  每月預算已達上限：{strategy_name} "
                  f"本月已花 {current_spent:.0f} / {monthly_limit:.0f} 元，跳過此筆交易")
            return False
        return True
    
    def update_monthly_spending(strategy_name: str, cost: float, spent: dict):
        """扣減預算並儲存"""
        spent[strategy_name] = spent.get(strategy_name, 0) + cost
        save_monthly_budget(spent)
    
    # 初始化每月預算
    budget_spent = load_monthly_budget()

    # ==========================================
    # 大盤年線過濾器
    # ==========================================
    from core.market_filter import MarketTrendFilter
    market_filter = MarketTrendFilter()

    # ==========================================
    # 金字塔加碼追蹤（記錄每檔股票的買進次數與價格）
    # ==========================================
    pyramid_tracker = {}  # { symbol: { buy_count: 0, last_buy_price: 0 } }

    broker = BrokerAPI()
    risk_manager = RiskManager(
        max_risk_per_trade=float(os.getenv("MAX_RISK_PER_TRADE", 0.01)),
        max_daily_loss=float(os.getenv("MAX_DAILY_LOSS", 0.05)),
        max_daily_trades=int(os.getenv("MAX_DAILY_TRADES", 10))
    )
    
    strategy_instances = {
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
            atr_period=int(os.getenv("BREAKOUT_ATR_PERIOD", 14)),
            atr_threshold=float(os.getenv("BREAKOUT_ATR_THRESHOLD", 0.01)),
        )
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
                    # 下單股數計算（從 .env 讀取，不設定則使用預設值）
                    # ==========================================
                    position_size = 0
                    
                    # 金額制策略：指定單筆金額，自動換算股數
                    if strategy_name in ["bollinger", "vwap", "ma_cross"]:
                        amount_key = f"{strategy_name.upper()}_POSITION_AMOUNT"
                        defaults = {"bollinger": 2500, "vwap": 2500, "ma_cross": 2200}
                        target_amount = int(os.getenv(amount_key, defaults[strategy_name]))
                        
                        # 金字塔加碼：檢查是否啟用且為買進
                        pyramid_enabled = os.getenv("PYRAMID_ENABLED", "false").lower() == "true"
                        if pyramid_enabled and action == "BUY" and strategy_name == "bollinger":
                            # 初始化追蹤
                            if symbol not in pyramid_tracker:
                                pyramid_tracker[symbol] = {"buy_count": 0, "last_buy_price": 0}
                            tracker = pyramid_tracker[symbol]
                            
                            tier1 = int(os.getenv("PYRAMID_TIER1_SHARES", 200))
                            tier2 = int(os.getenv("PYRAMID_TIER2_SHARES", 400))
                            tier3 = int(os.getenv("PYRAMID_TIER3_SHARES", 600))
                            tier2_drop = float(os.getenv("PYRAMID_TIER2_DROP", 0.03))
                            tier3_drop = float(os.getenv("PYRAMID_TIER3_DROP", 0.05))
                            
                            if tracker["buy_count"] == 0:
                                # 首次買進
                                position_size = tier1
                                tracker["last_buy_price"] = current_price
                                tracker["buy_count"] = 1
                                print(f"🔔 金字塔加碼 Tier 1：{symbol} 首次買進 {tier1} 股 @ {current_price:.2f}")
                            elif tracker["buy_count"] == 1:
                                # 檢查是否跌夠深觸發 Tier 2
                                drop = (tracker["last_buy_price"] - current_price) / tracker["last_buy_price"]
                                if drop >= tier2_drop:
                                    position_size = tier2
                                    tracker["last_buy_price"] = current_price
                                    tracker["buy_count"] = 2
                                    print(f"🔔 金字塔加碼 Tier 2：{symbol} 加碼 {tier2} 股（跌 {drop:.1%}）")
                                else:
                                    # 未達加碼門檻，用一般金額制
                                    position_size = int(target_amount // current_price)
                            elif tracker["buy_count"] >= 2:
                                drop = (tracker["last_buy_price"] - current_price) / tracker["last_buy_price"]
                                if drop >= tier3_drop and tracker["buy_count"] < 3:
                                    position_size = tier3
                                    tracker["last_buy_price"] = current_price
                                    tracker["buy_count"] = 3
                                    print(f"🔔 金字塔加碼 Tier 3：{symbol} 加碼 {tier3} 股（跌 {drop:.1%}）")
                                else:
                                    position_size = int(target_amount // current_price)
                        else:
                            position_size = int(target_amount // current_price)
                        
                        if position_size <= 0:
                            position_size = 1  # 至少買 1 股
                    
                    # 股數制策略：直接指定買/賣股數
                    elif strategy_name == "breakout":
                        buy_shares = int(os.getenv("BREAKOUT_POSITION_BUY", 50))
                        sell_shares = int(os.getenv("BREAKOUT_POSITION_SELL", 100))
                        position_size = buy_shares if action == "BUY" else sell_shares
                    
                    if position_size <= 0:
                        continue
                        
                    if not risk_manager.check_trade_allowed(symbol, signal, current_price):
                        send_telegram_message(f"🛑 *{symbol}* 風險控管攔截（次數/虧損/漲跌停）")
                        continue
                    
                    # 每月預算檢查（僅買進時才扣預算）
                    if action == "BUY":
                        trade_cost = current_price * position_size
                        if not check_monthly_budget(strategy_name, trade_cost, budget_spent):
                            continue
                    
                    # 大盤年線過濾（僅買進時檢查）
                    if action == "BUY" and os.getenv("MARKET_TREND_FILTER", "true").lower() == "true":
                        if not market_filter.is_above_ma200():
                            print(f"🛑 {symbol} 買進被大盤年線過濾攔截")
                            continue
                    
                    # 下單執行
                    if USE_REAL_API:
                        order_result = broker.place_order(symbol, action.lower(), position_size)
                        if "error" in order_result:
                            continue
                    else:
                        broker.place_order(symbol, action, position_size)
                    
                    risk_manager.log_trade(symbol, signal, current_price, position_size)
                    
                    # 賣出時重置金字塔追蹤
                    if action == "SELL" and symbol in pyramid_tracker:
                        del pyramid_tracker[symbol]
                    
                    # 更新每月預算花費
                    if action == "BUY":
                        trade_cost = current_price * position_size
                        update_monthly_spending(strategy_name, trade_cost, budget_spent)
                    
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
