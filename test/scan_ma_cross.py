"""
MA Cross 參數掃描
fast_period: 5, 10, 15, 20
slow_period: 20, 30, 40, 50, 60
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import itertools
import pandas as pd
from config.symbols import ALL_SYMBOLS, get_yahoo_suffix
from data.yahoo_loader import load_historical_data
from strategies.ma_cross import ma_cross_strategy

START_DATE = "2023-01-01"

def calculate_performance(df: pd.DataFrame) -> dict:
    if df.empty or (df['signal'] == 0).all():
        return {"trades": 0, "win_rate": 0.0, "return": 0.0}
    df = df.copy()
    df['next_close'] = df['close'].shift(-1)
    df['trade_return'] = 0.0
    buy = df['signal'] == 1
    sell = df['signal'] == -1
    if buy.any():
        df.loc[buy, 'trade_return'] = (df.loc[buy, 'next_close'] - df.loc[buy, 'close']) / df.loc[buy, 'close']
    if sell.any():
        df.loc[sell, 'trade_return'] = (df.loc[sell, 'close'] - df.loc[sell, 'next_close']) / df.loc[sell, 'close']
    trades = df[df['signal'] != 0]
    if trades.empty:
        return {"trades": 0, "win_rate": 0.0, "return": 0.0}
    return {
        "trades": len(trades),
        "win_rate": (trades['trade_return'] > 0).sum() / len(trades),
        "return": trades['trade_return'].sum()
    }

FAST_VALS = [5, 10, 15, 20]
SLOW_VALS = [20, 30, 40, 50, 60]

print("=" * 80)
print("MA Cross 參數掃描")
print(f"資料期間: {START_DATE} ~ 今日")
print(f"標的: {', '.join(ALL_SYMBOLS)}")
print(f"fast_period: {FAST_VALS}")
print(f"slow_period: {SLOW_VALS}")
print("=" * 80)

# 先載入所有標的資料一次
data_cache = {}
for symbol in ALL_SYMBOLS:
    yf_symbol = symbol + get_yahoo_suffix(symbol)
    df = load_historical_data(yf_symbol, start=START_DATE)
    if not df.empty:
        data_cache[symbol] = df
        print(f"  ✓ {symbol} ({yf_symbol}): {len(df)} 筆")
    else:
        print(f"  ✗ {symbol}: 資料為空，跳過")

if not data_cache:
    print("❌ 無可用資料")
    exit(1)

results = []
total_combos = len(FAST_VALS) * len(SLOW_VALS)
combo_idx = 0

for fast, slow in itertools.product(FAST_VALS, SLOW_VALS):
    if fast >= slow:
        continue  # 快線必須小於慢線
    combo_idx += 1
    params = {"fast_period": fast, "slow_period": slow, "atr_threshold": 0.005}

    all_returns = []
    all_wins = []
    all_trades = []
    valid_symbols = 0

    for symbol, df in data_cache.items():
        result_df = ma_cross_strategy(df, **params)
        perf = calculate_performance(result_df)
        if perf["trades"] > 0:
            all_returns.append(perf["return"])
            all_wins.append(perf["win_rate"])
            all_trades.append(perf["trades"])
            valid_symbols += 1

    avg_return = sum(all_returns) / len(all_returns) if all_returns else 0
    avg_win_rate = sum(all_wins) / len(all_wins) if all_wins else 0
    total_trades = sum(all_trades)
    positive_ratio = sum(1 for r in all_returns if r > 0) / len(all_returns) if all_returns else 0

    results.append({
        "fast": fast,
        "slow": slow,
        "valid_symbols": valid_symbols,
        "total_trades": total_trades,
        "avg_win_rate": avg_win_rate,
        "avg_return": avg_return,
        "positive_ratio": positive_ratio,
        "return_per_trade": avg_return / total_trades if total_trades > 0 else 0,
    })

    print(f"  [{combo_idx}/{total_combos}] fast={fast:2d} slow={slow:2d}  "
          f"報酬={avg_return:>7.2%} 勝率={avg_win_rate:>5.1%} 交易={total_trades:3d} "
          f"正報酬比={positive_ratio:>4.0%}")

# 排名：依 avg_return 降序
results.sort(key=lambda r: r["avg_return"], reverse=True)

print("\n" + "=" * 80)
print("🏆 參數排名（依平均報酬降序）")
print("=" * 80)
print(f"{'排名':>4} {'fast':>4} {'slow':>4} {'標的數':>6} {'交易次數':>8} {'勝率':>6} {'報酬':>8} {'正報酬比':>8} {'每次報酬':>8}")
print("-" * 80)
for rank, r in enumerate(results, 1):
    print(f"{rank:4d} {r['fast']:4d} {r['slow']:4d} {r['valid_symbols']:6d} {r['total_trades']:8d} "
          f"{r['avg_win_rate']:5.1%} {r['avg_return']:7.2%} {r['positive_ratio']:7.0%} {r['return_per_trade']:7.4f}")

print("=" * 80)

# 存 CSV
import csv, os
from datetime import datetime
os.makedirs("results", exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
path = f"results/ma_cross_scan_{ts}.csv"
with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=[
        "fast", "slow", "valid_symbols", "total_trades",
        "avg_win_rate", "avg_return", "positive_ratio", "return_per_trade"])
    w.writeheader()
    w.writerows(results)
print(f"📁 CSVsaved to: {path}")
