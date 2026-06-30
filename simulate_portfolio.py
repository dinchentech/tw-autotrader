"""
simulate_portfolio.py — 完整投資組合模擬（每月定期定額 / 一筆資金）

Simulates:
  - Corrected VWAP (volume-weighted) 
  - Per-symbol position management (buy on signal 1, sell all on signal -1)
  - 手續費 0.1425% + 證交稅 (ETF 0.1% / 股票 0.3%)
  - Monthly DCA capital injection
  - Monthly portfolio valuation
  - Markdown report generation matching 回溯_2024_2025.MD / 回溯_50万_2024_2025.MD format
"""

import os, sys, csv, argparse
from datetime import datetime, timedelta, date
from typing import Optional
import pandas as pd
import numpy as np
import calendar
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data.yahoo_loader import load_historical_data
from config.symbols import get_yahoo_suffix
from core.config_loader import load_portfolio_config, get_strategy_params

# ── strategies ──────────────────────────────────────────────
from strategies.vwap_deviation import vwap_deviation_strategy
from strategies.ma_cross import ma_cross_strategy
from strategies.bollinger import bollinger_reverse_strategy
from strategies.breakout import breakout_strategy

STRATEGY_MAP = {
    "vwap":     vwap_deviation_strategy,
    "ma_cross": ma_cross_strategy,
    "bollinger": bollinger_reverse_strategy,
    "breakout":  breakout_strategy,
}

# 預設參數（與 backtest.py 一致）
DEFAULT_PARAMS = {
    "vwap":     {"sigma_mult": 1.5, "rsi_period": 5},
    "ma_cross": {"fast_period": 14, "slow_period": 60, "atr_threshold": 0.0},
    "bollinger": {"window": 20, "std_dev": 2.0, "rsi_period": 5},
    "breakout":  {"lookback": 25, "atr_period": 14, "atr_threshold": 0.02},
}

# 標的類別（判斷證交稅率）
ETF_SYMBOLS = {"0050", "0056", "00632R", "00646", "006208", "00878"}

COMMISSION_RATE = 0.001425       # 手續費 0.1425%
STOCK_TAX_RATE = 0.003           # 證交稅 股票 0.3%
ETF_TAX_RATE = 0.001             # 證交稅 ETF 0.1%


def tax_rate(symbol: str) -> float:
    return ETF_TAX_RATE if symbol in ETF_SYMBOLS else STOCK_TAX_RATE


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


# ── data loading with cache ─────────────────────────────────
_cache = {}
def get_data(symbol: str, start: str = "2023-01-01") -> pd.DataFrame:
    if symbol in _cache:
        return _cache[symbol]
    yf_sym = symbol + get_yahoo_suffix(symbol)
    df = load_historical_data(yf_sym, start=start)
    _cache[symbol] = df
    return df


def run_strategy(symbol: str, strategy_name: str, start: str = "2023-01-01",
                 params: Optional[dict] = None) -> pd.DataFrame:
    """下載資料 + 執行策略，回傳含 signal 欄位的 DataFrame"""
    df = get_data(symbol, start=start)
    if df.empty:
        return df
    if strategy_name == "keep_wait":
        # keep_wait 不需要訊號，直接回傳原始資料（signal=0）
        df["signal"] = 0
        return df
    # 從 PC_ 設定讀取策略參數（如有）
    pc_config = load_portfolio_config()
    pc_params = get_strategy_params(pc_config.get(symbol, {}), strategy_name) if symbol in pc_config else {}
    p = {**DEFAULT_PARAMS.get(strategy_name, {}), **pc_params, **(params or {})}
    func = STRATEGY_MAP[strategy_name]
    return func(df, **p)


# ── Portfolio Simulation Core ────────────────────────────────

class Position:
    """單一標的的持倉"""
    def __init__(self, symbol: str, strategy: str):
        self.symbol = symbol
        self.strategy = strategy
        self.shares = 0.0
        self.cost_basis = 0.0  # total cost paid (NT$)
        self.last_roll_year = None  # 上次滾入年份
        self.last_roll_month = None  # 上次滾入月份
        self.trades: list[dict] = []  # transaction log

    def value(self, price: float) -> float:
        return self.shares * price

    def buy(self, date, price: float, cash: float):
        """用 cash 買入最多股數, 回傳實際花費"""
        if cash <= 0 or price <= 0:
            return 0.0
        commission = round(cash * COMMISSION_RATE)
        # 實際可用於買股的錢
        available = cash - commission
        if available <= 0:
            return 0.0
        shares_bought = available / price
        cost = round(shares_bought * price, 2)
        actual_commission = round(cost * COMMISSION_RATE)
        total_cost = cost + actual_commission

        self.shares += shares_bought
        self.cost_basis += total_cost
        # 初始化滾入追蹤
        self.last_roll_year = date.year
        self.last_roll_month = date.month
        self.trades.append({
            "date": date, "type": "buy", "price": price,
            "shares": round(shares_bought, 4), "amount": round(cost, 2),
            "commission": actual_commission, "tax": 0,
        })
        return total_cost

    def sell(self, date, price: float) -> float:
        """賣出全部持股, 回傳淨收入（扣除費用後）"""
        if self.shares <= 0 or price <= 0:
            return 0.0
        proceeds = self.shares * price
        commission = round(proceeds * COMMISSION_RATE)
        tax = round(proceeds * tax_rate(self.symbol))
        net = proceeds - commission - tax

        self.trades.append({
            "date": date, "type": "sell", "price": price,
            "shares": round(self.shares, 4), "amount": round(proceeds, 2),
            "commission": commission,
            "tax": round(tax, 2),
        })
        val = round(net, 2)
        self.shares = 0.0
        self.cost_basis = 0.0
        return val


def first_trading_days_of_month(dates: pd.DatetimeIndex) -> set:
    """回傳每個月第一個交易日 set"""
    seen = set()
    result = set()
    for d in sorted(dates):
        ym = (d.year, d.month)
        if ym not in seen:
            seen.add(ym)
            result.add(d)
    return result


def simulate_dca(config_list, start_date="2022-01-01", end_date="2025-12-31",
                 monthly_total=20000, profit_roll_months=0.0, profit_roll_percentage=1.0) -> dict:
    """
    定期定額模擬 - 支援獲利滾入本金功能

    config_list: [(symbol, strategy, monthly_allocation), ...]
    profit_roll_months: M 個月 - 每 M 個月滾入一次已實現獲利 (預設 0=立即滾入)
    profit_roll_percentage: P % - 滾入比例 (0-1 間，預設 1.0 = 100%)
    """
    # 收集所有標的的 signal data
    symbols = list(set(c[0] for c in config_list))
    signal_data = {}
    for sym in symbols:
        strategy_name = next(c[1] for c in config_list if c[0] == sym)
        df = run_strategy(sym, strategy_name, start=start_date)
        if df.empty:
            print(f"  ⚠️ {sym} 資料為空，跳過")
            continue
        if end_date:
            df = df[df.index <= end_date]
        signal_data[sym] = df

    # 初始化持倉
    positions = {c[0]: Position(c[0], c[1]) for c in config_list}

    # 每月配置現金 (symbol -> cash bucket)
    cash_buckets = {c[0]: 0.0 for c in config_list}

    # 追蹤月價值
    monthly_records = []
    all_dates = pd.DatetimeIndex(sorted(set(
        d for df in signal_data.values() for d in df.index
    )))
    first_days = first_trading_days_of_month(all_dates)

    total_injected = 0.0
    transaction_log: list[dict] = []
    general_cash = 0.0  # 共享資金池（滾入獲利）

    # 逐日模擬
    for current_date in sorted(all_dates):
        # 月初撥款
        if current_date in first_days and current_date >= pd.Timestamp(start_date):
            for sym, _, alloc in config_list:
                cash_buckets[sym] += alloc
            total_injected += monthly_total

        # 處理每個標的的訊號
        for sym, strategy_name, _ in config_list:
            if sym not in signal_data:
                continue
            df = signal_data[sym]
            if current_date not in df.index:
                continue
            row = df.loc[current_date]
            sig = row.get("signal", 0)
            price = row.get("close", 0)
            if pd.isna(sig) or pd.isna(price) or price <= 0:
                continue
            sig = int(sig)
            pos = positions[sym]

            if sig == 1 or strategy_name == "keep_wait":  # 買進
                available = cash_buckets[sym]
                if available > 0 and (pos.shares == 0 or strategy_name == "keep_wait"):
                    spent = pos.buy(current_date, price, available)
                    cash_buckets[sym] -= spent
                    if spent > 0:
                        transaction_log.append(pos.trades[-1].copy())
            elif sig == -1:  # 賣出
                if pos.shares > 0:
                    # 先保存 cost_basis（sell() 會將其歸零）
                    cost_before_sell = pos.cost_basis
                    proceeds = pos.sell(current_date, price)
                    # 獲利滾入本金 - 支援每 M 個月滾入 P% 的已實現獲利
                    profit = proceeds - cost_before_sell
                    rolled_amount = 0.0
                    if profit > 0 and profit_roll_months >= 0:
                        months_since_last_roll = (current_date.year - pos.last_roll_year) * 12 + (current_date.month - pos.last_roll_month)
                        
                        if months_since_last_roll >= profit_roll_months:
                            rolled_amount = profit * profit_roll_percentage
                            pos.last_roll_year = current_date.year
                            pos.last_roll_month = current_date.month
                            transaction_log.append({
                                "date": current_date, "type": "profit_roll", "price": price,
                                "shares": 0, "amount": rolled_amount, "commission": 0, "tax": 0,
                                "description": f"獲利滾入: +NT${rolled_amount:.2f} (每{profit_roll_months}個月滾入一次, P={profit_roll_percentage*100:.0f}%)"
                            })
                    cash_buckets[sym] += proceeds - rolled_amount
                    general_cash += rolled_amount
                    if proceeds > 0:
                        transaction_log.append(pos.trades[-1].copy())

        # 月底記錄組合價值
        month_end_dates = _month_ends(all_dates, start_date, end_date)
        for med in month_end_dates:
            if current_date == med:
                total_val = sum(cash_buckets.values()) + general_cash
                for sym, _, _ in config_list:
                    if sym in signal_data and sym in positions:
                        df = signal_data[sym]
                        if current_date in df.index:
                            px = float(df.loc[current_date, "close"])
                            total_val += positions[sym].value(px)
                monthly_records.append({
                    "date": current_date,
                    "value": round(total_val, 2),
                })
                break

    return {
        "config": config_list,
        "positions": positions,
        "cash_buckets": cash_buckets,
        "general_cash": general_cash,
        "total_injected": total_injected,
        "transaction_log": transaction_log,
        "monthly_records": monthly_records,
        "signal_data": signal_data,
        "monthly_total": monthly_total,
        "profit_roll_months": profit_roll_months,
        "profit_roll_percentage": profit_roll_percentage,
    }


def simulate_lumpsum(config_list, start_date="2024-01-01", end_date="2025-12-31",
                     initial_capital=500000, profit_roll_months=3.0, profit_roll_percentage=1.0) -> dict:
    """
    一筆資金模擬 - 支援獲利滾入本金功能

    config_list: [(symbol, strategy, allocation_amount), ...]
    profit_roll_months: M 個月 - 每 M 個月滾入一次已實現獲利 (預設 3，0=不滾入)
    profit_roll_percentage: P % - 滾入比例 (0-1 間，預設 1.0 = 100%)
    """
    symbols = list(set(c[0] for c in config_list))
    signal_data = {}
    for sym in symbols:
        strategy_name = next(c[1] for c in config_list if c[0] == sym)
        df = run_strategy(sym, strategy_name, start=start_date)
        if df.empty:
            print(f"  ⚠️ {sym} 資料為空，跳過")
            continue
        if end_date:
            df = df[df.index <= end_date]
        signal_data[sym] = df

    positions = {c[0]: Position(c[0], c[1]) for c in config_list}
    cash_buckets = {c[0]: float(c[2]) for c in config_list}
    total_initial = sum(c[2] for c in config_list)

    general_cash = float(initial_capital) - total_initial

    capital_injection_log = [
        {"date": start_date, "amount": float(initial_capital), "source": "initial",
         "running_total": float(initial_capital), "description": "初始資金"}
    ]

    capital_entries = read_capital_file()
    pending_injections = {}
    for date_str, amount in capital_entries:
        pending_injections[date_str] = amount

    # keep_wait 追蹤狀態
    KEEP_WAIT_PARAMS = {
        "2412": {"initial_buy_pct": 0.7, "initial_shares": 12, "add_drop_pct": 5.0, "add_shares": 6,
                 "max_additions": 2, "tp_pct": 15.0, "tp_sell_ratio": 50.0, "cooldown_days": 30},
        "2382": {"initial_buy_pct": 0.7, "initial_shares": 12, "add_drop_pct": 5.0, "add_shares": 6,
                 "max_additions": 2, "tp_pct": 15.0, "tp_sell_ratio": 50.0, "cooldown_days": 30},
    }
    kw_state = {}
    for sym, strategy_name, alloc in config_list:
        if strategy_name == "keep_wait":
            kw_state[sym] = {
                "buy_count": 0, "avg_cost": 0.0, "cooldown_until": None,
                "total_cost": 0.0, "total_shares": 0,
            }

    all_dates = pd.DatetimeIndex(sorted(set(
        d for df in signal_data.values() for d in df.index
    )))
    transaction_log: list[dict] = []
    monthly_records = []

    for current_date in sorted(all_dates):
        date_str = current_date.strftime("%Y-%m-%d")
        if date_str in pending_injections:
            extra = pending_injections.pop(date_str)
            general_cash += extra
            running_total = sum(inj["amount"] for inj in capital_injection_log)
            capital_injection_log.append({
                "date": current_date, "amount": extra, "source": "external",
                "running_total": running_total + extra,
                "description": "使用者外部加碼"
            })
            total_alloc = sum(c[2] for c in config_list)
            if total_alloc > 0:
                for sym, strat, alloc in config_list:
                    if strat == "keep_wait":
                        ratio = alloc / total_alloc
                        share = extra * ratio
                        cash_buckets[sym] += share
                        st = kw_state.get(sym)
                        if st:
                            df = signal_data.get(sym)
                            if df is not None and current_date in df.index:
                                px = float(df.loc[current_date, "close"])
                                kw_p = KEEP_WAIT_PARAMS.get(sym, {})
                                initial_buy_pct = kw_p.get("initial_buy_pct", 0.7)
                                buy_amount = cash_buckets[sym] * initial_buy_pct
                                if buy_amount >= px * (1 + COMMISSION_RATE):
                                    pos = positions[sym]
                                    spent = pos.buy(current_date, px, buy_amount)
                                    if spent > 0:
                                        cash_buckets[sym] -= spent
                                        shares_bought = spent / px
                                        st["total_cost"] += spent
                                        st["total_shares"] += shares_bought
                                        st["avg_cost"] = px
                                        st["buy_count"] += 1
                                        transaction_log.append(pos.trades[-1].copy())
                general_cash = 0

        for sym, strategy_name, alloc in config_list:
            if sym not in signal_data:
                continue
            df = signal_data[sym]
            if current_date not in df.index:
                continue
            row = df.loc[current_date]
            price = row.get("close", 0)
            if pd.isna(price) or price <= 0:
                continue
            pos = positions[sym]

            if strategy_name == "keep_wait":
                st = kw_state.get(sym)
                if not st:
                    continue
                if st["cooldown_until"] and current_date < st["cooldown_until"]:
                    continue

                if st["buy_count"] == 0:
                    kw_p = KEEP_WAIT_PARAMS.get(sym, {})
                    initial_buy_pct = kw_p.get("initial_buy_pct", 0.7)
                    buy_amount = cash_buckets[sym] * initial_buy_pct
                    if buy_amount >= price * (1 + COMMISSION_RATE):
                        spent = pos.buy(current_date, price, buy_amount)
                        if spent > 0:
                            cash_buckets[sym] -= spent
                            shares_bought = spent / price
                            st["total_cost"] += spent
                            st["total_shares"] += shares_bought
                            st["avg_cost"] = price
                            st["buy_count"] = 1
                            transaction_log.append(pos.trades[-1].copy())
                else:
                    kw_p = KEEP_WAIT_PARAMS.get(sym, {})
                    kw_add = kw_p.get("add_shares", 6)
                    kw_drop = kw_p.get("add_drop_pct", 5.0)
                    kw_max = kw_p.get("max_additions", 2)
                    kw_tp = kw_p.get("tp_pct", 15.0)
                    kw_sell_ratio = kw_p.get("tp_sell_ratio", 50.0)
                    kw_cd = kw_p.get("cooldown_days", 30)

                    avg_cost = st["avg_cost"]
                    drop_pct = (avg_cost - price) / avg_cost * 100 if avg_cost > 0 else 0
                    profit_pct = (price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0

                    if profit_pct >= kw_tp and st["total_shares"] > 0:
                        if pos.shares > 0:
                            proceeds = pos.sell(current_date, price)
                            cash_buckets[sym] += proceeds
                            if proceeds > 0:
                                transaction_log.append(pos.trades[-1].copy())
                        st["avg_cost"] = 0.0
                        st["buy_count"] = 0
                        st["total_cost"] = 0.0
                        st["total_shares"] = 0
                        st["cooldown_until"] = current_date + timedelta(days=kw_cd)
                    elif drop_pct >= kw_drop and st["buy_count"] < kw_max:
                        if cash_buckets[sym] >= kw_add * price * (1 + COMMISSION_RATE):
                            spent = pos.buy(current_date, price, kw_add * price)
                            if spent > 0:
                                cash_buckets[sym] -= spent
                                prev_shares = st["total_shares"]
                                st["total_cost"] += spent
                                st["total_shares"] += kw_add
                                st["avg_cost"] = (avg_cost * prev_shares + price * kw_add) / st["total_shares"]
                                st["buy_count"] += 1
                                transaction_log.append(pos.trades[-1].copy())
                continue

                    # ── 訊號策略 ──
            sig = row.get("signal", 0)
            if pd.isna(sig):
                continue
            sig = int(sig)

            if sig == 1:  # 買進
                available = cash_buckets[sym]
                if available > 5 and pos.shares == 0:
                    spent = pos.buy(current_date, price, available)
                    cash_buckets[sym] -= spent
                    if spent > 0:
                        transaction_log.append(pos.trades[-1].copy())
            elif sig == -1:  # 賣出
                if pos.shares > 0:
                    cost_before_sell = pos.cost_basis
                    proceeds = pos.sell(current_date, price)
                    profit = proceeds - cost_before_sell
                    rolled_amount = 0.0
                    if profit > 0:
                        months_since_last_roll = (current_date.year - pos.last_roll_year) * 12 + (current_date.month - pos.last_roll_month)
                        
                        if months_since_last_roll >= profit_roll_months:
                            rolled_amount = profit * profit_roll_percentage
                            pos.last_roll_year = current_date.year
                            pos.last_roll_month = current_date.month
                            transaction_log.append({
                                "date": current_date, "type": "profit_roll", "price": price,
                                "shares": 0, "amount": rolled_amount, "commission": 0, "tax": 0,
                                "description": f"獲利滾入: +NT${rolled_amount:.2f} (每{profit_roll_months}個月滾入一次, P={profit_roll_percentage*100:.0f}%)"
                            })
                            running_total = sum(inj["amount"] for inj in capital_injection_log)
                            capital_injection_log.append({
                                "date": current_date, "amount": rolled_amount, "source": "profit_roll",
                                "running_total": running_total + rolled_amount,
                                "description": f"獲利滾入: {sym} 賣出獲利"
                            })
                        else:
                            transaction_log.append({
                                "date": current_date, "type": "profit_hold", "price": price,
                                "shares": 0, "amount": 0, "commission": 0, "tax": 0,
                                "description": f"獲利等待滾入: NT${profit:.2f} (需再{months_since_last_roll}/{profit_roll_months}個月)"
                            })
                    cash_buckets[sym] += proceeds - rolled_amount
                    general_cash += rolled_amount
                    if proceeds > 0:
                        transaction_log.append(pos.trades[-1].copy())

        month_end_dates = _month_ends(all_dates, start_date, end_date)
        for med in month_end_dates:
            if current_date == med:
                date_str = current_date.strftime("%Y-%m-%d")
                
                if date_str in pending_injections:
                    extra = pending_injections.pop(date_str)
                    general_cash += extra
                    running_total = sum(inj["amount"] for inj in capital_injection_log)
                    capital_injection_log.append({
                        "date": current_date, "amount": extra, "source": "external",
                        "running_total": running_total + extra,
                        "description": "使用者外部加碼"
                    })

                if general_cash > 0:
                    total_alloc = sum(c[2] for c in config_list)
                    if total_alloc > 0:
                        reallocated = 0
                        for sym, strat, alloc in config_list:
                            ratio = alloc / total_alloc
                            share = general_cash * ratio
                            cash_buckets[sym] += share
                            reallocated += share
                            if strat == "keep_wait" and sym in positions:
                                st = kw_state.get(sym)
                                if st and cash_buckets[sym] > 0:
                                    kw_p = KEEP_WAIT_PARAMS.get(sym, {})
                                    initial_buy_pct = kw_p.get("initial_buy_pct", 0.7)
                                    df = signal_data.get(sym)
                                    if df is not None and current_date in df.index:
                                        px = float(df.loc[current_date, "close"])
                                        buy_amount = cash_buckets[sym] * initial_buy_pct
                                        if buy_amount >= px * (1 + COMMISSION_RATE):
                                            pos = positions[sym]
                                            spent = pos.buy(current_date, px, buy_amount)
                                            if spent > 0:
                                                cash_buckets[sym] -= spent
                                                shares_bought = spent / px
                                                st["total_cost"] += spent
                                                st["total_shares"] += shares_bought
                                                st["avg_cost"] = px
                                                st["buy_count"] += 1
                                                transaction_log.append(pos.trades[-1].copy())
                        general_cash -= reallocated

                total_val = sum(cash_buckets.values()) + general_cash
                for sym, _, _ in config_list:
                    if sym in signal_data and sym in positions:
                        df = signal_data[sym]
                        if current_date in df.index:
                            px = float(df.loc[current_date, "close"])
                            total_val += positions[sym].value(px)
                monthly_records.append({
                    "date": current_date,
                    "value": round(total_val, 2),
                })
                break

    return {
        "config": config_list,
        "positions": positions,
        "cash_buckets": cash_buckets,
        "general_cash": general_cash,
        "initial_capital": initial_capital,
        "total_initial": total_initial,
        "transaction_log": transaction_log,
        "monthly_records": monthly_records,
        "signal_data": signal_data,
        "profit_roll_months": profit_roll_months,
        "profit_roll_percentage": profit_roll_percentage,
        "capital_injection_log": capital_injection_log,
    }


def _month_ends(dates, start, end):
    """回測期間內每個月最後一個交易日的 set"""
    st = pd.Timestamp(start)
    en = pd.Timestamp(end) if end else dates[-1]
    subset = [d for d in sorted(dates) if st <= d <= en]
    seen = set()
    result = {}
    for d in subset:
        ym = (d.year, d.month)
        result[ym] = d  # 最後一個會蓋掉前面的，即得到月底
    return set(result.values())


# ── Report Generation ────────────────────────────────────────

def fmt_ntd(val):
    return f"NT${val:,.0f}"

def fmt_ntd_detail(val):
    return f"NT${val:>8,.0f}"

def fmt_ntd_compact(val):
    if abs(val) >= 10000:
        return f"NT${val:,.0f}"
    return f"NT${val:>7,.0f}"

def fmt_pct(val):
    if val >= 0:
        return f"+{val:.1%}"
    return f"{val:.1%}"

def fmt_ntd_small(val):
    return f"NT${val:>7,.0f}"


def generate_dca_report(result: dict) -> str:
    config = result["config"]
    positions = result["positions"]
    cash_buckets = result["cash_buckets"]
    general_cash = result.get("general_cash", 0)
    total_injected = result["total_injected"]
    tx_log = result["transaction_log"]
    monthly = result["monthly_records"]
    monthly_total = result["monthly_total"]
    profit_roll_months = result.get("profit_roll_months", 0.0)
    profit_roll_percentage = result.get("profit_roll_percentage", 1.0)

    # 各標的績效
    lines = []
    lines.append("# 每月2萬元策略 — 2022 & 2025 回溯模擬")
    lines.append("")
    lines.append(f"> 📅 模擬日期：{datetime.now().strftime('%Y-%m-%d')}")
    lines.append("> ⚠️ **過去績效不代表未來獲利，本模擬僅供參考。**")
    lines.append("")
    lines.append("## 📋 策略配置")
    lines.append("")
    lines.append(f"每月總預算 **NT${monthly_total:,}**，按以下權重分配至四檔標的，各策略獨立運作：")
    lines.append("")
    lines.append("| 標的 | 代號 | 策略 | 每月配置 | 權重 |")
    lines.append("|------|------|------|---------|------|")
    total_w = sum(c[2] for c in config)
    for sym, strat, alloc in config:
        weight = alloc / total_w * 100
        lines.append(f"| {sym} | {sym} | {strat} | NT${alloc:,.0f} | {weight:.0f}% |")
    lines.append("")

    # 總績效
    total_final_value = monthly[-1]["value"] if monthly else 0
    total_pnl = total_final_value - total_injected
    total_return = total_pnl / total_injected if total_injected else 0
    days = (monthly[-1]["date"] - monthly[0]["date"]).days if len(monthly) >= 2 else 730
    years = days / 365.25
    cagr = (total_final_value / total_injected) ** (1 / years) - 1 if total_injected > 0 and years > 0 else 0

    # 計算總手續費和稅
    total_commission = sum(t.get("commission", 0) for t in tx_log)
    total_tax = sum(t.get("tax", 0) for t in tx_log)
    
    # 計算獲利滾入總額
    profit_roll_transactions = [t for t in tx_log if t.get("type") == "profit_roll"]
    total_profit_roll = sum(t.get("amount", 0) for t in profit_roll_transactions)

    lines.append("## 📊 總績效摘要")
    lines.append("")
    lines.append("| 指標 | 數值 |")
    lines.append("|------|------|")
    lines.append(f"| 模擬期間 | 2024-01-02 ~ 2025-12-31（{days} 天） |")
    lines.append(f"| 總投入資金 | {fmt_ntd(total_injected)} |")
    lines.append(f"| 組合終值 | {fmt_ntd(total_final_value)} |")
    lines.append(f"| **總損益** | **{fmt_ntd(total_pnl)} ({fmt_pct(total_return)})** |")
    lines.append(f"| **年化報酬率 (CAGR)** | **{fmt_pct(cagr)}** |")
    lines.append(f"| 總交易手續費 | {fmt_ntd(total_commission)} |")
    lines.append(f"| 總交易稅 | {fmt_ntd(total_tax)} |")
    if total_profit_roll > 0:
        lines.append(f"| **獲利滾入總額** | **{fmt_ntd(total_profit_roll)} (M={profit_roll_months}, P={profit_roll_percentage*100:.0f}%)** |")
    lines.append("")
    lines.append("> 💡 **價格說明**：使用 Yahoo Finance `auto_adjust=True`，歷史價格已回調除權息，")
    lines.append("> 報酬率計算正確。")
    lines.append(">")
    lines.append("> ✅ **VWAP 已修正**：改用真實成交量加權計算 VWAP（`Σ(close×volume)/Σ(volume)`），非之前收盤價近似。")
    lines.append("")

    # 各標的績效
    lines.append("## 🏆 各標的績效")
    lines.append("")
    lines.append("| 標的 | 策略 | 投入資金 | 終值 | 損益 | 報酬率 | 買/賣次數 |")
    lines.append("|------|------|---------|------|------|--------|----------|")

    # 計算各標的最終價值（含現金）
    final_date = monthly[-1]["date"] if monthly else None
    for sym, strat, alloc in config:
        cash_rem = cash_buckets.get(sym, 0)
        pos = positions.get(sym)
        shares_val = 0.0
        if pos and final_date and sym in result["signal_data"]:
            df = result["signal_data"][sym]
            if final_date in df.index:
                px = float(df.loc[final_date, "close"])
                shares_val = pos.value(px) if pos else 0
        total_val = cash_rem + shares_val
        pnl = total_val - (total_injected * alloc / sum(c[2] for c in config))
        ret = pnl / (total_injected * alloc / sum(c[2] for c in config)) if (total_injected * alloc / sum(c[2] for c in config)) > 0 else 0
        buys = sum(1 for t in tx_log if t.get("symbol", sym) == sym and t.get("type") == "buy")
        sells = sum(1 for t in tx_log if t.get("symbol", sym) == sym and t.get("type") == "sell")
        if pos:
            buys = sum(1 for t in pos.trades if t["type"] == "buy")
            sells = sum(1 for t in pos.trades if t["type"] == "sell")
        lines.append(f"| {sym} | {strat} | {fmt_ntd(total_injected * alloc / sum(c[2] for c in config))} | {fmt_ntd(total_val)} | {fmt_ntd(pnl)} | {fmt_pct(ret)} | {buys}/{sells} |")

    general_cash_val = result.get("general_cash", 0)
    if general_cash_val > 0:
        lines.append(f"| 滾入資金池 | — | — | {fmt_ntd(general_cash_val)} | {fmt_ntd(general_cash_val)} | — | — |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 年度績效
    lines.append("## 📅 年度績效")
    lines.append("")

    for year in [2024, 2025]:
        yr_records = [r for r in monthly if r["date"].year == year]
        if not yr_records:
            continue
        yr_start_val = yr_records[0]["value"] - (monthly_total if year == 2024 else monthly_total)  # 年初(不含當月投入)
        yr_end_val = yr_records[-1]["value"] if yr_records else 0
        yr_injection = monthly_total * len(yr_records)
        yr_pnl = yr_end_val - yr_start_val - yr_injection
        yr_ret = yr_pnl / (yr_start_val + yr_injection) if (yr_start_val + yr_injection) > 0 else 0

        lines.append(f"### {year}年")
        lines.append("")
        lines.append("| 指標 | 數值 |")
        lines.append("|------|------|")
        lines.append(f"| 年初組合價值 | {fmt_ntd(yr_start_val)} |")
        lines.append(f"| 年度投入 | {fmt_ntd(yr_injection)} |")
        lines.append(f"| 年底組合價值 | {fmt_ntd(yr_end_val)} |")
        lines.append(f"| **年度損益** | **{fmt_ntd(yr_pnl)} ({fmt_pct(yr_ret)})** |")
        lines.append("")

        # 各標的年度明細
        lines.append("**各標的明細：**")
        lines.append("")
        lines.append("| 標的 | 策略 | 買/賣次數 |")
        lines.append("|------|------|----------|")
        for sym, strat, alloc in config:
            pos = positions.get(sym)
            if pos:
                yr_trades = [t for t in pos.trades if t["date"].year == year]
                yr_buys = sum(1 for t in yr_trades if t["type"] == "buy")
                yr_sells = sum(1 for t in yr_trades if t["type"] == "sell")
            else:
                yr_buys = yr_sells = 0
            lines.append(f"| {sym} | {strat} | {yr_buys}買/{yr_sells}賣 |")
        lines.append("")

    # 每月績效
    lines.append("## 📆 每月績效明細")
    lines.append("")
    lines.append("| 月份 | 投入 | 組合價值 | 當月增減 | 累計損益 |")
    lines.append("|------|------|---------|---------|---------|")
    cumulative_pnl = 0
    prev_val = 0
    for i, rec in enumerate(monthly):
        injection = monthly_total if rec["date"] in first_trading_days_of_month(pd.DatetimeIndex([rec["date"]])) or i == 0 or (monthly[i-1]["date"].month != rec["date"].month) else 0
        # simpler: each record is after monthly injection
        injection = monthly_total  # 假設每個月底記錄包含當月投入
        monthly_change = rec["value"] - prev_val - (injection if i > 0 else 0)
        prev_val = rec["value"]
        cumulative_pnl = rec["value"] - (i + 1) * monthly_total
        lines.append(f"| {rec['date'].strftime('%Y-%m')} | {fmt_ntd_compact(monthly_total)} | {fmt_ntd_detail(rec['value'])} | {fmt_ntd_small(monthly_change)} | {fmt_ntd_small(cumulative_pnl)} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 各標的交易記錄
    lines.append("## 📝 各標的交易記錄")
    lines.append("")
    for sym, strat, alloc in config:
        lines.append(f"### {sym} — {strat}")
        lines.append("")
        pos = positions.get(sym)
        if not pos or not pos.trades:
            lines.append("無交易訊號")
            lines.append("")
            continue
        lines.append("| 日期 | 類型 | 價格 | 金額 | 股數 | 費用 |")
        lines.append("|------|------|------|------|------|------|")
        for t in pos.trades:
            date_str = t["date"].strftime("%Y-%m-%d")
            typ = "🟢 買" if t["type"] == "buy" else "🔴 賣"
            price = f"NT${t['price']:>8.1f}"
            amt = f"NT${t['amount']:>8,.0f}"
            shares = f"{t['shares']:>7.1f}"
            fee_parts = []
            if t["commission"] > 0:
                fee_parts.append(f"NT${t['commission']}")
            if t.get("tax", 0) > 0:
                fee_parts.append(f"(+稅{t['tax']:.0f})")
            fee_str = " ".join(fee_parts) if fee_parts else "—"
            lines.append(f"| {date_str} | {typ} | {price} | {amt} | {shares} | {fee_str} |")
        lines.append("")

    # 與買入持有比較
    lines.append("## 📈 與買入持有比較")
    lines.append("")
    total_w_alloc = sum(c[2] for c in config)
    lines.append(f"假設每月同額資金（NT${monthly_total:,}）平均買入各標的（按相同權重），不做策略交易：")
    lines.append("")
    # 計算買入持有
    bh_final = buy_hold_dca(config, monthly_total)
    lines.append("| 比較項目 | 策略交易 | 買入持有 | 差異 |")
    lines.append("|----------|---------|---------|------|")
    lines.append(f"| 總投入 | {fmt_ntd(total_injected)} | {fmt_ntd(total_injected)} | - |")
    lines.append(f"| 終值 | {fmt_ntd(total_final_value)} | {fmt_ntd(bh_final)} | {fmt_ntd(total_final_value - bh_final)} |")
    lines.append(f"| 總損益 | {fmt_ntd(total_pnl)} | {fmt_ntd(bh_final - total_injected)} | {fmt_ntd(total_pnl - (bh_final - total_injected))} |")
    lines.append(f"| 報酬率 | {fmt_pct(total_return)} | {fmt_pct((bh_final - total_injected) / total_injected)} | {fmt_pct(total_return - (bh_final - total_injected) / total_injected)} |")
    lines.append(f"| 年化報酬 | {fmt_pct(cagr)} | — | — |")
    lines.append("")
    lines.append("> **為什麼策略落後買入持有？** 2024-2025 為台股大多頭年，買入持有全數吃下漲幅，")
    lines.append("> 而策略會停利出場導致現金閒置。但策略的核心價值在於空頭年有紀律地守住本金，")
    lines.append("> 不會像買入持有那樣承受 30-50% 的跌幅。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## ⚠️ 免責聲明")
    lines.append("")
    lines.append("1. **過去績效不代表未來獲利** — 本模擬基於歷史資料，不保證未來表現")
    lines.append("2. **交易成本已計入** — 包含手續費（0.1425%）與證交稅（ETF 0.1% / 股票 0.3%）")
    lines.append("3. **未計入滑價** — 假設以收盤價成交，實盤可能因流動性產生偏差")
    lines.append("4. **策略參數固定** — 使用預設參數，未針對2024-2025市場最佳化")
    lines.append("5. **資料來源** — Yahoo Finance (auto_adjust=True，已調整除權息)")
    lines.append("6. **模擬假設** — 每月第一個交易日撥入預算，訊號觸發當日以收盤價交易")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*報告產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append("")
    return "\n".join(lines)


def generate_lumpsum_report(result: dict) -> str:
    config = result["config"]
    positions = result["positions"]
    cash_buckets = result["cash_buckets"]
    general_cash = result.get("general_cash", 0)
    initial_capital = result["initial_capital"]
    tx_log = result["transaction_log"]
    monthly = result["monthly_records"]
    profit_roll_months = result.get("profit_roll_months", 3.0)
    profit_roll_percentage = result.get("profit_roll_percentage", 1.0)

    lines = []
    lines.append("# 50萬一筆資金 — 2024 & 2025 回溯模擬")
    lines.append("")
    lines.append(f"> 📅 模擬日期：{datetime.now().strftime('%Y-%m-%d')}")
    lines.append("> ⚠️ **過去績效不代表未來獲利，僅供參考。**")
    lines.append("> 💡 初始資本NT$500,000一次到位，獲利可再投入。")
    lines.append("")

    # 配置表
    lines.append("## 📋 策略配置")
    lines.append("")
    # 按策略分組
    strat_groups = {}
    for sym, strat, alloc in config:
        strat_groups.setdefault(strat, []).append((sym, alloc))
    lines.append("| 策略 | 資金 | 佔比 | 標的 | 策略類型 |")
    lines.append("|------|-----|------|------|---------|")
    for strat, items in strat_groups.items():
        syms_str = ", ".join(s for s, _ in items)
        total_alloc = sum(a for _, a in items)
        pct = total_alloc / initial_capital * 100
        stype = "順勢" if strat in ("ma_cross", "breakout") else "逆勢"
        lines.append(f"| {strat} | {fmt_ntd(total_alloc)} | {pct:.0f}% | {syms_str} | {stype} |")
    lines.append(f"| **總計** | **{fmt_ntd(initial_capital)}** | **100%** | **{len(config)} 檔** | — |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 總績效
    final_value = monthly[-1]["value"] if monthly else initial_capital
    capital_injection_log = result.get("capital_injection_log", [])
    total_injected = sum(inj["amount"] for inj in capital_injection_log if inj["source"] in ("initial", "external"))
    if total_injected == 0:
        total_injected = initial_capital
    total_pnl = final_value - total_injected
    total_return = total_pnl / total_injected
    days = (monthly[-1]["date"] - monthly[0]["date"]).days if len(monthly) >= 2 else 730
    years = days / 365.25
    cagr = (final_value / total_injected) ** (1 / years) - 1 if years > 0 else 0
    total_commission = sum(t.get("commission", 0) for t in tx_log)
    total_tax = sum(t.get("tax", 0) for t in tx_log)
    
    # 計算獲利滾入總額
    profit_roll_transactions = [t for t in tx_log if t.get("type") == "profit_roll"]
    total_profit_roll = sum(t.get("amount", 0) for t in profit_roll_transactions)

    lines.append("## 📊 總績效")
    lines.append("")
    lines.append("| 指標 | 數值 |")
    lines.append("|------|------|")
    lines.append(f"| 初始資本 | {fmt_ntd(initial_capital)} |")
    lines.append(f"| 外部加碼 | {fmt_ntd(total_injected - initial_capital)} |") if total_injected > initial_capital else None
    lines.append(f"| **總投入資金** | **{fmt_ntd(total_injected)}** |")
    lines.append(f"| 組合終值 (2025-12-31) | {fmt_ntd(final_value)} |")
    lines.append(f"| **總損益** | **{fmt_ntd(total_pnl)} ({fmt_pct(total_return)})** |")
    lines.append(f"| **年化報酬率 (CAGR)** | **{fmt_pct(cagr)}** |")
    lines.append(f"| 模擬期間 | 2024-01-02 ~ 2025-12-31 ({days} 天) |")
    lines.append(f"| 總手續費 | {fmt_ntd(total_commission)} |")
    lines.append(f"| 總交易稅 | {fmt_ntd(total_tax)} |")
    lines.append(f"| **獲利滾入總額** | **{fmt_ntd(total_profit_roll)} (M={profit_roll_months}, P={profit_roll_percentage*100:.0f}%)** |")
    if monthly:
        avg_deployed = sum(r["value"] for r in monthly) / len(monthly)
        max_deployed = max(r["value"] for r in monthly)
        lines.append(f"| 平均動用資金 | {fmt_ntd(avg_deployed)} |")
        lines.append(f"| 最高動用資金 | {fmt_ntd(max_deployed)} |")
    lines.append("")
    lines.append("> ✅ **VWAP 已修正**：改用真實成交量加權計算 VWAP（`Σ(close×volume)/Σ(volume)`），非之前收盤價近似。")
    lines.append("")

    capital_injection_log = result.get("capital_injection_log", [])
    if capital_injection_log:
        lines.append("## 💰 資金投入紀錄")
        lines.append("")
        lines.append("| 日期 | 金額 | 來源 | 累計本金 | 說明 |")
        lines.append("|------|------|------|---------|------|")
        for inj in capital_injection_log:
            date_str = inj["date"] if isinstance(inj["date"], str) else inj["date"].strftime("%Y-%m-%d")
            source_label = {"initial": "初始資金", "profit_roll": "獲利滾入", "external": "外部加碼"}.get(inj["source"], inj["source"])
            lines.append(f"| {date_str} | {fmt_ntd(inj['amount'])} | {source_label} | {fmt_ntd(inj['running_total'])} | {inj.get('description', '')} |")
        total_injected = sum(inj["amount"] for inj in capital_injection_log if inj["source"] in ("initial", "external"))
        lines.append(f"| **合計** | **{fmt_ntd(total_injected)}** | **初始+外部** | — | — |")
        lines.append("")

    # 各標的績效
    lines.append("## 🏆 各標的績效")
    lines.append("")
    lines.append("| 標的 | 策略 | 初始資金 | 終值 | 損益 | 報酬率 | 交易 |")
    lines.append("|------|------|---------|------|------|--------|------|")
    final_date = monthly[-1]["date"] if monthly else None
    strat_totals = {}
    for sym, strat, alloc in config:
        cash_rem = cash_buckets.get(sym, 0)
        pos = positions.get(sym)
        shares_val = 0.0
        if pos and final_date and sym in result["signal_data"]:
            df = result["signal_data"][sym]
            if final_date in df.index:
                px = float(df.loc[final_date, "close"])
                shares_val = pos.value(px)
        total_val = cash_rem + shares_val
        pnl = total_val - alloc
        ret = pnl / alloc if alloc > 0 else 0
        if pos:
            buys = sum(1 for t in pos.trades if t["type"] == "buy")
            sells = sum(1 for t in pos.trades if t["type"] == "sell")
        else:
            buys = sells = 0
        lines.append(f"| {sym} | {strat} | {fmt_ntd(alloc)} | {fmt_ntd(total_val)} | {fmt_ntd(pnl)} | {fmt_pct(ret)} | {buys}買/{sells}賣 |")
        # 累計策略總計
        strat_totals.setdefault(strat, {"alloc": 0, "val": 0})
        strat_totals[strat]["alloc"] += alloc
        strat_totals[strat]["val"] += total_val

    lines.append("")
    lines.append("### 各策略彙總")
    lines.append("")
    lines.append("| 策略 | 初始資金 | 終值 | 損益 | 報酬率 |")
    lines.append("|------|---------|------|------|--------|")
    for strat, data in strat_totals.items():
        spnl = data["val"] - data["alloc"]
        sret = spnl / data["alloc"] if data["alloc"] > 0 else 0
        lines.append(f"| {strat} | {fmt_ntd(data['alloc'])} | {fmt_ntd(data['val'])} | {fmt_ntd(spnl)} | {fmt_pct(sret)} |")

    if general_cash > 0:
        lines.append(f"| **滾入資金池** | **—** | **{fmt_ntd(general_cash)}** | **{fmt_ntd(general_cash)}** | **—** |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 年度績效
    lines.append("## 📅 年度績效")
    lines.append("")

    for year in [2024, 2025]:
        yr_records = [r for r in monthly if r["date"].year == year]
        if not yr_records:
            continue
        yr_start_val = result["initial_capital"] if year == 2024 else monthly[[i for i, r in enumerate(monthly) if r["date"].year == year][0] - 1]["value"] if any(r["date"].year == year - 1 for r in monthly) else yr_records[0]["value"]
        # 更簡單：年初 = 前一年底
        prev_yr_records = [r for r in monthly if r["date"].year == year - 1]
        if prev_yr_records:
            yr_start_val = prev_yr_records[-1]["value"]
        else:
            yr_start_val = initial_capital if year == 2024 else yr_records[0]["value"]
        yr_end_val = yr_records[-1]["value"]
        yr_pnl = yr_end_val - yr_start_val
        yr_ret = yr_pnl / yr_start_val if yr_start_val > 0 else 0
        lines.append(f"### {year}年")
        lines.append("")
        lines.append("| 指標 | 數值 |")
        lines.append("|------|------|")
        lines.append(f"| 年初組合價值 | {fmt_ntd(yr_start_val)} |")
        lines.append(f"| 年底組合價值 | {fmt_ntd(yr_end_val)} |")
        lines.append(f"| **年度損益** | **{fmt_ntd(yr_pnl)} ({fmt_pct(yr_ret)})** |")
        lines.append("")
        lines.append("**各標的明細：**")
        lines.append("")
        lines.append("| 標的 | 策略 | 訊號次數 |")
        lines.append("|------|------|--------|")
        for sym, strat, alloc in config:
            pos = positions.get(sym)
            if pos:
                yr_trades = [t for t in pos.trades if t["date"].year == year]
                yr_buys = sum(1 for t in yr_trades if t["type"] == "buy")
                yr_sells = sum(1 for t in yr_trades if t["type"] == "sell")
            else:
                yr_buys = yr_sells = 0
            lines.append(f"| {sym} | {strat} | {yr_buys}買/{yr_sells}賣 |")
        lines.append("")

    # 每月組合價值
    lines.append("## 📆 每月組合價值")
    lines.append("")
    lines.append("| 月份 | 組合價值 | 當月增減 | 累計損益 |")
    lines.append("|------|---------|---------|---------|")
    prev_val = initial_capital
    for i, rec in enumerate(monthly):
        change = rec["value"] - prev_val
        pnl = rec["value"] - initial_capital
        lines.append(f"| {rec['date'].strftime('%Y-%m')} | {fmt_ntd_detail(rec['value'])} | {fmt_ntd_small(change)} | {fmt_ntd_small(pnl)} |")
        prev_val = rec["value"]
    lines.append("")

    # 與買入持有比較
    lines.append("## 📈 與買入持有比較")
    lines.append("")
    lines.append("同額資金（NT$500,000）在第一天按相同比例買入各標的且持有至期末：")
    lines.append("")
    bh_final = buy_hold_lumpsum(config)
    lines.append("| 比較項目 | 策略交易 | 買入持有 | 差異 |")
    lines.append("|----------|---------|---------|------|")
    lines.append(f"| 初始資金 | {fmt_ntd(initial_capital)} | {fmt_ntd(initial_capital)} | - |")
    lines.append(f"| 終值 | {fmt_ntd(final_value)} | {fmt_ntd(bh_final)} | {fmt_ntd(final_value - bh_final)} |")
    lines.append(f"| 總損益 | {fmt_ntd(total_pnl)} | {fmt_ntd(bh_final - initial_capital)} | {fmt_ntd(total_pnl - (bh_final - initial_capital))} |")
    lines.append(f"| 報酬率 | {fmt_pct(total_return)} | {fmt_pct((bh_final - initial_capital) / initial_capital)} | {fmt_pct(total_return - (bh_final - initial_capital) / initial_capital)} |")
    lines.append("")
    lines.append(f"> 💡 **獲利滾入說明**：每 {profit_roll_months} 個月滾入一次已實現獲利（P={profit_roll_percentage*100:.0f}%），總滾入金額 {fmt_ntd(total_profit_roll)}。")
    lines.append("")

    # 交易記錄
    lines.append("## 📝 交易記錄")
    lines.append("")
    for sym, strat, alloc in config:
        lines.append(f"### {sym} — {strat}")
        lines.append("")
        pos = positions.get(sym)
        if not pos or not pos.trades:
            lines.append("無交易訊號")
            lines.append("")
            continue
        lines.append("| 日期 | 類型 | 價格 | 金額 | 費用 |")
        lines.append("|------|------|------|------|------|")
        for t in pos.trades:
            date_str = t["date"].strftime("%Y-%m-%d")
            typ = "🟢 買" if t["type"] == "buy" else "🔴 賣"
            price = f"NT${t['price']:>8.1f}"
            amt = f"NT${t['amount']:>8,.0f}"
            fee_parts = []
            if t["commission"] > 0:
                fee_parts.append(f"NT${t['commission']}")
            if t.get("tax", 0) > 0:
                fee_parts.append(f"(+稅{t['tax']:.0f})")
            fee_str = " ".join(fee_parts) if fee_parts else "—"
            lines.append(f"| {date_str} | {typ} | {price} | {amt} | {fee_str} |")
        lines.append("")
    
    # 獲利滾入記錄
    if profit_roll_transactions:
        lines.append("## 🎯 獲利滾入記錄")
        lines.append("")
        lines.append(f"| 日期 | 類型 | 金額 | 說明 |")
        lines.append("|------|------|------|------|")
        for t in profit_roll_transactions:
            date_str = t["date"].strftime("%Y-%m-%d")
            typ = "🔄 滾入"
            amt = f"NT${t['amount']:>8,.0f}"
            desc = t.get("description", "")
            lines.append(f"| {date_str} | {typ} | {amt} | {desc} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## ⚠️ 免責聲明")
    lines.append("")
    lines.append("1. 過去績效不代表未來獲利，本模擬基於歷史資料不保證未來表現")
    lines.append("2. 已計入交易成本：手續費0.1425% + 證交稅（ETF 0.1%/股票 0.3%）")
    lines.append("3. 未計入：滑價、金字塔加碼、大盤年線過濾、股利收入")
    lines.append("4. 參數固定使用預設值，未針對2024-2025市場最佳化")
    lines.append("5. 資料來源：Yahoo Finance (auto_adjust=True)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*報告產生：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append("")

    return "\n".join(lines)


# ── Buy & Hold comparison ───────────────────────────────────

def buy_hold_dca(config_list, monthly_total=20000):
    """定期定額買入持有：每月按權重買入，持有到最後"""
    total_val = 0.0
    sym_weight = {c[0]: c[2] / sum(c[2] for c in config_list) for c in config_list}
    total_shares = {c[0]: 0.0 for c in config_list}

    all_dates = None
    for sym, _, _ in config_list:
        df = get_data(sym, start="2023-01-01")
        if df.empty:
            continue
        df = df[df.index >= "2024-01-01"]
        df = df[df.index <= "2025-12-31"]
        if all_dates is None:
            all_dates = df.index
        else:
            all_dates = all_dates.union(df.index)

    if all_dates is None:
        return 0.0

    all_dates = sorted(all_dates)
    first_days = first_trading_days_of_month(pd.DatetimeIndex(all_dates))

    # 模擬買入持有
    bh_shares = {c[0]: 0.0 for c in config_list}
    bh_cash = {c[0]: 0.0 for c in config_list}

    for dt in all_dates:
        dt_ts = pd.Timestamp(dt)
        # 每月第一天買入
        if dt_ts in first_days and dt_ts >= pd.Timestamp("2024-01-01"):
            for sym, _, _ in config_list:
                df = get_data(sym)
                if df.empty or dt_ts not in df.index:
                    continue
                px = float(df.loc[dt_ts, "close"])
                if px <= 0:
                    continue
                alloc = monthly_total * sym_weight[sym]
                commission = round(alloc * COMMISSION_RATE)
                available = alloc - commission
                if available > 0:
                    new_shares = available / px
                    bh_shares[sym] += new_shares
                    bh_cash[sym] -= alloc  # 支出

    # 期末價值
    end_date = pd.Timestamp("2025-12-31")
    final_val = 0.0
    for sym, _, _ in config_list:
        df = get_data(sym)
        if df.empty:
            continue
        # 找最接近月底的交易日
        avail_dates = df[df.index <= end_date].index
        if len(avail_dates) == 0:
            continue
        last_dt = avail_dates[-1]
        px = float(df.loc[last_dt, "close"])
        final_val += bh_shares[sym] * px

    return final_val


def buy_hold_lumpsum(config_list):
    """一筆資金買入持有"""
    total_val = 0.0
    for sym, _, alloc in config_list:
        df = get_data(sym, start="2023-01-01")
        if df.empty:
            continue
        df = df[df.index >= "2024-01-01"]
        if df.empty:
            continue
        # 第一個交易日買入
        first_date = df.index[0]
        px = float(df.loc[first_date, "close"])
        if px <= 0:
            continue
        commission = round(alloc * COMMISSION_RATE)
        available = alloc - commission
        shares = available / px

        # 最後交易日結算
        df_yr = df[df.index <= "2025-12-31"]
        if df_yr.empty:
            continue
        last_date = df_yr.index[-1]
        final_px = float(df_yr.loc[last_date, "close"])
        total_val += shares * final_px

    return total_val


# ── Signal logging helper ───────────────────────────────────

def attach_symbol_to_txlog(tx_log, positions):
    """為 transaction_log 附加 symbol 欄位（用於統計）"""
    # tx_log 已經在 Position.trades 中有完整的記錄
    pass


# ── main ────────────────────────────────────────────────────

def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="投資組合模擬報告產生器")
    parser.add_argument("--mode", choices=["dca", "lumpsum", "all"], default=None,
                        help="模擬模式（未指定時從 DCA_AMOUNT 環境變數判斷）")
    parser.add_argument("--output-dir", default=".",
                        help="輸出目錄")
    parser.add_argument("--start-date", type=str, default="2022-01-01",
                        help="模擬開始日期 (YYYY-MM-DD)，預設 2022-01-01")
    parser.add_argument("--end-date", type=str, default="2025-12-31",
                        help="模擬結束日期 (YYYY-MM-DD)，預設 2025-12-31")
    parser.add_argument("--profit-roll-months", type=float, default=3.0,
                        help="每 M 個月滾入一次已實現獲利 (預設 3，0=不滾入)")
    parser.add_argument("--profit-roll-percentage", type=float, default=1.0,
                        help="滾入比例 P（0-1 間，預設 1.0 = 100pct）")
    args = parser.parse_args()

    output_dir = args.output_dir

    # ── 從 DCA_AMOUNT 環境變數判斷模式 ──
    if args.mode is None:
        dca_amount = int(os.getenv("DCA_AMOUNT", "0"))
        if dca_amount > 0:
            args.mode = "dca"
            print(f"📋 DCA_AMOUNT={dca_amount}，自動選擇 DCA 模式")
        else:
            args.mode = "lumpsum"
            print(f"📋 DCA_AMOUNT=0，自動選擇 Lumpsum 模式")

    # 從 PC_ 環境變數讀取投資組合設定
    pc_config = load_portfolio_config()
    if pc_config:
        total_alloc = sum(float(cfg.get("alloc", 20)) for cfg in pc_config.values())
        monthly_total = int(os.getenv("DCA_AMOUNT", "20000"))
        lumpsum_total = int(os.getenv("TOTAL_CAPITAL", "500000"))

        dca_config = []
        lumpsum_config = []
        for sym, cfg in pc_config.items():
            strat = cfg["strategy"]
            alloc_pct = float(cfg.get("alloc", 20)) / total_alloc if total_alloc > 0 else (1.0 / len(pc_config))
            dca_config.append((sym, strat, int(monthly_total * alloc_pct)))
            lumpsum_config.append((sym, strat, int(lumpsum_total * alloc_pct)))

        # 補償整數誤差
        ls_diff = lumpsum_total - sum(c[2] for c in lumpsum_config)
        if ls_diff != 0 and lumpsum_config:
            lumpsum_config[-1] = (lumpsum_config[-1][0], lumpsum_config[-1][1],
                                  lumpsum_config[-1][2] + ls_diff)

        print(f"📋 從 PC_ 設定建立投資組合，共 {len(pc_config)} 檔")
        for sym, strat, amt in dca_config:
            print(f"   {sym} → {strat} (DCA NT${amt:,}/月)")
    else:
        # ── 預設 DCA config ──
        dca_config = [
            ("0050", "bollinger", 10000),
            ("2330", "ma_cross",  4000),
            ("2382", "keep_wait", 3000),
            ("2881", "vwap",      3000),
        ]
        # ── 預設 Lump sum config ──
        lumpsum_config = [
            ("0050",  "bollinger", 66666),
            ("006208","bollinger", 66666),
            ("00878", "bollinger", 66668),
            ("2330",  "ma_cross",  75000),
            ("2454",  "ma_cross",  75000),
            ("2881",  "vwap",      50000),
            ("2886",  "vwap",      50000),
            ("2382",  "keep_wait", 50000),
        ]

    total_ls = sum(c[2] for c in lumpsum_config)
    assert total_ls == 500000, f"Lumpsum config totals {total_ls}, expected 500000"

    if args.mode in ("all", "dca"):
        print(f"📊 模擬：每月定期定額 NT$20,000... (M={args.profit_roll_months}, P={args.profit_roll_percentage*100:.0f}%) ({args.start_date} ~ {args.end_date})")
        dca_result = simulate_dca(dca_config, start_date=args.start_date, end_date=args.end_date,
                                  monthly_total=20000, profit_roll_months=args.profit_roll_months,
                                  profit_roll_percentage=args.profit_roll_percentage)
        dca_report = generate_dca_report(dca_result)
        dca_path = os.path.join(output_dir, f"回溯_{args.start_date[:4]}_{args.end_date[:4]}.MD")
        with open(dca_path, "w", encoding="utf-8") as f:
            f.write(dca_report)
        print(f"  ✅ 已寫入 {dca_path}")

    if args.mode in ("all", "lumpsum"):
        print(f"📊 模擬：一筆資金 NT$500,000... (M={args.profit_roll_months}, P={args.profit_roll_percentage*100:.0f}%) ({args.start_date} ~ {args.end_date})")
        ls_result = simulate_lumpsum(lumpsum_config, start_date=args.start_date, end_date=args.end_date,
                                     initial_capital=500000, 
                                     profit_roll_months=args.profit_roll_months,
                                     profit_roll_percentage=args.profit_roll_percentage)
        ls_report = generate_lumpsum_report(ls_result)
        ls_path = os.path.join(output_dir, f"回溯_50万_{args.start_date[:4]}_{args.end_date[:4]}.MD")
        with open(ls_path, "w", encoding="utf-8") as f:
            f.write(ls_report)
        print(f"  ✅ 已寫入 {ls_path}")

        # ── 方案二主報告已包含全部 8 檔（含 keep_wait）──
        # 長榮替代版不再需要（已移除 breakout 策略）


if __name__ == "__main__":
    main()
