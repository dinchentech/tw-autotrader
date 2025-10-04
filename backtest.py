# backtest.py
import os
import argparse
import csv
import pandas as pd
from datetime import datetime
from config.symbols import ALL_SYMBOLS, get_yahoo_suffix
from core.strategy_engine import StrategyEngine
from data.yahoo_loader import load_historical_data

# 匯入所有策略
from strategies.vwap_deviation import vwap_deviation_strategy
from strategies.ma_cross import ma_cross_strategy
from strategies.bollinger import bollinger_reverse_strategy
from strategies.breakout import breakout_strategy

# 策略配置映射
STRATEGY_CONFIG = {
    "vwap": {
        "func": vwap_deviation_strategy,
        "params": {"sigma_mult": 1.5, "rsi_period": 5}
    },
    "ma_cross": {
        "func": ma_cross_strategy,
        "params": {"fast_period": 9, "slow_period": 21}
    },
    "bollinger": {
        "func": bollinger_reverse_strategy,
        "params": {"window": 20, "std_dev": 2.0, "rsi_period": 5}
    },
    "breakout": {
        "func": breakout_strategy,
        "params": {"lookback": 20, "atr_period": 14}
    }
}

def get_strategy_from_env_or_args():
    """從環境變數或命令列取得策略名稱"""
    parser = argparse.ArgumentParser(description='TW AutoTrader - Backtest Mode')
    parser.add_argument('--strategy', type=str, default=None,
                        help='選擇策略: vwap, ma_cross, bollinger, breakout')
    parser.add_argument('--start', type=str, default="2023-01-01",
                        help='回測開始日期 (YYYY-MM-DD)')
    args = parser.parse_args()
    
    strategy_name = args.strategy or os.getenv("STRATEGY", "vwap")
    strategy_name = strategy_name.lower()
    
    if strategy_name not in STRATEGY_CONFIG:
        print(f"❌ 無效策略: {strategy_name}，使用預設 'vwap'")
        strategy_name = "vwap"
    
    return strategy_name, args.start

def calculate_performance(df: pd.DataFrame) -> dict:
    """計算策略績效"""
    if df.empty or (df['signal'] == 0).all():
        return {"total_trades": 0, "win_rate": 0.0, "total_return": 0.0}
    
    df = df.copy()
    df['next_close'] = df['close'].shift(-1)
    df['trade_return'] = 0.0
    
    # 買進訊號：下一根K的漲跌幅
    buy_mask = df['signal'] == 1
    if buy_mask.any():
        df.loc[buy_mask, 'trade_return'] = (df.loc[buy_mask, 'next_close'] - df.loc[buy_mask, 'close']) / df.loc[buy_mask, 'close']
    
    # 賣出訊號：下一根K的跌跌幅（做空報酬）
    sell_mask = df['signal'] == -1
    if sell_mask.any():
        df.loc[sell_mask, 'trade_return'] = (df.loc[sell_mask, 'close'] - df.loc[sell_mask, 'next_close']) / df.loc[sell_mask, 'close']
    
    trades = df[df['signal'] != 0]
    if trades.empty:
        return {"total_trades": 0, "win_rate": 0.0, "total_return": 0.0}
    
    total_trades = len(trades)
    win_trades = (trades['trade_return'] > 0).sum()
    win_rate = win_trades / total_trades
    total_return = trades['trade_return'].sum()
    
    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "total_return": total_return
    }

def export_results_to_csv(results: list, strategy_name: str):
    """將回測結果匯出為 CSV"""
    if not results:
        print("⚠️ 無結果可匯出")
        return
    
    os.makedirs("results", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"results/backtest_results_{strategy_name}_{timestamp}.csv"
    
    fieldnames = [
        "symbol", 
        "total_trades", 
        "win_rate", 
        "total_return",
        "avg_return_per_trade"
    ]
    
    for r in results:
        r["avg_return_per_trade"] = r["return"] / r["trades"] if r["trades"] > 0 else 0.0
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = {
                "symbol": r["symbol"],
                "total_trades": r["trades"],
                "win_rate": f"{r['win_rate']:.4f}",
                "total_return": f"{r['return']:.4f}",
                "avg_return_per_trade": f"{r['avg_return_per_trade']:.4f}"
            }
            writer.writerow(row)
    
    print(f"\n✅ 績效結果已匯出: {filename}")

def main():
    strategy_name, start_date = get_strategy_from_env_or_args()
    config = STRATEGY_CONFIG[strategy_name]
    
    print(f"📊 開始回測 TW AutoTrader")
    print(f"🎯 使用策略: {strategy_name}")
    print(f"⚙️  策略參數: {config['params']}")
    print(f"📅 回測期間: {start_date} ~ 今日\n")
    
    engine = StrategyEngine(config["func"], **config["params"])
    
    all_results = []
    for symbol in ALL_SYMBOLS:
        yf_symbol = symbol + get_yahoo_suffix(symbol)
        print(f"  → 回測 {symbol} ({yf_symbol})...")
        
        df = load_historical_data(yf_symbol, start=start_date)
        if df.empty:
            print(f"    ⚠️  資料為空，跳過")
            continue
        
        # 確保 breakout 策略有 high/low 欄位
        if strategy_name == "breakout":
            required_cols = ['high', 'low']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                print(f"    ⚠️  缺少欄位 {missing_cols}，跳過")
                continue
        
        df = engine.run(df)
        perf = calculate_performance(df)
        
        if perf["total_trades"] > 0:
            result = {
                "symbol": symbol,
                "trades": perf["total_trades"],
                "win_rate": perf["win_rate"],
                "return": perf["total_return"]
            }
            all_results.append(result)
            print(f"    ✅ 交易次數: {perf['total_trades']}, 勝率: {perf['win_rate']:.1%}, 總報酬: {perf['total_return']:.2%}")
        else:
            print(f"    ❌ 無有效交易訊號")
    
    # 輸出總結與匯出
    if all_results:
        print("\n" + "="*60)
        print("📈 回測總結")
        print("="*60)
        for r in all_results:
            print(f"{r['symbol']:6} | 交易: {r['trades']:2d} 次 | 勝率: {r['win_rate']:5.1%} | 報酬: {r['return']:6.2%}")
        
        avg_win_rate = sum(r['win_rate'] for r in all_results) / len(all_results)
        avg_return = sum(r['return'] for r in all_results) / len(all_results)
        total_trades = sum(r['trades'] for r in all_results)
        print("-"*60)
        print(f"平均   | 交易: {total_trades:2d} 次 | 勝率: {avg_win_rate:5.1%} | 報酬: {avg_return:6.2%}")
        
        export_results_to_csv(all_results, strategy_name)
    else:
        print("\n❌ 所有標的均無有效交易訊號")

if __name__ == "__main__":
    main()