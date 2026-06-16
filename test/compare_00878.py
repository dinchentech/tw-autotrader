#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
import math
import numpy as np
import pandas as pd
import yfinance as yf

from strategies.bollinger import bollinger_reverse_strategy
from strategies.kd import kd_strategy

SYMBOL = "00878"
START = "2025-01-01"
END = "2026-06-16"
INITIAL_CAPITAL = 500_000

# 策略參數（用預設值）
BOLLINGER_PARAMS = {"window": 20, "std_dev": 2.0, "rsi_period": 5}
KD_PARAMS = {"k_period": 9, "d_period": 3, "oversold": 30, "overbought": 70}

np.random.seed(42)


def load_data(symbol: str, start: str, end: str) -> pd.DataFrame:
    yf_symbol = f"{symbol}.TW"
    print(f"📥 下載 {yf_symbol} ({start} ~ {end})...")
    df = yf.download(yf_symbol, start=start, end=end, auto_adjust=True)
    if df.empty:
        print(f"❌ {yf_symbol} 無資料")
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    return df


def compute_equity(df: pd.DataFrame, capital: float, buy_cost=0.001425, sell_cost=0.004425) -> pd.DataFrame:
    """從 signal 欄位計算每日權益曲線（與 backtest_finmind 一致）"""
    df = df.copy()
    orig_index = df.index
    df = df.reset_index(drop=True)
    cash = float(capital)
    hold = 0.0
    total_buy_cost = 0.0
    equity_curve = []
    wins = 0
    losses = 0
    total_txn = 0

    for i in range(len(df)):
        signal = int(df.loc[i, "signal"])
        price = float(df.loc[i, "close"])

        if signal == 1 and cash > 0:
            invest = cash * 0.5
            shares = int(invest / (price * (1 + buy_cost)))
            if shares > 0:
                cost = shares * price * (1 + buy_cost)
                cash -= cost
                total_buy_cost += cost
                hold += shares
                total_txn += 1

        elif signal == -1 and hold > 0:
            proceeds = hold * price * (1 - sell_cost)
            avg_cost_per_share = total_buy_cost / hold if hold > 0 else 0
            trade_cost = hold * avg_cost_per_share
            if proceeds > trade_cost:
                wins += 1
            else:
                losses += 1
            cash += proceeds
            total_buy_cost = 0.0
            hold = 0

        equity = cash + hold * price
        equity_curve.append(equity)

    # 最後若還有庫存，平倉
    if hold > 0 and len(df) > 0:
        price = float(df.loc[len(df) - 1, "close"])
        proceeds = hold * price * (1 - sell_cost)
        avg_cost_per_share = total_buy_cost / hold if hold > 0 else 0
        trade_cost = hold * avg_cost_per_share
        if proceeds > trade_cost:
            wins += 1
        else:
            losses += 1
        cash += proceeds
        hold = 0
        equity_curve[-1] = cash

    df["equity"] = equity_curve
    df.index = orig_index

    total_trades = total_txn
    resolved = wins + losses
    win_rate = wins / resolved if resolved > 0 else 0.0
    total_return = (equity_curve[-1] - capital) / capital

    # 最大回撤
    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / peak
    max_dd = dd.min()

    return df, {
        "final_equity": round(equity_curve[-1], 2),
        "total_return": round(total_return * 100, 2),
        "total_trades": total_txn,
        "win_rate": round(win_rate * 100, 1),
        "max_drawdown": round(max_dd * 100, 2),
    }


# ─── 主程式 ──────────────────────────────────────────────
df_raw = load_data(SYMBOL, START, END)
if df_raw.empty:
    exit(1)

# 確保有 high/low
if "high" not in df_raw.columns or "low" not in df_raw.columns:
    print("⚠️  缺少 high/low 欄位，用 close 模擬")
    df_raw["high"] = df_raw["close"] * 1.005
    df_raw["low"] = df_raw["close"] * 0.995

print(f"\n📊 資料筆數: {len(df_raw)}")

# ── 布林策略 ──
df_boll = bollinger_reverse_strategy(df_raw.copy(), **BOLLINGER_PARAMS)
df_boll_equity, boll_perf = compute_equity(df_boll, INITIAL_CAPITAL)

# ── KD 策略 ──
df_kd = kd_strategy(df_raw.copy(), **KD_PARAMS)
df_kd_equity, kd_perf = compute_equity(df_kd, INITIAL_CAPITAL)

# ── 輸出結果 ──
print(f"\n{'='*60}")
print(f"  00878 策略回測比較（2025/01/01 ~ 2026/06/16）")
print(f"{'='*60}")
print(f"{'指標':<16} {'📊 布林反轉':>12} {'📈 KD 隨機指標':>14}")
print(f"{'-'*42}")
print(f"{'最終權益':<16} {boll_perf['final_equity']:>12,.0f} {kd_perf['final_equity']:>14,.0f}")
print(f"{'總報酬率':<16} {boll_perf['total_return']:>11.2f}% {kd_perf['total_return']:>13.2f}%")
print(f"{'交易次數':<16} {boll_perf['total_trades']:>12} {kd_perf['total_trades']:>14}")
print(f"{'勝率':<16} {boll_perf['win_rate']:>11.1f}% {kd_perf['win_rate']:>13.1f}%")
print(f"{'最大回撤':<16} {boll_perf['max_drawdown']:>11.2f}% {kd_perf['max_drawdown']:>13.2f}%")

# ── 生成 HTML ──
j_boll_equity = json.dumps([round(v, 2) for v in df_boll_equity["equity"].tolist()])
j_kd_equity = json.dumps([round(v, 2) for v in df_kd_equity["equity"].tolist()])
j_dates = json.dumps([str(d.date()) for d in df_boll_equity.index])

df_boll_signals = df_boll_equity[df_boll_equity["signal"] != 0]
df_kd_signals = df_kd_equity[df_kd_equity["signal"] != 0]

j_boll_signals = json.dumps([
    {"date": str(d.date()), "signal": int(s), "price": round(float(p), 2)}
    for d, s, p in zip(df_boll_signals.index, df_boll_signals["signal"], df_boll_signals["close"])
])
j_kd_signals = json.dumps([
    {"date": str(d.date()), "signal": int(s), "price": round(float(p), 2)}
    for d, s, p in zip(df_kd_signals.index, df_kd_signals["signal"], df_kd_signals["close"])
])

html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>00878 — 布林 vs KD 策略比較</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:"Inter",-apple-system,sans-serif;background:#0d1117;color:#e6edf3;display:flex;justify-content:center;padding:40px 20px}}
  .container{{max-width:1000px;width:100%}}
  h1{{font-size:22px;font-weight:600;margin-bottom:4px}}
  .sub{{color:#8b949e;font-size:14px;margin-bottom:24px}}
  .card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin-bottom:20px}}
  .comparison-table{{width:100%;border-collapse:collapse;font-size:14px}}
  .comparison-table th{{text-align:left;color:#8b949e;font-weight:500;padding:10px 12px;border-bottom:1px solid #21262d}}
  .comparison-table td{{padding:10px 12px;border-bottom:1px solid #21262d}}
  .comparison-table .label{{font-weight:500;color:#e6edf3}}
  .comparison-table .val{{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}}
  .better{{color:#7ee787}}.worse{{color:#f85149}}.neutral{{color:#e6edf3}}
  .win-badge{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:4px;margin-left:6px}}
  .win-better{{background:#1c3a1c;color:#7ee787}}
  .win-worse{{background:#3a1c1c;color:#f85149}}
  .win-tie{{background:#1c2a3a;color:#58a6ff}}
  canvas{{width:100%!important;height:auto!important;display:block}}
  .signal-table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:12px}}
  .signal-table th{{text-align:left;color:#8b949e;font-weight:500;padding:6px 8px;border-bottom:1px solid #21262d;white-space:nowrap}}
  .signal-table td{{padding:6px 8px;border-bottom:1px solid #21262d;font-variant-numeric:tabular-nums}}
  .buy{{color:#7ee787;font-weight:600}}.sell{{color:#f85149;font-weight:600}}
  h2{{font-size:16px;font-weight:600;margin-bottom:12px;color:#e6edf3}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
  .mini-card{{background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:14px}}
  .mini-card .metric{{color:#8b949e;font-size:11px;margin-bottom:4px}}
  .mini-card .value{{font-size:20px;font-weight:700}}
  .verdict-box{{border:1px solid #30363d;border-radius:8px;padding:16px;margin-top:20px;background:#0d1117}}
  .verdict-box h3{{font-size:15px;margin-bottom:8px}}
  .verdict-box ul{{color:#8b949e;font-size:13px;padding-left:18px;line-height:1.8}}
</style>
</head>
<body>
<div class="container">
  <h1>📊 00878 — 布林反轉 vs KD 隨機指標</h1>
  <div class="sub">回測期間：{START} ~ {END} · 起始資金：NT${INITIAL_CAPITAL:,} · 手續費：0.1425% / 證交稅：0.3%</div>

  <div class="card">
    <table class="comparison-table">
      <thead><tr>
        <th>指標</th><th style="text-align:right">📊 布林反轉</th><th style="text-align:right">📈 KD 隨機指標</th><th style="text-align:right">差距</th>
      </tr></thead>
      <tbody>
"""

# 計算每項指標的優劣
metrics = [
    ("總報酬率", boll_perf["total_return"], kd_perf["total_return"], "%", True),
    ("勝率", boll_perf["win_rate"], kd_perf["win_rate"], "%", True),
    ("交易次數", boll_perf["total_trades"], kd_perf["total_trades"], "", False),
    ("最大回撤", boll_perf["max_drawdown"], kd_perf["max_drawdown"], "%", False),
    ("最終權益", boll_perf["final_equity"], kd_perf["final_equity"], "元", True),
]

for label, bv, kv, unit, higher_is_better in metrics:
    diff = bv - kv if isinstance(bv, (int, float)) else 0
    if unit == "%":
        b_str = f"{bv:+.2f}{unit}" if label != "勝率" else f"{bv:.1f}{unit}"
        k_str = f"{kv:+.2f}{unit}" if label != "勝率" else f"{kv:.1f}{unit}"
        diff_str = f"{diff:+.2f}pp" if label != "交易次數" else ""
    elif unit == "元":
        b_str = f"NT${bv:,.0f}"
        k_str = f"NT${kv:,.0f}"
        diff_str = f"NT${diff:+,.0f}"
    else:
        b_str = str(bv)
        k_str = str(kv)
        diff_str = f"{diff:+d}"

    if higher_is_better:
        b_class = "better" if diff > 0 else ("worse" if diff < 0 else "neutral")
        k_class = "worse" if diff > 0 else ("better" if diff < 0 else "neutral")
    else:
        b_class = "better" if diff < 0 else ("worse" if diff > 0 else "neutral")
        k_class = "worse" if diff < 0 else ("better" if diff > 0 else "neutral")

    html += f"""        <tr>
          <td class="label">{label}</td>
          <td class="val {b_class}">{b_str}</td>
          <td class="val {k_class}">{k_str}</td>
          <td class="val" style="color:#8b949e;font-size:12px">{diff_str}</td>
        </tr>
"""

# 決定最終 verdict
ret_diff = boll_perf["total_return"] - kd_perf["total_return"]
if abs(ret_diff) < 0.5:
    verdict = "兩者表現相當"
    detail = "布林與 KD 在 00878 上的回測結果非常接近，沒有顯著差異。"
elif ret_diff > 0:
    verdict = "📊 布林反轉略勝一籌"
    detail = f"布林策略總報酬 {boll_perf['total_return']:+.2f}%，KD 策略 {kd_perf['total_return']:+.2f}%，差距 {abs(ret_diff):.2f} 個百分點。"
else:
    verdict = "📈 KD 隨機指標略勝一籌"
    detail = f"KD 策略總報酬 {kd_perf['total_return']:+.2f}%，布林策略 {boll_perf['total_return']:+.2f}%，差距 {abs(ret_diff):.2f} 個百分點。"

html += f"""      </tbody>
    </table>
  </div>

  <h2>權益曲線</h2>
  <div class="card">
    <canvas id="equityChart" height="320"></canvas>
  </div>

  <div class="grid2">
    <div class="mini-card">
      <div class="metric">📊 布林反轉 · 交易明細</div>
      <table class="signal-table">
        <thead><tr><th>日期</th><th>動作</th><th>價格</th></tr></thead>
        <tbody>
"""
for sig in json.loads(j_boll_signals):
    action = "買進" if sig["signal"] == 1 else "賣出"
    cls = "buy" if sig["signal"] == 1 else "sell"
    html += f"          <tr><td>{sig['date']}</td><td class='{cls}'>{action}</td><td>{sig['price']:.2f}</td></tr>\n"

html += f"""        </tbody>
      </table>
    </div>
    <div class="mini-card">
      <div class="metric">📈 KD 隨機指標 · 交易明細</div>
      <table class="signal-table">
        <thead><tr><th>日期</th><th>動作</th><th>價格</th></tr></thead>
        <tbody>
"""
for sig in json.loads(j_kd_signals):
    action = "買進" if sig["signal"] == 1 else "賣出"
    cls = "buy" if sig["signal"] == 1 else "sell"
    html += f"          <tr><td>{sig['date']}</td><td class='{cls}'>{action}</td><td>{sig['price']:.2f}</td></tr>\n"

html += f"""        </tbody>
      </table>
    </div>
  </div>

  <div class="verdict-box">
    <h3>⚖️ 結論：{verdict}</h3>
    <ul>
      <li>{detail}</li>
      <li>布林反轉交易次數：{boll_perf['total_trades']} 次 vs KD：{kd_perf['total_trades']} 次</li>
      <li>布林反轉勝率：{boll_perf['win_rate']:.1f}% vs KD：{kd_perf['win_rate']:.1f}%</li>
      <li>布林反轉最大回撤：{boll_perf['max_drawdown']:.2f}% vs KD：{kd_perf['max_drawdown']:.2f}%</li>
    </ul>
  </div>
</div>

<script>
const dates = {j_dates};
const bollEquity = {j_boll_equity};
const kdEquity = {j_kd_equity};

function drawChart() {{

  const minVal = Math.min(Math.min(...bollEquity), Math.min(...kdEquity));
  const maxVal = Math.max(Math.max(...bollEquity), Math.max(...kdEquity));
  const pad = (maxVal - minVal) * 0.08;
  const yMin = minVal - pad;
  const yMax = maxVal + pad;

  const canvas = document.getElementById('equityChart');
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(rect.width - 40, 400);
  const h = 320;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = w + 'px';
  canvas.style.height = h + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const padL = 70, padR = 20, padT = 20, padB = 40;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;

  const xScale = plotW / (dates.length - 1);
  const yScale = plotH / (yMax - yMin);

  function toX(i) {{ return padL + i * xScale; }}
  function toY(v) {{ return padT + plotH - (v - yMin) * yScale; }}

  // 背景
  ctx.fillStyle = '#0d1117';
  ctx.fillRect(0, 0, w, h);

  // 網格
  ctx.strokeStyle = '#21262d';
  ctx.lineWidth = 1;
  for (let y = 0; y <= 4; y++) {{
    const yy = padT + (plotH / 4) * y;
    ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(w - padR, yy); ctx.stroke();
  }}

  // Y 軸標籤
  ctx.fillStyle = '#8b949e';
  ctx.font = '11px Inter, sans-serif';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let y = 0; y <= 4; y++) {{
    const val = yMax - (yMax - yMin) / 4 * y;
    const yy = padT + (plotH / 4) * y;
    ctx.fillText('NT$' + val.toLocaleString('zh-TW', {{maximumFractionDigits:0}}), padL - 8, yy);
  }}

  // 折線
  function drawLine(data, color) {{
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {{
      const xx = toX(i);
      const yy = toY(data[i]);
      if (i === 0) ctx.moveTo(xx, yy);
      else ctx.lineTo(xx, yy);
    }}
    ctx.stroke();
  }}

  drawLine(bollEquity, '#58a6ff');
  drawLine(kdEquity, '#f0883e');

  // 基準線
  ctx.strokeStyle = '#30363d';
  ctx.setLineDash([4, 4]);
  const baseY = toY({INITIAL_CAPITAL});
  ctx.beginPath(); ctx.moveTo(padL, baseY); ctx.lineTo(w - padR, baseY); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = '#8b949e';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'bottom';
  ctx.font = '10px Inter, sans-serif';
  ctx.fillText('起始資金 NT${INITIAL_CAPITAL:,}', padL + 4, baseY - 2);

  // 圖例
  const legendY = 12;
  ctx.fillStyle = '#58a6ff';
  ctx.fillRect(w - 180, legendY, 12, 3);
  ctx.fillStyle = '#e6edf3';
  ctx.font = '11px Inter, sans-serif';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText('布林反轉', w - 164, legendY - 4);

  ctx.fillStyle = '#f0883e';
  ctx.fillRect(w - 100, legendY, 12, 3);
  ctx.fillStyle = '#e6edf3';
  ctx.fillText('KD 隨機指標', w - 84, legendY - 4);
}}

window.addEventListener('load', drawChart);
window.addEventListener('resize', drawChart);
</script>
</body>
</html>
"""

out = os.path.join(os.path.dirname(__file__), "compare_00878.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n✅ 已輸出: compare_00878.html")
