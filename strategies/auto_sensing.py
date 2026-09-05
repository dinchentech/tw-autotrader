"""strategies/auto_sensing.py — 型態感知策略路由器 + 自動感知策略

- route_strategy(df, as_of=None): 「型態感知策略路由器」。依「截至 as_of（預設最後一筆收盤）」
  的股價型態（股價 vs MA20/MA60、20日動能），回傳該股當下最合適的 4 策略之一
  (ma_cross / breakout / bollinger / vwap)。適合「每天開盤前或收盤後」呼叫一次。
- auto_sensing_strategy(df): 「自動感知」策略函式。逐日呼叫 route_strategy 選出當下最適策略，
  並取該策略當日訊號；回傳含 signal 欄位的 DataFrame。可像其他策略函式一樣丟給
  回測/實盤使用（drop-in）。

規則（僅用 ≤ 當日資料，無前瞻）:
  趨勢(價>MA20 且 MA20>MA60 且 20日動能>0)  → 順勢: 20日動能>5% 用 breakout，否則 ma_cross
  否則(盤整/下跌)                          → 回歸: 價<MA20 用 bollinger(買低)，否則 vwap
"""
import pandas as pd

from strategies.ma_cross import ma_cross_strategy
from strategies.breakout import breakout_strategy
from strategies.bollinger import bollinger_reverse_strategy
from strategies.vwap_deviation import vwap_deviation_strategy

UNDERLYING = {
    "ma_cross": ma_cross_strategy,
    "breakout": breakout_strategy,
    "bollinger": bollinger_reverse_strategy,
    "vwap": vwap_deviation_strategy,
}


def route_strategy(df: pd.DataFrame, as_of=None) -> str:
    """型態感知策略路由器：回傳 ['ma_cross','breakout','bollinger','vwap'] 之一。

    df: 日K DataFrame（index=date，至少含 close 欄位；建議也有 open/high/low/volume）。
    as_of: 只看 ≤ as_of 的資料（日期 Timestamp）；None=用 df 最後一筆（適合收盤後）。
    """
    d = df if as_of is None else df.loc[:as_of]
    if len(d) == 0:
        return "ma_cross"
    close = d["close"].astype(float)
    cp = float(close.iloc[-1])
    if cp <= 0:
        return "ma_cross"
    ma20 = float(close.rolling(20, min_periods=1).mean().iloc[-1])
    ma60 = float(close.rolling(60, min_periods=1).mean().iloc[-1])
    ref = float(close.iloc[max(0, len(close) - 21)])
    mom20 = (cp / ref - 1.0) if ref > 0 else 0.0

    trend_up = (cp > ma20) and (ma20 > ma60) and (mom20 > 0)
    if trend_up:
        return "breakout" if mom20 > 0.05 else "ma_cross"
    return "bollinger" if cp < ma20 else "vwap"


def auto_sensing_strategy(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """「自動感知」策略函式：逐日依型態路由到 4 策略之一，並取該策略當日訊號。

    回傳含 signal 欄位（1=買, -1=賣, 0=無）的 DataFrame，可作 drop-in 策略函式。
    """
    df = df.copy()
    signals = {name: UNDERLYING[name](df.copy())["signal"] for name in UNDERLYING}
    out = pd.Series(0, index=df.index)
    for i in range(len(df)):
        form = route_strategy(df.iloc[:i + 1])
        out.iloc[i] = signals[form].iloc[i]
    df["signal"] = out
    return df


if __name__ == "__main__":
    # 快速自檢：載入 2330 範例資料
    import os, sys
    sys.path.insert(0, "/home/frank/tw-autotrader")
    os.chdir("/home/frank/tw-autotrader")
    import scripts.stock_selector_grid as ssg
    df = ssg.load_stock("2330")
    print("2330 近3日路由:", [route_strategy(df, d) for d in df.index[-3:]])
    r = auto_sensing_strategy(df)
    print("auto_sensing_strategy 訊號分布:", r["signal"].value_counts().to_dict())
