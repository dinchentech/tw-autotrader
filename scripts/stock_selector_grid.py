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
import pickle
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── 候選股票池（市值前 150 大） ─────────────────────────
STOCK_NO = int(os.getenv("STOCK_NO", "150"))
CANDIDATE_POOL = []
CAP_RANKING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cache", "inst_momentum", "mcap_ranking.pkl")
if os.path.exists(CAP_RANKING):
    ranked = pickle.loads(open(CAP_RANKING, "rb").read())
    CANDIDATE_POOL = [s for s in ranked if s.isdigit() and len(s) == 4][:STOCK_NO]
if not CANDIDATE_POOL:
    # 無排名檔時的 fallback
    CANDIDATE_POOL = [str(i) for i in range(1101, 9999)]

POOL_LABELS = {}

START_DATE = "2022-01-01"
END_DATE = "2025-12-31"

# ══════════════════════════════════════════════════════════════
# 資料載入
# ══════════════════════════════════════════════════════════════

_cache = {}
def load_stock(symbol: str) -> pd.DataFrame:
    if symbol in _cache:
        return _cache[symbol]
    yf_sym = f"{symbol}.TW" if symbol.isdigit() else f"{symbol}.TW"
    df = yf.download(yf_sym, start=START_DATE, end="2026-12-31", auto_adjust=True, progress=False)
    if df.empty:
        _cache[symbol] = df
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
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

    # 動能分數
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

    # 綜合
    momentum_val = max(0, m_ret)
    total = (momentum_val * m_w + tech_score * t_w + stability * s_w * 0.01 + cat_val * c_w)

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

def quarter_end_dates(start="2022-01-01", end="2025-12-31"):
    from pandas.tseries.offsets import QuarterEnd
    """用 pandas QuarterEnd 正確取得季度末日期"""
    all_dates = pd.bdate_range(start=start, end=end, freq="B")
    trading_set = set(all_dates)
    quarters = set()
    for d in all_dates:
        if d.month in (3, 6, 9, 12):
            quarters.add((d.year, d.month))
    result = []
    for yr, mo in sorted(quarters):
        # 該月所有交易日中最後一個
        candidates = [d for d in all_dates if d.year == yr and d.month == mo]
        if candidates:
            result.append(candidates[-1])
    return result


def _snap_date(df, target):
    """將日期對齊到 df 中 <= target 的最後交易日"""
    if target in df.index:
        return target
    avail = df[df.index <= target].index
    if len(avail) > 0:
        return avail[-1]
    # 沒有更早的日期，用第一個交易日
    return df.index[0] if len(df.index) > 0 else None


def backtest_selector(data, params, top_n=4, verbose=False):
    """
    回測每季選股績效。
    每季末用 params 選股 → 持有到下季末 → 計算報酬。
    最後一季只評價不買賣。
    """
    import math
    quarter_dates = quarter_end_dates()
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
        selected = pick_top_stocks(data, buy_date_q, params, top_n)
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
        if qd.month == 12:
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
# Grid Search
# ══════════════════════════════════════════════════════════════

GRID_PARAMS = {
    "momentum_days": [21, 63, 125],
    "momentum_weight": [0.5, 1.0, 2.0],
    "technical_weight": [0.0, 0.3, 0.5, 1.0],
    "stability_weight": [0.0, 0.3, 0.5],
    "catalyst_weight": [0.0, 0.3, 0.5, 1.0],
    "use_ma_filter": [False, True],
    "min_price": [5, 10],
}

DEFAULT_PARAMS = {
    "momentum_days": 21,
    "momentum_weight": 2.0,
    "technical_weight": 0.3,
    "stability_weight": 0.0,
    "catalyst_weight": 0.0,
    "use_ma_filter": False,
    "min_price": 5,
}


def run_grid_search(data, top_n=4):
    """Grid Search 所有參數組合"""
    keys = list(GRID_PARAMS.keys())
    values = list(GRID_PARAMS.values())
    combinations = list(itertools.product(*values))
    total = len(combinations)

    print(f"\n🔍 Grid Search — {len(keys)} 個維度 × {total} 種組合")
    print(f"   選股池: {len(data)} 檔 | 每季選 top {top_n} 檔")
    print(f"   回測期間: {START_DATE} ~ {END_DATE}")
    print(f"   {'='*55}")

    results = []
    t0 = time.time()

    for ci, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        bt = backtest_selector(data, params, top_n, verbose=False)
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


def recommend_next_quarter(data, params, top_n=4, mode="momentum"):
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
        print("❌ 無法取得最新資料")
        return

    mode_label = {"momentum": "純動能", "catalyst": "純催化劑", "core-satellite": "核心+衛星"}
    print(f"\n📅 基準日期: {best_date.strftime('%Y-%m-%d')}  模式: {mode_label.get(mode, mode)}")

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
        selected = pick_top_stocks(data, best_date, params, top_n)

    if not selected:
        print("❌ 無法選出推薦持股")
        return

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


# ══════════════════════════════════════════════════════════════
# HTML 報告
# ══════════════════════════════════════════════════════════════

def generate_html_report(best_results, data, best_params, output_path):
    """產出 HTML 報告"""
    bt = backtest_selector(data, best_params, top_n=4, verbose=False)

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
    parser = argparse.ArgumentParser(description="每季選股 Grid Search")
    parser.add_argument("--grid", action="store_true", help="執行 Grid Search 找最佳參數")
    parser.add_argument("--backtest", action="store_true", help="用預設參數回測")
    parser.add_argument("--recommend", action="store_true", help="輸出下一季推薦持股")
    parser.add_argument("--report", action="store_true", help="產出 HTML 報告")
    parser.add_argument("--top-n", type=int, default=4, help="每季選股數 (default: 4)")
    parser.add_argument("--mode", choices=["momentum", "catalyst", "core-satellite"], default="momentum",
                        help="選股模式：momentum(純動能) / catalyst(純催化劑) / core-satellite(核心+衛星)")
    args = parser.parse_args()

    print("=" * 60)
    print("📊 每季選股神器 — Stock Selector Grid")
    print("=" * 60)

    # 自訂候選股（從 custom_pool.txt）— 詢問使用者是否合併
    custom = _load_custom_pool()
    if custom:
        print(f"\n📋 偵測到自訂候選股: {', '.join(custom)}")
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

    if args.report or (not args.grid and not args.backtest and not args.recommend and not args.report):
        print("\n🔍 預設執行 Grid Search...")
        results = run_grid_search(data, top_n=args.top_n)
        print_top_results(results, n=10)

        best_params = results[0]["params"]
        print(f"\n🏆 最佳參數: {best_params}")
        print(f"   終值: NT${results[0]['final_value']:,.0f} ({results[0]['total_return']:+.1%})")

        out = os.path.join(os.path.dirname(__file__), "..", "img", "stock_selector_grid_report.html")
        generate_html_report(results, data, best_params, out)
        recommend_next_quarter(data, best_params, top_n=args.top_n, mode=args.mode)

    if args.grid:
        results = run_grid_search(data, top_n=args.top_n)
        print_top_results(results, n=10)

        best_params = results[0]["params"]
        out = os.path.join(os.path.dirname(__file__), "..", "img", "stock_selector_grid_report.html")
        generate_html_report(results, data, best_params, out)
        recommend_next_quarter(data, best_params, top_n=args.top_n, mode=args.mode)

    if args.backtest:
        bt = backtest_selector(data, DEFAULT_PARAMS, top_n=args.top_n, verbose=True)
        print(f"\n📊 預設參數回測結果:")
        print(f"   終值: NT${bt['final_value']:,.0f} ({bt['total_return']:+.1%})")
        for yr, yd in bt["yearly"].items():
            print(f"   {yr}: {yd['total_ret']:+.1%}")

    if args.recommend:
        recommend_next_quarter(data, DEFAULT_PARAMS, top_n=args.top_n, mode=args.mode)


if __name__ == "__main__":
    main()
