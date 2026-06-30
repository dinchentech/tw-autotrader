"""
backtest_inst_momentum.py — 法人抬轎動能策略回測
=================================================
使用 TWSE 公開 API 取得三大法人買賣資料（免配額限制）。
價格資料來自 FinMind（快取支援）。

策略邏輯：
  1. 篩選全市場（--daily 每日篩選，否則每週五篩選）
         流動性 > 2000 張 + 法人買超 > 3% + 創 20 日高 + 站穩 MA20
  2. 排序取前 TOP_N 名，隔日開盤進場
  3. 每日監控：硬性停損 / 跌破 MA10 移動停利

使用方法：
  python backtest_inst_momentum.py                      # 預設：2025-01-01 ~ 2025-12-31
  python backtest_inst_momentum.py --start 2022-01-01   # 自訂起日
  python backtest_inst_momentum.py --start 2023-01-01 --end 2023-12-31

輸出：
  回測_動能_2024_2025.MD（或對應年份的報告）
"""
import os
import sys
import argparse
import pickle
import math
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv()
from core.inst_strategy_core import (
    compute_fish_score as _core_compute_fish_score,
    precompute_fish_scores as _core_precompute_fish_scores,
    screen_fish_qualified as _core_screen_fish_qualified,
    check_momentum_entry as _core_check_momentum_entry,
    check_position_exit as _core_check_position_exit,
    is_banned as _core_is_banned,
    add_loser_ban as _core_add_loser_ban,
    compute_profit_roll as _core_compute_profit_roll,
    log_capital_roll as _core_log_capital_roll,
)
import core.inst_strategy_core as inst_core


def precompute_fish_scores(all_data):
    return _core_precompute_fish_scores(all_data)


def screen_fish_qualified(all_data, screening_date, fish_scores, fish_days, fish_min_score):
    return _core_screen_fish_qualified(all_data, screening_date, fish_scores, fish_days, fish_min_score)


def check_momentum_entry(all_data, stock_id, check_date):
    return _core_check_momentum_entry(all_data, stock_id, check_date)


def screen_candidates(all_data, screening_date):
    candidates = []
    for stock_id in all_data:
        passes, score = _core_check_momentum_entry(all_data, stock_id, screening_date)
        if passes:
            candidates.append((stock_id, score))
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:TOP_N]

# ─── 參數 ─────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="法人抬轎動能策略回測")
parser.add_argument("--start", default="2025-01-01", help="起始日期 (YYYY-MM-DD)")
parser.add_argument("--end", default="2025-12-31", help="結束日期 (YYYY-MM-DD)")
parser.add_argument("--daily", action="store_true", help="啟用每日篩選（預設為每週五篩選）")
parser.add_argument("--top", type=int, default=0, help="篩選標的數（依 STOCK_NO 環境變數，預設 150）")
parser.add_argument("--buy-ratio", type=float, default=None, help="法人買超門檻（預設 0.03）")
parser.add_argument("--stop-loss", type=float, default=None, help="停損幅度（預設 0.07）")
parser.add_argument("--min-volume", type=int, default=None, help="流動性門檻（張，預設 2000）")
parser.add_argument("--loser-ban", type=int, default=None, help="停損黑名單天數（預設 0=停用）")
parser.add_argument("--lookback", type=int, default=None, help="創高/MA 回溯期（預設 20）")
parser.add_argument("--no-fish-pre-filter", dest="fish_pre_filter", action="store_false",
                    help="停用法人低吃過濾（預設啟用）")
parser.set_defaults(fish_pre_filter=True)
parser.add_argument("--fish-days", type=int, default=None, help="低吃回溯天數（預設 60）")
parser.add_argument("--fish-score", type=float, default=None, help="低吃最低分數門檻（預設 4.0）")
parser.add_argument("--auto-capital", action="store_true", help="啟用自動化加碼（每M個月賺錢時自動增加投入本金）")
parser.add_argument("--auto-cap-months", type=int, default=3, help="自動化加碼檢討週期（月數，預設 3）")
parser.add_argument("--auto-cap-ratio", type=float, default=0.5, help="自動化加碼比例（獲利的%%，0.5=加碼50%%獲利，預設 0.5）")
parser.add_argument("--profit-roll-months", type=float, default=0, help="獲利滾入週期（月，0=每次賣出都滾入，預設 0）")
parser.add_argument("--profit-roll-percentage", type=float, default=1.0, help="獲利滾入比例（0-1，1.0=100%%滾入，預設 1.0）")
args = parser.parse_args()

START_DATE = args.start
END_DATE = args.end
DAILY_SCREENING = args.daily
MAX_STOCKS = int(os.getenv("STOCK_NO", "150"))  # 前 N 大股票，控制 FinMind API 呼叫量
TOP_N_STOCKS = args.top or MAX_STOCKS  # --top 覆蓋 MAX_STOCKS / STOCK_NO

CACHE_DIR = Path(f"cache/inst_momentum/{START_DATE[:4]}")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
# 價格資料跨年份共用快取（歷史股價不會改變，不用每年重載）
PRICE_CACHE_DIR = Path("cache/inst_momentum/price")
PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", os.getenv("TOTAL_CAPITAL", 500000)))
TOP_N = 3
MIN_VOLUME_SHARES = 2000        # 張
BUY_RATIO_THRESHOLD = 0.03
LOOKBACK = 20
STOP_LOSS = 0.10
TRAILING_PERIOD = 10
LOSER_BAN_DAYS = int(os.getenv("INST_MOM_LOSER_BAN_DAYS", "0"))
BUY_COST = 0.001425
SELL_COST = 0.004425

# ─── CLI 參數覆蓋常數 ─────────────────────────────────
if args.buy_ratio is not None:
    BUY_RATIO_THRESHOLD = args.buy_ratio
if args.stop_loss is not None:
    STOP_LOSS = args.stop_loss
if args.min_volume is not None:
    MIN_VOLUME_SHARES = args.min_volume
if args.loser_ban is not None:
    LOSER_BAN_DAYS = args.loser_ban
if args.lookback is not None:
    LOOKBACK = args.lookback

# ─── 同步覆蓋到共用核心模組 ────────────────────────
inst_core.MIN_VOLUME_SHARES = MIN_VOLUME_SHARES
inst_core.BUY_RATIO_THRESHOLD = BUY_RATIO_THRESHOLD
inst_core.LOOKBACK = LOOKBACK
inst_core.STOP_LOSS = STOP_LOSS
inst_core.TRAILING_PERIOD = TRAILING_PERIOD
inst_core.LOSER_BAN_DAYS = LOSER_BAN_DAYS
inst_core.BUY_COST = BUY_COST
inst_core.SELL_COST = SELL_COST

# ─── 法人低吃過濾參數 ────────────────────────────────
FISH_PRE_FILTER = args.fish_pre_filter
FISH_DAYS = args.fish_days or 60
FISH_MIN_SCORE = args.fish_score if args.fish_score is not None else 4.0

AUTO_CAPITAL = args.auto_capital
AUTO_CAP_MONTHS = args.auto_cap_months
AUTO_CAP_RATIO = args.auto_cap_ratio
PROFIT_ROLL_MONTHS = args.profit_roll_months
PROFIT_ROLL_PERCENTAGE = args.profit_roll_percentage
inst_core.PROFIT_ROLL_MONTHS = PROFIT_ROLL_MONTHS
inst_core.PROFIT_ROLL_PERCENTAGE = PROFIT_ROLL_PERCENTAGE


def finmind_login():
    from FinMind.data import DataLoader
    from dotenv import load_dotenv
    load_dotenv()
    token = os.getenv("FINMIND_API_TOKEN", "")
    dl = DataLoader(token=token)
    if token:
        dl.login_by_token(api_token=token)
    return dl


# ─── 階段 1a：下載價格資料（FinMind，含快取）─────────────

def get_all_stock_ids(dl) -> list:
    """回傳上市普通股 stock_id 列表（按市值排序取前 TOP_N_STOCKS）"""
    MCAP_RANKING = Path("cache/inst_momentum/mcap_ranking.pkl")
    n = TOP_N_STOCKS

    if MCAP_RANKING.exists():
        ranked = pickle.loads(MCAP_RANKING.read_bytes())
        # 過濾掉非 4 位數字（ETF、TDR 等）
        ranked = [s for s in ranked if s.isdigit() and len(s) == 4]
        ids = ranked[:n]
        print(f"📋 按市值排序，取前 {len(ids)} 檔上市股票")
        return ids

    # 無市值排名時，退而求其次：FinMind stock_id 排序
    cache_file = PRICE_CACHE_DIR / "stock_ids.pkl"
    if cache_file.exists():
        ids = pickle.loads(cache_file.read_bytes())
        return ids[:n]
    df = dl.taiwan_stock_info()
    ids = sorted(set(
        s.strip() for s in df["stock_id"]
        if s.strip().isdigit() and len(s.strip()) == 4
    ))
    ids = ids[:n]
    cache_file.write_bytes(pickle.dumps(ids))
    print(f"📋 上市股票總數: {len(ids)}（無市值排名，依 stock_id 排序）")
    return ids


def download_price_data(dl, stock_id: str) -> pd.DataFrame:
    """下載單一 stock 的日K，回傳含 ma20/ma10 的 DataFrame"""
    cache_file = PRICE_CACHE_DIR / f"{stock_id}.pkl"
    if cache_file.exists():
        df = pickle.loads(cache_file.read_bytes())
        if not df.empty and df["date"].max() >= pd.Timestamp(END_DATE) - timedelta(days=7):
            return df
    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d") - timedelta(days=60)
    start = start_dt.strftime("%Y-%m-%d")

    # 先試 FinMind，失敗則以 yfinance 補
    df_new = _try_finmind_price(dl, stock_id, start)
    if df_new is None:
        df_new = _try_yfinance_price(stock_id, start)

    if df_new is None or df_new.empty:
        return pd.DataFrame()

    df_price = df_new

    # 計算技術指標
    df_price["ma20"] = df_price["close"].rolling(LOOKBACK).mean()
    df_price["ma10"] = df_price["close"].rolling(TRAILING_PERIOD).mean()

    cache_file.write_bytes(pickle.dumps(df_price))
    return df_price


def _try_finmind_price(dl, stock_id: str, start: str) -> pd.DataFrame | None:
    """從 FinMind 下載股價，失敗回傳 None"""
    try:
        df = dl.taiwan_stock_daily(
            stock_id=stock_id, start_date=start, end_date=END_DATE
        )
    except Exception:
        return None
    if df.empty:
        return None
    df = df.rename(columns={
        "date": "date", "open": "open", "max": "high",
        "min": "low", "close": "close", "Trading_Volume": "volume",
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _try_yfinance_price(stock_id: str, start: str) -> pd.DataFrame | None:
    """以 yfinance 補下載股價，失敗回傳 None"""
    try:
        import yfinance as yf
        tk = yf.Ticker(f"{stock_id}.TW")
        df = tk.history(start=start, end=END_DATE)
    except Exception:
        return None
    if df.empty:
        return None
    df = df.reset_index()
    df["date"] = pd.to_datetime(df["Date"].dt.date)
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    df = df[["date", "open", "high", "low", "close", "volume"]]
    df = df.sort_values("date").reset_index(drop=True)
    return df


# ─── 階段 1b：從 TWSE 下載三大法人資料 ──────────────────────

def fetch_twse_inst_data(trading_dates: set) -> dict:
    """
    從 TWSE 公開 API 下載三大法人買賣超日報。
    TWSE 一次回傳全市場資料，不用逐股查詢，避開 FinMind 配額限制。

    回傳 { date_str: { stock_id: (inst_buy, inst_sell) } }
    其中 inst_buy/sell = 投信買進 + 外陸資買進/賣出
    """
    cache_key = f"twse_inst_{START_DATE}_{END_DATE}.pkl"
    cache_file = CACHE_DIR / cache_key
    if cache_file.exists():
        print(f"   載入 TWSE 法人資料快取（{cache_key}）...")
        return pickle.loads(cache_file.read_bytes())

    dates = sorted(d for d in trading_dates
                   if pd.Timestamp(START_DATE).date() <= d <= pd.Timestamp(END_DATE).date())
    inst_data = {}  # { date_str: { stock_id: (buy, sell) } }

    for i, d in enumerate(dates):
        date_str = d.strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999"
        try:
            resp = requests.get(url, timeout=15)
            data = resp.json()
        except Exception as e:
            print(f"  ⚠ TWSE 請求失敗 {date_str}: {e}")
            continue

        if data.get("stat") != "OK":
            continue

        day_data = {}
        for row in data.get("data", []):
            sid = str(row[0]).strip()
            if not sid.isdigit() or len(sid) != 4:
                continue
            try:
                foreign_buy = int(row[2].replace(",", ""))
                foreign_sell = int(row[3].replace(",", ""))
                trust_buy = int(row[8].replace(",", ""))
                trust_sell = int(row[9].replace(",", ""))
            except (ValueError, IndexError):
                continue
            day_data[sid] = (foreign_buy + trust_buy, foreign_sell + trust_sell)
        inst_data[d.isoformat()] = day_data

        if (i + 1) % 50 == 0:
            print(f"   TWSE 下載進度: {i+1}/{len(dates)}")

    cache_file.write_bytes(pickle.dumps(inst_data))
    print(f"✅ TWSE 法人資料下載完成: {len(inst_data)} 交易日")
    return inst_data


def merge_twse_inst(all_data: dict, twse_data: dict) -> dict:
    """
    將 TWSE 法人資料合併到各股的 DataFrame 中。
    使用 dict lookup 取代 DataFrame merge 以提升速度。
    """
    for stock_id, df in all_data.items():
        if df.empty:
            continue
        inst_buy_list = []
        inst_sell_list = []
        for d in df["date"]:
            d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            day_data = twse_data.get(d_str, {}).get(stock_id, (0, 0))
            inst_buy_list.append(day_data[0])
            inst_sell_list.append(day_data[1])
        df["inst_buy"] = inst_buy_list
        df["inst_sell"] = inst_sell_list
    return all_data


# ─── 階段 2a：法人低吃分數預計算 ──────────────────────

# ─── 階段 2b：兩階段篩選（低吃過濾 → 動能監控）────────────

# ─── 階段 3：交易模擬 ──────────────────────────────────

def check_position_exit(
    sid: str, positions: dict, daily_prices: dict, d: date, cash: float,
    trade_log: list, price_cache: dict
) -> tuple:
    price_info = daily_prices.get(sid, {})
    return _core_check_position_exit(sid, positions, price_info, d, cash, trade_log)


def build_price_cache(all_data, all_dates):
    price_cache = {}
    for d in all_dates:
        price_cache[d] = {}
    for stock_id, df in all_data.items():
        if df.empty:
            continue
        for _, row in df.iterrows():
            d = row["date"].date()
            if d in price_cache:
                price_cache[d][stock_id] = {
                    "close": row["close"],
                    "open": row["open"],
                    "ma10": row.get("ma10", None),
                    "ma20": row.get("ma20", None),
                    "volume": row["volume"],
                    "inst_buy": row.get("inst_buy", 0),
                    "inst_sell": row.get("inst_sell", 0),
                }
    return price_cache



def simulate(all_data: dict, candidates: dict = None,
             fish_qualified: dict = None, daily: bool = False,
             auto_capital: bool = False, auto_cap_months: int = 3,
             auto_cap_ratio: float = 1.0, profit_roll_months: float = 0,
             profit_roll_percentage: float = 1.0,
             all_dates: list = None,
             price_cache_prebuilt: dict = None) -> dict:
    """
    模擬交易。

    一般模式（candidates）：
      每週五篩選候選股，次週一開盤進場。

    低吃過濾模式（fish_qualified）：
      每篩選日更新觀察池，每日檢查池內動能訊號，有訊號隔日進場。

    自動化加碼（auto_capital=True）：
      每 M 個月結算，期間有獲利則按 P% 增加本金（本金只增不减）。
      新本金額度從下個月初起生效。

    獲利滾入（profit_roll_months, profit_roll_percentage）：
      賣出時若獲利，按 P% 滾入 general_cash 共享資金池。
      M=0 表示每次賣出都滾入，M>0 表示每 M 個月滾入一次。
    """
    cash = float(INITIAL_CAPITAL)
    general_cash = 0.0  # 共享資金池（滾入獲利）
    positions = {}       # { stock_id: { shares, buy_price, buy_date, last_roll_date } }
    trade_log = []
    equity_curve = []
    fish_mode = fish_qualified is not None

    # ── 自動化加碼狀態 ──
    current_capital = float(INITIAL_CAPITAL)  # 當前本金（會隨加碼調整）
    total_capital_invested = float(INITIAL_CAPITAL)  # 歷史總投入金額（含加碼）
    capital_schedule = [(all_dates[0] if all_dates else None, float(INITIAL_CAPITAL), "起始")]
    last_review_date = None   # 上次結算日
    last_review_capital = float(INITIAL_CAPITAL)  # 上次結算時的本金
    last_review_equity = float(INITIAL_CAPITAL)   # 上次結算時的權益

    # 收集所有交易日並排序
    if all_dates is None:
        all_dates = set()
        for df in all_data.values():
            if not df.empty:
                all_dates.update(df["date"].dt.date)
        all_dates = sorted(all_dates)

    # 預先建立每日價格 + 法人查詢（含 ma20, ma10, inst_buy, inst_sell）
    if price_cache_prebuilt is not None:
        price_cache = price_cache_prebuilt
    else:
        price_cache = {}
        for d in all_dates:
            price_cache[d] = {}
        for stock_id, df in all_data.items():
            if df.empty:
                continue
            for _, row in df.iterrows():
                d = row["date"].date()
                if d in price_cache:
                    price_cache[d][stock_id] = {
                        "close": row["close"],
                        "open": row["open"],
                        "ma10": row.get("ma10", None),
                        "ma20": row.get("ma20", None),
                        "volume": row["volume"],
                        "inst_buy": row.get("inst_buy", 0),
                        "inst_sell": row.get("inst_sell", 0),
                    }

    # 一般模式：篩選日 → 下個交易日對應
    screening_dates = sorted(candidates.keys()) if candidates else []
    next_day_map = {}
    for sd in screening_dates:
        for d in all_dates:
            if d > sd:
                next_day_map[sd] = d
                break

    # 低吃模式：每日對應下個交易日（用於標記隔日進場）
    all_dates_set = set(all_dates)
    next_trading_day = {}
    for i, d in enumerate(all_dates):
        for j in range(i + 1, len(all_dates)):
            if all_dates[j] > d:
                next_trading_day[d] = all_dates[j]
                break

    # 逐日模擬
    pending_entry = None  # (screening_date, candidates_list) 一般模式
    loser_ban = {}         # { stock_id: ban_until_date }

    # 低吃模式：每日動能標記
    fish_screening_dates = sorted(fish_qualified.keys()) if fish_mode else []
    fish_screening_idx = 0
    current_qualified = set()
    marked_for_entry = {}  # {entry_date: [(sid, score)]}

    def add_loser_ban(sid: str, sell_date: date):
        loser_ban[sid] = sell_date + timedelta(days=LOSER_BAN_DAYS)

    def is_banned(sid: str, today: date) -> bool:
        return sid in loser_ban and today <= loser_ban[sid]

    start_date = all_dates[0]

    for day_idx, d in enumerate(all_dates):
        daily_prices = price_cache[d]

        # ── 每日出場檢查 ──
        for sid in list(positions.keys()):
            proceeds, cost_basis, last_roll_date = check_position_exit(
                sid, positions, daily_prices, d, cash, trade_log, price_cache
            )
            if proceeds > 0:
                # 獲利滾入本金
                profit = proceeds - cost_basis
                rolled_amount = 0.0
                if profit > 0 and profit_roll_percentage > 0:
                    can_roll = (profit_roll_months == 0)  # M=0 → always roll
                    if not can_roll:
                        if last_roll_date:
                            months_since = (d.year - last_roll_date.year) * 12 + (d.month - last_roll_date.month)
                        else:
                            months_since = profit_roll_months
                        can_roll = months_since >= profit_roll_months
                    if can_roll:
                        rolled_amount = profit * profit_roll_percentage
                        current_capital += rolled_amount
                        trade_log.append({
                            "date": d.isoformat(), "action": "PROFIT_ROLL",
                            "stock_id": sid, "amount": round(rolled_amount, 0),
                            "description": f"獲利滾入: +NT${rolled_amount:.0f} (M={profit_roll_months}, P={profit_roll_percentage*100:.0f}%)"
                        })
                cash += proceeds

        if fish_mode and fish_screening_idx < len(fish_screening_dates):
            sd = fish_screening_dates[fish_screening_idx]
            if d >= sd:
                current_qualified = fish_qualified[sd]
                fish_screening_idx += 1

        # ── 一般模式：篩選日準備候選 ──
        if not fish_mode and d in candidates:
            pending_entry = (d, candidates[d])

        # ── 低吃模式：每日檢查觀察池動能訊號 ──
        if fish_mode and current_qualified:
            for sid in sorted(current_qualified):
                if sid in positions:
                    continue
                if is_banned(sid, d):
                    continue
                if len([s for s in positions if s not in current_qualified or True]) >= TOP_N:
                    break

                passes, score = check_momentum_entry(all_data, sid, pd.Timestamp(d))
                if passes:
                    entry_date = next_trading_day.get(d)
                    if entry_date:
                        if entry_date not in marked_for_entry:
                            marked_for_entry[entry_date] = []
                        marked_for_entry[entry_date].append((sid, score))

        # ── 執行日：出場檢查 + 買入新候選（一般模式） ──
        if not fish_mode and pending_entry is not None:
            screening_date, cands = pending_entry
            if d == next_day_map.get(screening_date):

                # 出場檢查：跌破 MA20
                for sid in list(positions.keys()):
                    price_info = daily_prices.get(sid, {})
                    current_price = price_info.get("close", 0)
                    if current_price <= 0:
                        continue
                    ma20 = price_info.get("ma20", 0)
                    if ma20 and not math.isnan(ma20) and current_price < ma20:
                        sell_price = price_info.get("open", current_price)
                        proceeds = positions[sid]["shares"] * sell_price * (1 - SELL_COST)
                        cost_basis = positions[sid]["shares"] * positions[sid]["buy_price"]
                        pnl = proceeds - cost_basis
                        last_roll_date = positions[sid].get("last_roll_date")
                        trade_log.append({
                            "date": d.isoformat(), "action": "SELL",
                            "stock_id": sid, "shares": positions[sid]["shares"],
                            "price": round(sell_price, 2), "pnl": round(pnl, 0),
                            "reason": "跌破 MA20 出場",
                        })
                        # 獲利滾入本金
                        rolled_amount = 0.0
                        if pnl > 0 and profit_roll_percentage > 0:
                            can_roll = (profit_roll_months == 0)
                            if not can_roll:
                                if last_roll_date:
                                    months_since = (d.year - last_roll_date.year) * 12 + (d.month - last_roll_date.month)
                                else:
                                    months_since = profit_roll_months
                                can_roll = months_since >= profit_roll_months
                            if can_roll:
                                rolled_amount = pnl * profit_roll_percentage
                                current_capital += rolled_amount
                                trade_log.append({
                                    "date": d.isoformat(), "action": "PROFIT_ROLL",
                                    "stock_id": sid, "amount": round(rolled_amount, 0),
                                    "description": f"獲利滾入: +NT${rolled_amount:.0f} (M={profit_roll_months}, P={profit_roll_percentage*100:.0f}%)"
                                })
                        cash += proceeds
                        if pnl < 0:
                            add_loser_ban(sid, d)
                        del positions[sid]

        # ── 一般模式：買入新候選 ──
        if not fish_mode and pending_entry is not None:
            screening_date, cands = pending_entry
            if d == next_day_map.get(screening_date):
                for stock_id, score in cands:
                    if stock_id in positions:
                        continue
                    if is_banned(stock_id, d):
                        continue
                    if len(positions) >= TOP_N:
                        break
                    price_info = daily_prices.get(stock_id, {})
                    buy_price = price_info.get("open", price_info.get("close", 0))
                    if buy_price <= 0:
                        continue
                    per_stock = current_capital / TOP_N
                    shares = int(per_stock / buy_price / 1000) * 1000
                    if shares <= 0:
                        continue
                    cost = shares * buy_price * (1 + BUY_COST)
                    if cash < cost:
                        shares = int(cash / (buy_price * (1 + BUY_COST)) / 1000) * 1000
                        if shares <= 0:
                            continue
                        cost = shares * buy_price * (1 + BUY_COST)
                    cash -= cost
                    positions[stock_id] = {
                        "shares": shares, "buy_price": buy_price, "buy_date": d,
                        "last_roll_date": d,
                    }
                    trade_log.append({
                        "date": d.isoformat(), "action": "BUY",
                        "stock_id": stock_id, "shares": shares,
                        "price": round(buy_price, 2), "pnl": 0,
                        "reason": f"篩選入選 score={score}",
                    })

        # ── 低吃模式：買入（隔日進場） ──
        if fish_mode and d in marked_for_entry:
            for stock_id, score in marked_for_entry[d]:
                if stock_id in positions:
                    continue
                if is_banned(stock_id, d):
                    continue
                if len(positions) >= TOP_N:
                    break
                price_info = daily_prices.get(stock_id, {})
                buy_price = price_info.get("open", price_info.get("close", 0))
                if buy_price <= 0:
                    continue
                per_stock = current_capital / TOP_N
                shares = int(per_stock / buy_price / 1000) * 1000
                if shares <= 0:
                    continue
                cost = shares * buy_price * (1 + BUY_COST)
                if cash < cost:
                    shares = int(cash / (buy_price * (1 + BUY_COST)) / 1000) * 1000
                    if shares <= 0:
                        continue
                    cost = shares * buy_price * (1 + BUY_COST)
                cash -= cost
                positions[stock_id] = {
                    "shares": shares, "buy_price": buy_price, "buy_date": d,
                    "last_roll_date": d,
                }
                trade_log.append({
                    "date": d.isoformat(), "action": "BUY",
                    "stock_id": stock_id, "shares": shares,
                    "price": round(buy_price, 2), "pnl": 0,
                    "reason": f"低吃池動能入場 score={score}",
                })
            del marked_for_entry[d]

        # ── 每日停損/停利檢查（第二輪，含 loser ban） ──
        for sid in list(positions.keys()):
            pos = positions[sid]
            price_info = daily_prices.get(sid, {})
            current_price = price_info.get("close", 0)
            if current_price <= 0:
                continue

            loss_pct = (current_price - pos["buy_price"]) / pos["buy_price"]
            if loss_pct <= -STOP_LOSS:
                proceeds = pos["shares"] * current_price * (1 - SELL_COST)
                cost_basis = pos["shares"] * pos["buy_price"]
                cash += proceeds
                pnl = proceeds - cost_basis
                trade_log.append({
                    "date": d.isoformat(),
                    "action": "SELL",
                    "stock_id": sid,
                    "shares": pos["shares"],
                    "price": round(current_price, 2),
                    "pnl": round(pnl, 0),
                    "reason": f"硬性停損 {loss_pct:.1%}",
                })
                if pnl < 0:
                    add_loser_ban(sid, d)
                del positions[sid]
                continue

            ma10 = price_info.get("ma10")
            if ma10 is not None and not math.isnan(ma10) and loss_pct > 0:
                if current_price < ma10:
                    proceeds = pos["shares"] * current_price * (1 - SELL_COST)
                    cost_basis = pos["shares"] * pos["buy_price"]
                    cash += proceeds
                    pnl = proceeds - cost_basis
                    trade_log.append({
                        "date": d.isoformat(),
                        "action": "SELL",
                        "stock_id": sid,
                        "shares": pos["shares"],
                        "price": round(current_price, 2),
                        "pnl": round(pnl, 0),
                        "reason": f"跌破 MA10({ma10:.0f})移動停利",
                    })
                    if pnl < 0:
                        add_loser_ban(sid, d)
                    del positions[sid]

        # ── 自動化加碼結算（月結） ──
        if auto_capital:
            months_diff = (d.year - start_date.year) * 12 + (d.month - start_date.month)
            is_review = months_diff > 0 and months_diff % auto_cap_months == 0 and \
                       (last_review_date is None or d.month != last_review_date.month or
                        (last_review_date.year, last_review_date.month) != (d.year, d.month))
            if is_review:
                if last_review_date is None:
                    last_review_equity = total_equity
                    last_review_capital = current_capital
                    last_review_date = d
                else:
                    period_profit = total_equity - last_review_equity
                    period_return = period_profit / last_review_capital
                    if period_return > 0:
                        injection = period_profit * auto_cap_ratio
                        cash += injection
                        total_capital_invested += injection
                        new_capital = current_capital + injection
                        capital_schedule.append((d, new_capital, f"+{period_return:.2%} 加碼{injection:,.0f}={period_profit:,.0f}×{auto_cap_ratio:.0%}"))
                        current_capital = new_capital
                    last_review_equity = total_equity
                    last_review_capital = current_capital
                    last_review_date = d

        # ── 當日權益 ──
        pos_value = 0
        for sid, pos in positions.items():
            price_info = daily_prices.get(sid, {})
            p = price_info.get("close", pos["buy_price"])
            pos_value += pos["shares"] * p

        total_equity = cash + general_cash + pos_value
        equity_curve.append({
            "date": d.isoformat(),
            "cash": round(cash, 0),
            "general_cash": round(general_cash, 0),
            "position_value": round(pos_value, 0),
            "total_equity": round(total_equity, 0),
            "capital": round(current_capital, 0),
        })

    # 期末平倉
    for sid in list(positions.keys()):
        pos = positions.pop(sid)
        last_d = all_dates[-1]
        price_info = price_cache.get(last_d, {}).get(sid, {})
        sell_price = price_info.get("close", pos["buy_price"])
        proceeds = pos["shares"] * sell_price * (1 - SELL_COST)
        cost_basis = pos["shares"] * pos["buy_price"]
        pnl = proceeds - cost_basis
        last_roll_date = pos.get("last_roll_date")
        trade_log.append({
            "date": last_d.isoformat(),
            "action": "SELL",
            "stock_id": sid,
            "shares": pos["shares"],
            "price": round(sell_price, 2),
            "pnl": round(pnl, 0),
            "reason": "期末平倉",
        })
        # 獲利滾入本金
        rolled_amount = 0.0
        if pnl > 0 and profit_roll_percentage > 0:
            can_roll = (profit_roll_months == 0)
            if not can_roll:
                if last_roll_date:
                    months_since = (last_d.year - last_roll_date.year) * 12 + (last_d.month - last_roll_date.month)
                else:
                    months_since = profit_roll_months
                can_roll = months_since >= profit_roll_months
            if can_roll:
                rolled_amount = pnl * profit_roll_percentage
                current_capital += rolled_amount
                trade_log.append({
                    "date": last_d.isoformat(), "action": "PROFIT_ROLL",
                    "stock_id": sid, "amount": round(rolled_amount, 0),
                    "description": f"獲利滾入: +NT${rolled_amount:.0f} (M={profit_roll_months}, P={profit_roll_percentage*100:.0f}%)"
                })
        cash += proceeds
        if equity_curve:
            equity_curve[-1]["cash"] = round(cash, 0)
            equity_curve[-1]["general_cash"] = round(general_cash, 0)
            equity_curve[-1]["position_value"] = 0
            equity_curve[-1]["total_equity"] = round(cash + general_cash, 0)

    return {
        "final_cash": cash,
        "general_cash": general_cash,
        "total_return": (cash + general_cash - INITIAL_CAPITAL) / INITIAL_CAPITAL,
        "trade_log": trade_log,
        "equity_curve": equity_curve,
        "capital_schedule": capital_schedule,
        "total_capital_invested": total_capital_invested,
        "profit_roll_months": profit_roll_months,
        "profit_roll_percentage": profit_roll_percentage,
    }


# ─── 階段 4：計算績效指標 ────────────────────────────────

def compute_metrics(result: dict) -> dict:
    trades = result["trade_log"]
    equity = result["equity_curve"]

    if not trades:
        final_eq = result.get("final_cash", INITIAL_CAPITAL)
        return {
            "total_trades": 0,
            "buy_trades": 0,
            "sell_trades": 0,
            "closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "avg_win": 0,
            "avg_loss": 0,
            "profit_factor": 0.0,
            "max_drawdown": 0,
            "max_drawdown_pct": 0.0,
            "total_return": round((final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL, 4),
            "final_equity": round(final_eq, 0),
        }

    buys = [t for t in trades if t["action"] == "BUY"]
    sells = [t for t in trades if t["action"] == "SELL"]
    total_trades = len(buys) + len(sells)

    closed_trades = [t for t in sells if t.get("pnl", 0) != 0]
    wins = [t for t in closed_trades if t["pnl"] > 0]
    losses = [t for t in closed_trades if t["pnl"] < 0]
    win_rate = len(wins) / len(closed_trades) if closed_trades else 0

    avg_win = np.mean([t["pnl"] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t["pnl"] for t in losses])) if losses else 0
    profit_factor = avg_win / avg_loss if avg_loss > 0 else float("inf")

    peak = INITIAL_CAPITAL
    max_drawdown = 0
    max_drawdown_pct = 0
    for e in equity:
        if e["total_equity"] > peak:
            peak = e["total_equity"]
        dd = peak - e["total_equity"]
        dd_pct = dd / peak if peak > 0 else 0
        if dd_pct > max_drawdown_pct:
            max_drawdown = dd
            max_drawdown_pct = dd_pct

    return {
        "total_trades": total_trades,
        "buy_trades": len(buys),
        "sell_trades": len(sells),
        "closed_trades": len(closed_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 0),
        "avg_loss": round(avg_loss, 0),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_drawdown, 0),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "total_return": round(result["total_return"], 4),
        "final_equity": round(result["final_cash"] + result.get("general_cash", 0), 0),
    }


def generate_monthly_breakdown(equity_curve: list, capital: float) -> list:
    monthly = defaultdict(lambda: {"start": 0, "end": 0, "high": 0, "low": float("inf")})
    for e in equity_curve:
        m = e["date"][:7]
        monthly[m]["end"] = e["total_equity"]
        if monthly[m]["start"] == 0:
            monthly[m]["start"] = e["total_equity"]
        monthly[m]["high"] = max(monthly[m]["high"], e["total_equity"])
        monthly[m]["low"] = min(monthly[m]["low"], e["total_equity"])

    rows = []
    prev_end = capital
    for m in sorted(monthly):
        d = monthly[m]
        ret = (d["end"] - prev_end) / prev_end * 100
        rows.append({
            "month": m,
            "start": d["start"],
            "end": d["end"],
            "return_pct": round(ret, 2),
            "high": d["high"],
            "low": d["low"],
        })
        prev_end = d["end"]
    return rows


def generate_report(result: dict, metrics: dict, monthly: list):
    """產生回測報告，檔名依日期範圍自動命名"""
    year_label = START_DATE[:4] + ("-" + END_DATE[:4] if START_DATE[:4] != END_DATE[:4] else "")
    report_filename = f"回測_動能_{year_label}.MD"
    lines = []
    lines.append(f"# 法人抬轎動能策略 — {year_label} 回測報告")
    lines.append("")
    lines.append("## 策略摘要")
    lines.append("")
    lines.append("| 項目 | 內容 |")
    lines.append("|------|------|")
    lines.append("| **策略名稱** | 法人抬轎動能策略（Group 2） |")
    lines.append(f"| **回測期間** | {START_DATE} → {END_DATE} |")
    lines.append(f"| **起始本金** | NT${int(INITIAL_CAPITAL):,} |")
    lines.append("| **交易成本** | 買 0.1425% / 賣 0.4425% |")
    lines.append(f"| **持有檔數** | {TOP_N} 檔 |")
    lines.append(f"| **流動性門檻** | 近 5 日平均 > {MIN_VOLUME_SHARES} 張 |")
    lines.append(f"| **法人買超門檻** | 投信+外資佔比 > {BUY_RATIO_THRESHOLD:.0%} |")
    lines.append(f"| **動能條件** | 創 {LOOKBACK} 日新高 + 站穩 MA{LOOKBACK} |")
    lines.append(f"| **停損** | {STOP_LOSS:.0%} 硬性停損 |")
    lines.append(f"| **停利** | 跌破 MA{TRAILING_PERIOD} 移動停利 |")
    lines.append(f"| **資料來源** | 股價: FinMind / 法人: TWSE 公開 API |")
    lines.append(f"| **篩選標的數** | 全市場前 {TOP_N_STOCKS} 檔（市值排序）|")
    if FISH_PRE_FILTER:
        lines.append(f"| **法人低吃過濾** | 篩選日前 {FISH_DAYS} 天內低吃分數 ≥ {FISH_MIN_SCORE} |")
    if AUTO_CAPITAL:
        lines.append(f"| **自動化加碼** | 每 {AUTO_CAP_MONTHS} 個月結算，獲利時加碼 {AUTO_CAP_RATIO:.0%}（本金只增不減）|")
    if PROFIT_ROLL_MONTHS > 0 or PROFIT_ROLL_PERCENTAGE < 1.0:
        lines.append(f"| **獲利滾入** | 每 {PROFIT_ROLL_MONTHS} 個月滾入 {PROFIT_ROLL_PERCENTAGE:.0%} 獲利至共享資金池 |")
    capital_schedule = result.get("capital_schedule", [])
    if AUTO_CAPITAL and len(capital_schedule) > 1:
        lines.append("")
        lines.append("## 本金變動記錄")
        lines.append("")
        lines.append("| 日期 | 本金 | 觸發原因 |")
        lines.append("|------|------|----------|")
        for entry_date, cap, trigger in capital_schedule:
            dt = entry_date.isoformat() if hasattr(entry_date, 'isoformat') else str(entry_date)
            lines.append(f"| {dt} | NT${cap:,.0f} | {trigger} |")
    lines.append("")
    lines.append("## 績效總覽")
    lines.append("")
    lines.append("| 指標 | 數值 |")
    lines.append("|------|------|")
    lines.append(f"| **最終權益** | NT${metrics['final_equity']:,.0f} |")
    lines.append(f"| **總報酬率** | {metrics['total_return']:+.2%} |")
    general_cash = result.get("general_cash", 0)
    if general_cash > 0:
        lines.append(f"| **滾入資金池** | NT${general_cash:,.0f} |")
    profit_roll_transactions = [t for t in result["trade_log"] if t.get("action") == "PROFIT_ROLL"]
    total_profit_roll = sum(t.get("amount", 0) for t in profit_roll_transactions)
    if total_profit_roll > 0:
        lines.append(f"| **獲利滾入總額** | NT${total_profit_roll:,.0f} (M={PROFIT_ROLL_MONTHS}, P={PROFIT_ROLL_PERCENTAGE:.0%}) |")
    lines.append(f"| **總交易次數** | {metrics['total_trades']}（買 {metrics['buy_trades']} / 賣 {metrics['sell_trades']}） |")
    lines.append(f"| **勝率** | {metrics['win_rate']:.2%} |")
    lines.append(f"| **平均獲利** | NT${metrics['avg_win']:,.0f} |")
    lines.append(f"| **平均虧損** | NT${metrics['avg_loss']:,.0f} |")
    lines.append(f"| **獲利因子** | {metrics['profit_factor']:.2f} |")
    lines.append(f"| **最大回撤** | NT${metrics['max_drawdown']:,.0f} ({metrics['max_drawdown_pct']:.2%}) |")
    lines.append("")
    lines.append("## 逐月權益變化")
    lines.append("")
    lines.append("| 月份 | 月初權益 | 月底權益 | 月報酬 | 月高點 | 月低點 |")
    lines.append("|------|---------|---------|--------|--------|--------|")
    for m in monthly:
        lines.append(
            f"| {m['month']} | NT${m['start']:,.0f} | NT${m['end']:,.0f} | "
            f"{m['return_pct']:+.2f}% | NT${m['high']:,.0f} | NT${m['low']:,.0f} |"
        )
    lines.append("")
    lines.append("## 逐筆交易紀錄")
    lines.append("")
    lines.append("| 日期 | 動作 | 股票 | 股數 | 價格 | 損益 | 原因 |")
    lines.append("|------|------|------|------|------|------|------|")
    for t in result["trade_log"]:
        if t["action"] == "PROFIT_ROLL":
            lines.append(
                f"| {t['date']} | {t['action']} | {t['stock_id']} | "
                f"- | - | {t.get('amount', 0):,} | {t['description']} |"
            )
        else:
            pnl_str = f"NT${t['pnl']:+,.0f}" if t["action"] == "SELL" else "-"
            lines.append(
                f"| {t['date']} | {t['action']} | {t['stock_id']} | "
                f"{t['shares']:,} | ${t['price']:.2f} | {pnl_str} | {t['reason']} |"
            )
    lines.append("")
    lines.append("---")
    lines.append(f"*報告產生時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    report = "\n".join(lines)
    Path(report_filename).write_text(report, encoding="utf-8")
    print(f"\n✅ 回測報告已寫入 {report_filename}")
    return report


# ═════════════════════════════════════════════════════════
# 主流程
# ═════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("📊 法人抬轎動能策略 2025 回測")
    print(f"   本金: NT${INITIAL_CAPITAL:,}")
    print(f"   期間: {START_DATE} ~ {END_DATE}")
    print(f"   資料: FinMind 股價 + TWSE 三大法人")
    print("=" * 60)

    # ── 1a. 價格資料 ──
    print("\n📥 階段 1a/4：讀取價格資料（快取）")
    dl = finmind_login()

    stock_ids = get_all_stock_ids(dl)
    print(f"   共 {len(stock_ids)} 檔上市股票")

    all_data = {}
    for i, sid in enumerate(stock_ids):
        df = download_price_data(dl, sid)
        if not df.empty:
            all_data[sid] = df
        if (i + 1) % 200 == 0:
            print(f"   進度: {i+1}/{len(stock_ids)}（已載入 {len(all_data)} 檔有資料）")

    print(f"✅ 價格資料: {len(all_data)} 檔股票有交易資料")

    # ── 1b. TWSE 法人資料 ──
    print("\n📥 階段 1b/4：下載三大法人資料（TWSE 公開 API）")
    all_dates = sorted(set(
        d.date() if hasattr(d, 'date') else d
        for df in all_data.values() if not df.empty
        for d in df["date"]
    ))
    print(f"   交易日數: {len(all_dates)}")
    twse_raw = fetch_twse_inst_data(set(all_dates))
    print(f"✅ 法人資料: {len(twse_raw)} 個交易日有資料")

    print("\n📥 階段 1c/4：合併法人資料...")
    all_data = merge_twse_inst(all_data, twse_raw)

    # ── 1d. 法人低吃分數預計算（選用） ──
    fish_scores = None
    if FISH_PRE_FILTER:
        print(f"\n📥 階段 1d/4：預計算法人低吃分數（回溯 {FISH_DAYS} 天，門檻 ≥ {FISH_MIN_SCORE}）...")
        fish_scores = precompute_fish_scores(all_data)

    # ── 2. 篩選（一般模式每週/低吃模式兩階段） ──
    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d").date()
    if DAILY_SCREENING:
        fridays = sorted(set(d for d in all_dates if d >= start_dt))
    else:
        fridays = sorted(set(d for d in all_dates if d.weekday() == 4))
        fridays = [d for d in fridays if d >= start_dt]

    if FISH_PRE_FILTER:
        # ── 低吃模式：階段一 — 觀察池篩選 ──
        step_label = "日" if DAILY_SCREENING else "週"
        freq_label = "每日" if DAILY_SCREENING else "每週"
        print(f"\n🔍 階段 2/4：篩選法人低吃觀察池（{freq_label}）...")
        fish_qualified = {}
        for i, fd in enumerate(fridays):
            screening_ts = pd.Timestamp(fd)
            qualified = screen_fish_qualified(
                all_data, screening_ts, fish_scores, FISH_DAYS, FISH_MIN_SCORE
            )
            if qualified:
                fish_qualified[fd] = qualified
            if (i + 1) % 50 == 0 or (i + 1) == len(fridays):
                print(f"   篩選進度: {i+1}/{len(fridays)} {step_label}（{len(fish_qualified)} {step_label}有合格觀察池）")

        print(f"✅ 低吃觀察池篩選完成: {len(fridays)} 個{step_label}中 {len(fish_qualified)} {step_label}有觀察池")
        print(f"   階段二：每日檢查觀察池動能訊號（在模擬交易中執行）")
        candidates = {}
    else:
        # ── 一般模式：每週篩選候選股 ──
        mode = "逐日" if DAILY_SCREENING else "逐週"
        step_label = "交易日" if DAILY_SCREENING else "週"
        print(f"\n🔍 階段 2/4：篩選每{'' if DAILY_SCREENING else '週'}候選股...（{mode}模式）")

        candidates = {}
        for i, fd in enumerate(fridays):
            screening_ts = pd.Timestamp(fd)
            cands = screen_candidates(all_data, screening_ts)
            if cands:
                candidates[fd] = cands
            if (i + 1) % 50 == 0 or (i + 1) == len(fridays):
                print(f"   篩選進度: {i+1}/{len(fridays)} {step_label}（{len(candidates)} {step_label}有候選股）")

        print(f"✅ 篩選完成: {len(fridays)} 個{step_label}中 {len(candidates)} {step_label}有合格標的")
        fish_qualified = None

    # 輸出篩選歷史（一般模式）
    if not FISH_PRE_FILTER:
        screen_log = []
        for fd, cands in sorted(candidates.items()):
            names = ", ".join(f"{s}({sc:.2%})" for s, sc in cands)
            fd_s = fd.isoformat() if hasattr(fd, "isoformat") else str(fd)[:10]
            screen_log.append(f"  {fd_s}: {names}")
        Path("cache/inst_momentum/screen_history.txt").write_text(
            "\n".join(screen_log), encoding="utf-8"
        )
        print(f"   篩選歷史已寫入 cache/inst_momentum/screen_history.txt")

    # ── 3. 模擬交易 ──
    print("\n💰 階段 3/4：模擬交易...")
    result = simulate(all_data, candidates=candidates if not FISH_PRE_FILTER else None,
                      fish_qualified=fish_qualified, daily=DAILY_SCREENING,
                      auto_capital=AUTO_CAPITAL, auto_cap_months=AUTO_CAP_MONTHS,
                      auto_cap_ratio=AUTO_CAP_RATIO,
                      profit_roll_months=PROFIT_ROLL_MONTHS,
                      profit_roll_percentage=PROFIT_ROLL_PERCENTAGE,
                      all_dates=all_dates)
    metrics = compute_metrics(result)
    monthly = generate_monthly_breakdown(result["equity_curve"], INITIAL_CAPITAL)

    print(f"   最終權益: NT${metrics['final_equity']:,.0f}")
    print(f"   總報酬: {metrics['total_return']:+.2%}")
    print(f"   交易次數: {metrics['total_trades']}")
    print(f"   勝率: {metrics['win_rate']:.2%}")
    print(f"   最大回撤: {metrics['max_drawdown_pct']:.2%}")

    # ── 4. 產生報告 ──
    print("\n📝 階段 4/4：產生回測報告...")
    generate_report(result, metrics, monthly)
    print("\n✅ 回測全部完成！")


if __name__ == "__main__":
    main()
