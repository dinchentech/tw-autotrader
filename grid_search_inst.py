"""
grid_search_inst.py — 法人抬轎策略參數搜尋
找出 2022~2025 每年都獲利的最佳參數
"""
import sys, os, pickle, time
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
sys.path.insert(0, ".")
import core.inst_strategy_core as inst_core
from backtest_inst_momentum import (
    finmind_login, get_all_stock_ids, download_price_data,
    fetch_twse_inst_data, merge_twse_inst, precompute_fish_scores,
    screen_fish_qualified, simulate, compute_metrics,
    generate_monthly_breakdown,
    START_DATE, END_DATE,
    MAX_STOCKS, TOP_N, MIN_VOLUME_SHARES, BUY_RATIO_THRESHOLD,
    BUY_COST, SELL_COST,
    PROFIT_ROLL_MONTHS, PROFIT_ROLL_PERCENTAGE,
    INITIAL_CAPITAL,
)

# ── 固定參數 ──────────────────────────────────────
FIXED_START = "2022-01-01"
FIXED_END   = "2025-12-31"

# ── Grid 範圍 ──────────────────────────────────────
STOP_LOSS_LIST    = [0.05, 0.07, 0.10]   # -5%, -7%, -10%
TRAILING_MA_LIST  = [5, 10, 20, 30]       # 移動停利 MA 週期
LOOKBACK_LIST     = [20, 30]              # 創新高 + MA 回溯期

# ── 載入資料（一次搞完）─────────────────────────────
print("=" * 60)
print("📊 Grid Search — 法人抬轎策略（2022-2025）")
print("=" * 60)

dl = finmind_login()
stock_ids = get_all_stock_ids(dl)
print(f"\n📥 讀取 {len(stock_ids)} 檔價格資料...")
all_data = {}
for i, sid in enumerate(stock_ids):
    df = download_price_data(dl, sid)
    if not df.empty:
        all_data[sid] = df
    if (i + 1) % 100 == 0:
        print(f"   {i+1}/{len(stock_ids)}")

all_dates = sorted(set(
    d.date() for df in all_data.values() if not df.empty for d in df["date"]
))
print(f"✅ {len(all_data)} 檔有資料，共 {len(all_dates)} 交易日")

twse_raw = fetch_twse_inst_data(set(all_dates))
all_data = merge_twse_inst(all_data, twse_raw)

fish_scores = precompute_fish_scores(all_data)
print(f"✅ 法人低吃分數預計算完成")

# ── 預建魚過濾觀察池（固定 score=4, days=60）─────────
print(f"\n🔍 預建魚過濾觀察池（score≥4.0, days=60）...")
start_dt = datetime.strptime(FIXED_START, "%Y-%m-%d").date()
fridays = sorted(set(d for d in all_dates if d.weekday() == 4))
fridays = [d for d in fridays if d >= start_dt]
fish_qualified = {}
for fd in fridays:
    q = screen_fish_qualified(all_data, pd.Timestamp(fd), fish_scores, 60, 4.0)
    if q:
        fish_qualified[fd] = q
print(f"   {len(fridays)} 週中 {len(fish_qualified)} 週有觀察池")

print(f"\n🚀 Grid Search 開始（共 {len(STOP_LOSS_LIST)*len(TRAILING_MA_LIST)*len(LOOKBACK_LIST)} 組）")
print(f"   固定: fish_score=4.0, fish_days=60, M=0, P=100%")
print()

results = []

for sl in STOP_LOSS_LIST:
    for tm in TRAILING_MA_LIST:
        for lb in LOOKBACK_LIST:
            # ── 更新全域參數 ──
            inst_core.STOP_LOSS       = sl
            inst_core.TRAILING_PERIOD = tm
            inst_core.LOOKBACK        = lb

            # 重新計算 MA（因 LOOKBACK 改了）
            ma_lb_col = f"ma{lb}"
            ma_tm_col = f"ma{tm}"
            for sid, df in all_data.items():
                if df.empty or len(df) < max(lb, tm) + 5:
                    continue
                df[ma_lb_col] = df["close"].rolling(lb).mean()
                df[ma_tm_col] = df["close"].rolling(tm).mean()

            # ── 執行模擬 ──
            t0 = time.time()
            result = simulate(
                all_data,
                candidates=None,
                fish_qualified=fish_qualified,
                daily=False,
                auto_capital=False,
                auto_cap_months=3,
                auto_cap_ratio=1.0,
                profit_roll_months=0,
                profit_roll_percentage=1.0,
                all_dates=all_dates,
            )
            elapsed = time.time() - t0

            metrics = compute_metrics(result)
            monthly = generate_monthly_breakdown(result["equity_curve"], INITIAL_CAPITAL)

            # ── 各年報酬 ──
            def year_ret(year):
                rows = [r for r in monthly if r["month"].startswith(year)]
                if not rows:
                    return None
                return rows[-1]["end"] - rows[0]["start"]

            yr = {}
            all_positive = True
            for y in ["2022","2023","2024","2025"]:
                r = year_ret(y)
                yr[y] = r
                if r is None or r <= 0:
                    all_positive = False

            ret = metrics["total_return"]
            tag = "✅" if all_positive else "  "

            print(f"{tag} SL={sl:.0%} TM={tm:2d} LB={lb:2d} | "
                  f"2022:{yr['2022']:+8.0f} 2023:{yr['2023']:+8.0f} "
                  f"2024:{yr['2024']:+8.0f} 2025:{yr['2025']:+8.0f} | "
                  f"總報酬:{ret:+6.2%} | {elapsed:.1f}s")

            results.append({
                "sl": sl, "tm": tm, "lb": lb,
                "yr": yr, "ret": ret,
                "metrics": metrics, "monthly": monthly,
                "result": result,
                "all_positive": all_positive,
            })

print()
print("=" * 60)
print("🏆 每年都獲利的組合（依總報酬排序）：")
print("=" * 60)
winners = [r for r in results if r["all_positive"]]
winners.sort(key=lambda x: x["ret"], reverse=True)
for i, r in enumerate(winners[:10]):
    print(f"  {i+1}. SL={r['sl']:.0%} TM={r['tm']:2d} LB={r['lb']:2d} | "
          f"2022:{r['yr']['2022']:+8.0f} 2023:{r['yr']['2023']:+8.0f} "
          f"2024:{r['yr']['2024']:+8.0f} 2025:{r['yr']['2025']:+8.0f} | "
          f"總報酬:{r['ret']:+6.2%}")

if winners:
    best = winners[0]
    print()
    print("📌 最佳參數：")
    print(f"   Stop Loss:   {best['sl']:.0%}")
    print(f"   Trailing MA: MA{best['tm']}")
    print(f"   Lookback:    {best['lb']} 日")
    print(f"   總報酬:       {best['ret']:+6.2%}")
    print(f"   各年損益:     2022 NT${best['yr']['2022']:+,.0f}  "
          f"2023 NT${best['yr']['2023']:+,.0f}  "
          f"2024 NT${best['yr']['2024']:+,.0f}  "
          f"2025 NT${best['yr']['2025']:+,.0f}")