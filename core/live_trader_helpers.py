import os
import json
import time
import requests
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # 讀取 .env 檔

SYS_TELEGRAM_BOT_TOKEN = "8459224155:AAFL5OaRHUqnuCJBg_yTiJSmIYPcQ5YwS8M"
SYS_TELEGRAM_CHAT_ID = "8384117171"

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

# 載入用戶自訂策略
try:
    from user_strategies import USER_STRATEGY_MAP
    STRATEGY_FUNCS.update(USER_STRATEGY_MAP)
    print(f"✅ 已載入 {len(USER_STRATEGY_MAP)} 個用戶自訂策略")
except ImportError:
    print("ℹ️  未找到 user_strategies.py，僅使用內建策略")


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
        df = pd.read_csv(csv_path, on_bad_lines='skip')
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


def send_closing_summary():
    try:
        holdings_path = Path("logs/holdings.json")
        alloc_path = Path("logs/stock_allocation.json")
        csv_path = Path("logs/performance.csv")

        if not holdings_path.exists():
            return

        with open(holdings_path) as f:
            holdings = json.load(f)
        if not holdings:
            return

        alloc = {}
        if alloc_path.exists():
            with open(alloc_path) as f:
                alloc = json.load(f)

        date_str = datetime.now().strftime("%Y-%m-%d")

        msg = f"📋 *收盤持倉報告 ({date_str})* V{APP_VERSION}\n"
        msg += "─" * 20 + "\n"

        total_cost = 0
        total_value = 0
        total_unrealized = 0

        for sym in sorted(holdings.keys()):
            shares = holdings.get(sym, 0)
            if shares <= 0:
                continue
            alloc_data = alloc.get(sym, {})
            avg_cost = 0
            if alloc_data.get("total_buy_shares", 0) > 0:
                avg_cost = alloc_data["total_buy_cost"] / alloc_data["total_buy_shares"]

            current_price = avg_cost
            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path, on_bad_lines='skip')
                    sym_df = df[df["symbol"] == sym]
                    if not sym_df.empty:
                        current_price = sym_df["price"].iloc[-1]
                except Exception:
                    pass

            cost_basis = avg_cost * shares if avg_cost > 0 else 0
            market_value = current_price * shares
            unrealized = market_value - cost_basis
            pct = (current_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0

            total_cost += cost_basis
            total_value += market_value
            total_unrealized += unrealized

            emoji = "🟢" if unrealized >= 0 else "🔴"
            msg += f"{emoji} {sym}: {shares}股\n"
            msg += f"   成本均價 {avg_cost:,.0f} | 參考市價 {current_price:,.0f}\n"
            msg += f"   未實現損益 {unrealized:+,.0f} ({pct:+.2f}%)\n"

        msg += "─" * 20 + "\n"
        msg += f"總成本: NT${total_cost:,.0f}\n"
        msg += f"總市值: NT${total_value:,.0f}\n"
        msg += f"未實現損益: {'+' if total_unrealized >= 0 else ''}{total_unrealized:,.0f}\n"

        send_telegram_message(msg)
        print("✅ 收盤持倉報告已發送")
    except Exception as e:
        print(f"❌ 發送收盤持倉報告失敗: {e}")


def _next_market_open(now: datetime) -> datetime:
    """計算下次台股開盤時間 (交易日 08:45，提前暖機)"""
    if now.weekday() < 5 and (now.hour < 8 or (now.hour == 8 and now.minute < 45)):
        return now.replace(hour=8, minute=45, second=0, microsecond=0)
    for days in range(1, 8):
        dt = now + timedelta(days=days)
        if dt.weekday() < 5:
            return dt.replace(hour=8, minute=45, second=0, microsecond=0)
    return now.replace(hour=8, minute=45) + timedelta(days=1)


APP_VERSION = "2.03"
BUILD_DATE = "2026-07-12 18:00:00"


def get_stock_capital(symbol: str) -> float:
    """計算單一股票的資金上限"""
    cfg = PORTFOLIO_CONFIG.get(symbol, {})
    alloc_pct = float(cfg.get("alloc", 20))
    return TOTAL_CAPITAL * alloc_pct / 100.0


