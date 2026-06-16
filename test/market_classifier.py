"""
2026 電子股市場狀態分類器
使用四大電子股（2330·2454·2317·2382）等權重合成電子指數
ADX(14) + ATR(14)/Close 分類: 趨勢/盤整/高波動/低波動
"""
import json, os
import numpy as np
import pandas as pd
import yfinance as yf

STOCKS = ["2330.TW", "2454.TW", "2317.TW", "2382.TW"]
LABELS = {"2330.TW": "台積電", "2454.TW": "聯發科", "2317.TW": "鴻海", "2382.TW": "廣達"}
START = "2024-01-01"

# ── Load data ──
print("📥 載入資料 ...")
prices = {}
for sym in STOCKS:
    df = yf.download(sym, start=START, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    prices[sym] = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume"
    })

# Equal-weighted composite index (normalized to 100 at start)
close_df = pd.DataFrame({sym: prices[sym]["close"] for sym in STOCKS}).dropna()
base = close_df.iloc[0]

def build_comp(col):
    df = pd.DataFrame({sym: prices[sym][col] for sym in STOCKS}).dropna()
    return df.div(base).mean(axis=1) * 100

idx_df = pd.DataFrame({
    "open": build_comp("open"),
    "high": build_comp("high"),
    "low": build_comp("low"),
    "close": build_comp("close"),
    "volume": build_comp("volume"),
}).dropna()

print(f"📊 電子指數: {len(idx_df)} 日, {idx_df.index[0].date()} ~ {idx_df.index[-1].date()}")

# ── ADX calculation ──
def calc_adx(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr = pd.concat([
        high - low, (high - prev).abs(), (low - prev).abs()
    ], axis=1).max(axis=1)
    up = high - high.shift(1)
    dn = low.shift(1) - low
    pdm = pd.Series(0.0, index=df.index)
    ndm = pd.Series(0.0, index=df.index)
    pdm[(up > dn) & (up > 0)] = up
    ndm[(dn > up) & (dn > 0)] = dn

    def w(s, p):
        return s.ewm(alpha=1/p, adjust=False).mean()

    tr_s = w(tr, period)
    pdi = 100 * w(pdm, period) / tr_s
    ndi = 100 * w(ndm, period) / tr_s
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return pd.DataFrame({
        "pos_di": pdi, "neg_di": ndi, "adx": w(dx, period), "dx": dx
    }, index=df.index)

# ATR
tr = pd.concat([
    idx_df["high"] - idx_df["low"],
    (idx_df["high"] - idx_df["close"].shift(1)).abs(),
    (idx_df["low"] - idx_df["close"].shift(1)).abs(),
], axis=1).max(axis=1)
atr = tr.ewm(alpha=1/14, adjust=False).mean()
atr_pct = atr / idx_df["close"] * 100
adx_df = calc_adx(idx_df, 14)

# ── Classification ──
high_th = atr_pct.dropna().quantile(0.80)
low_th = atr_pct.dropna().quantile(0.20)
adx_th = 22.0

rows = []
for i in range(len(idx_df)):
    a = atr_pct.iloc[i]
    adx_v = adx_df["adx"].iloc[i]
    pdi = adx_df["pos_di"].iloc[i]
    ndi = adx_df["neg_di"].iloc[i]
    close_v = idx_df["close"].iloc[i]

    if pd.isna(a) or pd.isna(adx_v):
        state = "N/A"
    elif a >= high_th:
        state = "高波動" if adx_v < adx_th else "趨勢"
    elif a <= low_th:
        state = "低波動" if adx_v < adx_th else "趨勢"
    elif adx_v >= adx_th:
        state = "趨勢"
    else:
        state = "盤整"

    direction = "上漲" if pdi > ndi else "下跌" if ndi > pdi else "持平"
    rows.append({
        "date": idx_df.index[i].strftime("%Y-%m-%d"),
        "close": round(close_v, 1),
        "atr_pct": round(a, 2) if not pd.isna(a) else None,
        "adx": round(adx_v, 1) if not pd.isna(adx_v) else None,
        "pos_di": round(pdi, 1) if not pd.isna(pdi) else None,
        "neg_di": round(ndi, 1) if not pd.isna(ndi) else None,
        "state": state,
        "direction": direction,
    })

dfc = pd.DataFrame(rows)
latest = dfc.iloc[-1]
recent10 = dfc.tail(10)
rc = recent10["state"].value_counts()

print(f"\n{'='*50}")
print("📡 目前狀態:")
print(f"  日期:     {latest['date']}")
print(f"  指數:     {latest['close']:.1f}")
print(f"  ATR(14):  {latest['atr_pct']:.2f}% (高>{high_th:.2f}% 低<{low_th:.2f}%)")
print(f"  ADX(14):  {latest['adx']:.1f} (>={adx_th:.0f}=趨勢)")
print(f"  +DI/-DI:  {latest['pos_di']:.1f}/{latest['neg_di']:.1f}")
print(f"  狀態:     【{latest['state']}】{latest['direction']}")
print(f"\n📊 近10日分佈: {rc.to_dict()}")

# ── Generate HTML ──
state_cls_map = {"趨勢": "trend", "盤整": "range", "高波動": "highvol", "低波動": "lowvol"}
recent30 = dfc.tail(30).iloc[::-1]
chart_data = dfc.tail(120).to_dict("records")

# Build HTML safely (string concatenation to avoid f-string brace issues)
html_parts = []
html_parts.append("""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>電子股市場狀態分類器</title>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:"Inter",-apple-system,"Segoe UI",system-ui,sans-serif;background:#0d1117;color:#e6edf3;display:flex;justify-content:center;padding:40px 20px}
  .container{max-width:960px;width:100%}
  h1{font-size:22px;font-weight:600;letter-spacing:-0.3px;color:#f0f6fc;margin-bottom:4px}
  .sub{font-size:14px;color:#8b949e;margin-bottom:24px}
  .banner{border-radius:12px;padding:28px 32px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px}
  .banner .cls-label{font-size:13px;text-transform:uppercase;letter-spacing:1px;opacity:0.8}
  .banner .cls-value{font-size:42px;font-weight:700;letter-spacing:-1px}
  .banner .cls-sub{font-size:14px;opacity:0.7;margin-top:4px}
  .banner .stats{display:flex;gap:24px}
  .banner .stat-item{text-align:center}
  .banner .stat-item .num{font-size:20px;font-weight:600}
  .banner .stat-item .lbl{font-size:11px;opacity:0.6;margin-top:2px}
  .banner.trend{background:linear-gradient(135deg,#1a3a1a,#0d2817);border:1px solid #3fb950}
  .banner.trend .cls-value{color:#7ee787}
  .banner.range{background:linear-gradient(135deg,#1a2a3a,#0d1a28);border:1px solid #58a6ff}
  .banner.range .cls-value{color:#58a6ff}
  .banner.highvol{background:linear-gradient(135deg,#3a1a1a,#280d0d);border:1px solid #f85149}
  .banner.highvol .cls-value{color:#f85149}
  .banner.lowvol{background:linear-gradient(135deg,#2a1a3a,#1d0d28);border:1px solid #d2a8ff}
  .banner.lowvol .cls-value{color:#d2a8ff}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:20px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;text-align:center}
  .card .val{font-size:24px;font-weight:600}
  .card .lbl{font-size:11px;color:#8b949e;margin-top:4px}
  .chart-wrap{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin-bottom:20px}
  canvas{display:block;width:100%;height:auto}
  .twrap{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin-bottom:20px}
  .twrap h3{font-size:14px;font-weight:600;color:#f0f6fc;margin-bottom:12px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{text-align:left;color:#8b949e;font-weight:500;padding:6px 8px;border-bottom:1px solid #21262d}
  td{padding:6px 8px;border-bottom:1px solid #21262d;font-variant-numeric:tabular-nums}
  .num{text-align:right}
  .tag{display:inline-block;padding:1px 8px;border-radius:4px;font-size:11px;font-weight:500;letter-spacing:0.3px}
  .tag.trend{background:#1c3a1c;color:#7ee787}
  .tag.range{background:#1c2a3a;color:#58a6ff}
  .tag.highvol{background:#3a1c1c;color:#f85149}
  .tag.lowvol{background:#2a1c3a;color:#d2a8ff}
  .tag.up{color:#7ee787} .tag.down{color:#f85149}
  .hl{background:#1c2128}
</style>
</head>
<body>
<div class="container">
""")

# Class name for banner
bn_cls = state_cls_map.get(latest["state"], "range")
html_parts.append(f"""
<h1>電子股市場狀態分類器</h1>
<div class="sub">四大電子股（台積電·聯發科·鴻海·廣達）等權重合成指數 · ADX(14) + ATR(14) 分類</div>

<div class="banner {bn_cls}">
  <div>
    <div class="cls-label">當前市場狀態</div>
    <div class="cls-value">{latest['state']}</div>
    <div class="cls-sub">{latest['direction']} · 指數 {latest['close']:.1f} · {latest['date']}</div>
  </div>
  <div class="stats">
    <div class="stat-item"><div class="num">{latest['adx']:.1f}</div><div class="lbl">ADX(14)</div></div>
    <div class="stat-item"><div class="num">{latest['atr_pct']:.1f}%</div><div class="lbl">ATR(14)/Close</div></div>
    <div class="stat-item"><div class="num">{latest['pos_di']:.1f}/{latest['neg_di']:.1f}</div><div class="lbl">+DI / -DI</div></div>
  </div>
</div>

<div class="grid">
  <div class="card"><div class="val">{latest['close']:.1f}</div><div class="lbl">電子指數</div></div>
  <div class="card"><div class="val" style="color:{'#f0883e' if latest['atr_pct']>=high_th else '#d2a8ff' if latest['atr_pct']<=low_th else '#e6edf3'}">{latest['atr_pct']:.2f}%</div><div class="lbl">ATR% (高≥{high_th:.1f}% 低≤{low_th:.1f}%)</div></div>
  <div class="card"><div class="val" style="color:{'#7ee787' if latest['adx']>=adx_th else '#58a6ff'}">{latest['adx']:.1f}</div><div class="lbl">ADX (≥{adx_th:.0f}=趨勢)</div></div>
  <div class="card"><div class="val">{rc.get('趨勢',0)}/10</div><div class="lbl">近10日趨勢天數</div></div>
</div>
""")

html_parts.append("""
<div class="chart-wrap">
  <canvas id="chart" width="920" height="460"></canvas>
</div>
""")

# Table
html_parts.append("""
<div class="twrap">
  <h3>近30日狀態日報（最新在上）</h3>
  <table>
    <thead><tr><th>日期</th><th class="num">指數</th><th class="num">ATR%</th><th class="num">ADX</th><th class="num">+DI</th><th class="num">-DI</th><th>分類</th><th>方向</th></tr></thead>
    <tbody>
""")

for _, r in recent30.iterrows():
    cls = state_cls_map.get(r["state"], "")
    hl = ' class="hl"' if r["date"] == latest["date"] else ""
    dir_cls = "up" if r["direction"] == "上漲" else ("down" if r["direction"] == "下跌" else "")
    html_parts.append(f"""      <tr{hl}>
        <td>{r['date']}</td>
        <td class="num">{r['close']:.1f}</td>
        <td class="num">{r['atr_pct']:.2f}%</td>
        <td class="num">{r['adx']:.1f}</td>
        <td class="num">{r['pos_di']:.1f}</td>
        <td class="num">{r['neg_di']:.1f}</td>
        <td><span class="tag {cls}">{r['state']}</span></td>
        <td class="num"><span class="tag {dir_cls}">{r['direction']}</span></td>
      </tr>""")

html_parts.append("""
    </tbody>
  </table>
</div>
""")

# Chart JS
chart_json = json.dumps(chart_data, ensure_ascii=False)
html_parts.append(f"""
<script>
const data = {chart_json};
const aThresh = {adx_th};

const W=920, H=460, pad={{top:30,right:40,bottom:40,left:55}};
const cw=W-pad.left-pad.right, ch=H-pad.top-pad.bottom;
const canvas=document.getElementById("chart");
canvas.width=W; canvas.height=H;
const ctx=canvas.getContext("2d");

const closeMax=Math.max(...data.map(d=>d.close))*1.05;
const closeMin=Math.min(...data.map(d=>d.close))*0.95;
const n=data.length;

function cx(i){{return pad.left+(i/(n-1||1))*cw;}}
function cy(v,mn,mx){{return pad.top+ch-((v-mn)/(mx-mn||1))*ch;}}

// Grid
ctx.strokeStyle="#21262d"; ctx.lineWidth=1;
for(let i=0;i<5;i++){{let y=pad.top+ch*i/4; ctx.beginPath();ctx.moveTo(pad.left,y);ctx.lineTo(W-pad.right,y);ctx.stroke()}}
ctx.fillStyle="#484f58"; ctx.font="11px Inter,sans-serif"; ctx.textAlign="right";
[closeMin,(closeMin+closeMax)/2,closeMax].forEach(v=>{{ctx.fillText(v.toFixed(0),pad.left-6,cy(v,closeMin,closeMax)+4)}});

// Background state coloring
const fills={{'趨勢':'rgba(63,185,80,0.08)','盤整':'rgba(88,166,255,0.06)','高波動':'rgba(248,81,73,0.08)','低波動':'rgba(210,168,255,0.06)'}};
data.forEach((d,i)=>{{
  if(i===0) return;
  const f=fills[d.state]||'transparent';
  if(f!=='transparent'){{ctx.fillStyle=f; ctx.fillRect(cx(i-1),pad.top,cx(i)-cx(i-1),ch);}}
}});

// Price line
ctx.beginPath(); ctx.strokeStyle="#e6edf3"; ctx.lineWidth=2; ctx.lineJoin="round";
data.forEach((d,i)=>{{i===0?ctx.moveTo(cx(i),cy(d.close,closeMin,closeMax)):ctx.lineTo(cx(i),cy(d.close,closeMin,closeMax))}});
ctx.stroke();

// ADX line (secondary axis)
const adxMax=Math.max(...data.map(d=>d.adx||0))*1.2||50;
function cy2(v){{return pad.top+ch-(v/adxMax)*ch;}}
ctx.beginPath(); ctx.strokeStyle="#f0883e"; ctx.lineWidth=1.5; ctx.setLineDash([4,4]);
data.forEach((d,i)=>{{
  if(d.adx==null) return;
  i===0||data[i-1].adx==null?ctx.moveTo(cx(i),cy2(d.adx)):ctx.lineTo(cx(i),cy2(d.adx));
}});
ctx.stroke(); ctx.setLineDash([]);

// ADX threshold
const thY=cy2(aThresh);
ctx.beginPath(); ctx.strokeStyle="#f0883e"; ctx.lineWidth=1; ctx.setLineDash([3,3]);
ctx.moveTo(pad.left,thY); ctx.lineTo(W-pad.right,thY); ctx.stroke(); ctx.setLineDash([]);
ctx.fillStyle="#f0883e"; ctx.font="10px Inter,sans-serif"; ctx.textAlign="right";
ctx.fillText("ADX="+aThresh.toFixed(0),W-pad.right-10,thY-4);

// X labels
ctx.fillStyle="#484f58"; ctx.font="11px Inter,sans-serif"; ctx.textAlign="center";
data.forEach((d,i)=>{{if(i%15===0||i===n-1)ctx.fillText(d.date.slice(5),cx(i),H-pad.bottom+16)}});

// Legend
const leg=[{{l:"電子指數",c:"#e6edf3"}},{{l:"ADX(14)",c:"#f0883e"}},{{l:"ADX="+aThresh.toFixed(0)+"門檻",c:"#f0883e",d:1}}];
ctx.font="11px Inter,sans-serif"; ctx.textAlign="left";
leg.forEach((l,i)=>{{
  let x=pad.left+10+i*140, y=14;
  ctx.strokeStyle=l.c; ctx.lineWidth=2;
  if(l.d) ctx.setLineDash([3,3]);
  ctx.beginPath(); ctx.moveTo(x,y-3); ctx.lineTo(x+20,y-3); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle="#8b949e"; ctx.fillText(l.l,x+26,y+1);
}});
</script>
</div></body></html>
""")

path = os.path.join(os.path.dirname(__file__), "market_state.html")
with open(path, "w", encoding="utf-8") as f:
    f.writelines(html_parts)
print(f"\n✅ 已輸出: market_state.html")
print(f"   高波動門檻: >{high_th:.2f}%")
print(f"   低波動門檻: <{low_th:.2f}%")
print(f"   ADX趨勢門檻: >={adx_th:.0f}")
