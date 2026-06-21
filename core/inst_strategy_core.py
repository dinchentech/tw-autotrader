"""
法人抬轎動能策略 — 共用核心邏輯
回測（backtest_inst_momentum.py）與實盤（InstitutionalMomentumStrategy）共用此模組。
"""
import os
import math
import numpy as np
import pandas as pd
from datetime import date, timedelta

# ─── 共用常數（從 env 讀取）──────────────────────────
INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", os.getenv("TOTAL_CAPITAL", "500000")))
TOP_N = int(os.getenv("INST_MOM_TOP_N", "3"))
MIN_VOLUME_SHARES = 2000
BUY_RATIO_THRESHOLD = 0.03
LOOKBACK = 20
STOP_LOSS = 0.10
TRAILING_PERIOD = 10
LOSER_BAN_DAYS = int(os.getenv("INST_MOM_LOSER_BAN_DAYS", "0"))
BUY_COST = 0.001425
SELL_COST = 0.004425
PROFIT_ROLL_MONTHS = int(os.getenv("PROFIT_ROLL_MONTHS", "0"))
PROFIT_ROLL_PERCENTAGE = float(os.getenv("PROFIT_ROLL_PERCENTAGE", "1.0"))


# ─── Fish Score（法人低吃分數）────────────────────
def compute_fish_score(close_arr, open_arr, high_arr, low_arr, vol_arr,
                       inst_buy_arr, inst_sell_arr, idx: int) -> float:
    close_i = close_arr[idx]
    vol_i = vol_arr[idx]

    # 價格分數 (0-3)
    recent_low = low_arr[max(0, idx - 29):idx + 1].min()
    pct_from_low = (close_i - recent_low) / close_i if close_i > 0 else 1
    price_score = 0
    if pct_from_low < 0.02:
        price_score += 1
    if idx >= 19:
        ma20 = close_arr[idx - 19:idx + 1].mean()
        if close_i < ma20:
            price_score += 1
    if idx >= 59:
        ma60 = close_arr[idx - 59:idx + 1].mean()
        if close_i < ma60:
            price_score += 1
    if idx >= 5:
        streak = sum(1 for j in range(idx - 4, idx) if close_arr[j] < close_arr[j - 1])
        if streak >= 3 and close_i >= low_arr[max(0, idx - 2):idx + 1].min():
            price_score += 0.5
    price_score = min(price_score, 3)

    # 量能分數 (0-3)
    avg_vol_5 = vol_arr[max(0, idx - 4):idx + 1].mean()
    avg_vol_20 = vol_arr[max(0, idx - 19):idx + 1].mean()
    vol_ratio = vol_i / avg_vol_5 if avg_vol_5 > 0 else 1
    vol_score = 0
    if vol_ratio > 1.3:
        vol_score += 1
    if vol_ratio > 2:
        vol_score += 1
    if vol_ratio > 1.3:
        pct_chg = (close_i - open_arr[idx]) / open_arr[idx] if open_arr[idx] > 0 else 0
        if -0.02 <= pct_chg <= 0.02:
            vol_score += 1
        elif pct_chg > 0.03:
            vol_score -= 0.5
    if avg_vol_5 > avg_vol_20 * 1.2:
        vol_score += 0.5
    vol_score = max(0, min(vol_score, 3))

    # K線型態分數 (0-2)
    body = abs(close_i - open_arr[idx])
    lower_shadow = min(open_arr[idx], close_i) - low_arr[idx]
    upper_shadow = high_arr[idx] - max(open_arr[idx], close_i)
    total_range = high_arr[idx] - low_arr[idx]
    pattern_score = 0
    if total_range > 0:
        lower_ratio = lower_shadow / total_range
        if lower_ratio > 0.5 and body < total_range * 0.4:
            pattern_score += 1
        if lower_ratio > 0.6 and upper_shadow < total_range * 0.2:
            pattern_score += 1
        if body / total_range < 0.1 and lower_shadow > 0 and upper_shadow > 0:
            pattern_score += 1
    pattern_score = min(pattern_score, 2)

    # 法人分數 (0-2)
    net = inst_buy_arr[idx] - inst_sell_arr[idx]
    inst_score = 0
    if net > 0:
        inst_score += 1
    if net > 1000:
        inst_score += 1
    inst_score = min(inst_score, 2)

    return price_score + vol_score + pattern_score + inst_score


def precompute_fish_scores(all_data: dict) -> dict:
    fish_scores = {}
    for sid, df in all_data.items():
        if df.empty or len(df) < 30:
            continue
        close_arr = df["close"].values
        open_arr = df["open"].values
        high_arr = df["high"].values
        low_arr = df["low"].values
        vol_arr = df["volume"].values
        inst_buy_arr = df["inst_buy"].values
        inst_sell_arr = df["inst_sell"].values
        dates = df["date"].values

        scores = {}
        for idx in range(29, len(df)):
            score = compute_fish_score(
                close_arr, open_arr, high_arr, low_arr, vol_arr,
                inst_buy_arr, inst_sell_arr, idx
            )
            d = dates[idx]
            d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            scores[d_str] = score
        fish_scores[sid] = scores
    return fish_scores


# ─── Fish 過濾（每週篩選觀察池）────────────────────
def screen_fish_qualified(
    all_data: dict, screening_date, fish_scores: dict,
    fish_days: int, fish_min_score: float
) -> set:
    qualified = set()
    sd_str = screening_date.strftime("%Y-%m-%d") if hasattr(screening_date, "strftime") else str(screening_date)[:10]
    lookback_start = (pd.Timestamp(sd_str) - timedelta(days=fish_days)).strftime("%Y-%m-%d")

    for stock_id, df in all_data.items():
        if df.empty or len(df) < 30:
            continue
        stock_fish = fish_scores.get(stock_id, {})
        max_score = 0.0
        for d_str, sc in stock_fish.items():
            if lookback_start <= d_str < sd_str and sc > max_score:
                max_score = sc
                if max_score >= fish_min_score:
                    break
        if max_score >= fish_min_score:
            qualified.add(stock_id)
    return qualified


# ─── 動能進場檢查 ──────────────────────────────────
def check_momentum_entry(all_data: dict, stock_id: str, check_date) -> tuple:
    df = all_data.get(stock_id)
    if df is None or df.empty or len(df) < LOOKBACK + 5:
        return False, 0

    date_mask = df["date"] <= check_date
    if not date_mask.any():
        return False, 0
    recent = df[date_mask].tail(LOOKBACK + 5)
    if len(recent) < LOOKBACK + 1:
        return False, 0

    latest = recent.iloc[-1]
    latest_close = latest["close"]
    if latest_close <= 0 or math.isnan(latest_close):
        return False, 0

    vol_5 = recent.tail(5)["volume"].mean()
    if vol_5 / 1000 < MIN_VOLUME_SHARES:
        return False, 0

    if latest_close < recent.tail(LOOKBACK)["close"].max():
        return False, 0

    ma20 = latest.get("ma20")
    if ma20 is None or math.isnan(ma20) or latest_close <= ma20:
        return False, 0

    inst_recent = recent.tail(5)
    total_net_buy = inst_recent["inst_buy"].sum() - inst_recent["inst_sell"].sum()
    total_vol_5 = inst_recent["volume"].sum()
    if total_net_buy <= 0 or total_vol_5 <= 0:
        return False, 0
    ratio = total_net_buy / total_vol_5
    if ratio < BUY_RATIO_THRESHOLD:
        return False, 0

    return True, round(ratio, 4)


# ─── 持倉出場檢查 ──────────────────────────────────
def check_position_exit(
    sid: str, positions: dict, price_info: dict, d, cash: float,
    trade_log: list
) -> tuple:
    """
    price_info: { close, ma10 } — 單日單股價格資訊
    回傳 (proceeds, cost_basis, last_roll_date)（0 代表續抱）。
    """
    pos = positions[sid]

    current_price = price_info.get("close", 0)
    if current_price <= 0:
        return (0, 0, None)

    loss_pct = (current_price - pos["buy_price"]) / pos["buy_price"]

    if loss_pct <= -STOP_LOSS:
        sell_price = current_price
        reason = f"硬性停損 {loss_pct:.1%}"
    elif loss_pct > 0:
        ma10 = price_info.get("ma10")
        if ma10 is not None and not math.isnan(ma10) and current_price < ma10:
            sell_price = current_price
            reason = f"跌破 MA10({ma10:.0f})移動停利"
        else:
            return (0, 0, None)
    else:
        return (0, 0, None)

    proceeds = pos["shares"] * sell_price * (1 - SELL_COST)
    cost_basis = pos["shares"] * pos["buy_price"]
    pnl = proceeds - cost_basis
    last_roll_date = pos.get("last_roll_date")
    d_iso = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
    trade_log.append({
        "date": d_iso, "action": "SELL",
        "stock_id": sid, "shares": pos["shares"],
        "price": round(sell_price, 2), "pnl": round(pnl, 0),
        "reason": reason,
    })
    del positions[sid]
    return (proceeds, cost_basis, last_roll_date)


# ─── Loser Ban ─────────────────────────────────────
def is_banned(sid: str, today: date, loser_ban: dict) -> bool:
    return sid in loser_ban and today <= loser_ban[sid]


def add_loser_ban(sid: str, sell_date: date, loser_ban: dict, ban_days: int):
    if ban_days > 0:
        loser_ban[sid] = sell_date + timedelta(days=ban_days)


# ─── 獲利滾入 ──────────────────────────────────────
def compute_profit_roll(profit: float, profit_roll_months: int,
                        profit_roll_percentage: float,
                        last_roll_date, today) -> tuple:
    """
    回傳 (can_roll: bool, rolled_amount: float)。
    M=0 → 每次獲利都滾入；M>0 → 每 M 個月滾入一次。
    """
    if profit <= 0 or profit_roll_percentage <= 0:
        return False, 0.0

    if profit_roll_months == 0:
        return True, profit * profit_roll_percentage

    if last_roll_date:
        months_since = (today.year - last_roll_date.year) * 12 + (today.month - last_roll_date.month)
    else:
        months_since = profit_roll_months
    if months_since >= profit_roll_months:
        return True, profit * profit_roll_percentage
    return False, 0.0


# ─── capital.log 追蹤 ──────────────────────────────
def log_capital_roll(action: str, stock_id: str, amount: float,
                     new_capital: float, timestamp: str = ""):
    """Append profit roll event to capital.log"""
    log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "capital.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"{timestamp}, {action}, {stock_id}, {amount:+.0f}, capital={new_capital:.0f}\n")
