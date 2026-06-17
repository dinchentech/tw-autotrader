# backtest_2024_2025.py — 完整投資組合回溯模擬（含 keep_wait DCA 低接策略）
import sys
sys.path.insert(0, ".")

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from config.symbols import get_yahoo_suffix
from data.yahoo_loader import load_historical_data
from core.config_loader import load_portfolio_config, get_strategy_params, get_keep_wait_params
from strategies.bollinger import bollinger_reverse_strategy
from strategies.ma_cross import ma_cross_strategy
from strategies.vwap_deviation import vwap_deviation_strategy
from strategies.breakout import breakout_strategy

START = "2023-06-01"
BACKTEST_START = "2024-01-02"
BACKTEST_END = "2025-12-31"
BUY_COST = 0.001425
SELL_COST = 0.001425
TAX_ETF = 0.001
TAX_STOCK = 0.003

ETF_SYMBOLS = {"0050", "006208", "00878", "0056"}

STRATEGY_FUNCS = {
    "bollinger": bollinger_reverse_strategy,
    "ma_cross": ma_cross_strategy,
    "vwap": vwap_deviation_strategy,
    "breakout": breakout_strategy,
}


def load_data(symbol: str) -> pd.DataFrame:
    suffix = get_yahoo_suffix(symbol)
    df = load_historical_data(f"{symbol}{suffix}", START)
    if df.empty:
        print(f"  {symbol} 無資料")
        return df
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def run_signal_strategy(df: pd.DataFrame, strategy: str, params: dict) -> pd.DataFrame:
    return STRATEGY_FUNCS[strategy](df, **params)


def _build_portfolio_from_env(mode: str = "lumpsum") -> dict:
    """從 PC_ 環境變數建立回測用投資組合，格式同 run_lump_sum_simulation()"""
    pc_config = load_portfolio_config()
    if not pc_config:
        return {}

    portfolio = {}
    total_alloc = sum(float(cfg.get("alloc", 0)) for cfg in pc_config.values())
    for sym, cfg in pc_config.items():
        strat = cfg["strategy"]
        pct = (float(cfg.get("alloc", 20)) / total_alloc) if total_alloc > 0 else (1.0 / len(pc_config))
        entry = {"strategy": strat, "pct": pct}
        params = get_strategy_params(cfg, strat)
        if params:
            entry["params"] = params
        if strat == "keep_wait":
            kw_params = get_keep_wait_params(cfg)
            if kw_params:
                # backtest_2024_2025 用 kw_ 前綴
                mapped = {}
                mapping = {
                    "initial_shares": "kw_initial_shares",
                    "add_drop_pct": "kw_add_drop_pct",
                    "add_shares": "kw_add_shares",
                    "max_additions": "kw_max_additions",
                    "tp_trigger_pct": "kw_tp_pct",
                    "tp_sell_ratio": "kw_tp_sell_ratio",
                    "cooldown_days": "kw_cooldown_days",
                }
                for pc_key, bt_key in mapping.items():
                    if pc_key in kw_params:
                        mapped[bt_key] = kw_params[pc_key]
                entry["kw_params"] = mapped
        portfolio[sym] = entry

    print(f"📋 從 PC_ 設定建立投資組合（{mode}），共 {len(portfolio)} 檔")
    for sym, e in portfolio.items():
        print(f"   {sym} → {e['strategy']} (pct={e['pct']:.1%})")
    return portfolio


def simulate_keep_wait(df: pd.DataFrame,
                       kw_initial_shares: int = 45,
                       kw_add_drop_pct: float = 5.0,
                       kw_add_shares: int = 45,
                       kw_max_additions: int = 2,
                       kw_tp_pct: float = 15.0,
                       kw_tp_sell_ratio: float = 50.0,
                       kw_cooldown_days: int = 30,
                       initial_capital: float = 75_000,
                       is_etf: bool = False) -> tuple:
    records = []
    cash = initial_capital
    hold = 0
    avg_cost = 0.0
    buy_count = 0
    cooldown_until = None
    total_injected = initial_capital

    for i in range(len(df)):
        date = df.index[i]
        price = float(df.iloc[i]["close"])
        if price <= 0:
            continue
        if cooldown_until and date < cooldown_until:
            continue

        if hold == 0 and buy_count == 0 and cash > kw_initial_shares * price * (1 + BUY_COST):
            cost = kw_initial_shares * price * (1 + BUY_COST)
            cash -= cost
            hold += kw_initial_shares
            avg_cost = price
            records.append({"date": date, "type": "buy", "price": price,
                            "shares": kw_initial_shares, "amount": kw_initial_shares * price,
                            "fee": cost - kw_initial_shares * price})
            continue

        if hold > 0 and buy_count < kw_max_additions:
            drop_pct = (avg_cost - price) / avg_cost * 100
            if drop_pct >= kw_add_drop_pct and cash > kw_add_shares * price * (1 + BUY_COST):
                cost = kw_add_shares * price * (1 + BUY_COST)
                cash -= cost
                avg_cost = (avg_cost * hold + price * kw_add_shares) / (hold + kw_add_shares)
                hold += kw_add_shares
                buy_count += 1
                records.append({"date": date, "type": "buy", "price": price,
                                "shares": kw_add_shares, "amount": kw_add_shares * price,
                                "fee": cost - kw_add_shares * price})
                continue

        if hold > 0:
            profit_pct = (price - avg_cost) / avg_cost * 100
            if profit_pct >= kw_tp_pct:
                sell_shares = int(hold * kw_tp_sell_ratio / 100)
                if sell_shares <= 0:
                    sell_shares = hold
                tax_rate = TAX_ETF if is_etf else TAX_STOCK
                proceeds = sell_shares * price * (1 - SELL_COST - tax_rate)
                cash += proceeds
                hold -= sell_shares
                records.append({"date": date, "type": "sell", "price": price,
                                "shares": sell_shares, "amount": sell_shares * price,
                                "fee": sell_shares * price * (SELL_COST + tax_rate)})
                cooldown_until = date + timedelta(days=kw_cooldown_days)
                if hold == 0:
                    avg_cost = 0
                    buy_count = 0

    if hold > 0 and len(df) > 0:
        price = float(df.iloc[-1]["close"])
        tax_rate = TAX_ETF if is_etf else TAX_STOCK
        proceeds = hold * price * (1 - SELL_COST - tax_rate)
        cash += proceeds

    final_value = cash
    profit = final_value - total_injected
    roi = profit / total_injected * 100 if total_injected > 0 else 0
    return records, total_injected, final_value, profit, roi


def simulate_signal_strategy(df: pd.DataFrame, strategy: str, params: dict,
                              initial_capital: float, is_etf: bool = False,
                              monthly_budget: float = 0) -> tuple:
    signal_df = run_signal_strategy(df, strategy, params)
    records = []
    cash = initial_capital if monthly_budget == 0 else 0
    hold = 0
    total_injected = initial_capital if monthly_budget == 0 else 0
    dca_mode = monthly_budget > 0

    for i in range(len(signal_df)):
        date = signal_df.index[i]
        price = float(signal_df.iloc[i]["close"])
        if price <= 0:
            continue

        if dca_mode and i > 0 and date.month != signal_df.index[i-1].month:
            cash += monthly_budget
            total_injected += monthly_budget

        signal = int(signal_df.iloc[i]["signal"])

        if signal == 1 and cash > price * (1 + BUY_COST):
            invest = cash * 0.5
            shares = int(invest / (price * (1 + BUY_COST)))
            if shares > 0:
                cost = shares * price * (1 + BUY_COST)
                cash -= cost
                hold += shares
                records.append({"date": date, "type": "buy", "price": price,
                                "shares": shares, "amount": shares * price,
                                "fee": cost - shares * price})

        elif signal == -1 and hold > 0:
            tax_rate = TAX_ETF if is_etf else TAX_STOCK
            proceeds = hold * price * (1 - SELL_COST - tax_rate)
            cash += proceeds
            records.append({"date": date, "type": "sell", "price": price,
                            "shares": hold, "amount": hold * price,
                            "fee": hold * price * (SELL_COST + tax_rate)})
            hold = 0

    if hold > 0 and len(signal_df) > 0:
        price = float(signal_df.iloc[-1]["close"])
        tax_rate = TAX_ETF if is_etf else TAX_STOCK
        proceeds = hold * price * (1 - SELL_COST - tax_rate)
        cash += proceeds

    final_value = cash
    profit = final_value - total_injected
    roi = profit / total_injected * 100 if total_injected > 0 else 0
    return records, total_injected, final_value, profit, roi


def simulate_portfolio(portfolio: dict, mode: str = "dca",
                       total_capital: float = 500_000,
                       monthly_budget: float = 20_000) -> dict:
    print(f"\n{'='*60}")
    print(f"開始模擬: {'每月NT${:,.0f} DCA'.format(monthly_budget) if mode=='dca' else f'單筆NT${total_capital:,.0f}一次投入'}")
    print(f"期間: {BACKTEST_START} ~ {BACKTEST_END}")
    print(f"{'='*60}")

    all_data = {}
    for symbol, cfg in portfolio.items():
        df = load_data(symbol)
        if df.empty:
            print(f"  {symbol} 載入失敗，跳過")
            continue
        df = df[BACKTEST_START:BACKTEST_END]
        if len(df) < 50:
            print(f"  {symbol} 資料不足 ({len(df)} 天)，跳過")
            continue
        all_data[symbol] = df
        print(f"  {symbol} 載入 {len(df)} 天")

    results = {}
    for symbol, cfg in portfolio.items():
        if symbol not in all_data:
            continue
        df = all_data[symbol]
        strategy = cfg["strategy"]
        pct = cfg["pct"]
        is_etf = symbol[:2].isdigit() or (len(symbol) == 4 and symbol[:1] == "0") or symbol in ETF_SYMBOLS

        if strategy == "keep_wait":
            initial = total_capital * pct if mode == "lumpsum" else 0
            kw_params = cfg.get("kw_params", {})
            records, total_in, final_value, profit, roi = simulate_keep_wait(
                df, initial_capital=initial, is_etf=is_etf, **kw_params)
        elif mode == "dca":
            monthly_budget_stock = monthly_budget * pct
            records, total_in, final_value, profit, roi = simulate_signal_strategy(
                df, strategy, cfg.get("params", {}), 0, is_etf,
                monthly_budget=monthly_budget_stock)
        else:
            initial = total_capital * pct
            records, total_in, final_value, profit, roi = simulate_signal_strategy(
                df, strategy, cfg.get("params", {}), initial, is_etf)

        buys = len([r for r in records if r["type"] == "buy"])
        sells = len([r for r in records if r["type"] == "sell"])

        results[symbol] = {
            "strategy": strategy,
            "records": records,
            "total_in": total_in,
            "final_value": final_value,
            "profit": profit,
            "roi": roi,
            "buys": buys,
            "sells": sells,
            "is_etf": is_etf,
        }

        print(f"  {symbol} ({strategy}): 投入NT${total_in:,.0f} -> NT${final_value:,.0f} 損益NT${profit:,.0f} ({roi:+.1f}%)")

    return results


def run_dca_simulation():
    portfolio = _build_portfolio_from_env("dca")
    if not portfolio:
        portfolio = {
            "0050":  {"strategy": "bollinger", "pct": 0.50,
                      "params": {"window": 20, "std_dev": 2.0, "rsi_period": 5}},
            "2330":  {"strategy": "ma_cross",  "pct": 0.15,
                      "params": {"fast_period": 9, "slow_period": 21, "atr_threshold": 0.005}},
            "2382":  {"strategy": "breakout",  "pct": 0.15,
                      "params": {"lookback": 20, "atr_period": 14}},
            "2881":  {"strategy": "vwap",      "pct": 0.20,
                      "params": {"sigma_mult": 1.5, "rsi_period": 5}},
        }
    return simulate_portfolio(portfolio, mode="dca", monthly_budget=20_000)


def run_lump_sum_simulation():
    portfolio = _build_portfolio_from_env("lumpsum")
    if not portfolio:
        portfolio = {
            "0050":  {"strategy": "bollinger", "pct": 0.117,
                      "params": {"window": 20, "std_dev": 2.0, "rsi_period": 5}},
            "006208": {"strategy": "bollinger", "pct": 0.117,
                       "params": {"window": 20, "std_dev": 2.0, "rsi_period": 5}},
            "00878": {"strategy": "bollinger", "pct": 0.116,
                      "params": {"window": 20, "std_dev": 2.0, "rsi_period": 5}},
            "2330":  {"strategy": "ma_cross",  "pct": 0.15,
                      "params": {"fast_period": 9, "slow_period": 21, "atr_threshold": 0.005}},
            "2454":  {"strategy": "keep_wait", "pct": 0.15, "kw_params": {
                "kw_initial_shares": 45,
                "kw_add_drop_pct": 5.0,
                "kw_add_shares": 45,
                "kw_max_additions": 2,
                "kw_tp_pct": 15.0,
                "kw_tp_sell_ratio": 50.0,
                "kw_cooldown_days": 30,
            }},
            "2881":  {"strategy": "vwap",      "pct": 0.10,
                      "params": {"sigma_mult": 1.5, "rsi_period": 5}},
            "2886":  {"strategy": "vwap",      "pct": 0.10,
                      "params": {"sigma_mult": 1.5, "rsi_period": 5}},
            "2382":  {"strategy": "breakout",  "pct": 0.15,
                      "params": {"lookback": 20, "atr_period": 14}},
        }
    return simulate_portfolio(portfolio, mode="lumpsum", total_capital=500_000)


def generate_dca_report(results: dict) -> str:
    total_in = sum(r["total_in"] for r in results.values())
    total_final = sum(r["final_value"] for r in results.values())
    total_profit = total_final - total_in
    cagr = ((total_final / max(total_in, 1e-6)) ** (1 / 2) - 1) * 100

    lines = []
    lines.append("# 每月2萬元策略 -- 2024 & 2025 回溯模擬\n")
    lines.append(f"> 模擬日期：{datetime.now().strftime('%Y-%m-%d')}")
    lines.append("> **過去績效不代表未來獲利，本模擬僅供參考。**\n")
    lines.append("## 策略配置\n")
    lines.append("每月總預算 **NT$20,000**，按以下權重分配至各標的：\n")
    lines.append("| 標的 | 代號 | 策略 | 每月配置 | 權重 |")
    lines.append("|------|------|------|---------|------|")
    lines.append("| 0050 | 0050 | bollinger | NT$10,000 | 50% |")
    lines.append("| 2330 | 2330 | ma_cross | NT$3,000 | 15% |")
    lines.append("| 2382 | 2382 | breakout | NT$3,000 | 15% |")
    lines.append("| 2881 | 2881 | vwap | NT$4,000 | 20% |")
    lines.append(f"\n## 總績效摘要\n")
    lines.append("| 指標 | 數值 |")
    lines.append("|------|------|")
    lines.append(f"| 模擬期間 | {BACKTEST_START} ~ {BACKTEST_END}（730 天） |")
    lines.append(f"| 總投入資金 | NT${total_in:,.0f} |")
    lines.append(f"| 組合終值 | NT${total_final:,.0f} |")
    lines.append(f"| **總損益** | **NT${total_profit:,.0f} ({total_profit/total_in*100:+.1f}%)** |")
    lines.append(f"| **年化報酬率 (CAGR)** | **{cagr:+.1f}%** |")
    lines.append(f"\n## 各標的績效\n")
    lines.append("| 標的 | 策略 | 投入資金 | 終值 | 損益 | 報酬率 | 買/賣次數 |")
    lines.append("|------|------|---------|------|------|--------|----------|")
    for symbol in sorted(results.keys()):
        r = results[symbol]
        lines.append(f"| {symbol} | {r['strategy']} | NT${r['total_in']:>,.0f} | "
                     f"NT${r['final_value']:>,.0f} | NT${r['profit']:+,.0f} | "
                     f"{r['roi']:+.1f}% | {r['buys']}/{r['sells']} |")
    lines.append(f"\n## 各標的交易記錄\n")
    for symbol in sorted(results.keys()):
        r = results[symbol]
        lines.append(f"### {symbol} -- {r['strategy']}\n")
        lines.append("| 日期 | 類型 | 價格 | 金額 | 股數 | 費用 |")
        lines.append("|------|------|------|------|------|------|")
        for rec in r["records"]:
            d = rec['date'].strftime('%Y-%m-%d') if hasattr(rec['date'], 'strftime') else str(rec['date'])
            fee_str = f"NT${rec['fee']:>7,.0f}" if rec['fee'] > 0 else ""
            ttype = "買" if rec['type'] == "buy" else ("賣" if rec['type'] == "sell" else rec['type'])
            lines.append(f"| {d} | {ttype} | NT${rec['price']:>8,.1f} | NT${rec['amount']:>7,.0f} | "
                         f"{rec['shares']:>6.1f} | {fee_str} |")
        lines.append("")
    lines.append(f"\n## 免責聲明\n")
    lines.append("1. **過去績效不代表未來獲利** -- 本模擬基於歷史資料，不保證未來表現")
    lines.append("2. **交易成本已計入** -- 包含手續費（0.1425%）與證交稅（ETF 0.1% / 股票 0.3%）")
    lines.append("3. **未計入滑價** -- 假設以收盤價成交，實盤可能因流動性產生偏差")
    lines.append("4. **策略參數固定** -- 使用預設參數，未針對2024-2025市場最佳化")
    lines.append("5. **資料來源** -- Yahoo Finance (auto_adjust=True，已調整除權息)")
    lines.append("6. **模擬假設** -- 每月月初撥入預算，訊號觸發當日以收盤價交易")
    lines.append(f"\n---\n")
    lines.append(f"*報告產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
    return "\n".join(lines)


def generate_lump_report(results: dict) -> str:
    total_in = sum(r["total_in"] for r in results.values())
    total_final = sum(r["final_value"] for r in results.values())
    total_profit = total_final - total_in
    cagr = ((total_final / max(total_in, 1e-6)) ** (1 / 2) - 1) * 100

    lines = []
    lines.append("# 50萬一筆資金 -- 2024 & 2025 回溯模擬\n")
    lines.append(f"> 模擬日期：{datetime.now().strftime('%Y-%m-%d')}")
    lines.append("> **過去績效不代表未來獲利，僅供參考。**")
    lines.append("> 初始資本NT$500,000一次到位，獲利可再投入。\n")
    lines.append("## 策略配置\n")
    lines.append("| 策略 | 資金 | 佔比 | 標的 | 策略類型 |")
    lines.append("|------|-----|------|------|---------|")
    lines.append("| bollinger | NT$175,000 | 35% | 0050, 006208, 00878 | 逆勢 |")
    lines.append("| ma_cross | NT$75,000 | 15% | 2330 | 順勢 |")
    lines.append("| keep_wait | NT$75,000 | 15% | 2454 | DCA低接 |")
    lines.append("| vwap | NT$100,000 | 20% | 2881, 2886 | 逆勢 |")
    lines.append("| breakout | NT$75,000 | 15% | 2382 | 順勢 |")
    lines.append("| **總計** | **NT$500,000** | **100%** | **8 檔** | -- |\n")
    lines.append("## 總績效\n")
    lines.append("| 指標 | 數值 |")
    lines.append("|------|------|")
    lines.append(f"| 初始資本 | NT${total_in:,.0f} |")
    lines.append(f"| 組合終值 ({BACKTEST_END}) | NT${total_final:,.0f} |")
    lines.append(f"| **總損益** | **NT${total_profit:,.0f} ({total_profit/total_in*100:+.1f}%)** |")
    lines.append(f"| **年化報酬率 (CAGR)** | **{cagr:+.1f}%** |")
    lines.append(f"| 模擬期間 | {BACKTEST_START} ~ {BACKTEST_END}（730 天） |")
    lines.append(f"\n## 各標的績效\n")
    lines.append("| 標的 | 策略 | 初始資金 | 終值 | 損益 | 報酬率 | 交易 |")
    lines.append("|------|------|---------|------|------|--------|------|")
    for symbol in sorted(results.keys()):
        r = results[symbol]
        lines.append(f"| {symbol} | {r['strategy']} | NT${r['total_in']:>,.0f} | "
                     f"NT${r['final_value']:>,.0f} | NT${r['profit']:+,.0f} | "
                     f"{r['roi']:+.1f}% | {r['buys']}買/{r['sells']}賣 |")
    strat_results = {}
    for symbol, r in results.items():
        s = r["strategy"]
        strat_results.setdefault(s, {"total_in": 0, "final": 0, "profit": 0})
        strat_results[s]["total_in"] += r["total_in"]
        strat_results[s]["final"] += r["final_value"]
        strat_results[s]["profit"] += r["profit"]
    lines.append(f"\n### 各策略彙總\n")
    lines.append("| 策略 | 初始資金 | 終值 | 損益 | 報酬率 |")
    lines.append("|------|---------|------|------|--------|")
    for s in sorted(strat_results.keys()):
        v = strat_results[s]
        roi = v["profit"] / v["total_in"] * 100 if v["total_in"] > 0 else 0
        lines.append(f"| {s} | NT${v['total_in']:>,.0f} | NT${v['final']:>,.0f} | "
                     f"NT${v['profit']:+,.0f} | {roi:+.1f}% |")
    lines.append(f"\n## 交易記錄\n")
    for symbol in sorted(results.keys()):
        r = results[symbol]
        lines.append(f"### {symbol} -- {r['strategy']}\n")
        lines.append("| 日期 | 類型 | 價格 | 金額 | 費用 |")
        lines.append("|------|------|------|------|------|")
        for rec in r["records"]:
            d = rec['date'].strftime('%Y-%m-%d') if hasattr(rec['date'], 'strftime') else str(rec['date'])
            fee_str = f"NT${rec['fee']:>7,.0f}" if rec['fee'] > 0 else ""
            ttype = "買" if rec['type'] == "buy" else ("賣" if rec['type'] == "sell" else rec['type'])
            lines.append(f"| {d} | {ttype} | NT${rec['price']:>8,.1f} | NT${rec['amount']:>7,.0f} | {fee_str} |")
        lines.append("")
    lines.append(f"\n## 免責聲明\n")
    lines.append("1. 過去績效不代表未來獲利，本模擬基於歷史資料不保證未來表現")
    lines.append("2. 已計入交易成本：手續費0.1425% + 證交稅（ETF 0.1%/股票 0.3%）")
    lines.append("3. 未計入：滑價、金字塔加碼、大盤年線過濾、股利收入")
    lines.append("4. 參數固定使用預設值，未針對2024-2025市場最佳化")
    lines.append("5. 資料來源：Yahoo Finance (auto_adjust=True)")
    lines.append(f"\n---\n")
    lines.append(f"*報告產生：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    from dateutil.relativedelta import relativedelta
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="TW AutoTrader 2024-2025 回溯")
    parser.add_argument("--mode", choices=["dca", "lump", "all"], default="all")
    args = parser.parse_args()

    if args.mode in ("dca", "all"):
        print("開始 DCA 模擬（每月NT$20,000）...")
        dca_results = run_dca_simulation()
        dca_report = generate_dca_report(dca_results)
        with open("/tmp/backtest_dca_2024_2025.md", "w") as f:
            f.write(dca_report)
        print("DCA 報告已寫入 /tmp/backtest_dca_2024_2025.md")

    if args.mode in ("lump", "all"):
        print("\n開始 Lump Sum 模擬（單筆NT$500,000）...")
        lump_results = run_lump_sum_simulation()
        lump_report = generate_lump_report(lump_results)
        with open("/tmp/backtest_lump_2024_2025.md", "w") as f:
            f.write(lump_report)
        print("Lump Sum 報告已寫入 /tmp/backtest_lump_2024_2025.md")
