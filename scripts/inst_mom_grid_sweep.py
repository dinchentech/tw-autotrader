#!/usr/bin/env python3
"""法人動能參數 Grid Sweep（2026-08-29，正確 FinMind 原始價 + 完整 TWSE 法人）

背景：2026-08-28 資料稽核發現舊參數（LB10/FD120/BR0.08/TR20）是在「還原價污染 +
法人殘缺」的假資料上調出的，真實（原始價）2022-2026 為 -41.51%。本腳本用正確資料
重掃參數空間，找 2022-2026 窗口最佳組合。

用法：python scripts/inst_mom_grid_sweep.py [--quick]
輸出：results/inst_mom_grid_2022_2026.csv（含全部組合結果）
"""
import subprocess
import sys
import csv
import time
import itertools
from pathlib import Path

START, END = "2022-01-01", "2026-07-31"
RESULTS = Path("results/inst_mom_grid_2022_2026.csv")

# 參數空間（先做主要維度；--quick 縮小）
GRID = {
    "lookback": [5, 10, 15, 20],          # 創新高/MA 回溯
    "fish_days": [60, 90, 120, 150],      # 魚過濾回溯
    "buy_ratio": [0.03, 0.05, 0.08, 0.12],# 法人買超門檻
    "trailing": [10, 15, 20, 30],         # 移動停利 MA
}
BASE = ["--start", START, "--end", END, "--daily",
        "--lookback", "10", "--fish-days", "120",
        "--buy-ratio", "0.08", "--trailing", "20"]

def parse_report() -> dict:
    """從最新 回測_動能_2022-2026.MD 抓指標"""
    out = {}
    p = Path("回測_動能_2022-2026.MD")
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        for key in ("總報酬率", "勝率", "最大回撤", "總交易次數"):
            if line.startswith(f"| **{key}**"):
                val = line.split("|")[2].strip().replace("**", "").replace("%", "").replace(",", "")
                try:
                    out[key] = float(val)
                except ValueError:
                    pass
    return out

def main():
    quick = "--quick" in sys.argv
    keys = ["lookback", "fish_days", "buy_ratio", "trailing"]
    if quick:
        combos = [dict(zip(keys, c)) for c in itertools.product(
            [10, 20], [90, 120], [0.05, 0.08], [10, 20])]
    else:
        combos = [dict(zip(keys, c)) for c in itertools.product(
            *[GRID[k] for k in keys])]
    print(f"組合數: {len(combos)}（2022-2026、正確原始價）", flush=True)

    rows = []
    for i, combo in enumerate(combos):
        args = list(BASE)
        # 覆蓋 BASE
        for k, v in combo.items():
            flag = "--" + k.replace("_", "-")
            for j in range(len(args)):
                if args[j] == flag:
                    args[j + 1] = str(v)
        print(f"[{i+1}/{len(combos)}] {combo}", flush=True)
        try:
            r = subprocess.run(["python", "backtest_inst_momentum.py"] + args,
                               capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            print("  timeout", flush=True)
            continue
        stats = parse_report()
        stats.update(combo)
        rows.append(stats)
        print(f"  → {stats.get('總報酬率', '?')}% 勝率 {stats.get('勝率', '?')}%", flush=True)

    RESULTS.parent.mkdir(exist_ok=True)
    with RESULTS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["lookback", "fish_days", "buy_ratio",
                                          "trailing", "總報酬率", "勝率", "最大回撤", "總交易次數"])
        w.writeheader()
        for r in sorted(rows, key=lambda x: x.get("總報酬率", -999), reverse=True):
            w.writerow(r)
    print(f"\n完成 → {RESULTS}（依總報酬排序）", flush=True)

if __name__ == "__main__":
    main()
