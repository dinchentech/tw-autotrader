"""
grid_fish_params.py — 魚過濾每日篩選 grid search（純快取，免 FinMind API）
"""
import sys, os, pickle, time
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
sys.path.insert(0, ".")

import core.inst_strategy_core as inst_core
from backtest_inst_momentum import (
    simulate, compute_metrics, generate_monthly_breakdown,
    precompute_fish_scores, INITIAL_CAPITAL,
)

FIXED_START, FIXED_END = "2022-01-01", "2025-12-31"
inst_core.STOP_LOSS, inst_core.TRAILING_PERIOD, inst_core.LOOKBACK = 0.10, 10, 20

FISH_DAYS_LIST = [20, 30, 45, 60, 90, 120]
FISH_SCORE_LIST = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
SL_LIST = [0.07, 0.10]
TOP_N = 270

PRICE_DIR = Path("cache/inst_momentum/price")
TWSE_CACHE = Path("cache/inst_momentum/2022/twse_inst_2022-01-01_2025-12-31.pkl")
MCAP_RANKING = Path("cache/inst_momentum/mcap_ranking.pkl")

print("🐟 Grid Search — 每日魚過濾, top 270, 純快取")
t0 = time.time()

ranked = pickle.loads(MCAP_RANKING.read_bytes())
ranked = [s for s in ranked if s.isdigit() and len(s) == 4][:TOP_N]

all_data = {}
for sid in ranked:
    f = PRICE_DIR / f"{sid}.pkl"
    if not f.exists():
        continue
    df = pickle.loads(f.read_bytes())
    if isinstance(df, pd.DataFrame) and not df.empty and "date" in df.columns:
        if df["date"].min() <= pd.Timestamp(FIXED_START) and df["date"].max() >= pd.Timestamp(FIXED_END):
            all_data[sid] = df.copy()

twse = pickle.loads(TWSE_CACHE.read_bytes())
for sid, df in all_data.items():
    for i, row in df.iterrows():
        ds = row["date"].date().isoformat()
        ib, iss = twse.get(ds, {}).get(sid, (0, 0))
        df.at[i, "inst_buy"], df.at[i, "inst_sell"] = int(ib), int(iss)
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma10"] = df["close"].rolling(10).mean()

all_dates = sorted(set(d.date() for df in all_data.values() for d in df["date"]))
start_dt = datetime.strptime(FIXED_START, "%Y-%m-%d").date()
daily_dates = sorted(set(d for d in all_dates if d >= start_dt))
daily_str_set = set(d.strftime("%Y-%m-%d") for d in daily_dates)

print(f"✅ {len(all_data)} stocks, {len(all_dates)} dates, load={time.time()-t0:.0f}s")

fs0 = time.time()
fish_scores = precompute_fish_scores(all_data)
print(f"✅ fish_scores: {len(fish_scores)} stocks, {time.time()-fs0:.0f}s")

rm0 = time.time()
rolling_max = {}
for sid, scores in fish_scores.items():
    sd = sorted(scores.keys())
    if not sd: continue
    sv = np.array([scores[d] for d in sd])
    sdi = pd.to_datetime(sd)
    for fd in FISH_DAYS_LIST:
        rm = pd.Series(sv, index=sdi).rolling(f"{fd}D", min_periods=1).max()
        dmap = {}
        for dd in rm.index:
            ds = dd.strftime("%Y-%m-%d")
            if ds in daily_str_set:
                dmap[ds] = float(rm.loc[dd]) if not pd.isna(rm.loc[dd]) else 0.0
        rolling_max[(sid, fd)] = dmap
print(f"✅ rolling_max: {len(rolling_max)} entries, {time.time()-rm0:.0f}s")

total_results = len(FISH_DAYS_LIST) * len(FISH_SCORE_LIST) * len(SL_LIST) + len(SL_LIST)
print(f"🚀 {total_results} combos...\n")

total, results = 0, []
for fish_days in FISH_DAYS_LIST:
    for fish_score in FISH_SCORE_LIST:
        for sl in SL_LIST:
            cs = time.time()
            fish_qualified = {}
            for dd in daily_dates:
                ds = dd.strftime("%Y-%m-%d")
                q = set()
                for sid in all_data:
                    if rolling_max.get((sid, fish_days), {}).get(ds, 0.0) >= fish_score:
                        q.add(sid)
                if q:
                    fish_qualified[dd] = q

            inst_core.STOP_LOSS = sl
            result = simulate(all_data, candidates=None, fish_qualified=fish_qualified,
                              daily=False, auto_capital=False, auto_cap_months=3,
                              auto_cap_ratio=1.0, profit_roll_months=0,
                              profit_roll_percentage=1.0, all_dates=all_dates)
            metrics = compute_metrics(result)
            monthly = generate_monthly_breakdown(result["equity_curve"], INITIAL_CAPITAL)
            def yr(y):
                rows = [r for r in monthly if r["month"].startswith(y)]
                if not rows: return None
                return rows[-1]["end"] - rows[0]["start"]
            yr_v = {y: yr(y) for y in ["2022","2023","2024","2025"]}
            ret = metrics["total_return"]
            total += 1
            print(f"[{total:3d}] d={fish_days:3d} s={fish_score:.1f} sl={sl:.0%} | "
                  f"ret={ret:+6.2%} wr={metrics['win_rate']:.2%} dd={metrics['max_drawdown_pct']:.2%} "
                  f"tr={metrics['total_trades']:3d} qd={len(fish_qualified):3d} | "
                  f"22:{yr_v['2022']:+7.0f} 23:{yr_v['2023']:+7.0f} 24:{yr_v['2024']:+7.0f} 25:{yr_v['2025']:+7.0f} | {time.time()-cs:.0f}s")
            results.append(dict(days=fish_days, score=fish_score, sl=sl, yr=yr_v,
                                ret=ret, wr=metrics["win_rate"], dd=metrics["max_drawdown_pct"],
                                trades=metrics["total_trades"], has_fish=True, qd=len(fish_qualified)))

for sl in SL_LIST:
    inst_core.STOP_LOSS = sl
    result = simulate(all_data, candidates=None, fish_qualified=None, daily=False,
                      auto_capital=False, auto_cap_months=3, auto_cap_ratio=1.0,
                      profit_roll_months=0, profit_roll_percentage=1.0, all_dates=all_dates)
    metrics = compute_metrics(result)
    monthly = generate_monthly_breakdown(result["equity_curve"], INITIAL_CAPITAL)
    def yr(y):
        rows = [r for r in monthly if r["month"].startswith(y)]
        if not rows: return None
        return rows[-1]["end"] - rows[0]["start"]
    yr_v = {y: yr(y) for y in ["2022","2023","2024","2025"]}
    total += 1
    print(f"[{total:3d}] NO FISH          sl={sl:.0%} | "
          f"ret={metrics['total_return']:+6.2%} wr={metrics['win_rate']:.2%} dd={metrics['max_drawdown_pct']:.2%} "
          f"tr={metrics['total_trades']:3d} | "
          f"22:{yr_v['2022']:+7.0f} 23:{yr_v['2023']:+7.0f} 24:{yr_v['2024']:+7.0f} 25:{yr_v['2025']:+7.0f}")
    results.append(dict(days=0, score=0., sl=sl, yr=yr_v, ret=metrics["total_return"],
                        wr=metrics["win_rate"], dd=metrics["max_drawdown_pct"],
                        trades=metrics["total_trades"], has_fish=False, qd=0))

print()
print("=" * 70)
print("🏆 TOP 20 總報酬")
results.sort(key=lambda x: x["ret"], reverse=True)
for i, r in enumerate(results[:20]):
    l = f"d={r['days']:3d} s={r['score']:.1f}" if r['has_fish'] else "NO_FISH"
    print(f"  {i+1:2d}. {l} sl={r['sl']:.0%} | ret={r['ret']:+6.2%} wr={r['wr']:.2%} dd={r['dd']:.2%} tr={r['trades']}")

print()
print("🏆 各年皆正")
ap = [r for r in results if r['has_fish'] and all(r["yr"][y] is not None and r["yr"][y] > 0 for y in ["2022","2023","2024","2025"])]
ap.sort(key=lambda x: x["ret"], reverse=True)
for i, r in enumerate(ap[:10]):
    print(f"  {i+1:2d}. d={r['days']:3d} s={r['score']:.1f} sl={r['sl']:.0%} | ret={r['ret']:+6.2%} wr={r['wr']:.2%} dd={r['dd']:.2%}")

if ap:
    b = ap[0]
    print(f"\n📌 BEST: days={b['days']} score={b['score']:.1f} sl={b['sl']:.0%} → {b['ret']:+.2%}")
else:
    print("\n❌ 無各年皆正組合")
    b = results[0]
    print(f"📌 TOP: days={b['days']} score={b['score']:.1f} sl={b['sl']:.0%} → {b['ret']:+.2%}")