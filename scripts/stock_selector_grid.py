#!/usr/bin/env python3
"""
stock_selector_grid.py — 每季選股神器 + Grid Search 找最佳參數

Usage:
  # Grid Search 找最佳選股參數 (2022~2025)
  python scripts/stock_selector_grid.py --grid

  # 檢視特定參數組合的歷史績效
  python scripts/stock_selector_grid.py --backtest

  # 用最佳參數輸出下一季推薦持股
  python scripts/stock_selector_grid.py --recommend

  # 產出 HTML 報告
  python scripts/stock_selector_grid.py --report
"""
import argparse
import itertools
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.cache_io import load_cache, dump_cache, load_cache_or_raw

# ── 候選股票池（市值前 N 大） ─────────────────────────
STOCK_NO = int(os.getenv("ROTATE_STOCK_NO", os.getenv("STOCK_NO", "50")))  # 全輪替候選池（優先 ROTATE_STOCK_NO，fallback STOCK_NO）
ROTATE_MODE = int(os.getenv("ROTATE_MODE", "5"))  # 0=off 1=1/4/7/10 2=2/5/8/11 3=3/6/9/12 4=1+2 5=2+3
MIN_DAILY_AMOUNT = float(os.getenv("MIN_DAILY_AMOUNT", "0"))  # 日均成交額門檻（萬元，0=不啟用）
CANDIDATE_POOL = []
CAP_RANKING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cache", "inst_momentum", "mcap_ranking.pkl")
if os.path.exists(CAP_RANKING):
    ranked, _ = load_cache_or_raw(CAP_RANKING)
    ranked = ranked or []
    CANDIDATE_POOL = [s for s in ranked if s.isdigit() and len(s) == 4][:STOCK_NO]
if not CANDIDATE_POOL:
    # 無排名檔時的 fallback
    CANDIDATE_POOL = [str(i) for i in range(1101, 9999)]

POOL_LABELS = {}
# 從 FinMind 載入股票名稱
try:
    from FinMind.data import DataLoader as _DL
    _dl = _DL()
    _info = _dl.taiwan_stock_info()
    for _, _r in _info.iterrows():
        _sid = str(_r["stock_id"]).strip()
        if _sid.isdigit() and len(_sid) == 4:
            POOL_LABELS[_sid] = _r["stock_name"]
except Exception:
    pass

START_DATE = "2022-01-01"
END_DATE = "2025-12-31"
# 實盤選股只需近期資料（動能 63 日 + MA60 足夠）。VM 實盤可設 SELECTOR_LOOKBACK_DAYS=250 減少下載量。
LOOKBACK_DAYS = int(os.getenv("SELECTOR_LOOKBACK_DAYS", "0"))  # 0=用 START_DATE 完整期間（回測用）

# ══════════════════════════════════════════════════════════════
# 資料載入
# ══════════════════════════════════════════════════════════════

_cache = {}
_PRICE_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cache", "selector_prices")

def load_stock(symbol: str) -> pd.DataFrame:
    if symbol in _cache:
        return _cache[symbol]
    # 磁碟快取：先讀 pkl，避免每次重新下載
    pkl_path = os.path.join(_PRICE_CACHE_DIR, f"{symbol}.pkl")
    if os.path.exists(pkl_path):
        df, _ = load_cache(pkl_path)
        if df is not None and not df.empty:
            _cache[symbol] = df
            return df
    yf_sym = f"{symbol}.TW" if symbol.isdigit() else f"{symbol}.TW"
    if LOOKBACK_DAYS > 0:
        from datetime import date as _date, timedelta as _td
        start = (_date.today() - _td(days=LOOKBACK_DAYS)).isoformat()
        df = yf.download(yf_sym, start=start, end="2026-12-31", auto_adjust=True, progress=False)
    else:
        df = yf.download(yf_sym, start=START_DATE, end="2026-12-31", auto_adjust=True, progress=False)
    if df.empty:
        _cache[symbol] = df
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    # 寫入磁碟快取
    try:
        os.makedirs(_PRICE_CACHE_DIR, exist_ok=True)
        dump_cache(pkl_path, df, meta={"symbol": symbol, "source": "yfinance"})
    except Exception:
        pass
    _cache[symbol] = df
    return df


def load_all_stocks(pool=None):
    if pool is None:
        pool = CANDIDATE_POOL
    data = {}
    for sym in pool:
        df = load_stock(sym)
        if not df.empty:
            data[sym] = df
    return data


# ── 交易成本 ──
ETF_STOCKS = {"0050","0056","006208","00878","00646","00632R"}
COMMISSION_RATE = 0.001425
STOCK_TAX = 0.003
ETF_TAX = 0.001
def tax_rate(sym): return ETF_TAX if sym in ETF_STOCKS else STOCK_TAX


# ══════════════════════════════════════════════════════════════
# 技術指標（僅用截至當前日期的資料）
# ══════════════════════════════════════════════════════════════

def trailing_ret(df, end_date, days):
    if end_date not in df.index:
        return None
    idx = df.index.get_loc(end_date)
    start_idx = max(0, idx - days)
    sp = float(df.iloc[start_idx]["close"])
    ep = float(df.iloc[idx]["close"])
    if sp <= 0:
        return None
    return (ep - sp) / sp


def ma_position(df, end_date, days=20):
    """股價在均線上方/下方，回傳偏離 %"""
    if end_date not in df.index:
        return None
    idx = df.index.get_loc(end_date)
    start = max(0, idx - days)
    ma = float(df.iloc[start:idx+1]["close"].mean())
    cp = float(df.iloc[idx]["close"])
    if ma <= 0:
        return None
    return (cp - ma) / ma


def volatility(df, end_date, days=63):
    if end_date not in df.index:
        return None
    idx = df.index.get_loc(end_date)
    start = max(0, idx - days)
    prices = df.iloc[start:idx+1]["close"].values
    if len(prices) < 5:
        return None
    return float(np.std(prices / np.mean(prices)))


# ══════════════════════════════════════════════════════════════
# 潛力股模式評分（從 find_catalyst_stocks.py 萃取）
# ══════════════════════════════════════════════════════════════

def catalyst_score(df, end_date):
    """
    模仿 find_catalyst_stocks.py 的「長期盤整→近期突破」評分。
    只使用截至 end_date 的價格與成交量資料，無外部 API。

    回傳 dict: { stable_score, breakout_score, volume_score, catalyst_total }
    或 None（資料不足時）。
    """
    n_required = 130  # 約半年交易日
    if end_date not in df.index:
        return None
    idx = df.index.get_loc(end_date)
    if idx < n_required:
        return None

    start_idx = idx - n_required
    mid = start_idx + n_required // 2

    prices = df.iloc[start_idx:idx+1]["close"].values
    volumes = df.iloc[start_idx:idx+1]["volume"].values

    # === 前半段（盤整偵測）===
    fh_p = prices[:n_required//2]
    fh_mean = np.mean(fh_p)
    fh_min = np.min(fh_p)
    fh_max = np.max(fh_p)
    fh_range_pct = (fh_max - fh_min) / fh_mean * 100 if fh_mean > 0 else 999

    # === 後半段（突破偵測）===
    sh_p = prices[n_required//2:]
    current_price = float(prices[-1])
    pct_above_fh_high = (current_price - fh_max) / fh_max * 100 if fh_max > 0 else 0
    pct_above_fh_mean = (current_price - fh_mean) / fh_mean * 100 if fh_mean > 0 else 0

    # 量能變化
    fh_vol = np.mean(volumes[:n_required//2]) if n_required//2 > 0 else 1
    sh_vol = np.mean(volumes[n_required//2:]) if len(volumes) > n_required//2 else fh_vol
    vol_ratio = sh_vol / fh_vol if fh_vol > 0 else 1.0

    # 近期動能
    recent_20d = prices[-20:] if len(prices) >= 20 else prices
    recent_60d = prices[-60:] if len(prices) >= 60 else prices
    chg_20d = (recent_20d[-1] - recent_20d[0]) / recent_20d[0] * 100 if recent_20d[0] > 0 else 0
    chg_60d = (recent_60d[-1] - recent_60d[0]) / recent_60d[0] * 100 if recent_60d[0] > 0 else 0

    # 評分（對應 find_catalyst_stocks.py calculate_score）
    # 1. 盤整品質 (0~1): 波動越小越高
    s_stable = max(0, 1 - fh_range_pct / 40)

    # 2. 突破力道 (0~1): 突破幅度越大越高
    if pct_above_fh_mean > 0:
        s_breakout = min(pct_above_fh_mean / 80, 1.0)
        if pct_above_fh_mean > 30:
            s_breakout *= 1.2
        s_breakout = min(s_breakout, 1.0)
    else:
        s_breakout = 0

    # 3. 量能確認 (0~1): 後半段量 / 前半段量
    s_volume = min(vol_ratio / 5, 1.0) if vol_ratio > 1.0 else vol_ratio * 0.2

    # 4. 動能延續性輔助（近60日上漲趨勢加分）
    s_momentum_aux = min(max(0, chg_60d) / 50, 1.0)

    # 綜合（權重對應原本 find_catalyst_stocks.py 的 0.2/0.3/0.15/0.25/0.1）
    cat_total = (s_stable * 0.20 + s_breakout * 0.35 + s_volume * 0.15 + s_momentum_aux * 0.30)

    return {
        "stable_score": float(s_stable),
        "breakout_score": float(min(s_breakout, 1.0)),
        "volume_score": float(min(s_volume, 1.0)),
        "mom_aux_score": float(s_momentum_aux),
        "cat_total": float(cat_total),
        "stable_range_pct": float(fh_range_pct),
        "pct_above_high": float(pct_above_fh_high),
        "pct_above_mean": float(pct_above_fh_mean),
        "vol_ratio": float(vol_ratio),
        "chg_20d": float(chg_20d),
        "chg_60d": float(chg_60d),
    }


# ══════════════════════════════════════════════════════════════
# 選股評分函數（參數可調）
# ══════════════════════════════════════════════════════════════

# 快取 catalyst 分數（stock, date_str → score dict）
_catalyst_cache = {}

def score_stock(sym, df, end_date, params):
    """
    給一檔股票打分（只用截至 end_date 的資訊）
    params 字典:
      - momentum_days: 動能回看天數 (21/63/125)
      - momentum_weight: 動能權重
      - technical_weight: 技術面權重（均線位置）
      - stability_weight: 穩定性權重（低波動加分）
      - catalyst_weight: 潛力股模式評分權重（盤整→突破）
      - use_ma_filter: 是否要求股價站上 MA20
      - min_price: 最低股價門檻
    """
    m_days = params.get("momentum_days", 63)
    m_w = params.get("momentum_weight", 1.0)
    t_w = params.get("technical_weight", 0.5)
    s_w = params.get("stability_weight", 0.3)
    c_w = params.get("catalyst_weight", 0.0)
    use_ma = params.get("use_ma_filter", False)
    min_px = params.get("min_price", 5)

    if end_date not in df.index:
        return None

    cp = float(df.loc[end_date, "close"])
    if cp < min_px:
        return None

    if MIN_DAILY_AMOUNT > 0:
        idx = df.index.get_loc(end_date)
        start_i = max(0, idx - 20)
        window = df.iloc[start_i:idx + 1]
        avg_vol = window["volume"].mean()
        avg_amount_wan = (avg_vol * 1000 * cp) / 10000.0
        if avg_amount_wan < MIN_DAILY_AMOUNT:
            return None

    # 動能分數（支援雙動能: momentum_days 為主, momentum2_days/weight 為輔）
    m_ret = trailing_ret(df, end_date, m_days)
    if m_ret is None:
        return None

    if use_ma:
        ma20_pos = ma_position(df, end_date, 20)
        if ma20_pos is None or ma20_pos < 0:
            return None

    # 技術面分數：離 MA20 越近越好（正偏離獎勵）
    ma20_pct = ma_position(df, end_date, 20) or 0
    ma60_pct = ma_position(df, end_date, 60) or 0
    tech_score = (max(0, ma20_pct) * 0.6 + max(0, ma60_pct) * 0.4)

    # 穩定度：波動越低分數越高
    vol = volatility(df, end_date)
    stability = 1.0 / (vol + 0.05) if vol else 0

    # 潛力股模式評分（快取）
    cache_key = (sym, end_date.strftime("%Y-%m-%d"))
    if cache_key not in _catalyst_cache:
        _catalyst_cache[cache_key] = catalyst_score(df, end_date)
    cat = _catalyst_cache[cache_key]
    cat_val = cat["cat_total"] if cat else 0

    # 綜合（雙動能: momentum2 加權獨立於 momentum_weight）
    m2_days = params.get("momentum2_days", None)
    m2_term = 0.0
    if m2_days:
        m2_ret = trailing_ret(df, end_date, m2_days)
        m2_term = max(0, m2_ret) * params.get("momentum2_weight", 1.0)
    total = (max(0, m_ret) * m_w + m2_term + tech_score * t_w + stability * s_w * 0.01 + cat_val * c_w)

    return {
        "symbol": sym,
        "close": cp,
        "momentum": m_ret,
        "tech_score": tech_score,
        "stability": stability,
        "catalyst": cat_val,
        "cat_stable": cat["stable_score"] if cat else 0,
        "cat_breakout": cat["breakout_score"] if cat else 0,
        "cat_volume": cat["volume_score"] if cat else 0,
        "total": total,
        "ma20_pct": ma20_pct,
        "ma60_pct": ma60_pct,
        "vol": vol,
    }


def pick_top_stocks(data, end_date, params, top_n=4, exclude=None):
    """從候選池選出最高分的 N 檔股票"""
    if exclude is None:
        exclude = set()
    scored = []
    for sym, df in data.items():
        if sym in exclude:
            continue
        s = score_stock(sym, df, end_date, params)
        if s is not None:
            scored.append(s)
    scored.sort(key=lambda x: x["total"], reverse=True)
    return scored[:top_n]


# ══════════════════════════════════════════════════════════════
# 季度回測
# ══════════════════════════════════════════════════════════════

def quarter_end_dates(start=None, end=None, quarter_months=None):
    if start is None:
        start = START_DATE
    if end is None:
        end = END_DATE
    from pandas.tseries.offsets import QuarterEnd
    """季度末日期。quarter_months: (1,4,7,10) / (2,5,8,11) / (3,6,9,12) 預設 (3,6,9,12)"""
    if quarter_months is None:
        quarter_months = (3, 6, 9, 12)
    all_dates = pd.bdate_range(start=start, end=end, freq="B")
    trading_set = set(all_dates)
    quarters = set()
    for d in all_dates:
        if d.month in quarter_months:
            quarters.add((d.year, d.month))
    result = []
    for yr, mo in sorted(quarters):
        # 該月所有交易日中最後一個
        candidates = [d for d in all_dates if d.year == yr and d.month == mo]
        if candidates:
            result.append(candidates[-1])
    return result


def month_end_dates(start=None, end=None):
    if start is None:
        start = START_DATE
    if end is None:
        end = END_DATE
    """回測期間內每個月最後交易日"""
    all_dates = pd.bdate_range(start=start, end=end, freq="B")
    months = set()
    for d in all_dates:
        months.add((d.year, d.month))
    result = []
    for yr, mo in sorted(months):
        candidates = [d for d in all_dates if d.year == yr and d.month == mo]
        if candidates:
            result.append(candidates[-1])
    return result


def _detect_and_adjust(market_df, current_date, params, verbose=False):
    """
    依市場狀態自動調整 momentum_days。
    使用 0050 的 MA200 斜率判斷：年線向上用 21d，年線走平/向下用 63d。
    """
    if current_date not in market_df.index:
        return
    idx = market_df.index.get_loc(current_date)
    if idx < 240:
        return
    
    close = market_df["close"].values
    cp = close[idx]
    ma200 = np.mean(close[idx-199:idx+1])
    ma200_before = np.mean(close[idx-239:idx-199])
    ma200_slope = (ma200 - ma200_before) / ma200_before if ma200_before > 0 else 0
    above_ma200 = cp > ma200
    
    original_days = params.get("momentum_days", 21)
    
    if above_ma200 and ma200_slope > 0.002:
        # 年線向上 + 價格在年線上 → 多頭趨勢 → 21d
        params["momentum_days"] = 21
        reason = f"多頭(年線+{ma200_slope:.1%})"
    else:
        # 年線走平或向下，或價格跌破年線 → 盤整/空頭 → 63d
        params["momentum_days"] = 63
        direction = "上" if ma200_slope > 0 else "下"
        reason = f"年線{direction}({ma200_slope:+.1%})"
    
    if verbose and params["momentum_days"] != original_days:
        print(f"    📊 auto_momentum: {reason} → momentum_days {original_days}→{params['momentum_days']}")


def _snap_date(df, target):
    """將日期對齊到 df 中 <= target 的最後交易日"""
    if target in df.index:
        return target
    avail = df[df.index <= target].index
    if len(avail) > 0:
        return avail[-1]
    # 沒有更早的日期，用第一個交易日
    return df.index[0] if len(df.index) > 0 else None


def backtest_selector(data, params, top_n=4, verbose=False, mode="momentum", 
                       auto_momentum=False, market_data=None, quarter_months=None,
                       quarterly_pool=None):
    """
    回測每季選股績效。
    每季末用 params 選股 → 持有到下季末 → 計算報酬。
    最後一季只評價不買賣。
    mode: momentum / catalyst / core-satellite
    auto_momentum: True = 依市場狀態自動切換 momentum_days（21/63）
    market_data: 0050 或大盤指數 DataFrame，用於判讀市場狀態
    quarter_months: (1,4,7,10) / (2,5,8,11) / (3,6,9,12)，預設 (3,6,9,12)
    """
    import math
    quarter_dates = quarter_end_dates(quarter_months=quarter_months)
    capital = 500000.0
    records = []
    holdings_list = []
    year_vals = {}
    last_val = capital
    current_holdings = []

    for qi, qd in enumerate(quarter_dates):
        is_last = (qi == len(quarter_dates) - 1)

        if is_last:
            # 最後一季：評價現有持股，不換股
            chosen = current_holdings
            nxt_val = 0.0
            alloc_per = capital / len(chosen) if chosen else 0
            for sym in chosen:
                if sym not in data:
                    continue
                df = data[sym]
                val_date = _snap_date(df, qd)
                if val_date is None:
                    continue
                px = float(df.loc[val_date, "close"])
                shares = last_shares.get(sym, 0)
                nxt_val += shares * px

            q_ret = (nxt_val - capital) / capital if capital > 0 else 0
            if verbose:
                print(f"  {qd.strftime('%Y-%m-%d')} → 評價 {chosen} → 報酬 {q_ret:+.2%} (終值 NT${nxt_val:,.0f})")
            capital = nxt_val
            records.append({"date": qd, "holdings": chosen, "return": q_ret, "value": capital})
            yr = qd.year
            if yr not in year_vals:
                year_vals[yr] = {"start": last_val, "end": capital, "records": []}
            year_vals[yr]["records"].append(q_ret)
            if qd.month == 12:
                year_vals[yr]["end"] = capital
            break

        # 選股日對齊到實際交易日
        buy_date_q = _snap_date(list(data.values())[0], qd) if data else qd
        data_q = data
        if quarterly_pool is not None:
            month = buy_date_q.strftime("%Y-%m") if hasattr(buy_date_q, "strftime") else str(buy_date_q)[:7]
            pool = None
            for q, p in quarterly_pool.items():
                if q <= month:
                    pool = p
                else:
                    break
            if pool is not None:
                data_q = {k: v for k, v in data.items() if k in pool}
        if mode == "catalyst":
            scored = []
            for sym, df in data_q.items():
                if buy_date_q not in df.index:
                    continue
                cs = _catalyst_score(df, buy_date_q)
                if cs <= 0:
                    continue
                scored.append({"symbol": sym, "total": cs})
            scored.sort(key=lambda x: x["total"], reverse=True)
            selected = scored[:top_n]
        elif mode == "core-satellite":
            core_n = max(top_n - 1, 1)
            core = pick_top_stocks(data_q, buy_date_q, params, core_n)
            core_syms = {s["symbol"] for s in core}
            sat = []
            for sym, df in data_q.items():
                if sym in core_syms or buy_date_q not in df.index:
                    continue
                cs = _catalyst_score(df, buy_date_q)
                if cs > 0:
                    sat.append({"symbol": sym, "total": cs})
            sat.sort(key=lambda x: x["total"], reverse=True)
            sat_pick = sat[:1] if sat else []
            selected = core + sat_pick
        else:
            # ── auto_momentum：依市場狀態自動切換動能天數 ──
            adj_params = dict(params)
            if auto_momentum and market_data is not None and buy_date_q in market_data.index:
                _detect_and_adjust(market_data, buy_date_q, adj_params, verbose)
            selected = pick_top_stocks(data_q, buy_date_q, adj_params, top_n)
        if not selected:
            continue

        chosen = [s["symbol"] for s in selected]
        current_holdings = chosen
        holdings_list.append((qd, chosen))

        alloc = capital / len(chosen)
        nxt_val = 0.0
        last_shares = {}

        for sym in chosen:
            if sym not in data:
                continue
            df = data[sym]
            buy_date = _snap_date(df, qd)
            if buy_date is None:
                continue

            # 下一季末（賣出日）
            nq_idx = qi + 1
            end_target = quarter_dates[nq_idx]
            sell_date = _snap_date(df, end_target)
            if sell_date is None or sell_date <= buy_date:
                continue

            buy_px = float(df.loc[buy_date, "close"])
            if buy_px <= 0:
                continue

            shares = alloc / buy_px
            last_shares[sym] = shares
            sell_px = float(df.loc[sell_date, "close"])
            nxt_val += shares * sell_px

        q_ret = (nxt_val - capital) / capital if capital > 0 else 0
        if verbose:
            print(f"  {qd.strftime('%Y-%m-%d')} → 持有 {chosen} → 報酬 {q_ret:+.2%} (終值 NT${nxt_val:,.0f})")

        capital = nxt_val

        records.append({
            "date": qd,
            "holdings": chosen,
            "return": q_ret,
            "value": capital,
        })

        yr = qd.year
        if yr not in year_vals:
            year_vals[yr] = {"start": last_val, "end": capital, "records": []}
        year_vals[yr]["records"].append(q_ret)
        year_vals[yr]["end"] = capital

        last_val = capital

    # 年度績效
    yearly = {}
    for yr, v in year_vals.items():
        if v["records"]:
            yearly[yr] = {
                "start": v["start"],
                "end": v["end"],
                "returns": v["records"],
                "total_ret": (v["end"] - v["start"]) / v["start"] if v["start"] > 0 else 0,
            }

    final_val = capital
    total_ret = (final_val - 500000) / 500000
    return {
        "records": records,
        "yearly": yearly,
        "final_value": final_val,
        "total_return": total_ret,
    }


# ══════════════════════════════════════════════════════════════
# TWO_BY_TWO 策略回測 — Group 1
# ══════════════════════════════════════════════════════════════

def backtest_two_by_two(data, params, verbose=False, mode="momentum",
                        auto_momentum=False, market_data=None):
    """
    TWO_BY_TWO 策略回測（Group 1）。
    4 個 slot 循環輪替，每個月檢討，每次選 2 檔，持有 2 個月。
    第 1 個月部署一半（2 slot），第 2 個月部署另一半，之後每月換 2 檔。
    """
    dates = month_end_dates()
    capital = 500000.0
    cash = capital
    slots = [None] * 4
    slot_buy_idx = [-1] * 4
    records = []
    year_vals = {}
    last_val = capital

    for ri, md in enumerate(dates):
        is_last = (ri == len(dates) - 1)

        # ── Step 1: 賣出滿 2 月的 slot ──
        for si in range(4):
            if slot_buy_idx[si] == -1:
                continue
            if ri - slot_buy_idx[si] < 2:
                continue
            sym = slots[si]["sym"]
            if sym not in data:
                slot_buy_idx[si] = -1
                slots[si] = None
                continue
            df = data[sym]
            sell_date = _snap_date(df, md)
            if sell_date is None:
                continue
            px = float(df.loc[sell_date, "close"])
            shares = slots[si]["shares"]
            proceeds = shares * px * (1 - COMMISSION_RATE - tax_rate(sym))
            cash += proceeds
            if verbose:
                buy_px = slots[si].get("buy_px", 0)
                ret = (px - buy_px) / buy_px if buy_px > 0 else 0
                print(f"  💰 賣出 {sym} {shares:.1f}股 @ {px:.0f} (+{ret:+.2%}) 得款 NT${proceeds:,.0f}")
            slot_buy_idx[si] = -1
            slots[si] = None

        # ── Step 2: 評價組合總值 ──
        total_val = cash
        for si in range(4):
            if slot_buy_idx[si] == -1 or slots[si] is None:
                continue
            sym = slots[si]["sym"]
            if sym not in data:
                continue
            df = data[sym]
            val_date = _snap_date(df, md)
            if val_date is None:
                continue
            px = float(df.loc[val_date, "close"])
            total_val += slots[si]["shares"] * px

        period_ret = (total_val - last_val) / last_val if last_val > 0 else 0
        held = [slots[i]["sym"] for i in range(4) if slot_buy_idx[i] != -1 and slots[i] is not None]

        if verbose and not is_last:
            print(f"\n📅 {md.strftime('%Y-%m-%d')}  TWO_BY_TWO  持有={held}  總值=NT${total_val:,.0f}")

        if is_last:
            capital = total_val
            records.append({"date": md, "holdings": held, "return": period_ret, "value": capital})
            yr = md.year
            if yr not in year_vals:
                year_vals[yr] = {"start": last_val, "end": capital, "records": []}
            year_vals[yr]["records"].append(period_ret)
            if md.month == 12:
                year_vals[yr]["end"] = capital
            break

        records.append({"date": md, "holdings": held, "return": period_ret, "value": total_val})
        yr = md.year
        if yr not in year_vals:
            year_vals[yr] = {"start": last_val, "end": total_val, "records": []}
        year_vals[yr]["records"].append(period_ret)
        if md.month == 12:
            year_vals[yr]["end"] = total_val

        last_val = total_val
        capital = total_val
        target_per_slot = capital / 4.0

        # ── Step 3: 選股（排除已持有）──
        buy_date_q = _snap_date(list(data.values())[0], md) if data else md
        adj_params = dict(params)
        if auto_momentum and market_data is not None and buy_date_q in market_data.index:
            _detect_and_adjust(market_data, buy_date_q, adj_params, verbose)

        held_syms = {slots[i]["sym"] for i in range(4) if slot_buy_idx[i] != -1 and slots[i] is not None}

        n_to_buy = 2
        if mode == "catalyst":
            scored = []
            for sym, df in data.items():
                if sym in held_syms or buy_date_q not in df.index:
                    continue
                cs = _catalyst_score(df, buy_date_q)
                if cs <= 0:
                    continue
                scored.append({"symbol": sym, "total": cs})
            scored.sort(key=lambda x: x["total"], reverse=True)
            selected = scored[:n_to_buy]
        else:
            selected = pick_top_stocks(data, buy_date_q, adj_params, n_to_buy + len(held_syms),
                                       exclude=held_syms)
            selected = selected[:n_to_buy]

        chosen = [s["symbol"] for s in selected]
        if verbose and chosen:
            print(f"  📥 選股: {chosen}")

        # ── Step 4: 填入空 slot ──
        fill_idx = 0
        for si in range(4):
            if slot_buy_idx[si] != -1:
                continue
            if fill_idx >= len(chosen):
                break
            sym = chosen[fill_idx]
            if sym not in data:
                fill_idx += 1
                continue
            df = data[sym]
            buy_date_sym = _snap_date(df, md)
            if buy_date_sym is None:
                fill_idx += 1
                continue
            buy_px = float(df.loc[buy_date_sym, "close"])
            if buy_px <= 0:
                fill_idx += 1
                continue
            shares = target_per_slot / buy_px
            cost = shares * buy_px * (1 + COMMISSION_RATE)
            cash -= cost
            slots[si] = {"sym": sym, "shares": shares, "buy_px": buy_px}
            slot_buy_idx[si] = ri
            if verbose:
                print(f"    🟢 slot{si} 買入 {sym} {shares:.1f}股 @ {buy_px:.0f} → NT${cost:,.0f}")
            fill_idx += 1

    yearly = {}
    for yr, v in year_vals.items():
        if v["records"]:
            yearly[yr] = {
                "start": v["start"],
                "end": v["end"],
                "returns": v["records"],
                "total_ret": (v["end"] - v["start"]) / v["start"] if v["start"] > 0 else 0,
            }

    final_val = capital
    total_ret = (final_val - 500000) / 500000
    return {
        "records": records,
        "yearly": yearly,
        "final_value": final_val,
        "total_return": total_ret,
    }


def backtest_dual_quarterly(data, params, top_n=4, verbose=False, mode="momentum",
                            auto_momentum=False, market_data=None,
                            qm_a=(2,5,8,11), qm_b=(3,6,9,12), quarterly_pool=None):
    """兩段季度排程 50/50 資金各半並行回測。日期用 module 的 START_DATE/END_DATE。"""
    bt_a = backtest_selector(data, params, top_n, verbose, mode, auto_momentum,
                              market_data, quarter_months=qm_a, quarterly_pool=quarterly_pool)
    bt_b = backtest_selector(data, params, top_n, False, mode,
                              auto_momentum, market_data, quarter_months=qm_b,
                              quarterly_pool=quarterly_pool)
    final_val = (bt_a["final_value"] + bt_b["final_value"]) / 2
    total_ret = (final_val - 500000) / 500000
    yearly = {}
    for yr in set(list(bt_a["yearly"].keys()) + list(bt_b["yearly"].keys())):
        ya = bt_a["yearly"].get(yr, {})
        yb = bt_b["yearly"].get(yr, {})
        yearly[yr] = {"total_ret": (ya.get("total_ret", 0) + yb.get("total_ret", 0)) / 2}
    return {"final_value": final_val, "total_return": total_ret, "yearly": yearly}


# ══════════════════════════════════════════════════════════════
# Grid Search
# ══════════════════════════════════════════════════════════════

GRID_PARAMS = {
    "momentum_days": [21, 63, 125],
    "momentum_weight": [0.5, 1.0, 2.0],
    "technical_weight": [0.0, 0.3, 0.5, 1.0],
    "stability_weight": [0.0, 0.3, 0.5],
    "catalyst_weight": [0.0, 0.3, 0.5, 1.0],
    "auto_momentum": [0, 1],
    "use_ma_filter": [False, True],
    "min_price": [5, 10],
}

DEFAULT_PARAMS = {
    "momentum_days": 21,
    "momentum_weight": 2.0,
    "technical_weight": 0.3,
    "stability_weight": 0.5,
    "catalyst_weight": 0.0,
    "auto_momentum": 1,
    "use_ma_filter": True,
    "min_price": 5,
}


def _run_backtest(data, params, top_n, strategy, mode, auto_momentum, market_data, verbose=False, quarter_months=None):
    """依 strategy 選擇回測函數"""
    if strategy == "two_by_two":
        return backtest_two_by_two(data, params, verbose=verbose, mode=mode,
                                    auto_momentum=auto_momentum, market_data=market_data)
    return backtest_selector(data, params, top_n=top_n, verbose=verbose, mode=mode,
                              auto_momentum=auto_momentum, market_data=market_data,
                              quarter_months=quarter_months)


def run_grid_search(data, top_n=4, auto_momentum=False, market_data=None, strategy="quarterly", quarter_months=(3,6,9,12)):
    """Grid Search 所有參數組合"""
    keys = list(GRID_PARAMS.keys())
    values = list(GRID_PARAMS.values())
    combinations = list(itertools.product(*values))
    total = len(combinations)

    strat_label = "TWO_BY_TWO" if strategy == "two_by_two" else f"每季({','.join(str(x) for x in quarter_months)})"
    print(f"\n🔍 Grid Search — {len(keys)} 個維度 × {total} 種組合")
    print(f"   選股池: {len(data)} 檔 | {strat_label}")
    print(f"   回測期間: {START_DATE} ~ {END_DATE}")
    print(f"   {'='*55}")

    results = []
    t0 = time.time()

    for ci, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        bt = _run_backtest(data, params, top_n, strategy, "momentum",
                           auto_momentum, market_data, quarter_months=quarter_months)
        results.append({
            "params": params,
            "final_value": bt["final_value"],
            "total_return": bt["total_return"],
        })

        if (ci + 1) % 50 == 0 or ci == 0 or ci == total - 1:
            pct = (ci + 1) / total * 100
            elapsed = time.time() - t0
            best_so_far = max(results, key=lambda r: r["final_value"])
            print(f"   [{ci+1:3d}/{total}] {pct:4.0f}%  "
                  f"目前最佳: {best_so_far['final_value']:>8,.0f} "
                  f"({best_so_far['total_return']:+.1%}) "
                  f"參數: {best_so_far['params']}")

    # 排序
    results.sort(key=lambda r: r["final_value"], reverse=True)
    elapsed = time.time() - t0
    print(f"\n✅ Grid Search 完成! {elapsed:.0f}s")
    return results


def print_top_results(results, n=10):
    print(f"\n{'='*70}")
    print(f"🏆 TOP {n} 最佳參數組合（按終值排序）")
    print(f"{'='*70}")
    print(f"{'#':>3} {'終值':>12} {'報酬率':>8} {'參數'}")
    print(f"{'-'*3} {'-'*12} {'-'*8} {'-'*45}")
    for i, r in enumerate(results[:n]):
        p = r["params"]
        p_str = (f"動能{p['momentum_days']}d "
                 f"w_m={p['momentum_weight']:.1f} "
                 f"w_t={p['technical_weight']:.1f} "
                 f"w_s={p['stability_weight']:.1f} "
                 f"w_c={p['catalyst_weight']:.1f} "
                 f"MA={'Y' if p['use_ma_filter'] else 'N'}"
                 f"${p['min_price']}")
        print(f"{i+1:3d} NT${r['final_value']:>8,.0f} {r['total_return']:+7.1%}  {p_str}")


# ══════════════════════════════════════════════════════════════
# 推薦輸出
# ══════════════════════════════════════════════════════════════

def _catalyst_score(df, end_date):
    """潛力股模式評分（同 selector_workflow.py）"""
    n = 130
    if end_date not in df.index:
        return 0
    idx = df.index.get_loc(end_date)
    if idx < n:
        return 0
    si = idx - n
    prices = df.iloc[si:idx+1]["close"].values
    volumes = df.iloc[si:idx+1]["volume"].values
    mid = n // 2
    fh_p = prices[:mid]
    fh_mean, fh_max = np.mean(fh_p), np.max(fh_p)
    fh_range = (fh_max - np.min(fh_p)) / fh_mean * 100 if fh_mean > 0 else 999
    sh_p = prices[mid:]
    cp = prices[-1]
    pct_above = (cp - fh_mean) / fh_mean * 100 if fh_mean > 0 else 0
    fv = np.mean(volumes[:mid]) or 1
    sv = np.mean(volumes[mid:]) or 1
    vr = sv / fv
    s_stable = max(0, 1 - fh_range / 40)
    s_break = min(max(0, pct_above) / 80, 1.0)
    if pct_above > 30:
        s_break = min(s_break * 1.2, 1.0)
    s_vol = min(vr / 5, 1.0) if vr > 1 else vr * 0.2
    chg60 = (prices[-1] - prices[max(0, len(prices)-60)]) / prices[max(0, len(prices)-60)] * 100 if prices[max(0, len(prices)-60)] > 0 else 0
    s_mom = min(max(0, chg60) / 50, 1.0)
    return s_stable * 0.20 + s_break * 0.35 + s_vol * 0.15 + s_mom * 0.30


def recommend_next_quarter(data, params, top_n=4, mode="momentum",
                            auto_momentum=False, market_data=None,
                            output_env=False, schedule_label="A"):
    """用給定參數選出下一季推薦持股"""
    today = datetime.now()
    # 用最近有資料的日期
    best_date = None
    for sym, df in data.items():
        avail = df[df.index <= pd.Timestamp(today)]
        if not avail.empty:
            d = avail.index[-1]
            if best_date is None or d > best_date:
                best_date = d

    if best_date is None:
        print("❌ 無法取得最新資料", file=sys.stderr)
        return

    mode_label = {"momentum": "純動能", "catalyst": "純催化劑", "core-satellite": "核心+衛星"}

    if mode == "catalyst":
        scored = []
        for sym, df in data.items():
            if best_date not in df.index:
                continue
            cs = _catalyst_score(df, best_date)
            if cs <= 0:
                continue
            scored.append({"symbol": sym, "close": float(df.loc[best_date, "close"]), "total": cs})
        scored.sort(key=lambda x: x["total"], reverse=True)
        selected = scored[:top_n]
    elif mode == "core-satellite":
        # 核心 (80%)：動能選 top_n-1 檔
        core_n = max(top_n - 1, 1)
        core = pick_top_stocks(data, best_date, params, core_n)
        core_syms = {s["symbol"] for s in core}
        # 衛星 (20%)：從剩餘選項中催化劑最高分
        sat = []
        for sym, df in data.items():
            if sym in core_syms or best_date not in df.index:
                continue
            cs = _catalyst_score(df, best_date)
            if cs > 0:
                sat.append({"symbol": sym, "close": float(df.loc[best_date, "close"]), "catalyst": cs})
        sat.sort(key=lambda x: x["catalyst"], reverse=True)
        sat_pick = sat[:1] if sat else []
        selected = core + sat_pick
    else:
        adj_params = dict(params)
        if auto_momentum and market_data is not None and best_date in market_data.index:
            _detect_and_adjust(market_data, best_date, adj_params, verbose=True)
        selected = pick_top_stocks(data, best_date, adj_params, top_n)

    if not selected:
        print("❌ 無法選出推薦持股", file=sys.stderr)
        return

    if output_env:
        alloc = round(50.0 / top_n, 1)
        print(f"#SCHEDULE={schedule_label}")
        for s in selected:
            cfg = {"strategy": "keep_wait", "alloc": alloc, "max_entry_price": -1, "initial_buy_pct": 1.0}
            print(f"PC_{s['symbol']}={json.dumps(cfg, separators=(',', ':'))}")
        return

    print(f"\n📅 基準日期: {best_date.strftime('%Y-%m-%d')}  模式: {mode_label.get(mode, mode)}")
    header_map = {"momentum": ("近季動能", "momentum"), "catalyst": ("催化劑分", "total"), "core-satellite": ("近季動能", "momentum")}
    extra_col, extra_key = header_map.get(mode, ("近季動能", "momentum"))

    print(f"\n{'='*60}")
    print(f"  📊 下一季推薦持股（Top {top_n} · {mode_label.get(mode, mode)}）")
    print(f"{'='*60}")
    print(f" {'代號':>5} {'名稱':>8} {'股價':>8} {extra_col:>10}")
    print(f" {'-'*5} {'-'*8} {'-'*8} {'-'*10}")
    for s in selected:
        name = POOL_LABELS.get(s["symbol"], "")
        val = s.get(extra_key, s.get("total", 0))
        if extra_key == "momentum":
            print(f" {s['symbol']:>5} {name:>8} NT${s['close']:>6,.0f} {val:>+9.1%}")
        else:
            print(f" {s['symbol']:>5} {name:>8} NT${s['close']:>6,.0f} {val:>9.2f}")

    print(f"\n💡 模式: {mode_label.get(mode, mode)}")
    if mode == "momentum":
        print(f"   參數: {params}")


def recommend_two_by_two(data, params, mode="momentum",
                         auto_momentum=False, market_data=None):
    """用 TWO_BY_TWO 策略選出下一期推薦持股（顯示 slot 狀態）"""
    today = datetime.now()
    best_date = None
    for sym, df in data.items():
        avail = df[df.index <= pd.Timestamp(today)]
        if not avail.empty:
            d = avail.index[-1]
            if best_date is None or d > best_date:
                best_date = d
    if best_date is None:
        print("❌ 無法取得最新資料")
        return

    mode_label = {"momentum": "純動能", "catalyst": "純催化劑", "core-satellite": "核心+衛星"}
    print(f"\n📅 基準日期: {best_date.strftime('%Y-%m-%d')}  模式: {mode_label.get(mode, mode)}")

    # 找出這個月在 slot 週期的哪個階段
    base = pd.Timestamp("2022-01-01")
    months_since = (best_date.year - base.year) * 12 + (best_date.month - base.month)
    # ri=0 → deploy first 2 slots, ri=1 → second 2, ri>=2 → replace 2 expired
    ri = months_since
    slot_phase = "first_half" if ri == 0 else "second_half" if ri == 1 else "rotation"

    target_per_slot = 500000 / 4.0
    adj_params = dict(params)
    if auto_momentum and market_data is not None and best_date in market_data.index:
        _detect_and_adjust(market_data, best_date, adj_params, verbose=True)

    selected = pick_top_stocks(data, best_date, adj_params, 2)
    chosen = [s["symbol"] for s in selected]

    print(f"\n{'='*60}")
    print(f"  📊 TWO_BY_TWO 推薦持股（Group 1 · 每次選 2 檔 · 持有 2 個月）")
    print(f"{'='*60}")
    print(f"  Slot 狀態: {slot_phase}")
    if slot_phase == "first_half":
        print(f"  → 第一個部署月：部署 slot 0,1（各 NT${target_per_slot:,.0f}）")
    elif slot_phase == "second_half":
        print(f"  → 第二個部署月：部署 slot 2,3（各 NT${target_per_slot:,.0f}）")
    else:
        print(f"  → 輪替月：2 個 slot 到期，換入 2 檔新標的（各 NT${target_per_slot:,.0f}）")
    print()
    print(f" {'代號':>5} {'名稱':>8} {'股價':>8} {'近季動能':>10}")
    print(f" {'-'*5} {'-'*8} {'-'*8} {'-'*10}")
    for s in selected:
        name = POOL_LABELS.get(s["symbol"], "")
        val = s.get("momentum", s.get("total", 0))
        print(f" {s['symbol']:>5} {name:>8} NT${s['close']:>6,.0f} {val:>+9.1%}")
    print(f"\n💡 TWO_BY_TWO: 上述為本月新部署的 2 檔，另 2 檔為上月已持有（續抱中）")


# ══════════════════════════════════════════════════════════════
# HTML 報告
# ══════════════════════════════════════════════════════════════

def generate_html_report(best_results, data, best_params, output_path,
                          auto_momentum=False, market_data=None, strategy="quarterly", quarter_months=(3,6,9,12)):
    """產出 HTML 報告"""
    bt = _run_backtest(data, best_params, top_n=4, strategy=strategy, mode="momentum",
                       auto_momentum=auto_momentum, market_data=market_data, quarter_months=quarter_months)

    rows = ""
    for i, r in enumerate(best_results[:20]):
        p = r["params"]
        rows += f"""
        <tr>
          <td>{i+1}</td>
          <td><b>NT${r['final_value']:,.0f}</b></td>
          <td class="{'positive' if r['total_return']>0 else 'negative'}">{r['total_return']:+.1%}</td>
          <td>{p['momentum_days']}d</td>
          <td>{p['momentum_weight']:.1f}</td>
          <td>{p['technical_weight']:.1f}</td>
          <td>{p['stability_weight']:.1f}</td>
          <td>{p['catalyst_weight']:.1f}</td>
          <td>{'✅' if p['use_ma_filter'] else '❌'}</td>
          <td>${p['min_price']}</td>
        </tr>"""

    # 年度績效表
    yr_rows = ""
    for yr, yd in bt["yearly"].items():
        cls = "positive" if yd["end"] > yd["start"] else "negative"
        yr_rows += f"""
        <tr>
          <td>{yr}</td>
          <td>{yd['total_ret']:+.1%}</td>
          <td class="{cls}">NT${yd['start']:,.0f} → NT${yd['end']:,.0f}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>每季選股 Grid Search 報告</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,"Microsoft JhengHei",Arial,sans-serif;background:#f5f7fa;color:#1a1a2e;padding:30px;max-width:1100px;margin:0 auto}}
h1{{font-size:24px;margin-bottom:6px}} h2{{font-size:18px;margin:24px 0 12px;color:#333}}
.sub{{color:#888;font-size:14px;margin-bottom:20px}}
.card{{background:#fff;border-radius:12px;padding:20px;margin:16px 0;box-shadow:0 1px 6px rgba(0,0,0,.08)}}
.best{{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:24px;border-radius:12px;margin:16px 0}}
.best .val{{font-size:36px;font-weight:700}}
.best .lbl{{font-size:13px;color:#aaa;margin-top:4px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:12px 0}}
.gi{{padding:16px;background:rgba(255,255,255,.08);border-radius:8px;text-align:center}}
.gv{{font-size:22px;font-weight:600}} .gl{{font-size:12px;color:#888;margin-top:2px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}}
th{{background:#1a1a2e;color:#fff;padding:8px 10px;text-align:left;font-size:12px}}
td{{padding:8px 10px;border-bottom:1px solid #eee}}
tr:hover td{{background:#f8f9fa}}
.positive{{color:#e74c3c}} .negative{{color:#3498db}}
.tag{{display:inline-block;background:#e94560;color:#fff;padding:2px 10px;border-radius:10px;font-size:11px;margin:2px}}
</style>
</head>
<body>
<h1>📊 每季選股 Grid Search</h1>
<div class="sub">參數維度: {len(GRID_PARAMS)} 個 · 候選池: {len(data)} 檔 · 每季選 Top 4</div>

<div class="best">
  <h2>🏆 最佳參數組合</h2>
    <div class="grid">
      <div class="gi"><div class="gv">NT${best_results[0]['final_value']:,.0f}</div><div class="lbl">終值</div></div>
      <div class="gi"><div class="gv">{best_results[0]['total_return']:+.1%}</div><div class="lbl">總報酬</div></div>
      <div class="gi"><div class="gv">{best_results[0]['params']['momentum_days']}d</div><div class="lbl">動能回看</div></div>
      <div class="gi">
        <div>
          <span class="tag">M:{best_results[0]['params']['momentum_weight']:.1f}</span>
          <span class="tag">T:{best_results[0]['params']['technical_weight']:.1f}</span>
          <span class="tag">S:{best_results[0]['params']['stability_weight']:.1f}</span>
          <span class="tag">C:{best_results[0]['params']['catalyst_weight']:.1f}</span>
        </div>
        <div class="lbl">權重配置 (M動能/T技術/S穩定/C催化劑)</div>
      </div>
    </div>
</div>

<h2>📅 年度績效</h2>
<div class="card"><table>
<tr><th>年份</th><th>報酬率</th><th>資金變化</th></tr>
{yr_rows}
<tr><td><b>合計</b></td><td><b>{bt['total_return']:+.1%}</b></td><td><b>NT$500,000 → NT${bt['final_value']:,.0f}</b></td></tr>
</table></div>

<h2>📋 參數排名（Top 20）</h2>
<div class="card"><table>
<tr><th>#</th><th>終值</th><th>報酬率</th><th>動能天數</th><th>動能權重</th><th>技術權重</th><th>穩定權重</th><th>催化劑權重</th><th>MA過濾</th><th>最低股價</th></tr>
{rows}
</table></div>

<p style="color:#888;font-size:12px;margin-top:30px;text-align:center">
  產生: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 過去績效不代表未來獲利
</p>
</body>
</html>"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ 報告已輸出: {output_path}")


# ══════════════════════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════════════════════

def _load_custom_pool():
    """讀取 custom_pool.txt，回傳自訂股票代號列表（無此檔回傳空列表）"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "custom_pool.txt")
    if not os.path.exists(path):
        return []
    custom = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sid = line.split("#")[0].strip()
            if sid.isdigit() and len(sid) == 4 and sid not in CANDIDATE_POOL:
                custom.append(sid)
    return custom


def main():
    # 讀取使用者資金
    env_capital = 500000
    try:
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("TOTAL_CAPITAL="):
                    env_capital = int(line.strip().split("=")[1])
    except:
        pass

    parser = argparse.ArgumentParser(description="每季選股 Grid Search")
    parser.add_argument("--grid", action="store_true", help="執行 Grid Search 找最佳參數")
    parser.add_argument("--backtest", action="store_true", help="用預設參數回測")
    parser.add_argument("--recommend", action="store_true", help="輸出下一期推薦持股")
    parser.add_argument("--report", action="store_true", help="產出 HTML 報告")
    parser.add_argument("--top-n", type=int, default=0, help="每季選股數 (0=依資金自動決定)")
    parser.add_argument("--capital", type=int, default=env_capital, help=f"起始資金 (default: 從 .env 讀取={env_capital})")
    parser.add_argument("--auto-momentum", action="store_true", default=False,
                        help="自動依市場狀態切換動能天數（趨勢用21d、盤整用63d）")
    parser.add_argument("--mode", type=str, default="momentum",
                        choices=["momentum", "catalyst", "core-satellite"],
                        help="選股模式: momentum=純動能, catalyst=純催化劑, core-satellite=核心+衛星 (default: momentum)")
    parser.add_argument("--strategy", type=str, default="quarterly",
                        choices=["quarterly"],
                        help="回測策略: quarterly=每季全換 (default: quarterly)")
    parser.add_argument("--rotate-mode", type=int, default=0,
                        help="季度排程: 0=不啟用 1=1/4/7/10 2=2/5/8/11 3=3/6/9/12 4=1/4/7/10+2/5/8/11 5=2/5/8/11+3/6/9/12 (default: 0=由env ROTATE_MODE控制)")
    parser.add_argument("--quarter", type=str, default="3,6,9,12",
                        choices=["1,4,7,10", "2,5,8,11", "3,6,9,12"],
                        help="季度檢討月份 (被 --rotate-mode 優先覆蓋, default: 3,6,9,12)")
    parser.add_argument("--output-env", action="store_true", default=False,
                        help="輸出 PC_* .env 格式而非 console 表格（搭配 --recommend 使用）")
    parser.add_argument("--schedule-label", type=str, default="A",
                        help="排程標籤 A/B，用於 .env 區段標記（搭配 --output-env 使用）")
    args = parser.parse_args()

    capital = args.capital

    # 自動決定建議持股數
    if args.top_n > 0:
        top_n = args.top_n
    elif capital >= 2000000:
        top_n = 6
    elif capital >= 1000000:
        top_n = 5
    elif capital >= 500000:
        top_n = 4
    elif capital >= 200000:
        top_n = 3
    else:
        top_n = 2

    strat_label = {"quarterly": "每季全換", "two_by_two": "TWO_BY_TWO(每月2檔×2月) G1"}
    print("=" * 60)
    print("📊 每季選股神器 — Stock Selector Grid")
    print("=" * 60)
    print(f"   💰 起始資金: NT${capital:,}（--capital 可改）")
    print(f"   📋 建議持股: top {top_n} 檔（--top-n 可改）")
    print(f"   🎯 策略: {strat_label.get(args.strategy, args.strategy)}（--strategy 可改）")
    if args.auto_momentum:
        print(f"   🔄 auto_momentum: 開啟（依市場狀態自動切換 21d/63d）")
    print()

    # 自訂候選股（從 custom_pool.txt）
    custom = _load_custom_pool()
    if custom:
        print(f"📋 偵測到自訂候選股: {', '.join(custom)}")
        try:
            ans = input("   是否併入候選池？(Y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "y"
        if ans in ("", "y", "yes"):
            CANDIDATE_POOL.extend(custom)
            print(f"   ✅ 已加入，候選池共 {len(CANDIDATE_POOL)} 檔")
        else:
            print(f"   ⏭️  跳過")

    print(f"\n📥 載入 {len(CANDIDATE_POOL)} 檔候選股票資料...")
    data = load_all_stocks()
    print(f"✅ 成功載入 {len(data)} 檔")

    # auto_momentum 需要 0050 作為市場指標
    market_data = None
    if args.auto_momentum:
        print(f"\n📥 載入 0050 作為市場指標...")
        df_0050 = load_stock("0050")
        if not df_0050.empty:
            market_data = df_0050
            print(f"✅ 0050 資料載入成功（{len(df_0050)} 筆）")
        else:
            print(f"⚠️ 0050 資料載入失敗，auto_momentum 將不啟用")

    # 季度排程解析
    ROTATE_QMAP = {1: (1,4,7,10), 2: (2,5,8,11), 3: (3,6,9,12)}
    rotate_mode = args.rotate_mode if args.rotate_mode > 0 else ROTATE_MODE
    if args.quarter != "3,6,9,12":
        quarter_months = tuple(int(x) for x in args.quarter.split(","))
    elif 1 <= rotate_mode <= 3:
        quarter_months = ROTATE_QMAP[rotate_mode]
    else:
        quarter_months = (3,6,9,12)
    dual_mode = rotate_mode in (4, 5)
    if dual_mode:
        qm_a, qm_b = {4: ((1,4,7,10),(2,5,8,11)), 5: ((2,5,8,11),(3,6,9,12))}[rotate_mode]

    def _do_backtest():
        if dual_mode:
            return backtest_dual_quarterly(data, DEFAULT_PARAMS, top_n=top_n, verbose=True,
                                            auto_momentum=args.auto_momentum, market_data=market_data,
                                            qm_a=qm_a, qm_b=qm_b)
        return _run_backtest(data, DEFAULT_PARAMS, top_n=top_n, strategy=args.strategy,
                             mode=args.mode, auto_momentum=args.auto_momentum,
                             market_data=market_data, verbose=True, quarter_months=quarter_months)

    if args.report or (not args.grid and not args.backtest and not args.recommend and not args.report):
        print("\n🔍 預設執行 Grid Search...")
        results = run_grid_search(data, top_n=top_n, auto_momentum=args.auto_momentum,
                                   market_data=market_data, strategy=args.strategy,
                                   quarter_months=quarter_months)
        print_top_results(results, n=10)

        best_params = results[0]["params"]
        print(f"\n🏆 最佳參數: {best_params}")
        print(f"   終值: NT${results[0]['final_value']:,.0f} ({results[0]['total_return']:+.1%})")

        out = os.path.join(os.path.dirname(__file__), "..", "img", "stock_selector_grid_report.html")
        generate_html_report(results, data, best_params, out, auto_momentum=args.auto_momentum,
                             market_data=market_data, strategy=args.strategy,
                             quarter_months=quarter_months)
        recommend_next_quarter(data, best_params, top_n=top_n, mode=args.mode,
                                auto_momentum=args.auto_momentum, market_data=market_data,
                                output_env=args.output_env, schedule_label=args.schedule_label)

    if args.grid:
        results = run_grid_search(data, top_n=top_n, auto_momentum=args.auto_momentum,
                                   market_data=market_data, strategy=args.strategy,
                                   quarter_months=quarter_months)
        print_top_results(results, n=10)

        best_params = results[0]["params"]
        out = os.path.join(os.path.dirname(__file__), "..", "img", "stock_selector_grid_report.html")
        generate_html_report(results, data, best_params, out, auto_momentum=args.auto_momentum,
                             market_data=market_data, strategy=args.strategy,
                             quarter_months=quarter_months)
        recommend_next_quarter(data, best_params, top_n=top_n, mode=args.mode,
                                auto_momentum=args.auto_momentum, market_data=market_data,
                                output_env=args.output_env, schedule_label=args.schedule_label)

    if args.backtest:
        bt = _do_backtest()
        print(f"\n📊 預設參數回測結果:")
        print(f"   終值: NT${bt['final_value']:,.0f} ({bt['total_return']:+.1%})")
        for yr, yd in bt["yearly"].items():
            print(f"   {yr}: {yd['total_ret']:+.1%}")

    if args.recommend:
        if dual_mode:
            for label, qm in [("排程A", qm_a), ("排程B", qm_b)]:
                today = datetime.now()
                active = today.month in qm
                flag = "🟢 本月檢討" if active else "📅 下月檢討（預先產出）"
                # 用該排程選股（即使非檢討月也預先產出）
                today = datetime.now()
                buy_date = None
                for sym, df in data.items():
                    d = df[df.index <= pd.Timestamp(today)].index[-1] if not df[df.index <= pd.Timestamp(today)].empty else None
                    if d and (buy_date is None or d > buy_date):
                        buy_date = d
                if buy_date is None:
                    print("  ❌ 無法取得最新資料", file=sys.stderr)
                    continue
                adj_p = dict(DEFAULT_PARAMS)
                if args.auto_momentum and market_data is not None and buy_date in market_data.index:
                    _detect_and_adjust(market_data, buy_date, adj_p, verbose=True)
                selected = pick_top_stocks(data, buy_date, adj_p, top_n)
                if args.output_env:
                    sched_label = label.replace("排程", "")
                    alloc = round(50.0 / top_n, 1)
                    print(f"#SCHEDULE={sched_label}")
                    for s in selected:
                        cfg = {"strategy": "keep_wait", "alloc": alloc, "max_entry_price": -1, "initial_buy_pct": 1.0}
                        print(f"PC_{s['symbol']}={json.dumps(cfg, separators=(',', ':'))}")
                else:
                    print(f"\n{'─'*60}\n📋 {label} {'/'.join(str(m) for m in qm)}月  {flag}\n{'─'*60}")
                    print(f"\n📅 基準日期: {buy_date.strftime('%Y-%m-%d')}")
                    print(f" {'代號':>5} {'名稱':>8} {'股價':>8} {'近季動能':>10}")
                    print(f" {'-'*5} {'-'*8} {'-'*8} {'-'*10}")
                    for s in selected:
                        name = POOL_LABELS.get(s["symbol"], "")
                        print(f" {s['symbol']:>5} {name:>8} NT${s['close']:>6,.0f} {s['momentum']:>+9.1%}")
        else:
            recommend_next_quarter(data, DEFAULT_PARAMS, top_n=top_n, mode=args.mode,
                                   auto_momentum=args.auto_momentum, market_data=market_data,
                                   output_env=args.output_env, schedule_label=args.schedule_label)


if __name__ == "__main__":
    main()
