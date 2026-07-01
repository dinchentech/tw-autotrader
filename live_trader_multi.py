import os
import json
import time
import requests
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # 讀取 .env 檔

# 匯入共用設定載入器（V1.1 PC_<代號> JSON 格式）
from core.config_loader import load_portfolio_config, STRATEGY_PARAM_KEYS, get_strategy_params

PORTFOLIO_CONFIG = load_portfolio_config()

# 向後相容：無 PC_ 設定時回退到舊 PORTFOLIO 格式
if not PORTFOLIO_CONFIG:
    print("ℹ️ 未偵測到 PC_ 設定，嘗試讀取舊版 PORTFOLIO 格式...")
    legacy_raw = os.getenv("PORTFOLIO")
    if legacy_raw:
        for pair in legacy_raw.split(","):
            pair = pair.strip()
            if ":" not in pair:
                continue
            symbol, strategy = pair.split(":", 1)
            PORTFOLIO_CONFIG[symbol.strip()] = {"strategy": strategy.strip().lower()}
            print(f"  ↪ {symbol} → {strategy.strip().lower()}（舊格式，使用預設參數）")
    if not PORTFOLIO_CONFIG:
        PORTFOLIO_CONFIG = {
            "0050": {"strategy": "bollinger"},
            "2330": {"strategy": "ma_cross"},
            "2382": {"strategy": "breakout"},
            "2881": {"strategy": "vwap"},
        }

# ==========================================
# 策略函式匯入與映射（不含參數，參數從 per-stock config 取得）
# ==========================================
from strategies.vwap_deviation import vwap_deviation_strategy
from strategies.ma_cross import ma_cross_strategy
from strategies.bollinger import bollinger_reverse_strategy
from strategies.breakout import breakout_strategy
from strategies.keep_wait import keep_wait_strategy
from strategies.institutional_momentum import InstitutionalMomentumStrategy
from utils.telegram import send_trade_alert, send_telegram_message
from core.risk_manager import RiskManager

STRATEGY_FUNCS = {
    "vwap": vwap_deviation_strategy,
    "ma_cross": ma_cross_strategy,
    "bollinger": bollinger_reverse_strategy,
    "breakout": breakout_strategy,
    "keep_wait": keep_wait_strategy,
}


def read_capital_file(filepath: str = "capital.txt") -> list:
    """
    讀取 capital.txt，回傳 [(date_str, amount), ...]
    格式: 金額, YYYY/MM/DD  # comment
    金額可為負數（代表提領）
    """
    entries = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "," in line:
                    parts = line.split(",", 1)
                    amount_str = parts[0].strip()
                    date_part = parts[1].strip()
                    if "#" in date_part:
                        date_part = date_part.split("#")[0].strip()
                    try:
                        amount = float(amount_str)
                        date_str = date_part.replace("/", "-")
                        entries.append((date_str, amount))
                    except (ValueError, IndexError):
                        continue
    except FileNotFoundError:
        pass
    return entries


def load_processed_capital(filepath: str = "logs/processed_capital.json") -> list:
    """已處理的資金紀錄（避免重複處理）"""
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_processed_capital(processed: list, filepath: str = "logs/processed_capital.json"):
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(processed, f, indent=2)

# ==========================================
# 系統級參數
# ==========================================
TOTAL_CAPITAL = float(os.getenv("TOTAL_CAPITAL", os.getenv("INITIAL_CAPITAL", 500000)))
INST_MOM_CAPITAL = float(os.getenv("INST_MOM_CAPITAL", 0))
USE_REAL_API = os.getenv("USE_REAL_API", "false").lower() == "true"
BROKER = os.getenv("BROKER", "kgi").lower()
DCA_AMOUNT = int(os.getenv("DCA_AMOUNT", "0"))
MAX_DAILY_TRADES_PER_SYMBOL = int(os.getenv("MAX_DAILY_TRADES_PER_SYMBOL", "1"))
PROFIT_MARGIN = float(os.getenv("PROFIT_MARGIN", "100"))


def _create_broker():
    """延遲建立 broker 實例（避免 module-level import 失敗）"""
    if BROKER == "esun":
        from data.esun_provider import EsunProvider
        print("🏦 【玉山證券】使用玉山 API 進行行情 + 交易")
        return EsunProvider()
    elif USE_REAL_API:
        from data.kgi_real import KGIRealAPI
        print("🚀 【正式上線】使用真實凱基 API 進行自動化零股下單")
        return KGIRealAPI()
    else:
        from data.kgi_mock import KGIMockAPI
        print("🧪 【模擬測試】使用凱基 API 模擬器（雙通知，不動用真錢）")
        return KGIMockAPI()


# ==========================================
# 2. LINE Notify 通知
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
# 3. 每日 13:45 交易日報
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
    if now.weekday() < 5 and (now.hour < 8 or (now.hour == 8 and now.minute < 45)):
        return now.replace(hour=8, minute=45, second=0, microsecond=0)
    for days in range(1, 8):
        dt = now + timedelta(days=days)
        if dt.weekday() < 5:
            return dt.replace(hour=8, minute=45, second=0, microsecond=0)
    return now.replace(hour=8, minute=45) + timedelta(days=1)


APP_VERSION = "1.38"
BUILD_DATE = "2026-06-29"


def get_stock_capital(symbol: str) -> float:
    """計算單一股票的資金上限"""
    cfg = PORTFOLIO_CONFIG.get(symbol, {})
    alloc_pct = float(cfg.get("alloc", 20))
    return TOTAL_CAPITAL * alloc_pct / 100.0


def main():
    print(f"🚀 TW AutoTrader v{APP_VERSION} (build {BUILD_DATE}) 多股多策略分流系統啟動")
    print(f"📦 版號：v{APP_VERSION}｜建置日期：{BUILD_DATE}")

    # ── GCP 認證檢查 ──
    try:
        import subprocess
        r = subprocess.run(["gcloud", "auth", "print-access-token"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            print("⚠️  GCP 認證未通過 — 若需部署至 GCP，請執行：gcloud auth login")
    except FileNotFoundError:
        pass  # gcloud 未安裝，本地開發環境跳過檢查
    except Exception:
        pass  # 其他例外不影響啟動

    print(f"📈 個股設定：共 {len(PORTFOLIO_CONFIG)} 檔")
    for sym, cfg in PORTFOLIO_CONFIG.items():
        cap = get_stock_capital(sym)
        print(f"   {sym} → {cfg['strategy']}（上限 NT${cap:,.0f}）")
    send_line_notification(f"\n🤖 TW AutoTrader v{APP_VERSION} 雲端主機已成功啟動！開始全天候監控台股...")
    send_telegram_message(
        f"✅ *TW AutoTrader* v{APP_VERSION} 多股多策略系統已啟動\n📈 監控中: "
        + ", ".join(f"{s}[{c['strategy']}]" for s, c in PORTFOLIO_CONFIG.items())
    )

    # ==========================================
    # 股票數量上限檢查
    # ==========================================
    MAX_RECOMMENDED_STOCKS = 15
    if len(PORTFOLIO_CONFIG) > MAX_RECOMMENDED_STOCKS:
        print(f"⚠️  警告：投資組合中有 {len(PORTFOLIO_CONFIG)} 支股票，超過建議上限 {MAX_RECOMMENDED_STOCKS} 支。")
        print(f"   由於程式是順序處理，股票過多會導致每輪循環時間拉長，訊號失去即時性。")
        print(f"   建議將股票數降至 {MAX_RECOMMENDED_STOCKS} 支以下，或將程式改為非同步並行架構。")

    # ==========================================
    # 每月預算控管（per-stock）
    # ==========================================
    budget_file = Path("logs/monthly_budget.json")

    def load_monthly_budget() -> dict:
        current_month = datetime.now().strftime("%Y-%m")
        if budget_file.exists():
            try:
                data = json.loads(budget_file.read_text())
                if data.get("month") == current_month:
                    return data.get("spent", {})
            except Exception:
                pass
        return {}

    def save_monthly_budget(spent: dict):
        current_month = datetime.now().strftime("%Y-%m")
        budget_file.write_text(json.dumps({
            "month": current_month,
            "spent": spent
        }, indent=2))

    def check_monthly_budget(symbol: str, cost: float, spent: dict) -> bool:
        """檢查該股票本月預算是否足夠"""
        cfg = PORTFOLIO_CONFIG.get(symbol, {})
        monthly_limit = float(cfg.get("monthly_budget", 0))
        if monthly_limit <= 0:
            return True  # 0 = 不限制
        current_spent = spent.get(symbol, 0)
        if current_spent + cost > monthly_limit:
            print(f"⚠️  {symbol} 每月預算已達上限："
                  f"本月已花 {current_spent:.0f} / {monthly_limit:.0f} 元，跳過此筆交易")
            return False
        return True

    def update_monthly_spending(symbol: str, cost: float, spent: dict):
        spent[symbol] = spent.get(symbol, 0) + cost
        save_monthly_budget(spent)

    budget_spent = load_monthly_budget()

    # ==========================================
    # 個股資金配置上限追蹤（per-stock）
    #   logs/stock_allocation.json
    # ==========================================
    alloc_file = Path("logs/stock_allocation.json")

    def load_stock_allocation() -> dict:
        if alloc_file.exists():
            try:
                data = json.loads(alloc_file.read_text())
                for sym in PORTFOLIO_CONFIG:
                    data.setdefault(sym, {"total_buy_cost": 0, "total_buy_shares": 0})
                return data
            except Exception:
                pass
        return {sym: {"total_buy_cost": 0, "total_buy_shares": 0} for sym in PORTFOLIO_CONFIG}

    def save_stock_allocation(alloc: dict):
        alloc_file.write_text(json.dumps(alloc, indent=2))

    def check_stock_cap(symbol: str, cost: float, alloc: dict) -> bool:
        """檢查該股票是否已達資金配置上限"""
        cap = get_stock_capital(symbol)
        if cap <= 0:
            return True
        net = alloc.get(symbol, {}).get("total_buy_cost", 0)
        new_total = net + cost
        if new_total > cap:
            remaining = cap - net
            print(f"⚠️  {symbol} 本次需 NT${cost:,.0f}，已用 {net:.0f} / {cap:.0f} 元（剩 {remaining:.0f}），跳過")
            return False
        # 資金使用率超過 70% 時通知使用者
        usage = new_total / cap
        warned_key = f"{symbol}_cap_70pct"
        if usage >= 0.7 and not alloc.get(symbol, {}).get("_cap_warned", False):
            alloc.setdefault(symbol, {})["_cap_warned"] = True
            save_stock_allocation(alloc)
            msg = (f"⚠️ *{symbol}* 資金配置已使用 {usage:.0%}\n"
                   f"目前：NT${new_total:,.0f} / 上限 NT${cap:,.0f}\n"
                   f"如需要提高上限，請調整 `.env` 中該股票的 `alloc` 百分比")
            send_telegram_message(msg)
            print(f"📢 {symbol} 資金使用率 {usage:.0%}，已通知使用者")
        return True

    stock_alloc = load_stock_allocation()

    # 累計買賣總額（用於 CAPITAL_CONTROL_LINE 判斷）
    total_buy_all = 0
    total_sell_all = 0

    # ==========================================
    # 庫存追蹤
    # ==========================================
    holdings_file = Path("logs/holdings.json")

    def load_holdings() -> dict:
        if holdings_file.exists():
            try:
                return json.loads(holdings_file.read_text())
            except Exception:
                pass
        return {}

    def save_holdings(h: dict):
        holdings_file.write_text(json.dumps(h, indent=2))

    holdings = load_holdings()

    # ==========================================
    # 單日交易次數追蹤（持久化，避免 container 重啟歸零）
    # ==========================================
    daily_trades_file = Path("logs/daily_trades.json")
    
    # ==========================================
    # 交易冷卻時間追蹤（持久化）
    # ==========================================
    cooldown_file = Path("logs/last_trade_times.json")

    def load_last_trade_times() -> dict:
        if cooldown_file.exists():
            try:
                return json.loads(cooldown_file.read_text())
            except Exception:
                pass
        return {}

    def save_last_trade_times(times: dict):
        cooldown_file.write_text(json.dumps(times, indent=2))

    last_trade_times = load_last_trade_times()

    def load_daily_trades() -> dict:
        if daily_trades_file.exists():
            try:
                data = json.loads(daily_trades_file.read_text())
                # 回傳 {symbol: count} 與日期以供驗證
                return data.get("trades", {}), data.get("date")
            except Exception:
                pass
        return {}, None

    def save_daily_trades(trades: dict, date_str: str):
        daily_trades_file.write_text(json.dumps({
            "date": date_str,
            "trades": trades,
        }, indent=2))

    # ==========================================
    # 大盤年線過濾器
    # ==========================================
    from core.market_filter import MarketTrendFilter
    market_filter = MarketTrendFilter()

    # ==========================================
    # 金字塔加碼追蹤
    # ==========================================
    pyramid_tracker = {}

    if BROKER == "esun":
        USE_REAL_API = True  # 玉山永遠提供真實行情
    broker = _create_broker()
    risk_manager = RiskManager(
        max_risk_per_trade=float(os.getenv("MAX_RISK_PER_TRADE", 0.01)),
        max_daily_loss=float(os.getenv("MAX_DAILY_LOSS", 0.05)),
        max_daily_trades=int(os.getenv("MAX_DAILY_TRADES", 10))
    )

    inst_momentum = InstitutionalMomentumStrategy(
        broker=broker,
        capital=INST_MOM_CAPITAL,
        top_n=int(os.getenv("INST_MOM_TOP_N", 2)),
    )

    # ==========================================
    # 初始化歷史資料
    # ==========================================
    portfolio_history = {}
    for symbol, cfg in PORTFOLIO_CONFIG.items():
        df_init = broker.get_minute_bars(symbol, minutes=60) if USE_REAL_API else broker.get_historical_data(symbol, days=30)
        if df_init.empty:
            print(f"⚠️  {symbol} 盤中資料為空，改載入日 K 資料...")
            df_init = broker.get_historical_data(symbol, days=60)
            if not df_init.empty:
                px = broker.get_current_price(symbol)
                if px > 0:
                    new_row = pd.DataFrame({
                        'open': [px * 0.999], 'high': [px * 1.001],
                        'low': [px * 0.998], 'close': [px], 'volume': [5000]
                    }, index=[pd.Timestamp.now()])
                    df_init = pd.concat([df_init, new_row])
        if df_init.empty:
            print(f"❌ {symbol} 無法取得任何價格資料，跳過")
            continue
        portfolio_history[symbol] = df_init
        print(f"✅ {symbol} 初始化成功 -> [{cfg['strategy'].upper()}]")

    if INST_MOM_CAPITAL > 0:
        print(f"✅ Group 2 法人抬轎動能初始化成功（資本 NT${INST_MOM_CAPITAL:,.0f}）")
    else:
        print("ℹ️ Group 2 法人抬轎動能未啟用（INST_MOM_CAPITAL=0）")

    daily_report_sent_date = None
    last_capital_check_date = None
    processed_capital = load_processed_capital()
    daily_symbol_trades, daily_symbol_trades_date = load_daily_trades()
    if daily_symbol_trades_date is None:
        daily_symbol_trades = {}
    # 如果檔案記錄的日期不是今天，換日歸零
    today_str_init = datetime.now().strftime("%Y-%m-%d")
    if daily_symbol_trades_date != today_str_init:
        daily_symbol_trades = {}
        daily_symbol_trades_date = today_str_init

    def check_capital_injections():
        """檢查 capital.txt 新增資金投入，自動調整並執行 keep_wait 購買"""
        global TOTAL_CAPITAL
        nonlocal last_capital_check_date, processed_capital

        today = date.today().isoformat()
        if last_capital_check_date == today:
            return
        last_capital_check_date = today

        entries = read_capital_file()
        new_entries = [(d, a) for d, a in entries if f"{d}" not in processed_capital]

        if not new_entries:
            return

        for date_str, amount in new_entries:
            if amount == 0:
                continue

            old_capital = TOTAL_CAPITAL
            TOTAL_CAPITAL += amount
            processed_capital.append(date_str)

            source = "外部加碼" if amount > 0 else "資金提領"
            msg = f"💰 *資金變動*\n日期: {date_str}\n{source}: NT${amount:,.0f}\n資本: NT${old_capital:,.0f} → NT${TOTAL_CAPITAL:,.0f}"
            send_telegram_message(msg)
            print(f"💰 {date_str} {source} NT${amount:,.0f}，資本更新為 NT${TOTAL_CAPITAL:,.0f}")

            if amount > 0:
                for symbol, cfg in PORTFOLIO_CONFIG.items():
                    if cfg.get("strategy") != "keep_wait":
                        continue
                    alloc_pct = float(cfg.get("alloc", 20))
                    share_amount = TOTAL_CAPITAL * alloc_pct / 100.0
                    initial_buy_pct = float(cfg.get("initial_buy_pct", 0.7))
                    buy_amount = share_amount * initial_buy_pct

                    current_price = 0
                    try:
                        current_price = broker.get_current_price(symbol)
                    except Exception:
                        pass
                    if current_price <= 0:
                        continue

                    buy_shares = int(buy_amount / current_price)
                    if buy_shares <= 0:
                        continue

                    try:
                        broker.place_order(symbol, "buy", buy_shares)
                        risk_manager.log_trade(symbol, 1, current_price, buy_shares)
                        holdings[symbol] = holdings.get(symbol, 0) + buy_shares
                        save_holdings(holdings)
                        print(f"📥 {symbol} keep_wait 加碼 {buy_shares} 股 @ {current_price:.0f}")
                        send_telegram_message(f"📥 *{symbol}* keep_wait 加碼 {buy_shares} 股 @ {current_price:.0f}")
                    except Exception as e:
                        print(f"❌ {symbol} keep_wait 加碼失敗: {e}")

        save_processed_capital(processed_capital)

    def execute_keep_wait_on_profit_roll(symbol: str, profit_amount: float):
        """獲利滾入時執行 keep_wait 購買"""
        if profit_amount <= 0:
            return

        cfg = PORTFOLIO_CONFIG.get(symbol, {})
        if cfg.get("strategy") != "keep_wait":
            return

        initial_buy_pct = float(cfg.get("initial_buy_pct", 0.7))
        buy_amount = profit_amount * initial_buy_pct

        current_price = 0
        try:
            current_price = broker.get_current_price(symbol)
        except Exception:
            pass
        if current_price <= 0:
            return

        buy_shares = int(buy_amount / current_price)
        if buy_shares <= 0:
            return

        try:
            broker.place_order(symbol, "buy", buy_shares)
            risk_manager.log_trade(symbol, 1, current_price, buy_shares)
            holdings[symbol] = holdings.get(symbol, 0) + buy_shares
            save_holdings(holdings)
            print(f"📥 {symbol} 獲利滾入加碼 {buy_shares} 股 @ {current_price:.0f}（NT${profit_amount:,.0f} × {initial_buy_pct:.0%}）")
            send_telegram_message(f"📥 *{symbol}* 獲利滾入加碼 {buy_shares} 股 @ {current_price:.0f}")
        except Exception as e:
            print(f"❌ {symbol} 獲利滾入加碼失敗: {e}")

    # ==========================================
    # 主循環
    # ==========================================
    while True:
        now = datetime.now()
        is_weekday = now.weekday() < 5
        h, m = now.hour, now.minute

        check_capital_injections()

        # 重置單日交易次數與冷卻紀錄（換日歸零，且每週日歸零冷卻）
        today_str = now.strftime("%Y-%m-%d")
        if daily_symbol_trades_date != today_str:
            daily_symbol_trades = {}
            daily_symbol_trades_date = today_str
            save_daily_trades(daily_symbol_trades, today_str)
            
            # 每週日（6）重置冷卻紀錄
            if now.weekday() == 6:
                last_trade_times = {}
                save_last_trade_times(last_trade_times)
                print(f"🧹 每週自動清空冷卻紀錄 (last_trade_times.json)")

        # ------------------------------------------------------------
        # 時段 1：盤中 08:45-13:30 → 正常交易
        # ------------------------------------------------------------
        if is_weekday and ((h == 8 and m >= 45) or (h >= 9 and h < 13) or (h == 13 and m <= 30)):
            for symbol, cfg in PORTFOLIO_CONFIG.items():
                if symbol not in portfolio_history:
                    continue
                try:
                    accumulated_data = portfolio_history[symbol]
                    strategy_name = cfg["strategy"]

                    # ---- 單日交易次數限制（提前攔截，免於浪費運算） ----
                    if MAX_DAILY_TRADES_PER_SYMBOL > 0:
                        sym_trades_today = daily_symbol_trades.get(symbol, 0)
                        if sym_trades_today >= MAX_DAILY_TRADES_PER_SYMBOL:
                            continue

                    # ---- 30 分鐘強制冷卻檢查 ----
                    last_sell = last_trade_times.get(symbol)
                    if last_sell:
                        last_sell_dt = datetime.fromisoformat(last_sell)
                        if (now - last_sell_dt).total_seconds() < 1800:
                            continue


                    if USE_REAL_API:
                        new_data = broker.get_minute_bars(symbol, minutes=1)
                        if not new_data.empty:
                            accumulated_data = pd.concat([accumulated_data, new_data])
                        else:
                            # Esun 模擬環境可能無盤中 K 線，fallback 到 mock 報價
                            current_price = broker.get_current_price(symbol)
                            if current_price > 0:
                                new_row = pd.DataFrame({
                                    'open': [current_price * 0.999], 'high': [current_price * 1.001],
                                    'low': [current_price * 0.998], 'close': [current_price], 'volume': [5000]
                                }, index=[pd.Timestamp.now()])
                                accumulated_data = pd.concat([accumulated_data, new_row])
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

                    # ---- 取得策略訊號 ----
                    strat_func = STRATEGY_FUNCS[strategy_name]

                    # 從 per-stock config 提取該策略認識的參數
                    strat_params = get_strategy_params(cfg, strategy_name)

                    signal = strat_func(accumulated_data, **strat_params)['signal'].iloc[-1]
                    current_price = accumulated_data['close'].iloc[-1]

                    # ---- keep_wait DCA 低接邏輯（獨立在主循環中） ----
                    if strategy_name == "keep_wait":
                        kw_initial = int(cfg.get("initial_shares", 12))
                        kw_add = int(cfg.get("add_shares", 6))
                        kw_drop_pct = float(cfg.get("add_drop_pct", 5))  # 百分比
                        kw_max_add = int(cfg.get("max_additions", 2))
                        kw_tp_pct = float(cfg.get("tp_trigger_pct", 15))
                        kw_tp_sell = float(cfg.get("tp_sell_ratio", 50))
                        kw_cooldown = int(cfg.get("cooldown_days", 30))

                        if symbol not in pyramid_tracker:
                            pyramid_tracker[symbol] = {
                                "buy_count": 0, "last_buy_price": 0.0,
                                "total_cost": 0.0, "total_shares": 0,
                                "sold_date": None,
                                "notified_tp": set(),
                            }
                        trk = pyramid_tracker[symbol]

                        # 保存下單前 tracker 狀態（下單失敗時回滾用）
                        kw_pre_state = {
                            "buy_count": trk["buy_count"],
                            "last_buy_price": trk["last_buy_price"],
                            "total_cost": trk["total_cost"],
                            "total_shares": trk["total_shares"],
                            "sold_date": trk["sold_date"],
                        }

                        # 冷卻中
                        if trk.get("sold_date") and trk["buy_count"] == -1:
                            days_since_sold = (datetime.now() - trk["sold_date"]).days
                            if days_since_sold < kw_cooldown:
                                signal = 0
                                continue
                            else:
                                trk["buy_count"] = 0  # 冷卻結束，重新開始

                        # 初始進場（先檢查是否已有持股）
                        if trk["buy_count"] == 0:
                            existing = holdings.get(symbol, 0)
                            if existing > 0:
                                trk["total_shares"] = existing
                                trk["total_cost"] = current_price * existing
                                trk["last_buy_price"] = current_price
                                trk["buy_count"] = 1
                                signal = 0
                                print(f"📋 {symbol} keep_wait 偵測到既有持股 {existing} 股，恢復 tracker 狀態")
                                continue
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
                            elif drop_pct >= kw_drop_pct and trk["buy_count"] < kw_max_add:
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

                    # ---- 處理訊號 ----
                    if signal != 0:
                        action = "BUY" if signal == 1 else "SELL"

                        if strategy_name == "keep_wait":
                            pass  # position_size 已在 DCA 邏輯中設定
                        else:
                            position_size = 0

                        # ---- 計算下單股數 ----
                        if strategy_name in ["bollinger", "vwap", "ma_cross"]:
                            target_amount = float(cfg.get("position_amount", 2500))

                            pyramid_enabled = cfg.get("pyramid_enabled", False)
                            if pyramid_enabled and action == "BUY" and strategy_name == "bollinger":
                                if symbol not in pyramid_tracker:
                                    pyramid_tracker[symbol] = {"buy_count": 0, "last_buy_price": 0}
                                tracker = pyramid_tracker[symbol]

                                tier1 = int(cfg.get("pyramid_tier1_shares", 200))
                                tier2 = int(cfg.get("pyramid_tier2_shares", 400))
                                tier3 = int(cfg.get("pyramid_tier3_shares", 600))
                                tier2_drop = float(cfg.get("pyramid_tier2_drop", 0.03))
                                tier3_drop = float(cfg.get("pyramid_tier3_drop", 0.05))

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
                            buy_shares = int(cfg.get("buy_shares", 50))
                            sell_shares = int(cfg.get("sell_shares", 100))
                            position_size = buy_shares if action == "BUY" else sell_shares

                        if position_size <= 0:
                            continue

                        # ---- 風險控管 ----
                        allowed, reject_reason = risk_manager.check_trade_allowed(
                            symbol, signal, current_price,
                            total_buy=total_buy_all, total_sell=total_sell_all)
                        if not allowed:
                            send_telegram_message(f"🛑 *{symbol}* 風險控管攔截（{reject_reason}）")
                            continue

                        if action == "BUY":
                            trade_cost = current_price * position_size
                            if not check_monthly_budget(symbol, trade_cost, budget_spent):
                                continue
                            if not check_stock_cap(symbol, trade_cost, stock_alloc):
                                continue

                        # ---- 大盤年線過濾 ----
                        if action == "BUY" and os.getenv("MARKET_TREND_FILTER", "true").lower() == "true":
                            if not market_filter.is_above_ma200():
                                print(f"🛑 {symbol} 買進被大盤年線過濾攔截")
                                continue

                        # ---- 庫存檢查 ----
                        if action == "SELL":
                            owned = holdings.get(symbol, 0)
                            if owned < position_size:
                                if owned > 0:
                                    print(f"⚠️  {symbol} 持有 {owned} 股，不足賣出 {position_size} 股，跳過")
                                continue

                        # ---- 最小利潤/損失門檻 ----
                        if PROFIT_MARGIN > 0 and action == "SELL":
                            alloc_data = stock_alloc.get(symbol, {})
                            sell_shares = alloc_data.get("total_buy_shares", 0)
                            sell_cost = alloc_data.get("total_buy_cost", 0.0)
                            if sell_shares > 0:
                                avg_cost = sell_cost / sell_shares
                            elif strategy_name == "keep_wait" and symbol in pyramid_tracker:
                                trk = pyramid_tracker[symbol]
                                avg_cost = (trk["total_cost"] / trk["total_shares"]
                                            if trk["total_shares"] > 0 else current_price)
                            else:
                                avg_cost = current_price
                            expected_profit = (current_price - avg_cost) * position_size
                            if abs(expected_profit) < PROFIT_MARGIN:
                                print(f"⏸️  {symbol} 預估損益 {expected_profit:+.0f} 低於門檻 {PROFIT_MARGIN:.0f}，跳過")
                                continue

                        # ---- 下單 ----
                        if USE_REAL_API:
                            order_result = broker.place_order(symbol, action.lower(), position_size)
                            if "error" in order_result:
                                # 下單失敗，回滾 pyramid_tracker 狀態（避免 keep_wait 卡在不一致狀態）
                                if strategy_name == "keep_wait":
                                    trk["buy_count"] = kw_pre_state["buy_count"]
                                    trk["last_buy_price"] = kw_pre_state["last_buy_price"]
                                    trk["total_cost"] = kw_pre_state["total_cost"]
                                    trk["total_shares"] = kw_pre_state["total_shares"]
                                    trk["sold_date"] = kw_pre_state["sold_date"]
                                continue
                        else:
                            broker.place_order(symbol, action, position_size)

                        risk_manager.log_trade(symbol, signal, current_price, position_size)

                        if action == "BUY":
                            holdings[symbol] = holdings.get(symbol, 0) + position_size
                        else:
                            holdings[symbol] = max(0, holdings.get(symbol, 0) - position_size)
                        save_holdings(holdings)

                        if MAX_DAILY_TRADES_PER_SYMBOL > 0:
                            daily_symbol_trades[symbol] = daily_symbol_trades.get(symbol, 0) + 1
                            save_daily_trades(daily_symbol_trades, daily_symbol_trades_date)

                        if action == "SELL":
                            last_trade_times[symbol] = now.isoformat()
                            save_last_trade_times(last_trade_times)

                            sell_proceeds = current_price * position_size
                            total_sell_all += sell_proceeds
                            if symbol in pyramid_tracker and strategy_name != "keep_wait":
                                del pyramid_tracker[symbol]
                            if symbol in stock_alloc:
                                alloc_data = stock_alloc[symbol]
                                if alloc_data["total_buy_shares"] > 0:
                                    avg_cost = alloc_data["total_buy_cost"] / alloc_data["total_buy_shares"]
                                    cost_basis = avg_cost * position_size
                                    profit = sell_proceeds - cost_basis
                                    alloc_data["total_buy_cost"] = max(0, alloc_data["total_buy_cost"] - cost_basis)
                                    alloc_data["total_buy_shares"] = max(0, alloc_data["total_buy_shares"] - position_size)
                                    save_stock_allocation(stock_alloc)
                                    if profit > 0 and strategy_name == "keep_wait":
                                        execute_keep_wait_on_profit_roll(symbol, profit)

                        if action == "BUY":
                            trade_cost = current_price * position_size
                            total_buy_all += trade_cost
                            update_monthly_spending(symbol, trade_cost, budget_spent)
                            stock_alloc[symbol]["total_buy_cost"] += trade_cost
                            stock_alloc[symbol]["total_buy_shares"] += position_size
                            save_stock_allocation(stock_alloc)

                        action_zh = "買進" if action == "BUY" else "賣出"
                        notice_msg = f"\n🔔 交易通知\n股票: {symbol}\n動作: {action_zh}\n價格: {current_price:.2f}\n股數: {position_size} 股\n策略: {strategy_name.upper()}"
                        send_trade_alert(symbol, action, current_price, position_size, strategy_name.upper())
                        send_line_notification(notice_msg)

                except Exception as e:
                    print(f"❌ {symbol} 錯誤: {e}")

            # Group 2 法人抬轎動能
            if INST_MOM_CAPITAL > 0:
                try:
                    inst_momentum.run(broker, risk_manager, holdings, now)
                except Exception as e:
                    print(f"❌ [INST_MOM] 執行錯誤: {e}")

            time.sleep(60)
            continue

        # ------------------------------------------------------------
        # 時段 2：收盤後 13:31-13:59 → 發送日報
        # ------------------------------------------------------------
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

        # ------------------------------------------------------------
        # 時段 3：非交易時段 → 休眠到下次開盤
        # ------------------------------------------------------------
        next_open = _next_market_open(now)
        sleep_seconds = min((next_open - now).total_seconds(), 3600)
        if sleep_seconds >= 3600:
            print(f"💤 非交易時段，下次開盤 {next_open.strftime('%m/%d %H:%M')}，休眠中...")
        time.sleep(max(sleep_seconds, 60))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()
