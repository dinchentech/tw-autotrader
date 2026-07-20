#!/usr/bin/env python3
"""
selector_workflow.py — 四種選股工作流程回測比較

比較以下使用策略：
  A) 純動能（baseline）：stock_selector_grid 每季從固定池選 top 4
  B) 純催化劑：每季從固定池選 catalyst 最高分 4 檔
  C) 動能+催化劑混合：每季先用 catalyst 掃瞄，若發現高分新標的則加入候選池再選
  D) 動能核心+衛星：80% 資金給動能選股，20% 給 catalyst 最高分標的

Usage:
  python scripts/selector_workflow.py
  python scripts/selector_workflow.py --compare  (全部工作流程逐一執行並比較)
"""
import os, sys, time, itertools, json, pickle
from datetime import datetime
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
    CANDIDATE_POOL = [str(i) for i in range(1101, 9999)]

POOL_LABELS = {}
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

EXTRA_CANDIDATES = []

_cache = {}
def load_stock(symbol):
    if symbol in _cache:
        return _cache[symbol]
    yf_sym = f"{symbol}.TW"
    df = yf.download(yf_sym, start="2022-01-01", end="2026-12-31", auto_adjust=True, progress=False)
    if df.empty:
        _cache[symbol] = df
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    _cache[symbol] = df
    return df

def load_pool(symbols):
    data = {}
    for sym in symbols:
        df = load_stock(sym)
        if not df.empty:
            data[sym] = df
    return data

# ── 共用指標 ──
def trailing_ret(df, date, days):
    if date not in df.index:
        return None
    idx = df.index.get_loc(date)
    si = max(0, idx - days)
    sp = float(df.iloc[si]["close"])
    ep = float(df.iloc[idx]["close"])
    if sp <= 0:
        return None
    return (ep - sp) / sp

def catalyst_score(df, date):
    """潛力股模式評分（從 find_catalyst_stocks.py）"""
    n = 130
    if date not in df.index:
        return 0
    idx = df.index.get_loc(date)
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

def quarter_end_dates():
    start, end = "2022-01-01", "2025-12-31"
    bd = pd.bdate_range(start=start, end=end, freq="B")
    qs = {}
    for d in bd:
        if d.month in (3,6,9,12):
            qs[(d.year, d.month)] = d
    result = []
    for yr, mo in sorted(qs):
        cands = [d for d in bd if d.year == yr and d.month == mo]
        if cands:
            result.append(cands[-1])
    return result

def _snap(df, date):
    if date in df.index:
        return date
    avail = df[df.index <= date].index
    return avail[-1] if len(avail) > 0 else None

# ══════════════════════════════════════════════════════════════
# 四種工作流程
# ══════════════════════════════════════════════════════════════

def workflow_A_momentum(data, qd, params, top_n=4):
    """A: 純動能 — 從固定池選近季動能最強 N 檔"""
    m_days = params.get("momentum_days", 21)
    scored = []
    for sym, df in data.items():
        if qd not in df.index:
            continue
        ret = trailing_ret(df, qd, m_days)
        if ret is None or ret <= 0:
            continue
        scored.append((sym, ret, float(df.loc[qd, "close"])))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]


def workflow_B_catalyst(data, qd, top_n=4):
    """B: 純催化劑 — 選 catalyst 評分最高 N 檔"""
    scored = []
    for sym, df in data.items():
        if qd not in df.index:
            continue
        cs = catalyst_score(df, qd)
        if cs <= 0:
            continue
        scored.append((sym, cs, float(df.loc[qd, "close"])))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]


def workflow_C_catalyst_filter(data, core_data, qd, params, top_n=4, cat_threshold=0.4):
    """
    C: 動能+催化劑混合 — 先用 catalyst 掃全部（含額外套件），
    發現高分新標的則加入池中，再套動能選股。
    """
    # 在全部可選股票中計算 catalyst 分數
    all_data = {**data}
    # 掃描額外套件
    extra = load_pool(EXTRA_CANDIDATES)
    for sym, df in extra.items():
        all_data[sym] = df

    # 找出有潛力的新標的（catalyst 高分且不在核心池中）
    new_finds = []
    for sym, df in all_data.items():
        cs = catalyst_score(df, qd)
        if cs >= cat_threshold:
            new_finds.append((sym, cs))

    # 把高分新標的加入核心候選池
    enhanced_pool = dict(data)
    for sym, cs in new_finds:
        if sym not in enhanced_pool and sym in all_data:
            enhanced_pool[sym] = all_data[sym]

    return workflow_A_momentum(enhanced_pool, qd, params, top_n)


def workflow_D_core_satellite(data, qd, params, core_pct=0.8, top_n=4):
    """
    D: 核心+衛星 — top_n-1 由動能選出（core），1 檔由 catalyst 選出（satellite）。
    資金分配 core_pct% 給核心，其餘給衛星。
    """
    m_days = params.get("momentum_days", 21)
    # 動能選 core (top_n-1)
    scored = []
    for sym, df in data.items():
        if qd not in df.index:
            continue
        ret = trailing_ret(df, qd, m_days)
        if ret is None or ret <= 0:
            continue
        scored.append((sym, ret, float(df.loc[qd, "close"])))
    scored.sort(key=lambda x: x[1], reverse=True)
    core = scored[:top_n-1] if len(scored) >= top_n-1 else scored

    # 從剩餘選項中 catalyst 最高分的當衛星
    remaining = [s for s in data if s not in [c[0] for c in core]]
    sat = []
    if remaining:
        sat_scored = [(sym, catalyst_score(data[sym], qd)) for sym in remaining]
        sat_scored.sort(key=lambda x: x[1], reverse=True)
        if sat_scored and sat_scored[0][1] > 0:
            sat = [sat_scored[0]]
    return {
        "holdings": [(s[0], "core", s[1]) for s in core] + [(s[0], "satellite", s[1]) for s in sat],
        "labels": [s[0] for s in core] + [s[0] for s in sat],
        "core_pct": core_pct,
    }


# ══════════════════════════════════════════════════════════════
# 回測引擎
# ══════════════════════════════════════════════════════════════

ETF_SYMBOLS = {"0050", "0056", "00632R", "00646", "006208", "00878"}
STOCK_TAX = 0.003      # 證交稅 股票 0.3%
ETF_TAX = 0.001        # 證交稅 ETF 0.1%
COMMISSION = 1         # 零股手續費 NT$1（整股 0.1425%，但模擬中 shares 為零股）

def backtest_workflow(workflow_name, data, params, top_n=4, verbose=False):
    """通用回測框架，可帶入不同的 work function"""
    qds = quarter_end_dates()
    capital = 500000.0
    records = []
    year_vals = {}
    last_val = capital
    current_labels = []

    wf_map = {
        "A": (workflow_A_momentum, {}),
        "B": (workflow_B_catalyst, {}),
        "C": (workflow_C_catalyst_filter, {"params": params, "top_n": top_n}),
        "D": (workflow_D_core_satellite, {"params": params, "top_n": top_n}),
    }

    for qi, qd in enumerate(qds):
        is_last = (qi == len(qds) - 1)

        if is_last:
            # 最後一季：評價現有持股（不賣出，不扣稅）
            nxt_val = 0.0
            for label in current_labels:
                sym = label.split(":")[0]
                if sym not in data:
                    continue
                df = data[sym]
                vd = _snap(df, qd)
                if vd is None:
                    continue
                px = float(df.loc[vd, "close"])
                shares = last_shares.get(label, 0)
                nxt_val += shares * px
            q_ret = (nxt_val - capital) / capital if capital > 0 else 0
            if verbose:
                print(f"  {qd.date()} → 評價 → {q_ret:+.2%} (${nxt_val:,.0f})")
            capital = nxt_val
            records.append({"date": qd, "return": q_ret, "value": capital})
            break

        # 執行工作流程
        if workflow_name == "A":
            chosen = workflow_A_momentum(data, qd, params, top_n)
            labels = [(s[0], s[1]) for s in chosen]
        elif workflow_name == "B":
            chosen = workflow_B_catalyst(data, qd, top_n)
            labels = [(s[0], s[1]) for s in chosen]
        elif workflow_name == "C":
            chosen = workflow_C_catalyst_filter(data, {}, qd, params, top_n)
            labels = [(s[0], s[1]) for s in chosen]
        elif workflow_name == "D":
            wf = workflow_D_core_satellite(data, qd, params, top_n=top_n)
            labels_w = wf["holdings"]
            labels = [(s[0], s[1]) for s in labels_w]

        if not labels:
            continue

        current_labels = [l[0] for l in labels]
        n_h = len(labels)
        alloc = capital / n_h
        nxt_val = 0.0
        last_shares = {}

        for sym, score in labels:
            if sym not in data:
                continue
            df = data[sym]
            bd = _snap(df, qd)
            if bd is None:
                continue
            nq = qds[qi + 1]
            sd = _snap(df, nq)
            if sd is None or sd <= bd:
                continue
            bp = float(df.loc[bd, "close"])
            if bp <= 0:
                continue
            # 買入：NT$1 零股手續費
            available = alloc - COMMISSION
            shares = available / bp if bp > 0 else 0
            last_shares[sym] = shares
            sp = float(df.loc[sd, "close"])
            # 賣出：證交稅（股票0.3%/ETF 0.1%）+ NT$1 零股手續費
            gross = shares * sp
            tax_rate = ETF_TAX if sym in ETF_SYMBOLS else STOCK_TAX
            tax = gross * tax_rate
            net = gross - tax - COMMISSION
            nxt_val += net

        q_ret = (nxt_val - capital) / capital if capital > 0 else 0
        if verbose:
            print(f"  {qd.date()} → {current_labels} → {q_ret:+.2%} (${nxt_val:,.0f})")
        capital = nxt_val
        records.append({"date": qd, "holdings": current_labels, "return": q_ret, "value": capital})

    final_val = capital
    total_ret = (final_val - 500000) / 500000
    return {"records": records, "final_value": final_val, "total_return": total_ret}


# ══════════════════════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("📊 四種選股工作流程回測比較（2022~2025）")
    print("=" * 70)
    print()
    print(f"{'工作流程':<20} {'終值':>14} {'總報酬':>10} {'年化':>8} {'特點'}")
    print(f"{'-'*20} {'-'*14} {'-'*10} {'-'*8} {'-'*30}")

    params_best = {
        "momentum_days": 21, "momentum_weight": 2.0,
        "technical_weight": 0.3, "stability_weight": 0.5,
    }

    data = load_pool(CANDIDATE_POOL)
    print(f"\n📥 載入 {len(data)} 檔核心股票")

    workflows = [
        ("A｜純動能", "A",
         "每季從16檔固定池選\n近21日動能最強4檔"),
        ("B｜純催化劑", "B",
         "每季從固定池選\n潛力股模式評分最高4檔"),
        ("C｜動能+催化劑", "C",
         "先掃全部股票找催化劑標的\n加入候選池後用動能選"),
        ("D｜核心+衛星", "D",
         "資金80%給動能選3檔\n20%給催化劑最高分1檔"),
    ]

    results = []
    for wf_name, wf_key, wf_desc in workflows:
        bt = backtest_workflow(wf_key, data, params_best, top_n=4, verbose=False)
        final = bt["final_value"]
        ret = bt["total_return"]
        cagr = (final / 500000) ** (1 / 4) - 1
        results.append((wf_name, final, ret, cagr, wf_desc))
        print(f"{wf_name:<20} NT${final:>8,.0f} {ret:>+9.1%} {cagr:>+7.1%} {wf_desc}")
        print()

    # 排序
    results.sort(key=lambda r: r[1], reverse=True)
    
    print(f"\n{'='*70}")
    print(f"🏆 最佳工作流程：{results[0][0]} — NT${results[0][1]:,.0f} ({results[0][2]:+.1%})")
    print(f"{'='*70}")
    print()
    
    # 逐流程詳細回測
    print("\n🔍 各流程詳細季度表現：")
    for wf_name, wf_key, _ in [
        ("A｜純動能", "A", ""),
        ("B｜純催化劑", "B", ""),
        ("D｜核心+衛星", "D", ""),
    ]:
        print(f"\n── {wf_name} ──")
        bt = backtest_workflow(wf_key, data, params_best, top_n=4, verbose=True)
        print(f"   終值: NT${bt['final_value']:,.0f} ({bt['total_return']:+.1%})")

    print()
    print("=" * 70)
    print("💡 使用建議")
    print("=" * 70)
    print()
    print("  日常使用方式：")
    print("  ┌─────────────────────────────────────────────────────┐")
    print("  │ 1. 每月跑一次 find_catalyst_stocks.py               │")
    print("  │    掃全市場，看有沒有新冒出的翻倍潛力股            │")
    print("  │ 2. 若發現高分標的（score≥60），加到候選池          │")
    print("  │ 3. 每季初跑 stock_selector_grid.py                  │")
    print("  │    用 momentum 從候選池選出本季要持有的 4 檔       │")
    print("  │ 4. 把選股結果清單手動調整到 .env PC_ 設定          │")
    print("  └─────────────────────────────────────────────────────┘")
    print()
    print("  ⚠️ 每個工具各有定位：")
    print("  - stock_selector_grid.py =「這季要抱什麼？」（核心持股調整）")
    print("  - find_catalyst_stocks.py =「最近有什麼新機會？」（機會掃描）")
    print()


if __name__ == "__main__":
    main()
