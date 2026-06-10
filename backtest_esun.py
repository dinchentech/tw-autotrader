# backtest_esun.py — 玉山資料源回測（function-based 策略）
#
# Usage:
#   python backtest_esun.py                              # 批次回測全部標的
#   python backtest_esun.py --symbol 2330                 # 單一標的
#   python backtest_esun.py --symbol 2330 --start 2024-01-01 --end 2024-12-31
#   python backtest_esun.py --strategy ma_cross --fast_period 5 --slow_period 30
#
# 第一次執行前請確認 .env 有 BROKER=esun + 密碼設定。

import os
import argparse
import csv
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from config.symbols import ALL_SYMBOLS
from strategies.vwap_deviation import vwap_deviation_strategy
from strategies.ma_cross import ma_cross_strategy
from strategies.bollinger import bollinger_reverse_strategy
from strategies.breakout import breakout_strategy

# ── 策略設定（與 backtest.py 共用） ──────────────────────────────

STRATEGY_CONFIG = {
    "vwap": {
        "func": vwap_deviation_strategy,
        "params": {"sigma_mult": 1.5, "rsi_period": 5},
    },
    "ma_cross": {
        "func": ma_cross_strategy,
        "params": {"fast_period": 9, "slow_period": 21, "atr_threshold": 0.005},
    },
    "bollinger": {
        "func": bollinger_reverse_strategy,
        "params": {"window": 20, "std_dev": 2.0, "rsi_period": 5},
    },
    "breakout": {
        "func": breakout_strategy,
        "params": {"lookback": 20, "atr_period": 14},
    },
}

SHARED_PARAMS = {
    "rsi_period": {"default": 5, "type": int, "help": "RSI 計算週期"},
}

STRATEGY_PARAMS = {
    "vwap": {
        "sigma_mult":  {"default": 1.5,  "type": float, "help": "VWAP 偏離倍數"},
        "rsi_period":  SHARED_PARAMS["rsi_period"],
    },
    "ma_cross": {
        "fast_period": {"default": 9,  "type": int, "help": "快線週期"},
        "slow_period": {"default": 21, "type": int, "help": "慢線週期"},
        "atr_threshold": {"default": 0.005, "type": float, "help": "ATR 波動度門檻"},
    },
    "bollinger": {
        "window":     {"default": 20, "type": int, "help": "布林通道計算週期"},
        "std_dev":    {"default": 2.0,"type": float, "help": "標準差倍數"},
        "rsi_period": SHARED_PARAMS["rsi_period"],
    },
    "breakout": {
        "lookback":   {"default": 20, "type": int, "help": "突破回溯期間"},
        "atr_period": {"default": 14, "type": int, "help": "ATR 計算週期"},
    },
}

# ── 績效計算 ──────────────────────────────────────────────────────

def calculate_performance(df: pd.DataFrame) -> dict:
    if df.empty or (df['signal'] == 0).all():
        return {"total_trades": 0, "win_rate": 0.0, "total_return": 0.0}
    df = df.copy()
    df['next_close'] = df['close'].shift(-1)
    df['trade_return'] = 0.0
    buy_mask = df['signal'] == 1
    if buy_mask.any():
        df.loc[buy_mask, 'trade_return'] = (
            (df.loc[buy_mask, 'next_close'] - df.loc[buy_mask, 'close'])
            / df.loc[buy_mask, 'close']
        )
    sell_mask = df['signal'] == -1
    if sell_mask.any():
        df.loc[sell_mask, 'trade_return'] = (
            (df.loc[sell_mask, 'close'] - df.loc[sell_mask, 'next_close'])
            / df.loc[sell_mask, 'close']
        )
    trades = df[df['signal'] != 0]
    if trades.empty:
        return {"total_trades": 0, "win_rate": 0.0, "total_return": 0.0}
    total_trades = len(trades)
    win_trades = (trades['trade_return'] > 0).sum()
    win_rate = win_trades / total_trades
    total_return = trades['trade_return'].sum()
    return {"total_trades": total_trades, "win_rate": win_rate, "total_return": total_return}

def export_results(results: list, strategy_name: str):
    if not results:
        return
    os.makedirs("results", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"results/backtest_esun_{strategy_name}_{ts}.csv"
    fieldnames = ["symbol", "trades", "win_rate", "return", "avg_return"]
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in results:
            w.writerow({
                "symbol": r["symbol"],
                "trades": r["trades"],
                "win_rate": f"{r['win_rate']:.4f}",
                "return": f"{r['return']:.4f}",
                "avg_return": f"{r['return'] / r['trades']:.4f}" if r["trades"] > 0 else "0.0",
            })
    print(f"\n✅ 結果已匯出: {path}")

# ── CLI ──────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="TW AutoTrader — 玉山資料源回測")
    p.add_argument("--symbol", type=str, default="",
                   help="股票代號（留空 = 批次回測 ALL_SYMBOLS）")
    p.add_argument("--strategy", type=str, default="vwap",
                   choices=list(STRATEGY_CONFIG.keys()),
                   help="策略名稱")
    p.add_argument("--start", type=str, default="2023-01-01",
                   help="開始日期 YYYY-MM-DD")
    p.add_argument("--end", type=str, default="",
                   help="結束日期 YYYY-MM-DD（留空 = 今日）")

    added = set()
    for sname, sp in STRATEGY_PARAMS.items():
        for pname, popts in sp.items():
            if pname not in added:
                p.add_argument(f'--{pname}', type=popts["type"], default=None,
                               help=f'{sname}: {popts["help"]} (預設 {popts["default"]})')
                added.add(pname)
    return p.parse_args()

# ── main ─────────────────────────────────────────────────────────

def main():
    args = parse_args()
    strategy_name = args.strategy.lower()
    config = STRATEGY_CONFIG[strategy_name]
    params = config["params"].copy()
    for pname in STRATEGY_PARAMS[strategy_name]:
        cli = getattr(args, pname, None)
        if cli is not None:
            params[pname] = cli

    symbols = [args.symbol] if args.symbol else ALL_SYMBOLS

    print(f"📊 玉山資料源回測")
    print(f"🎯 策略: {strategy_name}")
    print(f"⚙️  參數: {params}")
    print(f"📅 期間: {args.start} ~ {args.end or '今日'}")
    print(f"📈 標的: {len(symbols)} 檔")

    from data.esun_provider import EsunProvider
    provider = EsunProvider()
    print("🔑 登入玉山 API…")
    provider.login()
    print("✅ 登入成功\n")

    all_results = []
    for symbol in symbols:
        print(f"  → 下載 {symbol}…", end=" ", flush=True)
        df = provider.get_historical_range(symbol, start=args.start, end=args.end or "")
        if df.empty:
            print("❌ 無資料")
            continue

        if strategy_name == "breakout":
            if not {'high', 'low'}.issubset(df.columns):
                print("❌ 缺少 high/low 欄位")
                continue

        df_result = config["func"](df, **params)
        perf = calculate_performance(df_result)

        if perf["total_trades"] > 0:
            all_results.append({
                "symbol": symbol,
                "trades": perf["total_trades"],
                "win_rate": perf["win_rate"],
                "return": perf["total_return"],
            })
            print(f"✅ 交易 {perf['total_trades']} 次, 勝率 {perf['win_rate']:.1%}, 報酬 {perf['total_return']:.2%}")
        else:
            print("❌ 無有效訊號")

    if all_results:
        print("\n" + "=" * 60)
        print("📈 回測總結")
        print("=" * 60)
        total_trades = 0
        win_rates = []
        returns = []
        for r in all_results:
            t = r["trades"]
            w = r["win_rate"]
            rt = r["return"]
            total_trades += t
            win_rates.append(w)
            returns.append(rt)
            print(f"{r['symbol']:6} | 交易: {t:2d} 次 | 勝率: {w:5.1%} | 報酬: {rt:6.2%}")
        print("-" * 60)
        print(f"平均   | 交易: {total_trades:2d} 次 | 勝率: {sum(win_rates)/len(win_rates):5.1%} | 報酬: {sum(returns)/len(returns):6.2%}")
        export_results(all_results, strategy_name)
    else:
        print("\n❌ 所有標的均無有效交易訊號")


if __name__ == "__main__":
    main()
