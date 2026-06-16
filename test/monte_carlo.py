"""
蒙地卡羅模擬 — 評估策略穩定性
使用 ma_cross (fast=5, slow=20) 在 2023-2024 測試期
對四大電子股（2330·2454·2317·2382）逐筆交易作靴帶抽樣
"""
import json, random, math, os
import numpy as np
import pandas as pd
import yfinance as yf

random.seed(42)
np.random.seed(42)

STOCKS = ["2330.TW", "2454.TW", "2317.TW", "2382.TW"]
PARAMS = {"fast_period": 5, "slow_period": 20, "atr_threshold": 0.005}
START, END = "2023-01-01", "2025-01-01"
N_SIM = 10000

def load_data(sym, start, end):
    df = yf.download(sym, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})

def run_strategy(df, fast, slow, atr_th):
    df = df.copy()
    df['MA_Fast'] = df['close'].rolling(window=fast, min_periods=1).mean()
    df['MA_Slow'] = df['close'].rolling(window=slow, min_periods=1).mean()
    prev = df['close'].shift(1)
    tr = pd.concat([
        df['high']-df['low'],
        (df['high']-prev).abs(),
        (df['low']-prev).abs()
    ], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14, min_periods=1).mean()
    df['signal'] = 0
    df['prev_fast'] = df['MA_Fast'].shift(1)
    df['prev_slow'] = df['MA_Slow'].shift(1)
    df['volatile_enough'] = (df['ATR']/df['close']) >= atr_th
    gc = (df['MA_Fast'] > df['MA_Slow']) & (df['prev_fast'] <= df['prev_slow']) & df['volatile_enough']
    dc = (df['MA_Fast'] < df['MA_Slow']) & (df['prev_fast'] >= df['prev_slow']) & df['volatile_enough']
    df.loc[gc, 'signal'] = 1
    df.loc[dc, 'signal'] = -1
    df['next_close'] = df['close'].shift(-1)
    df['trade_return'] = 0.0
    df.loc[df['signal']==1, 'trade_return'] = (df['next_close'] - df['close']) / df['close']
    df.loc[df['signal']==-1, 'trade_return'] = (df['close'] - df['next_close']) / df['close']
    trades = df[df['signal'] != 0].copy()
    return trades['trade_return'].dropna().values

print("📥 載入資料並執行策略 ...")
stock_returns = {}
for sym in STOCKS:
    df = load_data(sym, START, END)
    if df.empty:
        continue
    rets = run_strategy(df, PARAMS["fast_period"], PARAMS["slow_period"], PARAMS["atr_threshold"])
    stock_returns[sym] = np.array(rets, dtype=float)
    ur = float(np.prod(1 + stock_returns[sym]) - 1)
    wr = float(np.mean(rets > 0)) if len(rets) > 0 else 0
    print(f"  {sym}: {len(rets)} 筆交易, 總報酬 {ur:+.2%}, 勝率 {wr:.0%}")

stock_list = list(stock_returns.keys())
n_stocks = len(stock_list)
print(f"\n  共 {n_stocks} 檔股票, 合計 {sum(len(v) for v in stock_returns.values())} 筆交易")

def stock_equity_dd(selected_seqs, weights):
    n = max(len(s) for s in selected_seqs)
    eq = np.zeros(n)
    w_sum = 0.0
    for seq, w in zip(selected_seqs, weights):
        compounded = np.cumprod(1 + np.array(seq))
        padded = np.ones(n)
        padded[:len(compounded)] = compounded
        if len(compounded) < n:
            padded[len(compounded):] = compounded[-1]
        eq += w * padded
        w_sum += w
    eq /= w_sum
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    max_dd = float(np.max(dd))
    total_ret = float(eq[-1] - 1)
    return total_ret, max_dd

actual_seqs = [stock_returns[sym] for sym in stock_list]
actual_weights = [1.0] * len(stock_list)
actual_total, actual_mdd = stock_equity_dd(actual_seqs, actual_weights)

print(f"\n  實際等權重組合報酬: {actual_total:+.2%}, 最大回撤: {actual_mdd:.2%}")

print(f"\n  執行 {N_SIM:,} 次蒙地卡羅（股票層級靴帶抽樣）...")

sim_rets = []
sim_dds = []

for _ in range(N_SIM):
    idx = np.random.choice(n_stocks, size=n_stocks, replace=True)
    chosen_seqs = [stock_returns[stock_list[i]] for i in idx]
    chosen_w = [1.0] * n_stocks
    ret, mdd = stock_equity_dd(chosen_seqs, chosen_w)
    sim_rets.append(ret)
    sim_dds.append(mdd)

boot = np.array(sim_rets)
dds = np.array(sim_dds)

def report_boot(arr, label, actual):
    print(f"\n  {label}:")
    print(f"    平均:    {np.mean(arr):+.4f}")
    print(f"    中位數:  {np.median(arr):+.4f}")
    print(f"    標準差:  {np.std(arr):.4f}")
    print(f"    P5:      {np.percentile(arr, 5):+.4f}")
    print(f"    P25:     {np.percentile(arr, 25):+.4f}")
    print(f"    P75:     {np.percentile(arr, 75):+.4f}")
    print(f"    P95:     {np.percentile(arr, 95):+.4f}")
    pct = sum(1 for v in arr if v > 0) / len(arr)
    print(f"    正報酬機率: {pct:.1%}")
    rank = sum(1 for v in arr if v <= actual) / len(arr)
    print(f"    實際值排名: {rank:.1%}（實際值 > {rank:.1%} 的模擬）")
    print(f"    Sharpe-like: {np.mean(arr) / np.std(arr) * math.sqrt(252 / n_stocks) if np.std(arr) > 0 else 0:.2f}（組合層級）")
    return {
        "mean": round(np.mean(arr), 4),
        "median": round(np.median(arr), 4),
        "std": round(np.std(arr), 4),
        "p5": round(np.percentile(arr, 5), 4),
        "p25": round(np.percentile(arr, 25), 4),
        "p75": round(np.percentile(arr, 75), 4),
        "p95": round(np.percentile(arr, 95), 4),
        "pos_prob": round(pct, 4),
        "actual_rank": round(rank, 4),
        "sharpe": round(np.mean(arr) / np.std(arr) * math.sqrt(252 / n_stocks) if np.std(arr) > 0 else 0, 2),
    }

def report_dd(arr, label, actual_mdd):
    print(f"\n  {label}:")
    print(f"    平均最大回撤: {np.mean(arr):.2%}")
    print(f"    中位數最大回撤: {np.median(arr):.2%}")
    print(f"    標準差:        {np.std(arr):.2%}")
    print(f"    P5:            {np.percentile(arr, 5):.2%}")
    print(f"    P25:           {np.percentile(arr, 25):.2%}")
    print(f"    P75:           {np.percentile(arr, 75):.2%}")
    print(f"    P95:           {np.percentile(arr, 95):.2%}")
    rank = sum(1 for v in arr if v >= actual_mdd) / len(arr)
    print(f"    實際最大回撤 {actual_mdd:.2%} > {rank:.1%} 的模擬（排名越低表示回撤控制越好）")
    return {
        "mean": round(np.mean(arr), 4),
        "median": round(np.median(arr), 4),
        "std": round(np.std(arr), 4),
        "p5": round(np.percentile(arr, 5), 4),
        "p25": round(np.percentile(arr, 25), 4),
        "p75": round(np.percentile(arr, 75), 4),
        "p95": round(np.percentile(arr, 95), 4),
        "actual_mdd": round(actual_mdd, 4),
        "actual_rank": round(rank, 4),
    }

print("=" * 50)
boot_stat = report_boot(boot, "📦 股票層級靴帶抽樣（Stock Bootstrap）", actual_total)
print("-" * 50)
dd_stat = report_dd(dds, "⬇️ 最大回撤分析", actual_mdd)

hist_bins = 50
boot_hist_counts, boot_hist_edges = np.histogram(boot, bins=hist_bins)
hist_points = [
    {"x": round((boot_hist_edges[i] + boot_hist_edges[i+1]) / 2, 4), "y": int(boot_hist_counts[i])}
    for i in range(len(boot_hist_counts))
]

dd_bins = 50
dd_hist_counts, dd_hist_edges = np.histogram(dds, bins=dd_bins)
dd_hist_points = [
    {"x": round((dd_hist_edges[i] + dd_hist_edges[i+1]) / 2, 4), "y": int(dd_hist_counts[i])}
    for i in range(len(dd_hist_counts))
]

# 各股票詳細資料
stock_details = []
for sym in stock_list:
    seq = stock_returns[sym]
    details = {
        "symbol": sym.replace(".TW", ""),
        "trades": len(seq),
        "total_return": round(float(np.prod(1 + seq) - 1), 4),
        "win_rate": round(float(np.mean(seq > 0)), 4),
    }
    stock_details.append(details)

# ── 生成 HTML ──
html_parts = []
html_parts.append("""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>蒙地卡羅模擬 — 策略穩定性評估</title>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:"Inter",-apple-system,"Segoe UI",system-ui,sans-serif;background:#0d1117;color:#e6edf3;display:flex;justify-content:center;padding:40px 20px}
  .container{max-width:960px;width:100%}
  h1{font-size:22px;font-weight:600;letter-spacing:-0.3px;color:#f0f6fc;margin-bottom:4px}
  .sub{font-size:14px;color:#8b949e;margin-bottom:24px}

  .summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:20px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;text-align:center}
  .card .val{font-size:24px;font-weight:600}
  .card .lbl{font-size:11px;color:#8b949e;margin-top:4px}
  .card .val.green{color:#7ee787}.card .val.red{color:#f85149}.card .val.orange{color:#f0883e}.card .val.blue{color:#58a6ff}

  .chart-wrap{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin-bottom:20px}
  canvas{display:block;width:100%;height:auto}

  .stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
  .stat-box{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px}
  .stat-box h3{font-size:13px;font-weight:600;color:#f0f6fc;margin-bottom:10px}
  .stat-row{display:flex;justify-content:space-between;padding:4px 0;font-size:13px;border-bottom:1px solid #1c2128}
  .stat-row:last-child{border-bottom:none}
  .stat-row .lbl{color:#8b949e}
  .stat-row .val{font-variant-numeric:tabular-nums;font-weight:500}

  .twrap{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin-bottom:20px}
  .twrap h3{font-size:14px;font-weight:600;color:#f0f6fc;margin-bottom:12px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{text-align:left;color:#8b949e;font-weight:500;padding:6px 8px;border-bottom:1px solid #21262d}
  td{padding:6px 8px;border-bottom:1px solid #21262d;font-variant-numeric:tabular-nums}
  .num{text-align:right}

  .method-tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:4px;margin-left:6px}
  .method-tag.boot{background:#1c3a1c;color:#7ee787}
  .method-tag.shuf{background:#1c2a3a;color:#58a6ff}
  .method-tag.act{background:#3a2a1c;color:#f0883e}

  @media(max-width:640px){.stats-grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="container">
""")

j_boot = json.dumps(boot_stat, ensure_ascii=False)
j_dd = json.dumps(dd_stat, ensure_ascii=False)
j_hist = json.dumps(hist_points, ensure_ascii=False)
j_ddhist = json.dumps(dd_hist_points, ensure_ascii=False)
j_stock = json.dumps(stock_details, ensure_ascii=False)

html_parts.append(f"""
<h1>蒙地卡羅模擬 — 策略穩定性評估</h1>
<div class="sub">ma_cross (fast=5, slow=20) · 測試期 2023-2024 · 四大電子股 · {N_SIM:,} 次模擬</div>

<div class="summary">
  <div class="card">
    <div class="val green">{actual_total:+.2%}</div>
    <div class="lbl">📊 實際策略總報酬 <span class="method-tag act">實際</span></div>
  </div>
  <div class="card">
    <div class="val orange">{boot_stat['median']:+.2%}</div>
    <div class="lbl">🎯 靴帶抽樣中位數 <span class="method-tag boot">MC</span></div>
  </div>
  <div class="card">
    <div class="val">{boot_stat['pos_prob']:.0%}</div>
    <div class="lbl">📈 靴帶模擬正報酬機率</div>
  </div>
  <div class="card">
    <div class="val blue">{boot_stat['actual_rank']:.0%}</div>
    <div class="lbl">📈 實際值 > X% 的模擬結果</div>
  </div>
</div>
""")

html_parts.append("""
<div class="chart-wrap">
  <canvas id="chart" width="920" height="420"></canvas>
</div>
<div class="chart-wrap">
  <canvas id="chartDD" width="920" height="420"></canvas>
</div>
""")

# Statistics side-by-side
html_parts.append("""
<div class="stats-grid">
  <div class="stat-box">
    <h3>📦 靴帶抽樣 <span class="method-tag boot">Bootstrap</span></h3>
    <div class="stat-row"><span class="lbl">模擬次數</span><span class="val">{N_SIM:,}</span></div>
    <div class="stat-row"><span class="lbl">平均報酬</span><span class="val">{boot_stat['mean']:+.2%}</span></div>
    <div class="stat-row"><span class="lbl">中位數報酬</span><span class="val">{boot_stat['median']:+.2%}</span></div>
    <div class="stat-row"><span class="lbl">標準差</span><span class="val">±{boot_stat['std']:.2%}</span></div>
    <div class="stat-row"><span class="lbl">P5 / P95</span><span class="val">{boot_stat['p5']:+.2%} ~ {boot_stat['p95']:+.2%}</span></div>
    <div class="stat-row"><span class="lbl">正報酬機率</span><span class="val">{boot_stat['pos_prob']:.0%}</span></div>
    <div class="stat-row"><span class="lbl">實際值排名</span><span class="val">{boot_stat['actual_rank']:.0%}</span></div>
    <div class="stat-row"><span class="lbl">Sharpe-like</span><span class="val">{boot_stat['sharpe']}</span></div>
  </div>
  <div class="stat-box">
    <h3>⬇️ 最大回撤分析 <span class="method-tag shuf">Permutation</span></h3>
    <div class="stat-row"><span class="lbl">模擬次數</span><span class="val">{N_SIM:,}</span></div>
    <div class="stat-row"><span class="lbl">平均最大回撤</span><span class="val">{dd_stat['mean']:.2%}</span></div>
    <div class="stat-row"><span class="lbl">中位數最大回撤</span><span class="val">{dd_stat['median']:.2%}</span></div>
    <div class="stat-row"><span class="lbl">標準差</span><span class="val">±{dd_stat['std']:.2%}</span></div>
    <div class="stat-row"><span class="lbl">P5 / P95</span><span class="val">{dd_stat['p5']:.2%} ~ {dd_stat['p95']:.2%}</span></div>
    <div class="stat-row"><span class="lbl">實際最大回撤</span><span class="val">{actual_mdd:.2%}</span></div>
    <div class="stat-row"><span class="lbl">實際回撤排名</span><span class="val">{dd_stat['actual_rank']:.0%}</span></div>
    <div class="stat-row"><span class="lbl">（越低越好）</span><span class="val">{'優於' if dd_stat['actual_rank'] < 0.5 else '差於'}{abs(dd_stat['actual_rank']-0.5)*2:.0%} 的隨機順序</span></div>
  </div>
</div>
""")

# Stock breakdown
html_parts.append("""
<div class="twrap">
  <h3>各標的交易明細</h3>
  <table>
    <thead><tr><th>標的</th><th class="num">交易次數</th><th class="num">總報酬</th><th class="num">勝率</th><th class="num">平均每筆報酬</th></tr></thead>
    <tbody>
""")

for s in stock_details:
    avg_r = round(s["total_return"] / s["trades"], 4) if s["trades"] > 0 else 0
    cls = "green" if s["total_return"] > 0 else "red"
    html_parts.append(f"""      <tr>
        <td>{s['symbol']}</td>
        <td class="num">{s['trades']}</td>
        <td class="num {cls}">{s['total_return']:+.2%}</td>
        <td class="num">{s['win_rate']:.0%}</td>
        <td class="num">{avg_r:+.4f}</td>
      </tr>""")

html_parts.append("""
    </tbody>
  </table>
</div>
""")

html_parts.append(f"""
<script>
function drawHist(canvasId, data, actualVal, xLabel, colorPos, colorNeg, actualColor, actLabel, legItems) {{
  const W=920, H=420, pad={{top:30,right:30,bottom:45,left:65}};
  const cw=W-pad.left-pad.right, ch=H-pad.top-pad.bottom;
  const canvas=document.getElementById(canvasId);
  canvas.width=W; canvas.height=H;
  const ctx=canvas.getContext("2d");

  const maxY = Math.max(...data.map(d=>d.y)) * 1.2;
  const xMin = data[0].x;
  const xMax = data[data.length-1].x;

  function cx(v){{return pad.left + ((v - xMin) / (xMax - xMin || 1)) * cw;}}
  function cy(v){{return pad.top + ch - (v / maxY) * ch;}}

  ctx.strokeStyle="#21262d"; ctx.lineWidth=1;
  for(let i=0;i<5;i++){{let y=pad.top+ch*i/4; ctx.beginPath();ctx.moveTo(pad.left,y);ctx.lineTo(W-pad.right,y);ctx.stroke()}}

  ctx.fillStyle="#484f58"; ctx.font="11px Inter,sans-serif"; ctx.textAlign="right";
  ctx.fillText("0",pad.left-6,cy(0)+4);
  ctx.fillText(maxY.toFixed(0),pad.left-6,cy(maxY)+4);

  data.forEach(d=>{{
    const color = d.x < 0 ? colorNeg : colorPos;
    ctx.fillStyle = color;
    const w = Math.max(2, cx(data[1].x) - cx(data[0].x) - 1);
    ctx.fillRect(cx(d.x)-w/2, cy(d.y), w, ch - cy(d.y) + pad.top);
  }});

  if (actualVal !== null) {{
    const actX = cx(actualVal);
    ctx.beginPath(); ctx.strokeStyle=actualColor; ctx.lineWidth=3;
    ctx.moveTo(actX, pad.top); ctx.lineTo(actX, pad.top+ch); ctx.stroke();
    ctx.fillStyle=actualColor; ctx.font="bold 12px Inter,sans-serif"; ctx.textAlign="center";
    const prefix = actualVal >= 0 ? "+" : "";
    ctx.fillText("實際值 "+ prefix + (actualVal*100).toFixed(1)+"%", actX, pad.top-6);
  }}

  ctx.fillStyle="#484f58"; ctx.font="11px Inter,sans-serif"; ctx.textAlign="center";
  const xStep = Math.ceil((xMax - xMin) / 10 * 100) / 100;
  for(let v=Math.ceil(xMin/xStep)*xStep; v<=xMax; v+=xStep){{
    ctx.fillText((v*100).toFixed(1)+"%", cx(v), H-pad.bottom+16);
  }}

  ctx.fillStyle="#8b949e"; ctx.font="11px Inter,sans-serif"; ctx.textAlign="left";
  ctx.fillText(xLabel, pad.left+5, H-6);

  ctx.textAlign="left";
  legItems.forEach((l,i)=>{{
    let x=pad.left+10+i*180, y=14;
    ctx.fillStyle=l.c;
    ctx.fillRect(x,y-6,18,10);
    ctx.fillStyle="#8b949e"; ctx.font="11px Inter,sans-serif";
    ctx.fillText(l.l,x+24,y+3);
  }});
}}

// Chart 1: Bootstrap return distribution
drawHist("chart", {j_hist}, {actual_total}, "總報酬",
  "rgba(63,185,80,0.55)", "rgba(248,81,73,0.55)", "#f0883e",
  "實際報酬", [
    {{l:"靴帶抽樣分布",c:"rgba(63,185,80,0.55)"}},
    {{l:"實際策略報酬",c:"#f0883e"}}
  ]);

// Chart 2: Drawdown distribution (permutation test)
drawHist("chartDD", {j_ddhist}, null, "最大回撤",
  "rgba(248,81,73,0.55)", "rgba(248,81,73,0.55)", null,
  "實際回撤", [
    {{l:"回撤分布（排列測試）",c:"rgba(248,81,73,0.55)"}}
  ]);
</script>
</div></body></html>
""")

path = os.path.join(os.path.dirname(__file__), "monte_carlo.html")
with open(path, "w", encoding="utf-8") as f:
    f.writelines(html_parts)
print(f"\n✅ 已輸出: monte_carlo.html")
