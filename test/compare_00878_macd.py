#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
import numpy as np
import pandas as pd
import yfinance as yf

from strategies.ma_cross import ma_cross_strategy
from strategies.macd import macd_strategy

SYMBOL = "00878"
START = "2025-01-01"
END = "2026-06-16"
INITIAL_CAPITAL = 500_000

MA_CROSS_PARAMS = {"fast_period": 9, "slow_period": 21, "atr_threshold": 0.005}
MACD_PARAMS = {"fast": 12, "slow": 26, "signal": 9}

np.random.seed(42)


def load_data(symbol, start, end):
    yf_symbol = f"{symbol}.TW"
    print(f"下載 {yf_symbol} ({start} ~ {end})...")
    df = yf.download(yf_symbol, start=start, end=end, auto_adjust=True)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    if "high" not in df.columns:
        df["high"] = df["close"] * 1.005
        df["low"] = df["close"] * 0.995
    return df


def compute_equity(df, capital, buy_cost=0.001425, sell_cost=0.004425):
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
            avg_cost = total_buy_cost / hold
            trade_cost = hold * avg_cost
            if proceeds > trade_cost:
                wins += 1
            else:
                losses += 1
            cash += proceeds
            total_buy_cost = 0.0
            hold = 0

        equity_curve.append(cash + hold * price)

    if hold > 0 and len(df) > 0:
        price = float(df.loc[len(df) - 1, "close"])
        proceeds = hold * price * (1 - sell_cost)
        avg_cost = total_buy_cost / hold
        trade_cost = hold * avg_cost
        if proceeds > trade_cost:
            wins += 1
        else:
            losses += 1
        cash += proceeds
        hold = 0
        equity_curve[-1] = cash

    df["equity"] = equity_curve
    df.index = orig_index

    resolved = wins + losses
    win_rate = wins / resolved if resolved > 0 else 0.0
    total_return = (equity_curve[-1] - capital) / capital
    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / peak
    max_dd = dd.min()

    return df, {
        "final_equity": round(equity_curve[-1], 2),
        "total_return": round(total_return * 100, 2),
        "total_trades": total_txn,
        "win_rate": round(win_rate * 100, 1),
        "resolved": resolved,
        "max_drawdown": round(max_dd * 100, 2),
    }


df_raw = load_data(SYMBOL, START, END)
if df_raw.empty:
    exit(1)

print(f"資料 {len(df_raw)} 筆")

df_macd = macd_strategy(df_raw.copy(), **MACD_PARAMS)
df_macd_eq, macd_perf = compute_equity(df_macd, INITIAL_CAPITAL)

df_ma = ma_cross_strategy(df_raw.copy(), **MA_CROSS_PARAMS)
df_ma_eq, ma_perf = compute_equity(df_ma, INITIAL_CAPITAL)

print(f"\n{'='*60}")
print(f"  00878 MACD vs MA Cross（2025/01/01 ~ 2026/06/16）")
print(f"{'='*60}")
print(f"{'指標':<16} {'📈 MACD':>12} {'📊 MA Cross':>14}")
print(f"{'-'*42}")
print(f"{'最終權益':<16} {macd_perf['final_equity']:>12,.0f} {ma_perf['final_equity']:>14,.0f}")
print(f"{'總報酬率':<16} {macd_perf['total_return']:>11.2f}% {ma_perf['total_return']:>13.2f}%")
print(f"{'交易次數':<16} {macd_perf['total_trades']:>12} {ma_perf['total_trades']:>14}")
print(f"{'勝率':<16} {macd_perf['win_rate']:>11.1f}% {ma_perf['win_rate']:>13.1f}%")
print(f"{'最大回撤':<16} {macd_perf['max_drawdown']:>11.2f}% {ma_perf['max_drawdown']:>13.2f}%")

# ── HTML ──
j_macd_eq = json.dumps([round(v, 2) for v in df_macd_eq["equity"].tolist()])
j_ma_eq = json.dumps([round(v, 2) for v in df_ma_eq["equity"].tolist()])
j_dates = json.dumps([str(d.date()) for d in df_macd_eq.index])

def signal_rows(df_eq):
    rows = ""
    for idx, row in df_eq[df_eq["signal"] != 0].iterrows():
        a = "買進" if row["signal"] == 1 else "賣出"
        c = "buy" if row["signal"] == 1 else "sell"
        rows += f'<tr><td>{idx.date()}</td><td class="{c}">{a}</td><td>{row["close"]:.2f}</td></tr>\n'
    return rows

j_macd_signals = signal_rows(df_macd_eq)
j_ma_signals = signal_rows(df_ma_eq)

ret_diff = macd_perf["total_return"] - ma_perf["total_return"]
if abs(ret_diff) < 0.5:
    verdict, detail = "兩者表現相當", "MACD 與 MA Cross 回測結果非常接近。"
elif ret_diff > 0:
    verdict = "MACD 略勝一籌"
    detail = f"MACD {macd_perf['total_return']:+.2f}% vs MA Cross {ma_perf['total_return']:+.2f}%，差距 {abs(ret_diff):.2f}pp"
else:
    verdict = "MA Cross 略勝一籌"
    detail = f"MA Cross {ma_perf['total_return']:+.2f}% vs MACD {macd_perf['total_return']:+.2f}%，差距 {abs(ret_diff):.2f}pp"

html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>00878 — MACD vs MA Cross 比較</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:"Inter",-apple-system,sans-serif;background:#0d1117;color:#e6edf3;display:flex;justify-content:center;padding:40px 20px}}
  .container{{max-width:1000px;width:100%}}
  h1{{font-size:22px;font-weight:600;margin-bottom:4px}}
  .sub{{color:#8b949e;font-size:14px;margin-bottom:24px}}
  .card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin-bottom:20px}}
  table{{width:100%;border-collapse:collapse;font-size:14px}}
  th{{text-align:left;color:#8b949e;font-weight:500;padding:10px 12px;border-bottom:1px solid #21262d}}
  td{{padding:10px 12px;border-bottom:1px solid #21262d}}
  .label{{font-weight:500}}
  .val{{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}}
  .better{{color:#7ee787}}.worse{{color:#f85149}}.neutral{{color:#e6edf3}}
  canvas{{width:100%!important;height:auto!important;display:block}}
  .sig-table{{width:100%;font-size:12px;margin-top:10px}}
  .sig-table th{{padding:6px 8px;font-size:11px}}
  .sig-table td{{padding:6px 8px;font-variant-numeric:tabular-nums}}
  .buy{{color:#7ee787;font-weight:600}}.sell{{color:#f85149;font-weight:600}}
  h2{{font-size:16px;font-weight:600;margin-bottom:12px;color:#e6edf3}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
  .mini-card{{background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:14px}}
  .mini-card .h{{color:#8b949e;font-size:11px;margin-bottom:4px}}
  .verdict-box{{border:1px solid #30363d;border-radius:8px;padding:16px;margin-top:20px;background:#0d1117}}
  .verdict-box h3{{font-size:15px;margin-bottom:8px}}
  .verdict-box ul{{color:#8b949e;font-size:13px;padding-left:18px;line-height:1.8}}
</style>
</head>
<body>
<div class="container">
  <h1>00878 — MACD vs MA Cross</h1>
  <div class="sub">{START} ~ {END} | NT${INITIAL_CAPITAL:,} | 手續 0.1425% / 證交稅 0.3%</div>

  <div class="card">
    <table>
      <thead><tr>
        <th>指標</th><th style="text-align:right">MACD (12,26,9)</th><th style="text-align:right">MA Cross (9,21)</th><th style="text-align:right">差距</th>
      </tr></thead>
      <tbody>
"""

def metric_row(label, macd_v, ma_v, unit, higher_better):
    diff = macd_v - ma_v
    if unit == "%":
        m = f"{macd_v:+.2f}%" if "報酬" in label else f"{macd_v:.1f}%"
        a = f"{ma_v:+.2f}%" if "報酬" in label else f"{ma_v:.1f}%"
        d = f"{diff:+.2f}pp"
    elif unit == "元":
        m = f"NT${macd_v:,.0f}"
        a = f"NT${ma_v:,.0f}"
        d = f"NT${diff:+,.0f}"
    else:
        m, a, d = str(macd_v), str(ma_v), f"{diff:+d}"

    if higher_better:
        mc, ac = ("better", "worse") if diff > 0 else ("worse", "better") if diff < 0 else ("neutral", "neutral")
    else:
        mc, ac = ("better", "worse") if diff < 0 else ("worse", "better") if diff > 0 else ("neutral", "neutral")

    return f"""        <tr>
          <td class="label">{label}</td>
          <td class="val {mc}">{m}</td>
          <td class="val {ac}">{a}</td>
          <td class="val" style="color:#8b949e;font-size:12px">{d}</td>
        </tr>
"""

html += metric_row("總報酬率", macd_perf["total_return"], ma_perf["total_return"], "%", True)
html += metric_row("勝率", macd_perf["win_rate"], ma_perf["win_rate"], "%", True)
html += metric_row("交易次數", macd_perf["total_trades"], ma_perf["total_trades"], "", False)
html += metric_row("最大回撤", macd_perf["max_drawdown"], ma_perf["max_drawdown"], "%", False)
html += metric_row("最終權益", macd_perf["final_equity"], ma_perf["final_equity"], "元", True)

html += f"""      </tbody>
    </table>
  </div>

  <h2>權益曲線</h2>
  <div class="card">
    <canvas id="c" height="300"></canvas>
  </div>

  <div class="grid2">
    <div class="mini-card">
      <div class="h">MACD 交易明細</div>
      <table class="sig-table"><thead><tr><th>日期</th><th>動作</th><th>價格</th></tr></thead><tbody>
{j_macd_signals}      </tbody></table>
    </div>
    <div class="mini-card">
      <div class="h">MA Cross 交易明細</div>
      <table class="sig-table"><thead><tr><th>日期</th><th>動作</th><th>價格</th></tr></thead><tbody>
{j_ma_signals}      </tbody></table>
    </div>
  </div>

  <div class="verdict-box">
    <h3>{verdict}</h3>
    <ul>
      <li>{detail}</li>
      <li>MACD 交易 {macd_perf['total_trades']} 次 vs MA Cross {ma_perf['total_trades']} 次</li>
      <li>MACD 勝率 {macd_perf['win_rate']:.1f}% vs MA Cross {ma_perf['win_rate']:.1f}%</li>
      <li>MACD 最大回撤 {macd_perf['max_drawdown']:.2f}% vs MA Cross {ma_perf['max_drawdown']:.2f}%</li>
    </ul>
  </div>
</div>

<script>
const dates = {j_dates};
const macdEq = {j_macd_eq};
const maEq = {j_ma_eq};

function draw(){{
  const mn = Math.min(Math.min(...macdEq), Math.min(...maEq));
  const mx = Math.max(Math.max(...macdEq), Math.max(...maEq));
  const p = (mx-mn)*0.08, y0 = mn-p, y1 = mx+p;
  const cv = document.getElementById('c');
  const r = cv.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio||1;
  const w = Math.max(r.width-40,400), h = 300;
  cv.width = w*dpr; cv.height = h*dpr;
  cv.style.width = w+'px'; cv.style.height = h+'px';
  const ctx = cv.getContext('2d');
  ctx.scale(dpr,dpr);
  const L=70,R=20,T=20,B=40, pw=w-L-R, ph=h-T-B;
  const xs = pw/(dates.length-1), ys = ph/(y1-y0);
  const tx = i => L + i*xs;
  const ty = v => T + ph - (v-y0)*ys;

  ctx.fillStyle='#0d1117'; ctx.fillRect(0,0,w,h);
  ctx.strokeStyle='#21262d'; ctx.lineWidth=1;
  for(let y=0;y<=4;y++){{const yy=T+(ph/4)*y; ctx.beginPath();ctx.moveTo(L,yy);ctx.lineTo(w-R,yy);ctx.stroke()}}

  ctx.fillStyle='#8b949e'; ctx.font='11px Inter,sans-serif'; ctx.textAlign='right'; ctx.textBaseline='middle';
  for(let y=0;y<=4;y++){{const v=y1-(y1-y0)/4*y; ctx.fillText('NT$'+v.toLocaleString('zh-TW',{{maximumFractionDigits:0}}),L-8,T+(ph/4)*y)}}

  function drawLine(data,color){{ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();for(let i=0;i<data.length;i++){{const xx=tx(i),yy=ty(data[i]);i===0?ctx.moveTo(xx,yy):ctx.lineTo(xx,yy)}}ctx.stroke()}}
  drawLine(macdEq,'#58a6ff'); drawLine(maEq,'#da3633');

  ctx.strokeStyle='#30363d'; ctx.setLineDash([4,4]);
  const by=ty({INITIAL_CAPITAL}); ctx.beginPath();ctx.moveTo(L,by);ctx.lineTo(w-R,by);ctx.stroke();
  ctx.setLineDash([]); ctx.fillStyle='#8b949e'; ctx.textAlign='left'; ctx.textBaseline='bottom'; ctx.font='10px Inter,sans-serif';
  ctx.fillText('NT$500,000',L+4,by-2);

  ctx.fillStyle='#58a6ff'; ctx.fillRect(w-180,12,12,3);
  ctx.fillStyle='#e6edf3'; ctx.font='11px Inter,sans-serif'; ctx.textAlign='left'; ctx.textBaseline='top';
  ctx.fillText('MACD',w-164,8);
  ctx.fillStyle='#da3633'; ctx.fillRect(w-100,12,12,3);
  ctx.fillText('MA Cross',w-84,8);
}}
window.addEventListener('load',draw);
window.addEventListener('resize',draw);
</script>
</body>
</html>
"""

out = os.path.join(os.path.dirname(__file__), "compare_00878_macd.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"\n已輸出 compare_00878_macd.html")
