"""
Walk-Forward 驗證：fast=10, slow=40
  訓練期 2020-2021 → 驗證期 2022 → 測試期 2023-2024
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
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

PARAMS = {"fast_period": 10, "slow_period": 40, "atr_threshold": 0.005}
PERIODS = [
    ("訓練", "2020-01-01", "2021-12-31"),
    ("驗證", "2022-01-01", "2022-12-31"),
    ("測試", "2023-01-01", "2024-12-31"),
]

def calc_perf(df: pd.DataFrame) -> dict:
    if df.empty or (df['signal'] == 0).all():
        return {"trades": 0, "win_rate": 0.0, "total_return": 0.0, "avg_return": 0.0}
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
        return {"trades": 0, "win_rate": 0.0, "total_return": 0.0, "avg_return": 0.0}
    return {
        "trades": len(trades),
        "win_rate": (trades['trade_return'] > 0).sum() / len(trades),
        "total_return": trades['trade_return'].sum(),
        "avg_return": trades['trade_return'].mean(),
    }

# 載入全部資料（一次拉長區間，各期間 slice）
print("📥 載入資料 2020-01-01 ~ 2024-12-31 ...")
data_cache = {}
for symbol in ALL_SYMBOLS:
    yf_symbol = symbol + get_yahoo_suffix(symbol)
    df = load_data(yf_symbol, start="2020-01-01", end="2025-01-01")
    if not df.empty:
        data_cache[symbol] = df
        print(f"  ✓ {symbol}: {len(df)} 筆")
    else:
        print(f"  ✗ {symbol}: 無資料")

# 每個期間各存一列 results
all_periods = []
for pname, start, end in PERIODS:
    print(f"\n{'='*60}")
    print(f"📅 {pname}期: {start} ~ {end}")
    print('='*60)

    symbol_results = []
    for symbol, df_full in data_cache.items():
        df = df_full.loc[start:end].copy()
        if df.empty:
            print(f"  {symbol}: 無此區間資料")
            continue
        result_df = ma_cross_strategy(df, **PARAMS)
        perf = calc_perf(result_df)
        symbol_results.append({**perf, "symbol": symbol})
        if perf["trades"] > 0:
            print(f"  {symbol:6s} | 交易 {perf['trades']:3d} 次 | "
                  f"勝率 {perf['win_rate']:5.1%} | "
                  f"總報酬 {perf['total_return']:7.2%}")
        else:
            print(f"  {symbol:6s} | ❌ 無交易訊號")

    # 彙總
    valid = [r for r in symbol_results if r["trades"] > 0]
    if valid:
        avg_ret = sum(r["total_return"] for r in valid) / len(valid)
        avg_win = sum(r["win_rate"] for r in valid) / len(valid)
        total_trades = sum(r["trades"] for r in valid)
        positive = sum(1 for r in valid if r["total_return"] > 0)
        print(f"\n  📊 {pname}期 彙總 ({len(valid)} 檔有交易):")
        print(f"     平均總報酬: {avg_ret:+.2%}")
        print(f"     平均勝率:   {avg_win:.1%}")
        print(f"     總交易次數: {total_trades}")
        print(f"     正報酬標的: {positive}/{len(valid)} ({positive/len(valid):.0%})")
    else:
        avg_ret = avg_win = total_trades = 0.0
        positive = 0

    all_periods.append({
        "period": pname,
        "start": start,
        "end": end,
        "symbols_with_trades": len(valid),
        "avg_return": avg_ret,
        "avg_win_rate": avg_win,
        "total_trades": total_trades,
        "positive_symbols": positive,
    })

# 總結對照表
print("\n" + "="*60)
print("📋 Walk-Forward 驗證總結")
print("  參數: fast=10, slow=40, atr_threshold=0.005")
print("="*60)
print(f"{'期間':6s} {'區間':24s} {'有交易檔數':>8} {'平均報酬':>8} {'勝率':>6} {'交易次數':>8} {'正報酬比':>8}")
print("-"*60)
for p in all_periods:
    print(f"{p['period']:6s} {p['start']}~{p['end']}  "
          f"{p['symbols_with_trades']:4d}檔     "
          f"{p['avg_return']:>+7.2%}  "
          f"{p['avg_win_rate']:5.1%}  "
          f"{p['total_trades']:5d}次   "
          f"{p['positive_symbols']}/{p['symbols_with_trades']}")

# 存 CSV
import csv, os
from datetime import datetime
os.makedirs("results", exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
path = f"results/ma_cross_walkforward_{ts}.csv"
with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["period", "start", "end", "symbols_with_trades", "avg_return", "avg_win_rate", "total_trades", "positive_symbols"])
    w.writeheader()
    w.writerows(all_periods)
print(f"\n📁 CSV 已儲存: {path}")
