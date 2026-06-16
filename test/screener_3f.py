#!/usr/bin/env python3
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from FinMind.data import DataLoader
from dotenv import load_dotenv
load_dotenv()

TODAY = "2026-06-16"
PER_MAX = 20
REV_YOY_MIN = 10
FOREIGN_NET_MIN = 0  # 大於零即為買超

# 市值前 200 大股票（來源：scan_bollinger_candidates.py）
STOCKS = [
    "2330","2454","2317","2382","2881","2886","2882","2891","2892","2885",
    "2884","2887","2890","2883","2880","5880","5871","5876","6005","2834",
    "2308","2303","2345","2376","2357","2412","2409","3231","2383","2385",
    "2301","2327","2356","2360","2368","2377","2379","2388","2395","2408",
    "2474","2489","3008","3017","3022","3034","3037","3044","3045","3050",
    "3189","3229","3296","3312","3406","3443","3454","3481",
    "3532","3533","3545","3576","3583","3596","3617","3653","3661","3673",
    "3702","3706","3711","3715","4904","4915","4927","4938","4943","4958",
    "4961","4976","4977","4989","5007","5215","5234","5243","5269",
    "5288","5434","5469","5534",
    "5607","5608","6116",
    "6155","6166","6176","6189","6191","6202","6206","6213","6239",
    "6257","6269","6271","6278","6285","6405","6409","6412","6415","6431",
    "6446","6456","6477","6491","6505","6515","6525","6531","6533",
    "6541","6552","6573","6585","6645","6655","6669","6706",
    "6719","6742","6754","6756","6768","6770","6789","6799","6805","6806",
    "6830","6854","6861","6895","6901","6914","6928","6933","6937",
    "8028","8046","8105","8112","8114","8131","8150","8163","8210",
    "8215","8341","8443","8454","8464","8473","8476","8499","8926","8996",
    "9904","9907","9910","9914","9917","9921","9924","9925","9927","9940",
    "9941","9943","9945","9958",
]

DL = DataLoader()
TOKEN = os.getenv("FINMIND_API_TOKEN")
if TOKEN:
    DL.login_by_token(api_token=TOKEN)

def get_name(sid):
    try:
        info = DL.taiwan_stock_info()
        row = info[info["stock_id"] == sid]
        if not row.empty:
            return row.iloc[0]["stock_name"]
    except:
        pass
    return ""

def get_per(sid):
    try:
        df = DL.taiwan_stock_per_pbr(stock_id=sid, start_date=TODAY)
        if df.empty:
            return None
        last = df.iloc[-1]
        return last["PER"]
    except:
        return None

def get_revenue_yoy(sid):
    try:
        df = DL.taiwan_stock_month_revenue(stock_id=sid, start_date="2025-01-01")
        if df.empty or len(df) < 2:
            return None
        last = df.iloc[-1]
        last_yr = last["revenue_year"]
        last_mth = last["revenue_month"]
        last_rev = float(last["revenue"])
        prev = df[(df["revenue_year"] == last_yr - 1) & (df["revenue_month"] == last_mth)]
        if prev.empty:
            return None
        prev_rev = float(prev.iloc[-1]["revenue"])
        if prev_rev == 0:
            return None
        yoy = (last_rev - prev_rev) / prev_rev * 100
        return round(yoy, 1)
    except:
        return None

def get_foreign_net(sid):
    try:
        df = DL.taiwan_stock_institutional_investors(stock_id=sid, start_date="2026-06-06")
        foreign = df[df["name"] == "Foreign_Investor"]
        if foreign.empty:
            return 0
        net = (foreign["buy"] - foreign["sell"]).sum()
        return int(net)
    except:
        return 0

# ── 掃描 ──
results = []
total = len(STOCKS)
print(f"篩選條件：PER < {PER_MAX}、月營收年增 > {REV_YOY_MIN}%、外資買超")
print(f"掃描 {total} 檔…\n")

for i, sym in enumerate(STOCKS):
    sys.stdout.write(f"\r  [{i+1}/{total}] {sym}… ")
    sys.stdout.flush()

    name = get_name(sym)
    per = get_per(sym)
    yoy = get_revenue_yoy(sym)
    fnet = get_foreign_net(sym)

    if per is None or per >= PER_MAX:
        print(f"✗ PER={per}", end="")
        print()
        continue
    if yoy is None or yoy < REV_YOY_MIN:
        print(f"✗ PER={per} YoY={yoy}", end="")
        print()
        continue
    if fnet <= FOREIGN_NET_MIN:
        print(f"✗ PER={per} YoY={yoy} 外資={fnet:,}", end="")
        print()
        continue

    results.append({
        "symbol": sym,
        "name": name,
        "per": per,
        "yoy": yoy,
        "foreign_net": fnet,
    })
    print(f"✓ PER={per} YoY={yoy}% 外資={fnet:,}", end="")
    print()

results.sort(key=lambda r: r["foreign_net"], reverse=True)

print(f"\n{'='*70}")
print(f"符合條件：{len(results)} 檔（按外資買超排序）")
print(f"{'='*70}")
print(f"{'代號':>6} {'名稱':>6} {'本益比':>6} {'月營收年增':>9} {'外資買超':>12}")
print(f"{'-'*6} {'-'*6} {'-'*6} {'-'*9} {'-'*12}")
for r in results:
    print(f"{r['symbol']:>6} {r['name']:>6} {r['per']:>5.1f}  {r['yoy']:>+7.1f}%  {r['foreign_net']:>10,}")

# ── HTML ──
html_rows = ""
for r in results:
    html_rows += f"""        <tr>
          <td>{r['symbol']}</td>
          <td>{r['name']}</td>
          <td>{r['per']:.1f}</td>
          <td class="yoy">{r['yoy']:+.1f}%</td>
          <td class="fnet">{r['foreign_net']:,}</td>
        </tr>
"""

html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>三因子篩選 — PER&lt;20 · 月營收年增&gt;10% · 外資買超</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:"Inter",-apple-system,sans-serif;background:#0d1117;color:#e6edf3;display:flex;justify-content:center;padding:40px 20px}}
  .container{{max-width:720px;width:100%}}
  h1{{font-size:22px;font-weight:600;margin-bottom:4px}}
  .sub{{color:#8b949e;font-size:14px;margin-bottom:20px}}
  .card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;overflow-x:auto}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{text-align:left;color:#8b949e;font-weight:500;padding:8px 10px;border-bottom:1px solid #21262d;white-space:nowrap}}
  td{{padding:8px 10px;border-bottom:1px solid #21262d;font-variant-numeric:tabular-nums}}
  td:first-child{{font-weight:600}}
  .fnet{{text-align:right;color:#7ee787}}
  .yoy{{text-align:right;color:#7ee787}}
  .tag{{display:inline-block;background:#1c3a1c;color:#7ee787;font-size:11px;padding:2px 8px;border-radius:4px;margin-left:6px}}
  .count{{font-size:15px;padding:10px 0 16px 0;color:#e6edf3}}
</style>
</head>
<body>
<div class="container">
  <h1>三因子篩選</h1>
  <div class="sub">PER &lt; 20 · 月營收年增 &gt; 10% · 外資買超 · 掃描 {total} 檔</div>
  <div class="count"><span class="tag">{len(results)} 檔符合</span></div>
  <div class="card">
    <table>
      <thead><tr>
        <th>代號</th><th>名稱</th><th>本益比</th><th>月營收年增</th><th>外資買超</th>
      </tr></thead>
      <tbody>
{html_rows}      </tbody>
    </table>
  </div>
</div>
</body>
</html>
"""

out = os.path.join(os.path.dirname(__file__), "screener_3f.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"\n已輸出: screener_3f.html")
