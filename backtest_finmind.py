import os
import pandas as pd
from finmind.data import Data
from strategies.vwap_strategy import VWAPDeviationStrategy
from strategies.ma_cross_strategy import MACrossStrategy
from strategies.bollinger_strategy import BollingerReverseStrategy
from strategies.breakout_strategy import BreakoutStrategy

def run_finmind_backtest(symbol: str = "2330", start_date: str = "2023-01-01"):
    """使用 FinMind 執行回測"""
    print(f"📊 開始 FinMind 回測: {symbol}")
    
    # 取得資料
    data_loader = Data()
    finmind_token = os.getenv("FINMIND_API_TOKEN")
    if finmind_token:
        data_loader.login_by_token(api_token=finmind_token)
    else:
        print("⚠️ 未設定 FINMIND_API_TOKEN，使用模擬資料")
        # 建立模擬資料
        dates = pd.date_range(start=start_date, periods=250, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'open': 650 + np.random.randn(250).cumsum(),
            'high': 650 + np.random.randn(250).cumsum() + 5,
            'low': 650 + np.random.randn(250).cumsum() - 5,
            'close': 650 + np.random.randn(250).cumsum(),
            'volume': np.random.randint(1000000, 5000000, 250)
        })
        df = df.set_index('date')
        stock_price = df
    else:
        stock_price = data_loader.taiwan_stock_daily(
            stock_id=symbol,
            start_date=start_date
        )
        if stock_price.empty:
            print(f"❌ {symbol} 無資料")
            return
    
    # 測試四種策略
    strategies = {
        "VWAP Deviation": VWAPDeviationStrategy(sigma_mult=1.5, rsi_period=5),
        "MA Cross": MACrossStrategy(fast_period=9, slow_period=21),
        "Bollinger Reverse": BollingerReverseStrategy(window=20, std_dev=2.0),
        "Breakout": BreakoutStrategy(lookback=20)
    }
    
    results = {}
    for name, strategy in strategies.items():
        try:
            final_equity, total_txn, win_rate, avg_return = strategy.backtest(
                stock_price=stock_price,
                buy_cost=0.001425,  # 買進手續費
                sell_cost=0.004425  # 賣出手續費 + 證交稅
            )
            results[name] = {
                "final_equity": final_equity,
                "total_transactions": total_txn,
                "win_rate": win_rate,
                "avg_return": avg_return
            }
            print(f"\n{name} 策略績效:")
            print(f"  最終權益: {final_equity:.2f}")
            print(f"  交易次數: {total_txn}")
            print(f"  勝率: {win_rate:.2%}")
            print(f"  平均報酬: {avg_return:.2%}")
        except Exception as e:
            print(f"❌ {name} 策略錯誤: {e}")
            results[name] = None
    
    return results

if __name__ == "__main__":
    # 載入環境變數
    from dotenv import load_dotenv
    load_dotenv()
    
    run_finmind_backtest("2330", "2023-01-01")