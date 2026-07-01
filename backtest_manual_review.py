"""
backtest_manual_review.py — 逐年人工選股回測（方案二）

使用 simulate_lumpsum 逐年跑，年底依檢討結果調整配置。

2022 初始池（防守型，熊尾選股）：
  0050 keep_wait  20%  — ETF 核心
  2330 keep_wait  15%  — TSMC 跌27%，巴菲特在買
  2454 keep_wait  15%  — 聯發科跌40%，PER~8x
  2881 vwap       10%  — 富邦金，金融配息
  2886 vwap       10%  — 兆豐金，防禦
  2382 keep_wait  15%  — 廣達跌16%，價值股低接
  2412 keep_wait  10%  — 中華電，熊市避風港
  00878 keep_wait   5%  — 高股息小部位

2023 調整（AI 確認後轉攻擊）：
  0050 keep_wait  20%  — 核心續抱
  2330 ma_cross   15%  — TSMC 漲一段，改順勢
  2454 keep_wait  15%  — keep_wait 還在低接範圍
  2881 vwap       10%
  2886 vwap       10%
  2382 breakout   15%  — AI 確認，改動能追進
  3034 keep_wait  10%  — 新增聯詠，半導體復甦
  00878 keep_wait   5%
  (剔除 2412：牛市持有防禦股=機會成本)

2024 調整（汰弱換強）：
  0050 keep_wait  20%  — 核心續抱
  2330 ma_cross   15%  — TSMC 續抱
  2454 keep_wait  15%  — 續抱
  2881 vwap       10%
  2382 breakout   10%
  3034 keep_wait  10%
  2882 vwap       10%  — 國泰金取代兆豐金
  00878 keep_wait   5%
  2317 ma_cross    5%  — 新增鴻海，AI 轉型
  (剔除 2886：2024 只漲 5% 遠落後同業)

2025：不調整，沿用 2024 配置。

使用方法：
  python backtest_manual_review.py
"""

import sys, os, argparse
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulate_portfolio import (
    simulate_lumpsum,
    get_data,
    fmt_ntd, fmt_pct,
)
from config.symbols import get_yahoo_suffix
from core.config_loader import load_portfolio_config

load_dotenv()

# ── Yearly configurations ──────────────────────────────────

YEARLY_CONFIGS = {
    # (year, config_list, description)
    2022: {
        "desc": "熊尾防守 — 低接為王、防禦優先",
        "config": [
            ("0050",  "keep_wait", 100000),
            ("2330",  "keep_wait",  75000),
            ("2454",  "keep_wait",  75000),
            ("2881",  "vwap",       50000),
            ("2886",  "vwap",       50000),
            ("2382",  "keep_wait",  75000),
            ("2412",  "keep_wait",  50000),
            ("00878", "keep_wait",  25000),
        ],
        "notes": "Fed升息17碼、台股-22%、半導體庫存修正。全部keep_wait低接，不用順勢策略",
    },
    2023: {
        "desc": "AI確認 — 轉攻！防禦股換飆股",
        "config": [
            ("0050",  "keep_wait", None),  # 20%
            ("2330",  "ma_cross",  None),  # 15%
            ("2454",  "keep_wait", None),  # 15%
            ("2881",  "vwap",      None),  # 10%
            ("2886",  "vwap",      None),  # 10%
            ("2382",  "breakout",  None),  # 15%
            ("3034",  "keep_wait", None),  # 10% — 新進
            ("00878", "keep_wait", None),  # 5%
        ],
        "alloc_pct": [20, 15, 15, 10, 10, 15, 10, 5],
        "changes": "剔除2412（牛市防禦股=機會成本）→ 新增3034聯詠（半導體復甦）",
        "notes": "NVIDIA+239%、廣達+234%。2382 keep_wait→breakout改追動能",
    },
    2024: {
        "desc": "汰弱留強 — 金融換最強、新增鴻海",
        "config": [
            ("0050",  "keep_wait", None),  # 20%
            ("2330",  "ma_cross",  None),  # 15%
            ("2454",  "keep_wait", None),  # 15%
            ("2881",  "vwap",      None),  # 10%
            ("2382",  "breakout",  None),  # 10%
            ("3034",  "keep_wait", None),  # 10%
            ("2882",  "vwap",      None),  # 10% — 新進
            ("00878", "keep_wait", None),  # 5%
            ("2317",  "ma_cross",  None),  # 5% — 新進
        ],
        "alloc_pct": [20, 15, 15, 10, 10, 10, 10, 5, 5],
        "changes": "剔除2886（兆豐金+5%遠落後同業+58%）→ 新增2882國泰金+2317鴻海",
        "notes": "台積電+84%創新高、台股連兩年+25%+。2886兆豐金明顯落後換2882國泰金",
    },
    2025: {
        "desc": "沿用（2024配置不變）",
        "config": None,  # 沿用2024
        "changes": "無調整",
        "notes": "台股已漲多，防禦心態但不主動減倉",
    },
}


def fmt_pct_header(val):
    if val >= 0:
        return f"+{val:.1%}"
    return f"{val:.1%}"


def main():
    parser = argparse.ArgumentParser(description="逐年人工選股回測")
    parser.add_argument("--start", type=int, default=2022)
    parser.add_argument("--end", type=int, default=2025)
    args = parser.parse_args()

    print("=" * 65)
    print("  逐年人工選股回測 — 方案二 Lumpsum NT$500,000")
    print(f"  {args.start} ~ {args.end}")
    print("=" * 65)

    # 預載資料
    all_candidates = set()
    for yr_data in YEARLY_CONFIGS.values():
        if yr_data["config"]:
            for sym, _, _ in yr_data["config"]:
                all_candidates.add(sym)
    print(f"\n📥 預載 {len(all_candidates)} 檔標的資料...")
    for sym in sorted(all_candidates):
        get_data(sym, start=f"{args.start - 1}-12-01")
    print("✅ 資料載入完成\n")

    # 逐年模擬
    current_capital = 500_000
    year_results = {}
    prev_config = None

    for year in range(args.start, args.end + 1):
        yr_data = YEARLY_CONFIGS[year]
        config_template = yr_data["config"] if yr_data["config"] is not None else prev_config
        alloc_pct = yr_data.get("alloc_pct")

        if config_template is None:
            print(f"⚠️  {year} 無配置")
            continue

        # 建構當年 config (用比例分配資金)
        if alloc_pct:
            total_pct = sum(alloc_pct)
            config = []
            allocated = 0
            for (sym, strat, _), pct in zip(config_template, alloc_pct):
                amt = round(current_capital * pct / total_pct)
                config.append((sym, strat, amt))
                allocated += amt
            # 補償誤差
            diff = round(current_capital) - allocated
            if diff != 0 and config:
                s, st, a = config[-1]
                config[-1] = (s, st, a + diff)
        else:
            config = config_template

        prev_config = config

        y_start = f"{year}-01-01"
        y_end   = f"{year}-12-31"

        print(f"\n{'─'*65}")
        print(f"📊 {year} 年 — {yr_data['desc']}")
        print(f"   💰 可用資金: NT${current_capital:,.0f}")
        print(f"   📋 調整: {yr_data.get('changes', '沿用')}")
        print(f"   📝 {yr_data.get('notes', '')}")
        print(f"{'─'*65}")

        result = simulate_lumpsum(
            config,
            start_date=y_start,
            end_date=y_end,
            initial_capital=current_capital,
            profit_roll_months=0,
            profit_roll_percentage=1.0,
        )

        monthly = result["monthly_records"]
        end_val = monthly[-1]["value"] if monthly else current_capital
        yr_pnl = end_val - current_capital
        yr_ret = yr_pnl / current_capital if current_capital > 0 else 0

        yr_info = {
            "capital": current_capital,
            "end_val": end_val,
            "pnl": yr_pnl,
            "return": yr_ret,
            "config": config,
            "desc": yr_data["desc"],
            "changes": yr_data.get("changes", ""),
            "notes": yr_data.get("notes", ""),
        }
        year_results[year] = yr_info

        print(f"\n   ✅ {year} 結果:")
        print(f"      年頭: NT${current_capital:,.0f}")
        print(f"      年底: NT${end_val:,.0f}")
        print(f"      損益: NT${yr_pnl:,.0f} ({yr_ret:+.1%})")

        current_capital = end_val

    # ── 總結 ──
    final_val = year_results[args.end]["end_val"]
    total_pnl = final_val - 500000
    total_ret = total_pnl / 500000

    print(f"\n{'='*65}")
    print(f"  📈 總績效 — 人工逐年選股 vs 固定池 vs 0050")
    print(f"{'='*65}")

    # 方案二原版 Lumpsum 對比
    orig_annual = [-12.0, 36.6, 30.6, 9.2]
    orig_final = 856900
    orig_pnl = orig_final - 500000
    orig_ret = orig_pnl / 500000

    bh_annual = [-7.1, 31.7, 43.8, 20.9]
    bh_final = 1015515
    bh_pnl = bh_final - 500000
    bh_ret = bh_pnl / 500000

    print(f"\n| 指標 | 固定池原版 | 0050買進持有 | 人工逐年檢討 |")
    print(f"|:---|:---:|:---:|:---:|")
    print(f"| 初始資金 | NT$500,000 | NT$500,000 | NT$500,000 |")
    print(f"| **終值** | NT${orig_final:,} | NT${bh_final:,} | NT${final_val:,.0f} |")
    print(f"| **總損益** | NT${orig_pnl:,} ({orig_ret:+.1%}) | NT${bh_pnl:,} ({bh_ret:+.1%}) | NT${total_pnl:,.0f} ({total_ret:+.1%}) |")

    print(f"\n| 年份 | 固定池原版 | 0050 BH | 人工逐年選股 |")
    print(f"|:---:|:---:|:---:|:---:|")
    for i, year in enumerate(range(args.start, args.end + 1)):
        yr = year_results[year]
        oa = orig_annual[i] / 100.0
        ba = bh_annual[i] / 100.0
        print(f"| {year} | {oa:+.1%} | {ba:+.1%} | {yr['return']:+.1%} |")

    print(f"\n  詳細配置演變:")
    for year in range(args.start, args.end + 1):
        yr = year_results[year]
        print(f"\n   {year}年 ({yr['desc']}):")
        if yr['changes']:
            print(f"     調整: {yr['changes']}")
        for sym, strat, alloc in yr["config"]:
            print(f"     {sym:>6s} | {strat:<10s} | NT${alloc:>7,}")
        print(f"     底值: NT${yr['end_val']:,.0f} ({yr['return']:+.1%})")

    # 輸出對比表格
    md = [
        "| 指標 | 固定池原版 | 0050買進持有 | 人工逐年檢討 |",
        "|:---|:---:|:---:|:---:|",
        f"| 初始資金 | NT$500,000 | NT$500,000 | NT$500,000 |",
        f"| **終值** | NT${orig_final:,} | NT${bh_final:,} | NT${final_val:,.0f} |",
        f"| **總損益** | NT${orig_pnl:,} ({orig_ret:+.1%}) | NT${bh_pnl:,} ({bh_ret:+.1%}) | NT${total_pnl:,.0f} ({total_ret:+.1%}) |",
        f"| 年化報酬 | +14.7% | +19.4% | — |",
        "",
        "| 年份 | 固定池原版 | 0050 BH | 人工逐年選股 |",
        "|:---:|:---:|:---:|:---:|",
    ]
    for i, year in enumerate(range(args.start, args.end + 1)):
        yr = year_results[year]
        oa = orig_annual[i] / 100.0
        ba = bh_annual[i] / 100.0
        md.append(f"| {year} | {oa:+.1%} | {ba:+.1%} | {yr['return']:+.1%} |")

    print("\n" + "\n".join(md))


if __name__ == "__main__":
    main()
