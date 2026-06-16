"""
布林反轉策略合適標的掃描
掃描台灣前 200 大市值股票，評估對布林反轉策略的適合度
"""
import json, math, os
import numpy as np
import pandas as pd
import yfinance as yf

np.random.seed(42)

END = "2026-06-16"
START_6M = "2026-01-01"
START_2Y = "2024-06-16"

# 台灣前200大市值股票清單
STOCKS = [
    "0050","006208","00878",  # ETF（原配置布林）

    "2330","2454","2317","2382","2881","2886","2882","2891","2892","2885",
    "2884","2887","2890","2883","2880","5880","5871","5876","6005","2834",
    "2308","2303","2345","2376","2357","2412","2409","3231","2383","2385",
    "2301","2327","2356","2360","2368","2377","2379","2388","2395","2408",
    "2474","2489","3008","3017","3022","3034","3037","3044","3045","3050",
    "3189","3229","3260","3296","3312","3324","3406","3443","3454","3481",
    "3532","3533","3545","3576","3583","3596","3617","3653","3661","3673",
    "3702","3706","3711","3715","4904","4915","4927","4938","4943","4958",
    "4961","4966","4976","4977","4989","5007","5215","5234","5243","5269",
    "5274","5288","5347","5351","5371","5388","5434","5469","5483","5534",
    "5536","5607","5608","5876","5880","5907","5916","6005","6116","6147",
    "6155","6166","6176","6189","6191","6195","6202","6206","6213","6239",
    "6257","6269","6271","6278","6285","6405","6409","6412","6415","6431",
    "6446","6456","6477","6488","6491","6505","6515","6525","6531","6533",
    "6541","6552","6573","6585","6615","6645","6655","6669","6679","6706",
    "6719","6742","6754","6756","6768","6770","6789","6799","6805","6806",
    "6830","6854","6861","6895","6901","6914","6928","6933","6937","6972",
    "8028","8046","8069","8105","8112","8114","8131","8150","8163","8210",
    "8215","8341","8443","8454","8464","8473","8476","8499","8926","8996",
    "9904","9907","9910","9914","9917","9921","9924","9925","9927","9940",
    "9941","9943","9945","9958",
]

# 已知特定策略配置的標的（排除不用布林）
BOLLINGER_STOCKS = {"0050","006208","00878"}
ALREADY_USED = {"0050","006208","00878","2330","2454","2881","2886","2382"}

def load_data(sym, start, end):
    yf_sym = sym + ".TW"
    try:
        df = yf.download(yf_sym, start=start, end=end, auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty or len(df) < 50:
            return None
        df = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
        df.index = pd.to_datetime(df.index)
        return df
    except:
        return None

def calc_rsi(series, period=5):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calc_adx(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    plus_dm = high.diff()
    minus_dm = low.diff().abs() * -1
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.abs().rolling(window=period).mean() / atr)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx = dx.rolling(window=period).mean()
    return adx

def score_bollinger(df):
    df = df.copy()
    if len(df) < 100:
        return None
    
    n = len(df)
    
    # 布林通道
    df['MA'] = df['close'].rolling(window=20, min_periods=1).mean()
    df['Std'] = df['close'].rolling(window=20, min_periods=1).std()
    df['Upper'] = df['MA'] + 2.0 * df['Std']
    df['Lower'] = df['MA'] - 2.0 * df['Std']
    
    # 布林寬度（波動率指標）
    df['BB_Width'] = (df['Upper'] - df['Lower']) / df['MA']
    avg_bb_width = df['BB_Width'].iloc[20:].mean()
    
    # 布林接觸次數（適合反轉策略的訊號）
    recent = df.iloc[-180:]  # 近 6 個月
    band_touches = ((recent['close'] > recent['Upper']).sum() +
                    (recent['close'] < recent['Lower']).sum())
    touch_freq = band_touches / len(recent)
    
    # 近期訊號模擬（最後 180 天）
    df['RSI'] = calc_rsi(df['close'], 5)
    df['signal'] = 0
    buy = (df['close'] < df['Lower']) & (df['RSI'] < 30)
    sell = (df['close'] > df['Upper']) & (df['RSI'] > 70)
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    recent_df = df.iloc[-180:]
    trades = recent_df[recent_df['signal'] != 0].copy()
    
    if len(trades) < 2:
        return None
    
    # 計算交易報酬（訊號隔日報酬）
    trades['next_ret'] = 0.0
    for i in range(len(trades)):
        idx = trades.index[i]
        pos = df.index.get_loc(idx)
        if isinstance(pos, slice):
            pos = pos.start
        next_pos = pos + 1
        if next_pos < len(df):
            next_date = df.index[next_pos]
            this_close = df.loc[idx, 'close']
            next_close = df.loc[next_date, 'close']
            if trades.loc[idx, 'signal'] == 1:
                trades.loc[idx, 'next_ret'] = (next_close - this_close) / this_close
            else:
                trades.loc[idx, 'next_ret'] = (this_close - next_close) / this_close
    
    win_rate = (trades['next_ret'] > 0).mean()
    avg_return = trades['next_ret'].mean()
    total_return = float(np.prod(1 + trades['next_ret'].values) - 1) if len(trades) > 0 else 0
    
    # ADX 趨勢強度（低 = 盤整 = 適合均值回歸）
    adx_series = calc_adx(df)
    recent_adx = adx_series.iloc[-60:].mean() if len(adx_series) >= 60 else adx_series.mean()
    
    # RSI 擺盪品質（RSI 是否在兩端之間擺動）
    rsi = df['RSI'].iloc[-180:]
    rsi_overshoot = ((rsi < 30).sum() + (rsi > 70).sum()) / len(rsi)
    
    # 綜合評分
    # 正評分因素：低 ADX（盤整）、高觸及頻率、RSI 擺盪
    # 負評分因素：高 ADX（趨勢）、過寬或過窄的布林
    score = 0
    score += max(0, 1.0 - recent_adx / 30) * 30  # ADX < 20 加分
    score += touch_freq * 200                     # 觸及頻率加分
    score += rsi_overshoot * 50                   # RSI 極端值比例加分
    score += min(win_rate, 0.7) * 30              # 勝率加分（上限 70%）
    score += max(0, min(avg_return * 500, 20))    # 平均報酬加分
    
    # 扣分：波動過大或過小
    if avg_bb_width < 0.02:
        score -= 15
    elif avg_bb_width > 0.10:
        score -= 10
    
    # 保證金不足的罰分
    if len(trades) < 5:
        score *= 0.7
    
    return {
        "score": round(score, 1),
        "adx": round(recent_adx, 1),
        "touch_freq": round(touch_freq * 100, 1),
        "win_rate": round(win_rate * 100, 1),
        "avg_return": round(avg_return * 100, 2),
        "total_return": round(total_return * 100, 2),
        "n_trades": len(trades),
        "bb_width": round(avg_bb_width * 100, 2),
        "rsi_extreme": round(rsi_overshoot * 100, 1),
    }

print("掃描布林反轉合適標的（近 6 個月）...\n")

results = []
for sym in STOCKS:
    df = load_data(sym, START_6M, END)
    if df is None:
        continue
    s = score_bollinger(df)
    if s is None:
        continue
    results.append({"symbol": sym, **s})

results.sort(key=lambda x: x["score"], reverse=True)

# 輸出
print(f"掃描 {len(STOCKS)} 檔，成功獲取 {len(results)} 檔\n")

print("=" * 90)
print(f"{'排名':>3} {'代號':>6} {'總分':>5} {'ADX':>5} {'觸及%':>6} {'勝率%':>6} {'均報酬':>7} {'總報酬':>7} {'交易':>4} {'布林寬':>7} {'RSI極端':>7}")
print("=" * 90)
for i, r in enumerate(results[:30]):
    tag = " ⬅️ 已用" if r["symbol"] in ALREADY_USED else ""
    print(f"{i+1:3d} {r['symbol']:>6} {r['score']:5.1f} {r['adx']:5.1f} {r['touch_freq']:5.1f}% {r['win_rate']:5.1f}% {r['avg_return']:6.2f}% {r['total_return']:6.2f}% {r['n_trades']:4d} {r['bb_width']:6.2f}% {r['rsi_extreme']:6.1f}%{tag}")

# 已配置的布林標的排名
print("\n\n=== 目前布林配置的 3 檔排名 ===")
for r in results:
    if r["symbol"] in BOLLINGER_STOCKS:
        idx = results.index(r) + 1
        print(f"  {r['symbol']} — 第 {idx} 名（總分 {r['score']}）")

# 前 200 中未使用的排名（給建議）
print("\n\n=== 未使用但高分的標的（可考慮替換）===")
new_suggestions = [r for r in results if r["symbol"] not in ALREADY_USED and r["score"] > 30]
for i, r in enumerate(new_suggestions[:15]):
    print(f"  {i+1:2d}. {r['symbol']:>6} — 總分 {r['score']:.0f} | ADX {r['adx']} | 觸及 {r['touch_freq']:.0f}% | 勝率 {r['win_rate']:.0f}%")

# 輸出 HTML
top30 = results[:30]
for i, r in enumerate(top30):
    r["rank"] = i + 1
    r["in_portfolio"] = r["symbol"] in BOLLINGER_STOCKS
    r["used"] = r["symbol"] in ALREADY_USED
j_results = json.dumps([{
    "rank": i+1, "symbol": r["symbol"], "score": r["score"],
    "adx": r["adx"], "touch_freq": r["touch_freq"],
    "win_rate": r["win_rate"], "avg_return": r["avg_return"],
    "total_return": r["total_return"], "n_trades": r["n_trades"],
    "bb_width": r["bb_width"], "rsi_extreme": r["rsi_extreme"],
    "in_portfolio": r["symbol"] in BOLLINGER_STOCKS,
    "used": r["symbol"] in ALREADY_USED,
} for r in top30])

html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>布林反轉策略 — 合適標的掃描</title>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:"Inter",-apple-system,sans-serif;background:#0d1117;color:#e6edf3;display:flex;justify-content:center;padding:40px 20px}}
  .container{{max-width:1060px;width:100%}}
  h1{{font-size:22px;font-weight:600;margin-bottom:4px}}
  .sub{{color:#8b949e;font-size:14px;margin-bottom:20px}}
  .chart-wrap{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin-bottom:20px;overflow-x:auto}}
  table{{width:100%;border-collapse:collapse;font-size:12px}}
  th{{text-align:left;color:#8b949e;font-weight:500;padding:6px 8px;border-bottom:1px solid #21262d;white-space:nowrap}}
  td{{padding:6px 8px;border-bottom:1px solid #21262d;font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}}
  td:first-child{{text-align:center;font-weight:500}}
  td:nth-child(2){{text-align:left;font-weight:600}}
  .tag{{display:inline-block;font-size:10px;padding:1px 6px;border-radius:3px;margin-left:4px}}
  .tag.active{{background:#1c3a1c;color:#7ee787}}
  .tag.used{{background:#3a2a1c;color:#f0883e}}
  .pos{{color:#7ee787}}.neg{{color:#f85149}}
  .score-bar{{display:inline-block;height:6px;border-radius:3px;vertical-align:middle;margin-right:6px}}
</style>
</head>
<body>
<div class="container">
  <h1>📊 布林反轉策略 — 合適標的掃描</h1>
  <div class="sub">近 6 個月數據 · 評分依據：低 ADX（盤整）+ 高觸及頻率 + RSI 擺盪 + 勝率</div>

  <div class="chart-wrap">
    <table>
      <thead><tr>
        <th>#</th><th>代號</th><th>總分</th><th>ADX</th><th>觸及%</th><th>勝率%</th><th>均報酬</th><th>總報酬</th><th>交易</th><th>布林寬%</th><th>RSI極端%</th><th></th>
      </tr></thead>
      <tbody>
"""
for r in top30:
    s = r["score"]
    bar_color = "#7ee787" if s >= 50 else "#f0883e" if s >= 30 else "#f85149"
    bar_w = max(4, int(s * 1.2))
    tc = "pos" if r["total_return"] > 0 else "neg"
    ac = "pos" if r["avg_return"] > 0 else "neg"
    tag = ""
    if r["in_portfolio"]:
        tag = '<span class="tag active">已配置</span>'
    elif r["used"]:
        tag = '<span class="tag used">其他策略</span>'
    html += f"""        <tr>
          <td>{r['rank']}</td>
          <td>{r['symbol']} {tag}</td>
          <td><span class="score-bar" style="width:{bar_w}px;background:{bar_color}"></span>{s:.0f}</td>
          <td>{r['adx']:.1f}</td>
          <td>{r['touch_freq']:.1f}%</td>
          <td>{r['win_rate']:.0f}%</td>
          <td class="{ac}">{r['avg_return']:+.2f}%</td>
          <td class="{tc}">{r['total_return']:+.2f}%</td>
          <td>{r['n_trades']}</td>
          <td>{r['bb_width']:.2f}%</td>
          <td>{r['rsi_extreme']:.0f}%</td>
        </tr>"""

html += """      </tbody>
    </table>
  </div>
</div></body></html>
"""

path = os.path.join(os.path.dirname(__file__), "scan_bollinger_candidates.html")
with open(path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"\n✅ 已輸出: scan_bollinger_candidates.html (前 30 名熱力圖)")
