import os
import time
import requests
import pandas as pd
from datetime import datetime, date, timedelta
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # 讀取 .env 檔（本機開發用；Docker container 走 env_file 自動注入）

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

# ==========================================
# 策略資金配置上限（總量 × 各策略百分比）
# TOTAL_CAPITAL 可大於 INITIAL_CAPITAL（例如還有其他資金來源）
# ==========================================
TOTAL_CAPITAL = float(os.getenv("TOTAL_CAPITAL", os.getenv("INITIAL_CAPITAL", 500000)))

ALLOC_BOLLINGER = float(os.getenv("ALLOC_BOLLINGER", 40)) / 100.0
ALLOC_VWAP = float(os.getenv("ALLOC_VWAP", 20)) / 100.0
ALLOC_MA_CROSS = float(os.getenv("ALLOC_MA_CROSS", 20)) / 100.0
ALLOC_BREAKOUT = float(os.getenv("ALLOC_BREAKOUT", 20)) / 100.0
ALLOC_KEEP_WAIT = float(os.getenv("ALLOC_KEEP_WAIT", 0)) / 100.0
INST_MOM_CAPITAL = float(os.getenv("INST_MOM_CAPITAL", 0))

STRATEGY_ALLOC = {
    "bollinger": TOTAL_CAPITAL * ALLOC_BOLLINGER,
    "vwap": TOTAL_CAPITAL * ALLOC_VWAP,
    "ma_cross": TOTAL_CAPITAL * ALLOC_MA_CROSS,
    "breakout": TOTAL_CAPITAL * ALLOC_BREAKOUT,
    "keep_wait": TOTAL_CAPITAL * ALLOC_KEEP_WAIT,
}

USE_REAL_API = os.getenv("USE_REAL_API", "false").lower() == "true"
BROKER = os.getenv("BROKER", "kgi").lower()

if BROKER == "esun":
    from data.esun_provider import EsunProvider as BrokerAPI
    USE_REAL_API = True  # 玉山永遠提供真實行情
    print("🏦 【玉山證券】使用玉山 API 進行行情 + 交易")
elif USE_REAL_API:
    from data.kgi_real import KGIRealAPI as BrokerAPI
    print("🚀 【正式上線】使用真實凱基 API 進行自動化零股下單")
else:
    from data.kgi_mock import KGIMockAPI as BrokerAPI
    print("🧪 【模擬測試】使用凱基 API 模擬器（雙通知，不動用真錢）")

from strategies.vwap_deviation import vwap_deviation_strategy
from strategies.ma_cross import ma_cross_strategy
from strategies.bollinger import bollinger_reverse_strategy
from strategies.breakout import breakout_strategy
from strategies.keep_wait import keep_wait_strategy
from strategies.institutional_momentum import InstitutionalMomentumStrategy
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

# ==========================================
# 3. 每日 13:45 交易日報（發送到 Telegram）
# ==========================================
def send_daily_report():
    """讀取 logs/performance.csv，產生今日交易摘要發送到 Telegram"""
    csv_path = Path("logs/performance.csv")
    if not csv_path.exists():
        send_telegram_message("📊 *今日交易日報*\n📅 今日無交易紀錄")
        return

    try:
        df = pd.read_csv(csv_path)
        today = date.today()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        today_df = df[df["timestamp"].dt.date == today]
    except Exception as e:
        send_telegram_message(f"❌ 讀取交易紀錄失敗: {e}")
        return

    if today_df.empty:
        send_telegram_message("📊 *今日交易日報*\n📅 今日無交易紀錄")
        return

    buys = today_df[today_df["action"].str.upper() == "BUY"]
    sells = today_df[today_df["action"].str.upper() == "SELL"]

    msg = f"📊 *今日交易日報 ({today.isoformat()})*\n"
    msg += "─" * 20 + "\n"

    if not buys.empty:
        msg += "🔹 *買進*\n"
        for _, row in buys.iterrows():
            t = pd.Timestamp(row["timestamp"]).strftime("%H:%M")
            s = row["symbol"]
            msg += f"  {s}  {t}  @${row['price']:.2f}  {int(row['quantity'])}股\n"
        total_buy = (buys["price"] * buys["quantity"]).sum()
        msg += f"  買進總成本: NT${total_buy:,.0f}\n"

    if not sells.empty:
        msg += "🔸 *賣出*\n"
        for _, row in sells.iterrows():
            t = pd.Timestamp(row["timestamp"]).strftime("%H:%M")
            s = row["symbol"]
            msg += f"  {s}  {t}  @${row['price']:.2f}  {int(row['quantity'])}股\n"
        total_sell = (sells["price"] * sells["quantity"]).sum()
        msg += f"  賣出總收入: NT${total_sell:,.0f}\n"

    msg += "─" * 20
    send_telegram_message(msg)


def _next_market_open(now: datetime) -> datetime:
    """計算下次台股開盤時間 (交易日 08:45，提前暖機)"""
    # 交易日 08:45 前 → 今天 08:45
    if now.weekday() < 5 and (now.hour < 8 or (now.hour == 8 and now.minute < 45)):
        return now.replace(hour=8, minute=45, second=0, microsecond=0)
    # 往後找第一個交易日
    for days in range(1, 8):
        dt = now + timedelta(days=days)
        if dt.weekday() < 5:
            return dt.replace(hour=8, minute=45, second=0, microsecond=0)
    return now.replace(hour=8, minute=45) + timedelta(days=1)


APP_VERSION = "1.01"
BUILD_DATE = "2026-06-14"

def main():
    print(f"🚀 TW AutoTrader v{APP_VERSION} (build {BUILD_DATE}) 多股多策略分流系統啟動")
    print(f"📦 版號：v{APP_VERSION}｜建置日期：{BUILD_DATE}")
    send_line_notification(f"\n🤖 TW AutoTrader v{APP_VERSION} 雲端主機已成功啟動！開始全天候監控台股...")
    send_telegram_message(f"✅ *TW AutoTrader* v{APP_VERSION} 多股多策略系統已啟動\n📈 監控中: " + ", ".join(f"{s}[{p}]" for s, p in MY_PORTFOLIO.items()))

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
    # 策略配置上限追蹤（累計買進成本）
    # ==========================================
    alloc_file = Path("logs/strategy_allocation.json")

    def load_strategy_allocation() -> dict:
        if alloc_file.exists():
            try:
                data = json.loads(alloc_file.read_text())
                for s in STRATEGY_ALLOC:
                    data.setdefault(s, {"total_buy_cost": 0, "total_buy_shares": 0})
                return data
            except:
                pass
        return {s: {"total_buy_cost": 0, "total_buy_shares": 0} for s in STRATEGY_ALLOC}

    def save_strategy_allocation(alloc: dict):
        alloc_file.write_text(json.dumps(alloc, indent=2))

    def check_strategy_cap(strategy: str, cost: float, alloc: dict) -> bool:
        cap = STRATEGY_ALLOC.get(strategy, float("inf"))
        if cap <= 0:
            return True
        net = alloc.get(strategy, {}).get("total_buy_cost", 0)
        if net + cost > cap:
            remaining = cap - net
            print(f"⚠️  策略配置已達上限：{strategy} "
                  f"已用 {net:.0f} / {cap:.0f} 元（剩 {remaining:.0f}），跳過此筆交易")
            return False
        return True

    strategy_alloc = load_strategy_allocation()

    # 累計買賣總額（含已實現損益，用於 CAPITAL_CONTROL_LINE 資金充裕判斷）
    total_buy_all = 0
    total_sell_all = 0

    # ==========================================
    # 庫存追蹤（逐股票記錄持有股數，避免空賣）
    # ==========================================
    holdings_file = Path("logs/holdings.json")

    def load_holdings() -> dict:
        if holdings_file.exists():
            try:
                return json.loads(holdings_file.read_text())
            except:
                pass
        return {}

    def save_holdings(h: dict):
        holdings_file.write_text(json.dumps(h, indent=2))

    holdings = load_holdings()

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
    
    strategy_configs = {
        "vwap": (vwap_deviation_strategy, {
            "sigma_mult": float(os.getenv("VWAP_SIGMA_MULT", 1.5)),
            "rsi_period": int(os.getenv("VWAP_RSI_PERIOD", 5)),
        }),
        "ma_cross": (ma_cross_strategy, {
            "fast_period": int(os.getenv("MA_CROSS_FAST_PERIOD", 9)),
            "slow_period": int(os.getenv("MA_CROSS_SLOW_PERIOD", 21)),
            "atr_threshold": float(os.getenv("MA_CROSS_ATR_THRESHOLD", 0.005)),
        }),
        "bollinger": (bollinger_reverse_strategy, {
            "window": int(os.getenv("BOLLINGER_WINDOW", 20)),
            "std_dev": float(os.getenv("BOLLINGER_STD_DEV", 2.0)),
            "rsi_period": int(os.getenv("BOLLINGER_RSI_PERIOD", 5)),
        }),
        "breakout": (breakout_strategy, {
            "lookback": int(os.getenv("BREAKOUT_LOOKBACK", 20)),
            "atr_period": int(os.getenv("BREAKOUT_ATR_PERIOD", 14)),
            "atr_threshold": float(os.getenv("BREAKOUT_ATR_THRESHOLD", 0.01)),
        }),
        "keep_wait": (keep_wait_strategy, {}),
    }

    inst_momentum = InstitutionalMomentumStrategy(
        broker=broker,
        capital=INST_MOM_CAPITAL,
        top_n=int(os.getenv("INST_MOM_TOP_N", 2)),
    )
    
    portfolio_history = {}
    
    # 初始化歷史資料
    for symbol, strat_name in MY_PORTFOLIO.items():
        df_init = broker.get_minute_bars(symbol, minutes=60) if USE_REAL_API else broker.get_historical_data(symbol, days=30)
        if df_init.empty:
            continue
        portfolio_history[symbol] = df_init
        print(f"✅ {symbol} 初始化成功 -> [{strat_name.upper()}]")
    
    if INST_MOM_CAPITAL > 0:
        print(f"✅ Group 2 法人抬轎動能初始化成功（資本 NT${INST_MOM_CAPITAL:,.0f}）")
    else:
        print("ℹ️ Group 2 法人抬轎動能未啟用（INST_MOM_CAPITAL=0）")
    
    daily_report_sent_date = None

    while True:
        now = datetime.now()
        is_weekday = now.weekday() < 5
        h, m = now.hour, now.minute

        # ============================================================
        # 時段 1：盤中 08:45-13:30 → 提前暖機 + 正常交易
        # ============================================================
        if is_weekday and ((h == 8 and m >= 45) or (h >= 9 and h < 13) or (h == 13 and m <= 30)):
            for symbol, strategy_name in MY_PORTFOLIO.items():
                if symbol not in portfolio_history:
                    continue
                try:
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

                    strat_func, strat_params = strategy_configs[strategy_name]
                    signal = strat_func(accumulated_data, **strat_params)['signal'].iloc[-1]
                    current_price = accumulated_data['close'].iloc[-1]

                    if strategy_name == "keep_wait":
                        kw_initial = int(os.getenv("KW_INITIAL_SHARES", 1000))
                        kw_add = int(os.getenv("KW_ADD_SHARES", 2000))
                        kw_drop = float(os.getenv("KW_ADD_DROP_PCT", 0.05))
                        kw_max_add = int(os.getenv("KW_MAX_ADDITIONS", 3))
                        kw_tp_pct = float(os.getenv("KW_TP_TRIGGER_PCT", 15))
                        kw_tp_sell = float(os.getenv("KW_TP_SELL_RATIO", 100))
                        kw_cooldown = int(os.getenv("KW_COOLDOWN_DAYS", 30))

                        if symbol not in pyramid_tracker:
                            pyramid_tracker[symbol] = {
                                "buy_count": 0, "last_buy_price": 0.0,
                                "total_cost": 0.0, "total_shares": 0,
                                "sold_date": None,
                                "notified_tp": set(),
                            }
                        trk = pyramid_tracker[symbol]

                        if trk.get("sold_date") and trk["buy_count"] == -1:
                            days_since_sold = (datetime.now() - trk["sold_date"]).days
                            if days_since_sold < kw_cooldown:
                                signal = 0
                                continue
                            else:
                                trk["buy_count"] = 0

                        if trk["buy_count"] == 0:
                            signal = 1
                            position_size = kw_initial
                            trk["last_buy_price"] = current_price
                            trk["total_cost"] = current_price * position_size
                            trk["total_shares"] = position_size
                            trk["buy_count"] = 1
                            print(f"📥 {symbol} keep_wait 初始進場 {position_size} 股 @ {current_price:.0f}")
                        else:
                            avg_cost = trk["total_cost"] / trk["total_shares"] if trk["total_shares"] > 0 else current_price
                            drop_pct = (trk["last_buy_price"] - current_price) / trk["last_buy_price"] * 100
                            profit_pct = (current_price - avg_cost) / avg_cost * 100

                            if profit_pct >= kw_tp_pct and trk["total_shares"] > 0:
                                owned = holdings.get(symbol, 0)
                                if kw_tp_sell > 0 and owned > 0:
                                    sell_qty = max(1, int(owned * kw_tp_sell / 100))
                                    signal = -1
                                    position_size = sell_qty
                                    print(f"📈 {symbol} 停利 +{profit_pct:.1f}% 賣出 {sell_qty}/{owned} 股 ({kw_tp_sell:.0f}%)")
                                    trk["buy_count"] = -1
                                    trk["sold_date"] = datetime.now()
                                elif kw_tp_sell == 0 and owned > 0:
                                    signal = 0
                                    if profit_pct not in trk.setdefault("notified_tp", set()):
                                        trk["notified_tp"].add(profit_pct)
                                        msg = (f"📈 *{symbol}* 漲幅 +{profit_pct:.1f}% 已達目標 {kw_tp_pct:.0f}%\n"
                                               f"目前持有 {owned} 股，成本均價 {avg_cost:.0f}\n"
                                               f"是否手動獲利了結？")
                                        send_telegram_message(msg)
                                        print(f"📢 {symbol} 漲 {profit_pct:.1f}% 達標，已通知使用者")
                                else:
                                    signal = 0
                            elif drop_pct >= kw_drop * 100 and trk["buy_count"] < kw_max_add:
                                signal = 1
                                position_size = kw_add
                                trk["last_buy_price"] = current_price
                                trk["total_cost"] += current_price * position_size
                                trk["total_shares"] += position_size
                                trk["buy_count"] += 1
                                print(f"📉 {symbol} DCA 第 {trk['buy_count']} 次加碼 {position_size} 股 "
                                      f"@ {current_price:.0f}（距前次 -{drop_pct:.1f}%）")
                            else:
                                signal = 0

                        if signal == 0:
                            continue

                    if signal != 0:
                        action = "BUY" if signal == 1 else "SELL"

                        if strategy_name == "keep_wait":
                            pass  # position_size already set by DCA logic above
                        else:
                            position_size = 0

                        if strategy_name in ["bollinger", "vwap", "ma_cross"]:
                            amount_key = f"{strategy_name.upper()}_POSITION_AMOUNT"
                            defaults = {"bollinger": 2500, "vwap": 2500, "ma_cross": 2200}
                            target_amount = int(os.getenv(amount_key, defaults[strategy_name]))

                            pyramid_enabled = os.getenv("PYRAMID_ENABLED", "false").lower() == "true"
                            if pyramid_enabled and action == "BUY" and strategy_name == "bollinger":
                                if symbol not in pyramid_tracker:
                                    pyramid_tracker[symbol] = {"buy_count": 0, "last_buy_price": 0}
                                tracker = pyramid_tracker[symbol]

                                tier1 = int(os.getenv("PYRAMID_TIER1_SHARES", 200))
                                tier2 = int(os.getenv("PYRAMID_TIER2_SHARES", 400))
                                tier3 = int(os.getenv("PYRAMID_TIER3_SHARES", 600))
                                tier2_drop = float(os.getenv("PYRAMID_TIER2_DROP", 0.03))
                                tier3_drop = float(os.getenv("PYRAMID_TIER3_DROP", 0.05))

                                if tracker["buy_count"] == 0:
                                    position_size = tier1
                                    tracker["last_buy_price"] = current_price
                                    tracker["buy_count"] = 1
                                    print(f"🔔 金字塔加碼 Tier 1：{symbol} 首次買進 {tier1} 股 @ {current_price:.2f}")
                                elif tracker["buy_count"] == 1:
                                    drop = (tracker["last_buy_price"] - current_price) / tracker["last_buy_price"]
                                    if drop >= tier2_drop:
                                        position_size = tier2
                                        tracker["last_buy_price"] = current_price
                                        tracker["buy_count"] = 2
                                        print(f"🔔 金字塔加碼 Tier 2：{symbol} 加碼 {tier2} 股（跌 {drop:.1%}）")
                                    else:
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
                                position_size = 1

                        elif strategy_name == "breakout":
                            buy_shares = int(os.getenv("BREAKOUT_POSITION_BUY", 50))
                            sell_shares = int(os.getenv("BREAKOUT_POSITION_SELL", 100))
                            position_size = buy_shares if action == "BUY" else sell_shares

                        if position_size <= 0:
                            continue

                        allowed, reject_reason = risk_manager.check_trade_allowed(
                            symbol, signal, current_price,
                            total_buy=total_buy_all, total_sell=total_sell_all)
                        if not allowed:
                            send_telegram_message(f"🛑 *{symbol}* 風險控管攔截（{reject_reason}）")
                            continue

                        if action == "BUY":
                            trade_cost = current_price * position_size
                            if not check_monthly_budget(strategy_name, trade_cost, budget_spent):
                                continue
                            if not check_strategy_cap(strategy_name, trade_cost, strategy_alloc):
                                continue

                        if action == "BUY" and os.getenv("MARKET_TREND_FILTER", "true").lower() == "true":
                            if not market_filter.is_above_ma200():
                                print(f"🛑 {symbol} 買進被大盤年線過濾攔截")
                                continue

                        if action == "SELL":
                            owned = holdings.get(symbol, 0)
                            if owned < position_size:
                                if owned > 0:
                                    print(f"⚠️  {symbol} 持有 {owned} 股，不足賣出 {position_size} 股，跳過")
                                continue

                        if USE_REAL_API:
                            order_result = broker.place_order(symbol, action.lower(), position_size)
                            if "error" in order_result:
                                continue
                        else:
                            broker.place_order(symbol, action, position_size)

                        risk_manager.log_trade(symbol, signal, current_price, position_size)

                        if action == "BUY":
                            holdings[symbol] = holdings.get(symbol, 0) + position_size
                        else:
                            holdings[symbol] = max(0, holdings.get(symbol, 0) - position_size)
                        save_holdings(holdings)

                        if action == "SELL":
                            sell_proceeds = current_price * position_size
                            total_sell_all += sell_proceeds
                            if symbol in pyramid_tracker and strategy_name != "keep_wait":
                                del pyramid_tracker[symbol]
                            if strategy_name in strategy_alloc:
                                alloc_data = strategy_alloc[strategy_name]
                                if alloc_data["total_buy_shares"] > 0:
                                    avg_cost = alloc_data["total_buy_cost"] / alloc_data["total_buy_shares"]
                                    cost_basis = avg_cost * position_size
                                    alloc_data["total_buy_cost"] = max(0, alloc_data["total_buy_cost"] - cost_basis)
                                    alloc_data["total_buy_shares"] = max(0, alloc_data["total_buy_shares"] - position_size)
                                    save_strategy_allocation(strategy_alloc)

                        if action == "BUY":
                            trade_cost = current_price * position_size
                            total_buy_all += trade_cost
                            update_monthly_spending(strategy_name, trade_cost, budget_spent)
                            strategy_alloc[strategy_name]["total_buy_cost"] += trade_cost
                            strategy_alloc[strategy_name]["total_buy_shares"] += position_size
                            save_strategy_allocation(strategy_alloc)

                        action_zh = "買進" if action == "BUY" else "賣出"
                        notice_msg = f"\n🔔 交易通知\n股票: {symbol}\n動作: {action_zh}\n價格: {current_price:.2f}\n股數: {position_size} 股\n策略: {strategy_name.upper()}"
                        send_trade_alert(symbol, action, current_price, position_size, strategy_name.upper())
                        send_line_notification(notice_msg)

                except Exception as e:
                    print(f"❌ {symbol} 錯誤: {e}")

            if INST_MOM_CAPITAL > 0:
                try:
                    inst_momentum.run(broker, risk_manager, holdings, now)
                except Exception as e:
                    print(f"❌ [INST_MOM] 執行錯誤: {e}")

            time.sleep(60)
            continue

        # ============================================================
        # 時段 2：收盤後 13:31-13:59 → 等待發送日報（13:45準時發送）
        # ============================================================
        if is_weekday and h == 13 and m >= 31:
            if m == 45 and daily_report_sent_date != now.date():
                send_daily_report()
                try:
                    from scripts.generate_dashboard import main as gen_dash
                    gen_dash()
                except Exception as e:
                    print(f"❌ 產生儀表板失敗: {e}")
                daily_report_sent_date = now.date()
            if INST_MOM_CAPITAL > 0:
                try:
                    inst_momentum.run(broker, risk_manager, holdings, now)
                except Exception as e:
                    print(f"❌ [INST_MOM] 執行錯誤: {e}")
            time.sleep(60)
            continue

        # ============================================================
        # 時段 3：非交易時段（盤前、盤後、週末）→ 休眠到下次開盤
        # ============================================================
        next_open = _next_market_open(now)
        sleep_seconds = min((next_open - now).total_seconds(), 3600)
        if sleep_seconds >= 3600:
            print(f"💤 非交易時段，下次開盤 {next_open.strftime('%m/%d %H:%M')}，休眠中...")
        time.sleep(max(sleep_seconds, 60))

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()
