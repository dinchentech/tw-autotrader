#!/usr/bin/env python3
"""全輪替 2015-2025 參數 Grid Sweep（2026-08-30，目前完整 TWSE 法人 + FinMind 原始價快取）

背景：2026-08-29 資料稽核後（TWSE 法人 2015 起完整、欄位動態定位），先前的掃描
（rotate_day_sweep 8/18、mindrawback_sweep 8/19、N 敏感性）皆為稽核前資料
（2015-2017 法人 pass-through）。本腳本用「目前 2015-2025 快取」以生產基準
（N=100、top4、月尾選股日、auto_momentum、預設權重、INST_CONFIRM=1 15d、MDB=20、含成本）
單維掃描五大維度，確認現有全替換參數為 2015-2025 最佳。

基準組合（= .env 現行設定）：
  pool_n=100 · top_n=4 · inst_days=15 · min_drawback=20(one) · DEFAULT_PARAMS
  （momentum_weight 2.0 / technical_weight 0.3 / stability_weight 0.5 /
    use_ma_filter True / min_price 5 / auto_momentum 1）

用法: python scripts/backtest_rotation_grid_sweep.py
輸出: results/rotation_grid_sweep_2015_2025.csv / .json
"""
import os, sys, json, bisect, math, itertools
sys.path.insert(0, "/home/frank/tw-autotrader")
os.chdir("/home/frank/tw-autotrader")
import pandas as pd
from core.cache_io import load_cache_or_raw
import core.inst_strategy_core as ic
sys.path.insert(0, "scripts")
import stock_selector_grid as ssg

START, END = "2015-01-01", "2025-12-31"
ssg.START_DATE = START
ssg.END_DATE = END
_TAG = "2015_2025"

# ── 生產基準 ────────────────────────────────────────────────
BASE = {
    "pool_n": 100, "top_n": 4, "inst_days": 15,
    "min_drawback": 20.0, "min_drawback_unlimited": False,
}
BASE_PARAMS = dict(ssg.DEFAULT_PARAMS)  # MW2.0 / TW0.3 / SW0.5 / MAF True / MP5

# ── 掃描維度（每維只變一個維度，其餘 = 基準）──────────────────
DIMENSIONS = [
    ("pool_n", [
        {"pool_n": 50}, {"pool_n": 100}, {"pool_n": 150},
        {"pool_n": 200}, {"pool_n": 300},
    ]),
    ("inst_days", [
        {"inst_days": 10}, {"inst_days": 15}, {"inst_days": 21}, {"inst_days": 30},
    ]),
    ("min_drawback", [
        {"min_drawback": 0.0}, {"min_drawback": 10.0},
        {"min_drawback": 20.0}, {"min_drawback": 30.0},
    ]),
    ("top_n", [
        {"top_n": 2}, {"top_n": 3}, {"top_n": 4}, {"top_n": 5}, {"top_n": 6},
    ]),
    ("weights", [
        {"momentum_weight": 1.0, "stability_weight": 0.0, "use_ma_filter": False},
        {"momentum_weight": 1.0, "stability_weight": 0.0, "use_ma_filter": True},
        {"momentum_weight": 1.0, "stability_weight": 0.5, "use_ma_filter": False},
        {"momentum_weight": 1.0, "stability_weight": 0.5, "use_ma_filter": True},
        {"momentum_weight": 2.0, "stability_weight": 0.0, "use_ma_filter": False},
        {"momentum_weight": 2.0, "stability_weight": 0.0, "use_ma_filter": True},
        {"momentum_weight": 2.0, "stability_weight": 0.5, "use_ma_filter": False},
        {"momentum_weight": 2.0, "stability_weight": 0.5, "use_ma_filter": True},
    ]),
]

print("═" * 72)
print(f"  全輪替參數 Grid Sweep · {START} ~ {END} · 目前快取（完整法人 2015 起）")
print(f"  基準: N=100 · top4 · 月尾選股日 · inst 15d · MDB=20(one) · 預設權重(MW2/SW0.5/MAF)")
print(f"═" * 72)

# ── 資料載入（一次）─────────────────────────────────────────
hist, _ = load_cache_or_raw("cache/inst_momentum/historical_shares.pkl")
union = sorted({k[0] for k in hist})
print(f"聯集池 {len(union)} 檔")
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

POOL_NS = sorted({c.get("pool_n", BASE["pool_n"]) for _, combos in DIMENSIONS for c in combos})
pools = {}
for n in POOL_NS:
    pools[n] = ic.build_quarterly_pool(hist_for_pool, all_data_pool, top_n=n)
    empty = sum(1 for p in pools[n].values() if not p)
    print(f"逐季池 N={n}: {len(pools[n])} 季, 空池 {empty} 季")

mkt = ssg.load_stock("0050")
mkt = mkt.rename(columns={"close": "close"}) if "close" not in mkt.columns else mkt

inst_conf = ssg.load_twse_inst_merged()
_INST_SORTED = sorted(inst_conf.keys())
print(f"法人確認: {len(_INST_SORTED)} 交易日 ({_INST_SORTED[0]} ~ {_INST_SORTED[-1]})")

# 加速 patch（與原始 inst_net_buy 語義等價：取 ≤end_date 最後 N 天累計淨買超）
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

# ── 指標計算（同 backtest_rotation_historical.py）────────────
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

# ── 組合產生（基準先跑作驗證）────────────────────────────────
combos = [("baseline", dict(BASE), dict(BASE_PARAMS))]
for dim, cs in DIMENSIONS:
    for c in cs:
        over = dict(BASE)
        over.update({k: v for k, v in c.items() if k in BASE})
        pw = dict(BASE_PARAMS)
        pw.update({k: v for k, v in c.items() if k not in BASE})
        combos.append((dim, over, pw))

years = (pd.Timestamp(END) - pd.Timestamp(START)).days / 365.25
results = []
for idx, (dim, over, params) in enumerate(combos):
    params = dict(params)
    pool_n = over["pool_n"]; top_n = over["top_n"]; inst_days = over["inst_days"]
    mdb = over["min_drawback"]
    label = "基準" if dim == "baseline" else dim
    print(f"\n[{idx+1}/{len(combos)}] {label} · pool={pool_n} top={top_n} inst={inst_days}d MDB={mdb} "
          f"MW={params['momentum_weight']} SW={params['stability_weight']} MAF={params['use_ma_filter']}", flush=True)
    try:
        bt = ssg.backtest_dual_quarterly(data, params, top_n=top_n, mode="momentum",
                                         auto_momentum=True, market_data=mkt,
                                         qm_a=(2, 5, 8, 11), qm_b=(3, 6, 9, 12),
                                         quarterly_pool=pools[pool_n],
                                         inst_conf=inst_conf, inst_days=inst_days,
                                         min_drawback=mdb,
                                         min_drawback_unlimited=False)
    except Exception as e:
        print(f"  ✗ 失敗: {e}", flush=True)
        continue

    ann = (bt["total_return"] + 1) ** (1 / years) - 1 if bt["total_return"] > -1 else -1
    ca = schedule_daily_curve(bt.get("records_a", []), data)
    cb = schedule_daily_curve(bt.get("records_b", []), data)
    ix = ca.index.union(cb.index)
    comb = (padded(ca, ix) + padded(cb, ix)) / 2.0
    comb = comb.loc[comb.first_valid_index():].ffill().dropna()
    sharpe, mdd, mdd_date = sharpe_mdd(comb)
    skip_a = [r["date"].strftime("%Y-%m-%d") for r in bt.get("records_a", []) if r.get("skipped")]
    skip_b = [r["date"].strftime("%Y-%m-%d") for r in bt.get("records_b", []) if r.get("skipped")]

    row = {
        "dim": label, "pool_n": pool_n, "top_n": top_n, "inst_days": inst_days,
        "min_drawback": mdb, "momentum_weight": params["momentum_weight"],
        "stability_weight": params["stability_weight"], "use_ma_filter": params["use_ma_filter"],
        "final_value": round(bt["final_value"]), "total_return": round(bt["total_return"], 4),
        "annualized": round(ann, 4), "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "max_drawdown": round(mdd, 4) if mdd is not None else None, "max_drawdown_date": mdd_date,
        "skipped_count": len(skip_a) + len(skip_b), "skipped_A": skip_a, "skipped_B": skip_b,
        "yearly": {k: round(v["total_ret"], 4) for k, v in bt["yearly"].items()},
    }
    results.append(row)
    print(f"  → 終值 NT${row['final_value']:>11,}  總報酬 {row['total_return']:+7.1%}  "
          f"年化 {row['annualized']:+6.1%}  夏普 {row['sharpe']}  回撤 {row['max_drawdown']:>7.1%} ({row['max_drawdown_date']})  "
          f"跳過 {row['skipped_count']} 次", flush=True)

os.makedirs("results", exist_ok=True)
rows_out = []
for r in results:
    rows_out.append({
        "dim": r["dim"], "pool_n": r["pool_n"], "top_n": r["top_n"], "inst_days": r["inst_days"],
        "min_drawback": r["min_drawback"], "momentum_weight": r["momentum_weight"],
        "stability_weight": r["stability_weight"], "use_ma_filter": r["use_ma_filter"],
        "final_value": r["final_value"], "total_return": r["total_return"],
        "annualized": r["annualized"], "sharpe": r["sharpe"], "max_drawdown": r["max_drawdown"],
        "max_drawdown_date": r["max_drawdown_date"], "skipped_count": r["skipped_count"],
        **{f"yr_{k}": v for k, v in sorted(r["yearly"].items())},
    })
pd.DataFrame(rows_out).to_csv(f"results/rotation_grid_sweep_{_TAG}.csv", index=False, encoding="utf-8-sig")
json.dump(results, open(f"results/rotation_grid_sweep_{_TAG}.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"\n✅ 已存: results/rotation_grid_sweep_{_TAG}.csv / .json")
