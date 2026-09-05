#!/usr/bin/env python3
"""scripts/blend_rotation_vs_modelC.py — 全輪替 × 模型C 混合比例分析（2015-2025）

把兩條獨立「腿」的日頻權益曲線，依權重 w（全輪替）與 1-w（模型C）混合為單一帳戶，
計算組合的總報酬/年化/最大回撤/夏普，讓使用者調整兩類標的（中小飆股 vs 權值/防守）比例。

輸入（每日曲線，皆已正規化到 NT$500,000 起始）：
  - 全輪替: results/rotate_mode5_2015_2025_daily_equity.csv (equity_rotate5)
  - 模型C(正常/高穩定/高獲利): results/daily_<group>.csv
"""
import pandas as pd, numpy as np, math, os

os.makedirs("results", exist_ok=True)
ROT = pd.read_csv("results/rotate_mode5_2015_2025_daily_equity.csv", index_col=0, parse_dates=True)["equity_rotate5"]
ROT = ROT.dropna()
ROT_MULT = ROT / 500000.0
IDX = ROT_MULT.index
YEAR = (IDX[-1] - IDX[0]).days / 365.25

CGROUPS = {"正常": "results/daily_normal.csv",
           "高穩定": "results/daily_stable.csv",
           "高獲利": "results/daily_high_profit.csv"}


def load_c(path):
    s = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0].dropna()
    return (s / 500000.0).reindex(IDX).ffill()


def perf(s):
    s = s.dropna()
    rets = s.pct_change().dropna()
    sd = rets.std(ddof=1)
    sharpe = float(rets.mean() / sd * math.sqrt(252)) if sd and sd > 0 else float("nan")
    mdd = float(((s - s.cummax()) / s.cummax()).min())
    return sharpe, mdd


def metrics(s):
    total = s.iloc[-1] - 1.0
    ann = (s.iloc[-1] ** (1 / YEAR) - 1.0) if s.iloc[-1] > 0 else -1.0
    sh, mdd = perf(s)
    return total, ann, mdd, sh


print(f"期間: {IDX[0].date()} ~ {IDX[-1].date()} ({YEAR:.1f}年)  全輪替 vs 模型C 各組\n")
print("| w_全輪替 | 混合對象 | 總報酬 | 年化 | 最大回撤 | 夏普 |")
print("|:---:|:---:|:---:|:---:|:---:|:---:|")
for cname, cpath in CGROUPS.items():
    cm = load_c(cpath)
    for w in [1.0, 0.8, 0.6, 0.5, 0.4, 0.2, 0.0]:
        comb = w * ROT_MULT + (1 - w) * cm
        total, ann, mdd, sh = metrics(comb)
        print(f"| {w:.1f} | {cname} | {total*100:+.1f}% | {ann*100:+.1f}% | {mdd*100:+.1f}% | {sh:.2f} |")
    print("| --- | --- | --- | --- | --- | --- |")

# 單獨對照
print("\n(單獨) 全輪替 100%:", end=" ")
t, a, m, s = metrics(ROT_MULT)
print(f"總報酬{t*100:+.1f}% 年化{a*100:+.1f}% MDD{m*100:+.1f}% 夏普{s:.2f}")
