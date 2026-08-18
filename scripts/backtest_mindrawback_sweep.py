#!/usr/bin/env python3
"""MIN_DRAW_BACK 掃描回測 — 全輪替重大回撤保護（2026-08-18）

用法: python scripts/backtest_mindrawback_sweep.py [start] [end]
例:   python scripts/backtest_mindrawback_sweep.py            # 2015-01-01 ~ 2025-12-31

邏輯（與實盤規格一致）：
  MIN_DRAW_BACK>0 時，換股日若帳戶總回撤（自歷史峰值）> 門檻 → 該季不賣不買、續抱原持股；
  若下一季回撤仍超標 → 照常換股（最多延長一季）。0 = 停用（基線）。

設定與回測一致：ROTATE_MODE=5 雙排程（A:2/5/8/11、B:3/6/9/12）、月尾選股日（N=-1）、
誠實池前 100、每排程 4 檔、auto_momentum、MA 過濾、stability 0.5、法人確認 21d、含交易成本。

輸出: results/mindrawback_sweep_{start}_{end}.csv / .json
"""
import os, sys, json, bisect, math
sys.path.insert(0, "/home/frank/tw-autotrader")
os.chdir("/home/frank/tw-autotrader")
import pandas as pd
from core.cache_io import load_cache_or_raw
import core.inst_strategy_core as ic
sys.path.insert(0, "scripts")
import stock_selector_grid as ssg

START = sys.argv[1] if len(sys.argv) > 1 else "2015-01-01"
END = sys.argv[2] if len(sys.argv) > 2 else "2025-12-31"
POOL_N = int(os.getenv("SWEEP_POOL_N", "100"))
TOP_N = 4
ssg.START_DATE = START
ssg.END_DATE = END
_PERIOD_TAG = f"{START[:4]}_{END[:4]}"
THRESHOLDS = [0, 10, 20, 30]
COMBOS = [(0, "one"), (10, "one"), (20, "one"), (30, "one"),
          (10, "unlimited"), (20, "unlimited"), (30, "unlimited")]

print(f"═" * 70)
print(f"  MIN_DRAW_BACK 掃描 · {START} ~ {END} · 誠實池前 {POOL_N} · 月尾選股日 · 門檻 {THRESHOLDS}")
print(f"  one=最多延長一季 · unlimited=無限期延後")
print(f"═" * 70)

hist, _ = load_cache_or_raw("cache/inst_momentum/historical_shares.pkl")
union = sorted({k[0] for k in hist})
data = {}
for sid in union:
    df = ssg.load_stock(sid)
    if not df.empty and len(df) > 60:
        data[sid] = df
print(f"價格載入: {len(data)} 檔")

hist_for_pool = {(sid, q): v for (sid, q), v in hist.items()}
all_data_pool = {}
for sid, df in data.items():
    d2 = df.reset_index()
    d2 = d2.rename(columns={d2.columns[0]: "date"})
    all_data_pool[sid] = d2
pools = ic.build_quarterly_pool(hist_for_pool, all_data_pool, top_n=POOL_N)

mkt = ssg.load_stock("0050")
mkt = mkt.rename(columns={"close": "close"}) if "close" not in mkt.columns else mkt

params = dict(ssg.DEFAULT_PARAMS)

inst_conf = ssg.load_twse_inst_merged()
_INST_SORTED = sorted(inst_conf.keys())

def fast_inst_net_buy(inst_data, sid, end_date, days=21):
    sid = str(sid)
    end_str = pd.Timestamp(end_date).strftime("%Y-%m-%d")
    lo = bisect.bisect_right(_INST_SORTED, end_str)
    recent = _INST_SORTED[max(0, lo - days):lo]
    total = 0.0
    found = False
    for d in recent:
        row = inst_data[d].get(sid)
        if row is not None:
            total += row[0] - row[1]
            found = True
    return total if found else None
ssg.inst_net_buy = fast_inst_net_buy

_MKT_DAYS = pd.DatetimeIndex(sorted(mkt.index))

def month_end_dates(start, end, quarter_months, _n=-1):
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    months = {}
    for d in _MKT_DAYS:
        if d < s or d > e:
            continue
        months.setdefault((d.year, d.month), []).append(d)
    out = []
    for (yr, mo), days in sorted(months.items()):
        if mo in quarter_months and days:
            out.append(days[-1])
    return out

_orig_qed = ssg.quarter_end_dates

def schedule_daily_curve(records, data, commission=ssg.COMMISSION_RATE, initial=500000.0):
    segs = []
    for i, rec in enumerate(records):
        qd, chosen = rec["date"], rec["holdings"]
        if i == len(records) - 1:
            segs.append(pd.Series({qd: rec["value"]}))
            continue
        nxt = records[i + 1]["date"]
        capital = records[i - 1]["value"] if i > 0 else initial
        alloc = capital / len(chosen) if chosen else 0.0
        parts = []
        for sym in chosen:
            if sym not in data:
                continue
            df = data[sym]
            buy_date = ssg._snap_date(df, qd)
            if buy_date is None:
                continue
            buy_px = float(df.loc[buy_date, "close"])
            if buy_px <= 0:
                continue
            shares = alloc / (buy_px * (1 + commission))
            sub = df.loc[buy_date:nxt, "close"] * shares
            sub = sub[sub.index < nxt]
            parts.append(sub)
        if parts:
            segs.append(pd.concat(parts).groupby(level=0).sum())
    if not segs:
        return pd.Series(dtype=float)
    curve = pd.concat(segs).sort_index()
    return curve[~curve.index.duplicated(keep="last")]

def sharpe_mdd(curve, rf=0.0, periods=252):
    curve = curve.dropna()
    rets = curve.pct_change().dropna()
    if len(rets) < 3:
        return None, None, None
    ex = rets - rf / periods
    sd = ex.std(ddof=1)
    sharpe = float(ex.mean() / sd * math.sqrt(periods)) if sd > 0 else float("nan")
    run_max = curve.cummax()
    dd = curve / run_max - 1
    mdd = float(dd.min())
    mdd_date = dd.idxmin().strftime('%Y-%m-%d') if len(dd) else None
    return sharpe, mdd, mdd_date

def padded(s, idx, initial=500000.0):
    if len(s) == 0:
        return pd.Series(initial, index=idx)
    r = s.reindex(idx)
    r.loc[r.index < s.index[0]] = initial
    return r.ffill()

results = []
for mdb, mode in COMBOS:
    def qed(start=None, end=None, quarter_months=None):
        if quarter_months is None:
            quarter_months = (3, 6, 9, 12)
        if start is None:
            start = ssg.START_DATE
        if end is None:
            end = ssg.END_DATE
        return month_end_dates(start, end, quarter_months)
    ssg.quarter_end_dates = qed
    try:
        bt = ssg.backtest_dual_quarterly(data, params, top_n=TOP_N, mode="momentum",
                                         auto_momentum=True, market_data=mkt,
                                         qm_a=(2, 5, 8, 11), qm_b=(3, 6, 9, 12),
                                         quarterly_pool=pools,
                                         inst_conf=inst_conf, inst_days=21,
                                         min_drawback=mdb,
                                         min_drawback_unlimited=(mode == "unlimited"))
    finally:
        ssg.quarter_end_dates = _orig_qed

    years = (pd.Timestamp(END) - pd.Timestamp(START)).days / 365.25
    ann = (bt["total_return"] + 1) ** (1 / years) - 1 if bt["total_return"] > -1 else -1

    ca = schedule_daily_curve(bt.get("records_a", []), data)
    cb = schedule_daily_curve(bt.get("records_b", []), data)
    idx = ca.index.union(cb.index)
    comb = (padded(ca, idx) + padded(cb, idx)) / 2.0
    comb = comb.loc[comb.first_valid_index():].ffill().dropna()
    sharpe, mdd, mdd_date = sharpe_mdd(comb)

    skip_a = [r["date"].strftime("%Y-%m-%d") for r in bt.get("records_a", []) if r.get("skipped")]
    skip_b = [r["date"].strftime("%Y-%m-%d") for r in bt.get("records_b", []) if r.get("skipped")]

    row = {
        "min_drawback": mdb,
        "mode": mode,
        "final_value": round(bt["final_value"]),
        "total_return": round(bt["total_return"], 4),
        "annualized": round(ann, 4),
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "max_drawdown": round(mdd, 4) if mdd is not None else None,
        "max_drawdown_date": mdd_date,
        "skipped_count": len(skip_a) + len(skip_b),
        "skipped_A": skip_a,
        "skipped_B": skip_b,
        "yearly": {k: round(v["total_ret"], 4) for k, v in bt["yearly"].items()},
    }
    results.append(row)
    print(f"MDB={mdb:<3} {mode:<10} 終值 NT${row['final_value']:>11,}  總報酬 {row['total_return']:+7.1%}  "
          f"年化 {row['annualized']:+6.1%}  夏普 {row['sharpe']}  回撤 {row['max_drawdown']:>7.1%} ({row['max_drawdown_date']})  "
          f"跳過換股 {row['skipped_count']} 次 (A:{len(skip_a)} B:{len(skip_b)})")
    if skip_a or skip_b:
        print(f"      A 跳過: {skip_a}")
        print(f"      B 跳過: {skip_b}")

os.makedirs("results", exist_ok=True)
rows_out = []
for r in results:
    rows_out.append({
        "MIN_DRAW_BACK": r["min_drawback"], "mode": r["mode"], "final_value": r["final_value"],
        "total_return": r["total_return"], "annualized": r["annualized"],
        "sharpe": r["sharpe"], "max_drawdown": r["max_drawdown"],
        "max_drawdown_date": r["max_drawdown_date"], "skipped_count": r["skipped_count"],
        **{f"yr_{k}": v for k, v in sorted(r["yearly"].items())},
    })
pd.DataFrame(rows_out).to_csv(f"results/mindrawback_sweep_{_PERIOD_TAG}.csv",
                              index=False, encoding="utf-8-sig")
json.dump(results, open(f"results/mindrawback_sweep_{_PERIOD_TAG}.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"\n✅ 已存: results/mindrawback_sweep_{_PERIOD_TAG}.csv / .json")
