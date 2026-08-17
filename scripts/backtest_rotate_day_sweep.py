#!/usr/bin/env python3
"""選股日 N=-1..12 掃描回測 — ROTATE_MODE=5 雙排程（A: 2/5/8/11, B: 3/6/9/12），50 萬資本

用法: python scripts/backtest_rotate_day_sweep.py [start] [end]
例:   python scripts/backtest_rotate_day_sweep.py            # 2022-01-01 ~ 2025-12-31
      python scripts/backtest_rotate_day_sweep.py 2015-01-01 2025-12-31

與 backtest_rotation_historical.py 同資料層/同設定（誠實池 POOL_N=100、每排程 4 檔、
auto_momentum、MA 過濾、stability 0.5、min_price 5、INST_CONFIRM=1 法人確認 21d、計入交易成本），
唯一變因 = 「選股日」：N=-1 = 每月最後交易日（實盤 ROTATE_TRADING_DAY_N 預設，2026-08-18 起），
N=1..12 = 每月第 N 個交易日。選股日行事曆取自實際價格資料（0050 的交易日曆）。

輸出:
  results/rotate_day_sweep_{start}_{end}.csv    — 每 N 一列（獲利指標 + 年度報酬 + 選股多樣性）
  results/rotate_day_sweep_{start}_{end}.json   — 完整結果（含逐年、Sharpe/MDD、兩兩選股相似度）
  results/rotate_day_sweep_holdings_{start}_{end}.json — 每 N 的逐季持股（選股差異用）
"""
import os, sys, json, bisect, math
sys.path.insert(0, "/home/frank/tw-autotrader")
os.chdir("/home/frank/tw-autotrader")
import pandas as pd
from core.cache_io import load_cache_or_raw
import core.inst_strategy_core as ic
sys.path.insert(0, "scripts")
import stock_selector_grid as ssg

START = sys.argv[1] if len(sys.argv) > 1 else "2022-01-01"
END = sys.argv[2] if len(sys.argv) > 2 else "2025-12-31"
POOL_N = int(os.getenv("SWEEP_POOL_N", "100"))
TOP_N = 4
ssg.START_DATE = START
ssg.END_DATE = END
_PERIOD_TAG = f"{START[:4]}_{END[:4]}"

print(f"═" * 70)
print(f"  選股日 N=-1..12 掃描 · ROTATE_MODE=5 · {START} ~ {END} · 誠實池前 {POOL_N} · 每排程 {TOP_N} 檔")
print(f"═" * 70)

# ── 資料載入（同 backtest_rotation_historical.py）──────────────────
hist, _ = load_cache_or_raw("cache/inst_momentum/historical_shares.pkl")
union = sorted({k[0] for k in hist})
print(f"聯集池 {len(union)} 檔, 逐季前 {POOL_N}")

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
print(f"逐季池: {len(pools)} 季")

mkt = ssg.load_stock("0050")
mkt = mkt.rename(columns={"close": "close"}) if "close" not in mkt.columns else mkt

params = dict(ssg.DEFAULT_PARAMS)  # 生產設定

# 法人確認濾網（生產設定 INST_CONFIRM=1）
inst_conf = ssg.load_twse_inst_merged()
inst_days = 21
# 加速版 inst_net_buy：預排序 + bisect（語義與原版完全一致）
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

# ── 選股日行事曆：以實際價格資料（0050）的交易日為準 ──────────────
_MKT_DAYS = pd.DatetimeIndex(sorted(mkt.index))

def nth_trading_dates(start, end, quarter_months, n):
    """每月第 n 個實際交易日（取自價格行事曆）；n=-1 = 每月最後交易日。"""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    months = {}
    for d in _MKT_DAYS:
        if d < s or d > e:
            continue
        months.setdefault((d.year, d.month), []).append(d)
    out = []
    for (yr, mo), days in sorted(months.items()):
        if mo in quarter_months and days:
            out.append(days[-1] if n == -1 else days[n - 1])
    return out

# ── 日頻權益曲線（同 backtest_rotation_historical.py，複製）─────────
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
        return None, None
    ex = rets - rf / periods
    sd = ex.std(ddof=1)
    sharpe = float(ex.mean() / sd * math.sqrt(periods)) if sd > 0 else float("nan")
    run_max = curve.cummax()
    mdd = float(((curve - run_max) / run_max).min())
    return sharpe, mdd

def padded(s, idx, initial=500000.0):
    if len(s) == 0:
        return pd.Series(initial, index=idx)
    r = s.reindex(idx)
    r.loc[r.index < s.index[0]] = initial
    return r.ffill()

# ── 掃描 ─────────────────────────────────────────────────────────
_orig_qed = ssg.quarter_end_dates
results = []
holdings_all = {}

def run_n(label, qed_fn):
    def qed(start=None, end=None, quarter_months=None):
        if quarter_months is None:
            quarter_months = (3, 6, 9, 12)
        if start is None:
            start = ssg.START_DATE
        if end is None:
            end = ssg.END_DATE
        return qed_fn(start, end, quarter_months)
    ssg.quarter_end_dates = qed
    try:
        bt = ssg.backtest_dual_quarterly(data, params, top_n=TOP_N, mode="momentum",
                                         auto_momentum=True, market_data=mkt,
                                         qm_a=(2, 5, 8, 11), qm_b=(3, 6, 9, 12),
                                         quarterly_pool=pools,
                                         inst_conf=inst_conf, inst_days=inst_days)
    finally:
        ssg.quarter_end_dates = _orig_qed

    years = (pd.Timestamp(END) - pd.Timestamp(START)).days / 365.25
    ann = (bt["total_return"] + 1) ** (1 / years) - 1 if bt["total_return"] > -1 else -1

    # 組合權益曲線（兩排程平均，與 final_val 語義一致）
    ca = schedule_daily_curve(bt.get("records_a", []), data)
    cb = schedule_daily_curve(bt.get("records_b", []), data)
    idx = ca.index.union(cb.index)
    comb = (padded(ca, idx) + padded(cb, idx)) / 2.0
    comb = comb.loc[comb.first_valid_index():].ffill().dropna()
    sharpe, mdd = sharpe_mdd(comb)

    # 選股統計：兩排程所有季的持股
    all_hold = [h for rec in (bt.get("records_a", []) + bt.get("records_b", []))
                for h in (rec.get("holdings") or [])]
    distinct = sorted(set(all_hold))
    holdings_all[label] = {
        "A": [{"date": r["date"].strftime("%Y-%m-%d"), "holdings": r["holdings"]}
              for r in bt.get("records_a", [])],
        "B": [{"date": r["date"].strftime("%Y-%m-%d"), "holdings": r["holdings"]}
              for r in bt.get("records_b", [])],
    }

    row = {
        "N": label,
        "final_value": round(bt["final_value"]),
        "total_return": round(bt["total_return"], 4),
        "annualized": round(ann, 4),
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "max_drawdown": round(mdd, 4) if mdd is not None else None,
        "distinct_stocks": len(distinct),
        "yearly": {k: round(v["total_ret"], 4) for k, v in bt["yearly"].items()},
        "quarters_A": len(bt.get("records_a", [])),
        "quarters_B": len(bt.get("records_b", [])),
    }
    results.append(row)
    disp = "月末" if label == "-1" else f"N={label}"
    print(f"{disp:<5} 終值 NT${row['final_value']:>10,}  總報酬 {row['total_return']:+7.1%}  "
          f"年化 {row['annualized']:+6.1%}  夏普 {row['sharpe']}  回撤 {row['max_drawdown']:.1%}  "
          f"選股 {row['distinct_stocks']} 檔")

for n in [-1] + list(range(1, 13)):
    run_n(str(n), lambda s, e, qm, _n=n: nth_trading_dates(s, e, qm, _n))

# ── 選股差異：兩兩比較（同排程同季）────────────────────────────
def quarters_of(label, sched):
    return [r["holdings"] for r in holdings_all[label][sched] if r["holdings"]]

def jaccard(a, b):
    if not a and not b:
        return 1.0
    u = set(a) | set(b)
    return len(set(a) & set(b)) / len(u) if u else 1.0

labels = ["-1"] + [str(n) for n in range(1, 13)]
agreement = {}
for i, li in enumerate(labels):
    for lj in labels[i + 1:]:
        ja = [jaccard(a, b) for a, b in zip(quarters_of(li, "A"), quarters_of(lj, "A"))]
        jb = [jaccard(a, b) for a, b in zip(quarters_of(li, "B"), quarters_of(lj, "B"))]
        jall = ja + jb
        agreement[f"{li}vs{lj}"] = round(sum(jall) / len(jall), 4) if jall else None

# ── 輸出 ─────────────────────────────────────────────────────────
os.makedirs("results", exist_ok=True)
rows_out = []
for r in results:
    rows_out.append({
        "N": r["N"], "final_value": r["final_value"], "total_return": r["total_return"],
        "annualized": r["annualized"], "sharpe": r["sharpe"], "max_drawdown": r["max_drawdown"],
        "distinct_stocks": r["distinct_stocks"],
        **{f"yr_{k}": v for k, v in sorted(r["yearly"].items())},
    })
df = pd.DataFrame(rows_out)
df.to_csv(f"results/rotate_day_sweep_{_PERIOD_TAG}.csv", index=False, encoding="utf-8-sig")
json.dump({"results": results, "agreement": agreement},
          open(f"results/rotate_day_sweep_{_PERIOD_TAG}.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
json.dump(holdings_all, open(f"results/rotate_day_sweep_holdings_{_PERIOD_TAG}.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

print(f"\n✅ 已存: results/rotate_day_sweep_{_PERIOD_TAG}.csv / .json / holdings_{_PERIOD_TAG}.json")
