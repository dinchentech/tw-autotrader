"""
Walk-Forward 驗證（無 look-ahead bias）
  Step 1: 只用訓練期 2020-2021 掃描參數
  Step 2: 最佳參數 → 驗證期 2022
  Step 3: 最佳參數 → 測試期 2023-2024
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import itertools
import pandas as pd
import yfinance as yf
from config.symbols import ALL_SYMBOLS, get_yahoo_suffix
from strategies.ma_cross import ma_cross_strategy

def load_data(symbol: str, start: str, end: str) -> pd.DataFrame:
    try:
        df = yf.download(symbol, start=start, end=end, auto_adjust=True)
        if df.empty:
            return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume"
        })
        return df
    except Exception as e:
        print(f"❌ 載入 {symbol} 失敗: {e}")
        return pd.DataFrame()

def calc_perf(df: pd.DataFrame) -> dict:
    if df.empty or (df['signal'] == 0).all():
        return {"trades": 0, "win_rate": 0.0, "total_return": 0.0}
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
        return {"trades": 0, "win_rate": 0.0, "total_return": 0.0}
    return {
        "trades": len(trades),
        "win_rate": (trades['trade_return'] > 0).sum() / len(trades),
        "total_return": trades['trade_return'].sum(),
    }

# ============================================================
# Step 0: 載入全部資料
# ============================================================
print("📥 載入資料 2020-01-01 ~ 2025-01-01 ...")
full_data = {}
for symbol in ALL_SYMBOLS:
    yf_symbol = symbol + get_yahoo_suffix(symbol)
    df = load_data(yf_symbol, start="2020-01-01", end="2025-01-01")
    if not df.empty:
        full_data[symbol] = df
        print(f"  ✓ {symbol}: {len(df)} 筆")
    else:
        print(f"  ✗ {symbol}: 無資料")

TRAIN = ("2020-01-01", "2021-12-31")
VAL   = ("2022-01-01", "2022-12-31")
TEST  = ("2023-01-01", "2024-12-31")

# ============================================================
# Step 1: 只用訓練期掃描參數
# ============================================================
FAST_VALS = [5, 10, 15, 20]
SLOW_VALS = [20, 30, 40, 50, 60]

print(f"\n{'='*70}")
print("🔍 Step 1: 訓練期掃描參數（2020-2021）")
print(f"{'='*70}")

scan_results = []
total = len(FAST_VALS) * len(SLOW_VALS)
for i, (fast, slow) in enumerate(itertools.product(FAST_VALS, SLOW_VALS), 1):
    if fast >= slow:
        continue
    params = {"fast_period": fast, "slow_period": slow, "atr_threshold": 0.005}
    returns = []
    wins = []
    trades = []
    for symbol, df in full_data.items():
        result_df = ma_cross_strategy(df.loc[TRAIN[0]:TRAIN[1]].copy(), **params)
        perf = calc_perf(result_df)
        if perf["trades"] > 0:
            returns.append(perf["total_return"])
            wins.append(perf["win_rate"])
            trades.append(perf["trades"])
    avg_ret = sum(returns) / len(returns) if returns else -999
    avg_win = sum(wins) / len(wins) if wins else 0
    total_tr = sum(trades)
    positive_ratio = sum(1 for r in returns if r > 0) / len(returns) if returns else 0
    scan_results.append({
        "fast": fast, "slow": slow,
        "avg_return": avg_ret, "avg_win_rate": avg_win,
        "total_trades": total_tr, "positive_ratio": positive_ratio,
    })
    print(f"  [{i:2d}/{total}] fast={fast:2d} slow={slow:2d}  "
          f"報酬={avg_ret:>+7.2%}  勝率={avg_win:5.1%}  正報酬比={positive_ratio:>4.0%}")

scan_results.sort(key=lambda r: r["avg_return"], reverse=True)
best = scan_results[0]
BEST_FAST, BEST_SLOW = best["fast"], best["slow"]
BEST_PARAMS = {"fast_period": BEST_FAST, "slow_period": BEST_SLOW, "atr_threshold": 0.005}

print(f"\n🏆 訓練期最佳參數: fast={BEST_FAST}, slow={BEST_SLOW}")
print(f"   訓練期報酬: {best['avg_return']:+.2%}  勝率: {best['avg_win_rate']:.1%}  正報酬比: {best['positive_ratio']:.0%}")

# ============================================================
# Step 2: 在驗證期 + 測試期驗證
# ============================================================
print(f"\n{'='*70}")
print(f"📋 Step 2: Walk-Forward 驗證（參數 fast={BEST_FAST}, slow={BEST_SLOW}）")
print(f"{'='*70}")

all_rows = []
for pname, start, end in [("訓練", *TRAIN), ("驗證", *VAL), ("測試", *TEST)]:
    print(f"\n  📅 {pname}期: {start} ~ {end}")
    sym_results = []
    for symbol, df_full in full_data.items():
        df = df_full.loc[start:end].copy()
        if df.empty:
            continue
        result_df = ma_cross_strategy(df, **BEST_PARAMS)
        perf = calc_perf(result_df)
        sym_results.append({**perf, "symbol": symbol})
        if perf["trades"] > 0:
            print(f"    {symbol:6s} | 交易 {perf['trades']:3d} 次 | "
                  f"勝率 {perf['win_rate']:5.1%} | 總報酬 {perf['total_return']:>+7.2%}")
        else:
            print(f"    {symbol:6s} | ❌ 無交易訊號")

    valid = [r for r in sym_results if r["trades"] > 0]
    if valid:
        avg_ret = sum(r["total_return"] for r in valid) / len(valid)
        avg_win = sum(r["win_rate"] for r in valid) / len(valid)
        total_tr = sum(r["trades"] for r in valid)
        pos = sum(1 for r in valid if r["total_return"] > 0)
    else:
        avg_ret = avg_win = total_tr = pos = 0
    all_rows.append({
        "period": pname, "start": start, "end": end,
        "symbols": len(valid),
        "avg_return": avg_ret, "avg_win_rate": avg_win,
        "total_trades": total_tr, "positive": pos,
    })
    if valid:
        print(f"\n  📊 => 平均報酬 {avg_ret:>+7.2%}  勝率 {avg_win:5.1%}  "
              f"正報酬 {pos}/{len(valid)} ({pos/len(valid):.0%})")

# ============================================================
# 總結
# ============================================================
print(f"\n{'='*70}")
print("📋 Walk-Forward 驗證總結（參數由訓練期獨立選出）")
print(f"{'='*70}")
print(f"{'期間':6s} {'區間':24s} {'有交易':>6} {'平均報酬':>8} {'勝率':>6} {'交易次數':>7} {'正報酬比':>8}")
print("-"*70)
for r in all_rows:
    print(f"{r['period']:6s} {r['start']}~{r['end']}  "
          f"{r['symbols']:3d}檔   "
          f"{r['avg_return']:>+7.2%}  "
          f"{r['avg_win_rate']:5.1%}  "
          f"{r['total_trades']:4d}次   "
          f"{r['positive']}/{r['symbols']}")

# 存 CSV
import csv, os
from datetime import datetime
os.makedirs("results", exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
path = f"results/ma_cross_walkforward_honest_{ts}.csv"
with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["period", "start", "end", "symbols", "avg_return", "avg_win_rate", "total_trades", "positive"])
    w.writeheader()
    w.writerows(all_rows)
print(f"\n📁 CSV: {path}")

# 也存掃描結果
path2 = f"results/ma_cross_train_scan_{ts}.csv"
with open(path2, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["fast", "slow", "avg_return", "avg_win_rate", "total_trades", "positive_ratio"])
    w.writeheader()
    w.writerows(scan_results)
print(f"📁 訓練期掃描 CSV: {path2}")
