"""
backtest_yearly_review.py — 逐年檢討回測（不能有事後之明）
=======================================================

核心問題：方案一/二固定 8 檔池子跑 4 年，7/8 標的虧損，
只有 2454 keep_wait (+73%) 撐住整體報酬。

如果每年底做一次「5 分鐘三題檢討」，用「年末可得的資訊」
決定哪些 strategy-stock combo 該換掉，效果會如何？

逐年檢討規則（機械式，無事後之明）：
  Rule 0（部署時即可判斷）：ETF bollinger → ETF keep_wait
     （ETF 本質是長期持有，bollinger 均值回歸 = 在多頭市場提早出場）
  Rule 1：連虧 2 年（用該標的年報酬率衡量）→ 剔除
  Rule 2：替換標的 = 候選池中前一年報酬最高且不在池內的股票
  Rule 3：新進標的策略分派 — 半導體/高科技 → keep_wait，
     金融 → vwap，其他 → ma_cross
  Rule 4：候選池 = 市值前 30 大台股（公開資訊，年末可查）

架構：每年跑一段獨立的 simulate_lumpsum（年末清倉結算）。
  - DCA：年初清倉，以（上年底價值 + 12×月投入）重配。
    這等同「每年結算一次 + 繼續定投」，跟原版 simulate_dca 
    的差別在於我們每年做檢討所以要清算重配。
  - Lumpsum：年初清倉，以年末結算金額重配次年資金。
  - 檢討用「標的年報酬率」（單純價格漲跌幅），
    不依賴 Position 物件（每年都是新的）

使用方法：
  python backtest_yearly_review.py                 # 全部（DCA + Lumpsum）
  python backtest_yearly_review.py --mode dca       # 方案一（每月2萬）
  python backtest_yearly_review.py --mode lumpsum   # 方案二（50萬）
"""

import os, sys, argparse
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulate_portfolio import (
    simulate_lumpsum,
    get_data,
    COMMISSION_RATE,
)
from config.symbols import get_yahoo_suffix
from core.config_loader import load_portfolio_config

# ── 候選池（市值前 30 大，投資人年末可查到的公開資訊）──
CANDIDATE_POOL = [
    "2330", "2454", "3711", "3034", "2379", "2382", "6669", "5274",  # 半導體
    "2881", "2886", "2882", "2884", "2885", "2891",                  # 金融
    "2317", "2357", "2412", "2308", "2303", "2327",                   # 電子
    "6505", "1301", "1303", "1326",                                    # 傳產
    "3045", "4904",                                                    # 電信
    "0050", "006208", "00878", "0056",                                # ETF
]

ETF_SYMBOLS = {"0050", "0056", "006208", "00878", "00632R", "00646"}


# ── 初次配置修正（部署時即判斷，非事後之明）───────

def apply_initial_fixes(config_list):
    """
    Rule 0: ETF + bollinger 是結構性錯配（部署時就知道）→ 改 keep_wait。
    回傳修正後的 config_list。
    """
    fixed = []
    for sym, strat, alloc in config_list:
        if strat == "bollinger" and sym in ETF_SYMBOLS:
            print(f"   ⚡ Rule 0: {sym} bollinger→keep_wait（ETF不適合均值回歸）")
            fixed.append((sym, "keep_wait", alloc))
        else:
            fixed.append((sym, strat, alloc))
    return fixed


# ── 年度報酬率（單純價格，年末可查）─────────────────

def get_annual_return(symbol: str, year: int) -> float:
    """某標的某年度價格報酬率（年末可得的公開資訊）"""
    df = get_data(symbol, start=f"{year-1}-12-01")
    if df.empty:
        return None  # 無資料
    year_df = df[(df.index >= f"{year}-01-01") & (df.index <= f"{year}-12-31")]
    if len(year_df) < 2:
        return None
    start_price = float(year_df.iloc[0]["close"])
    end_price = float(year_df.iloc[-1]["close"])
    if pd.isna(start_price) or pd.isna(end_price) or start_price <= 0:
        return None
    return (end_price - start_price) / start_price


# ── 年末檢討規則 ────────────────────────────────────

# 追蹤每個 (symbol, strategy) 組合的逐年報酬
_combo_returns = {}  # {(sym, strat): {year: return}}


def record_combo_returns(config_list, year):
    """記錄每個組合的年度報酬（用標的價格漲跌幅代表）"""
    for sym, strat, _ in config_list:
        ret = get_annual_return(sym, year)
        key = (sym, strat)
        if key not in _combo_returns:
            _combo_returns[key] = {}
        _combo_returns[key][year] = ret


def apply_review_rules(config_list, year):
    """
    年末檢討（只看年末可得的資訊）。

    Rule 1: (sym, strat) 連虧 2 年 → 剔除，找候選池最佳替代
    Rule 2: 替換標的 = 候選池中前一年報酬最高且不在池內者
    Rule 3: 新進標的策略分派
    """
    current_symbols = {c[0] for c in config_list}
    new_config = []
    changes = []

    for sym, strat, alloc in config_list:
        key = (sym, strat)
        history = _combo_returns.get(key, {})
        ret_this = history.get(year)
        ret_prev = history.get(year - 1)

        # Rule 1: 連虧 2 年（需要有 2 年數據才能判斷）
        if (ret_this is not None and ret_prev is not None
                and ret_this < 0 and ret_prev < 0):
            changes.append((sym, strat, alloc,
                           f"連虧2年: {year-1}={ret_prev:+.1%}, {year}={ret_this:+.1%}"))
            continue  # 剔除

        new_config.append((sym, strat, alloc))

    # 替換被剔除的標的
    for sym, strat, alloc, reason in changes:
        replacement = find_replacement(current_symbols | {c[0] for c in new_config},
                                        year)
        if replacement:
            new_sym, new_strat = replacement
            new_config.append((new_sym, new_strat, alloc))
            print(f"   🔄 {sym}({strat}) → {new_sym}({new_strat}) | {reason}")
        else:
            print(f"   ⚠️ 無法替換 {sym}({strat}) | {reason}")

    return new_config, changes


def find_replacement(existing_symbols, year):
    """從候選池選前一年報酬最高且不重複的標的"""
    best_sym = None
    best_ret = -999.0
    for sym in CANDIDATE_POOL:
        if sym in existing_symbols:
            continue
        ret = get_annual_return(sym, year)
        if ret is None:
            continue
        if ret > best_ret:
            best_ret = ret
            best_sym = sym

    if best_sym is None:
        return None

    # Rule 3: 策略分派
    if best_sym in ETF_SYMBOLS:
        return (best_sym, "keep_wait")
    elif best_sym in ("2330", "2454", "3034", "6669", "5274", "2382", "3711", "2379"):
        return (best_sym, "keep_wait")
    elif best_sym in ("2881", "2882", "2886", "2884", "2885", "2891"):
        return (best_sym, "vwap")
    else:
        return (best_sym, "ma_cross")


# ── 模擬引擎 ────────────────────────────────────────

def run_yearly_review_dca(initial_config, start_year=2022, end_year=2025,
                          monthly_total=20000, profit_roll_months=0,
                          profit_roll_percentage=1.0) -> dict:
    """
    逐年檢討 DCA 回測。
    
    架構：每年跑一段 simulate_lumpsum，年初清倉結算。
    這等同「每年底做檢討 → 清算全部持倉 → 次年重新部署」。
    
    年初可用資金 = 上年底組合價值 + 12 × 月投入
    （第一年 = 12 × 月投入，因為年初無持倉）
    
    原版 simulate_dca 是每月撥款、持倉跨年，不做檢討。
    這裡的差別是：每年做檢討所以要清算重配，這導致
    「年均值回歸型策略」（bollinger/vwap）無法跨年持有待反彈，
    但 keep_wait 和 ma_cross 不受影響。
    """
    global _combo_returns
    _combo_returns = {}
    current_config = list(initial_config)
    year_results = {}
    total_injected = 0.0
    current_capital = 0.0  # 第一年無初始持倉

    for year in range(start_year, end_year + 1):
        y_start = f"{year}-01-01"
        y_end   = f"{year}-12-31"

        # 年初可用 = 上年底價值 + 今年 12 個月 DCA
        year_dca = monthly_total * 12
        current_capital += year_dca
        total_injected += year_dca

        # 重新分配資金（按 alloc 佔比分配 current_capital）
        total_alloc_amt = sum(c[2] for c in current_config)
        if total_alloc_amt > 0 and current_capital > 0:
            rescaled = []
            for sym, strat, alloc in current_config:
                new_alloc = round(current_capital * alloc / total_alloc_amt)
                rescaled.append((sym, strat, new_alloc))
            diff = round(current_capital) - sum(c[2] for c in rescaled)
            if diff != 0 and rescaled:
                s, st, a = rescaled[-1]
                rescaled[-1] = (s, st, a + diff)
        else:
            rescaled = list(current_config)

        print(f"\n{'='*60}")
        print(f"📊 {year} 年 — DCA 逐年檢討")
        print(f"   可用資金: NT${current_capital:,.0f}（含今年DCA NT${year_dca:,.0f}）")
        print(f"   配置: {[(s,st,a) for s,st,a in rescaled]}")
        print(f"{'='*60}")

        result = simulate_lumpsum(
            rescaled,
            start_date=y_start,
            end_date=y_end,
            initial_capital=current_capital,
            profit_roll_months=profit_roll_months,
            profit_roll_percentage=profit_roll_percentage,
        )

        monthly = result["monthly_records"]
        end_val = monthly[-1]["value"] if monthly else current_capital
        yr_pnl = end_val - current_capital
        yr_ret = yr_pnl / current_capital if current_capital > 0 else 0

        year_results[year] = {
            "capital": current_capital,
            "start_val": current_capital,
            "end_val": end_val,
            "injected": year_dca,
            "pnl": yr_pnl,
            "return": yr_ret,
            "config": list(current_config),
            "changes": [],
        }

        # 記錄每個 combo 的年度報酬
        record_combo_returns(current_config, year)

        # 年末檢討
        if year < end_year:
            print(f"\n   📋 {year} 年末檢討（標的年報酬率）：")
            for sym, strat, alloc in current_config:
                ret = get_annual_return(sym, year)
                ret_str = f"{ret:+.1%}" if ret is not None else "N/A"
                print(f"      {sym}({strat}): 年報酬={ret_str}")

            current_config, changes = apply_review_rules(current_config, year)
            year_results[year]["changes"] = changes

            # 更新資金為年末價值（下年初會再加上 12×月投入）
            current_capital = end_val
            print(f"   💰 年底結算: NT${current_capital:,.0f}")

    final_value = year_results[end_year]["end_val"]
    total_pnl = final_value - total_injected
    total_return = total_pnl / total_injected if total_injected > 0 else 0

    return {
        "mode": "dca",
        "monthly_total": monthly_total,
        "total_injected": total_injected,
        "final_value": final_value,
        "total_pnl": total_pnl,
        "total_return": total_return,
        "year_results": year_results,
    }


def run_yearly_review_lumpsum(initial_config, start_year=2022, end_year=2025,
                              initial_capital=500000, profit_roll_months=0,
                              profit_roll_percentage=1.0) -> dict:
    """
    逐年檢討 Lumpsum 回測。
    每年跑一段 simulate_lumpsum，年末清倉結算，次年重配資金。
    """
    global _combo_returns
    _combo_returns = {}
    current_config = list(initial_config)
    current_capital = initial_capital
    year_results = {}

    for year in range(start_year, end_year + 1):
        y_start = f"{year}-01-01"
        y_end   = f"{year}-12-31"

        # 重新分配資金（按 alloc 佔比分配 current_capital）
        total_alloc_amt = sum(c[2] for c in current_config)
        if total_alloc_amt > 0:
            rescaled = []
            for sym, strat, alloc in current_config:
                new_alloc = round(current_capital * alloc / total_alloc_amt)
                rescaled.append((sym, strat, new_alloc))
            # 補償整數誤差
            diff = round(current_capital) - sum(c[2] for c in rescaled)
            if diff != 0 and rescaled:
                s, st, a = rescaled[-1]
                rescaled[-1] = (s, st, a + diff)
        else:
            rescaled = list(current_config)

        print(f"\n{'='*60}")
        print(f"📊 {year} 年 — Lumpsum 逐年檢討")
        print(f"   可用資金: NT${current_capital:,.0f}")
        print(f"   配置: {[(s,st,a) for s,st,a in rescaled]}")
        print(f"{'='*60}")

        result = simulate_lumpsum(
            rescaled,
            start_date=y_start,
            end_date=y_end,
            initial_capital=current_capital,
            profit_roll_months=profit_roll_months,
            profit_roll_percentage=profit_roll_percentage,
        )

        monthly = result["monthly_records"]
        end_val = monthly[-1]["value"] if monthly else current_capital
        yr_pnl = end_val - current_capital
        yr_ret = yr_pnl / current_capital if current_capital > 0 else 0

        year_results[year] = {
            "capital": current_capital,
            "start_val": current_capital,
            "end_val": end_val,
            "pnl": yr_pnl,
            "return": yr_ret,
            "config": list(current_config),
            "changes": [],
        }

        # 記錄年度報酬
        record_combo_returns(current_config, year)

        # 年末檢討
        if year < end_year:
            print(f"\n   📋 {year} 年末檢討（標的年報酬率）：")
            for sym, strat, alloc in current_config:
                ret = get_annual_return(sym, year)
                ret_str = f"{ret:+.1%}" if ret is not None else "N/A"
                print(f"      {sym}({strat}): 年報酬={ret_str}")

            current_config, changes = apply_review_rules(current_config, year)
            year_results[year]["changes"] = changes

            current_capital = end_val
            print(f"   💰 明年可用資金: NT${current_capital:,.0f}")

    final_value = year_results[end_year]["end_val"]
    total_pnl = final_value - initial_capital
    total_return = total_pnl / initial_capital if initial_capital > 0 else 0

    return {
        "mode": "lumpsum",
        "initial_capital": initial_capital,
        "final_value": final_value,
        "total_pnl": total_pnl,
        "total_return": total_return,
        "year_results": year_results,
    }


# ── 報告 ────────────────────────────────────────────

def generate_review_report(result: dict) -> str:
    lines = []
    mode = result["mode"]
    is_dca = mode == "dca"

    lines.append("# 逐年檢討回測 — 不能有事後之明")
    lines.append("")
    lines.append(f"> 📅 模擬日期：{datetime.now().strftime('%Y-%m-%d')}")
    lines.append("> ⚠️ **過去績效不代表未來獲利，本模擬僅供參考。**")
    lines.append(">")
    lines.append("> 檢討規則（機械式，無事後之明）：")
    lines.append("> - Rule 0：ETF + bollinger → keep_wait（部署時即修正，結構性錯配）")
    lines.append("> - Rule 1：標的連虧 2 年 → 剔除，找候選池最佳替代")
    lines.append("> - Rule 2：替代標的 = 市值前 30 大中前一年報酬最高者")
    lines.append("> - Rule 3：新進策略分派 — 半導體→keep_wait, 金融→vwap, 其他→ma_cross")
    lines.append("> - 衡量基準：標的年報酬率（價格漲跌幅，年末可查）")
    lines.append("")

    # 總績效
    label = "DCA（每月 NT$20,000）" if is_dca else "Lumpsum（NT$500,000）"
    lines.append(f"## 📊 總績效（{label}）")
    lines.append("")
    lines.append("| 指標 | 數值 |")
    lines.append("|------|------|")
    if is_dca:
        lines.append(f"| 總投入 | NT${result['total_injected']:,.0f} |")
    else:
        lines.append(f"| 初始資金 | NT${result['initial_capital']:,.0f} |")
    lines.append(f"| 終值 | NT${result['final_value']:,.0f} |")
    lines.append(f"| **總損益** | **NT${result['total_pnl']:,.0f} ({result['total_return']:+.1%})** |")
    lines.append("")

    # 逐年
    lines.append("## 📅 逐年明細")
    lines.append("")
    yr = result["year_results"]
    for year in sorted(yr.keys()):
        y = yr[year]
        lines.append(f"### {year} 年")
        lines.append("")
        lines.append("| 指標 | 數值 |")
        lines.append("|------|------|")
        if is_dca:
            lines.append(f"| 可用資金（含當年DCA） | NT${y['capital']:,.0f} |")
            lines.append(f"| 其中當年DCA | NT${y['injected']:,.0f} |")
        else:
            lines.append(f"| 可用資金 | NT${y['capital']:,.0f} |")
        lines.append(f"| 年底價值 | NT${y['end_val']:,.0f} |")
        lines.append(f"| **年度損益** | **NT${y['pnl']:,.0f} ({y['return']:+.1%})** |")
        lines.append("")

        # 配置
        lines.append("**當年配置：**")
        lines.append("")
        lines.append("| 標的 | 策略 | 類型 |")
        lines.append("|------|------|------|")
        for sym, strat, alloc in y["config"]:
            stype = ("逆勢" if strat in ("bollinger", "vwap")
                     else "順勢" if strat in ("ma_cross", "breakout")
                     else "低接")
            lines.append(f"| {sym} | {strat} | {stype} |")
        lines.append("")

        # 變更
        if y.get("changes"):
            lines.append("**年末檢討變更：**")
            lines.append("")
            for sym, strat, alloc, reason in y["changes"]:
                lines.append(f"- {sym}({strat}): {reason}")
            lines.append("")

    # 與原版對比
    lines.append("## 📈 與固定池原版對比")
    lines.append("")
    lines.append("| | 逐年檢討版 | 固定池原版 | 差異 |")
    lines.append("|:---|:---|:---|:---|")

    if is_dca:
        orig = {"總報酬": "+39.7%", "2022": "-3.6%", "2023": "+24.7%",
                "2024": "+20.5%", "2025": "+6.0%"}
        orig_ret = 0.397
    else:
        orig = {"總報酬": "+71.4%", "2022": "-12.0%", "2023": "+36.6%",
                "2024": "+30.6%", "2025": "+9.2%"}
        orig_ret = 0.714

    # 總報酬
    review_total = f"{result['total_return']:+.1%}"
    diff_total = f"{result['total_return'] - orig_ret:+.1%}"
    lines.append(f"| 總報酬 | {review_total} | {orig['總報酬']} | {diff_total} |")

    for year in sorted(yr.keys()):
        yr_ret = yr[year]["return"]
        yr_str = f"{yr_ret:+.1%}"
        orig_str = orig.get(str(year), "N/A")
        # parse orig
        orig_val = float(orig_str.replace("%", "")) / 100
        diff = f"{yr_ret - orig_val:+.1%}"
        lines.append(f"| {year} | {yr_str} | {orig_str} | {diff} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*報告產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append("")
    return "\n".join(lines)


# ── main ────────────────────────────────────────────

def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="逐年檢討回測")
    parser.add_argument("--mode", choices=["dca", "lumpsum", "all"], default="all")
    parser.add_argument("--start", type=int, default=2022)
    parser.add_argument("--end", type=int, default=2025)
    parser.add_argument("--profit-roll-months", type=float, default=0)
    parser.add_argument("--profit-roll-percentage", type=float, default=1.0)
    args = parser.parse_args()

    prm = args.profit_roll_months
    prp = args.profit_roll_percentage

    # 從 PC_ 環境變數建立初始配置
    pc_config = load_portfolio_config()
    total_alloc_pct = sum(float(cfg.get("alloc", 20)) for cfg in pc_config.values())
    monthly_total = 20000
    lumpsum_total = 500000

    initial_dca = []
    initial_ls = []
    for sym, cfg in pc_config.items():
        strat = cfg["strategy"]
        pct = float(cfg.get("alloc", 20)) / total_alloc_pct if total_alloc_pct > 0 else (1.0 / len(pc_config))
        initial_dca.append((sym, strat, int(monthly_total * pct)))
        initial_ls.append((sym, strat, int(lumpsum_total * pct)))

    # 補償整數誤差
    for config, total in [(initial_dca, monthly_total), (initial_ls, lumpsum_total)]:
        diff = total - sum(c[2] for c in config)
        if diff != 0 and config:
            s, st, a = config[-1]
            config[-1] = (s, st, a + diff)

    # 預先載入候選池資料
    print("📥 預先載入候選池資料...")
    for sym in CANDIDATE_POOL:
        get_data(sym, start=f"{args.start - 1}-12-01")
    print("✅ 資料載入完成")

    # ── Rule 0: 初次配置修正 ──
    print("\n⚡ Rule 0: 初次配置修正（ETF bollinger→keep_wait）")
    initial_dca = apply_initial_fixes(initial_dca)
    initial_ls = apply_initial_fixes(initial_ls)

    if args.mode in ("all", "dca"):
        print(f"\n{'#'*60}")
        print(f"# 方案一 DCA：每月 NT${monthly_total:,} 逐年檢討回測")
        print(f"# {args.start} ~ {args.end}")
        print(f"{'#'*60}")

        dca_result = run_yearly_review_dca(
            initial_dca,
            start_year=args.start, end_year=args.end,
            monthly_total=monthly_total,
            profit_roll_months=prm, profit_roll_percentage=prp,
        )
        dca_report = generate_review_report(dca_result)
        dca_path = f"回溯_逐年檢討_{args.start}_{args.end}_DCA.MD"
        with open(dca_path, "w", encoding="utf-8") as f:
            f.write(dca_report)
        print(f"\n✅ DCA 報告 → {dca_path}")

    if args.mode in ("all", "lumpsum"):
        print(f"\n{'#'*60}")
        print(f"# 方案二 Lumpsum：NT${lumpsum_total:,} 逐年檢討回測")
        print(f"# {args.start} ~ {args.end}")
        print(f"{'#'*60}")

        ls_result = run_yearly_review_lumpsum(
            initial_ls,
            start_year=args.start, end_year=args.end,
            initial_capital=lumpsum_total,
            profit_roll_months=prm, profit_roll_percentage=prp,
        )
        ls_report = generate_review_report(ls_result)
        ls_path = f"回溯_逐年檢討_{args.start}_{args.end}_Lumpsum.MD"
        with open(ls_path, "w", encoding="utf-8") as f:
            f.write(ls_report)
        print(f"\n✅ Lumpsum 報告 → {ls_path}")


if __name__ == "__main__":
    main()
