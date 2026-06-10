""" 讀取 logs/performance.csv → 產出 logs/dashboard.html（Chart.js 儀表板）"""

import json
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime

import pandas as pd

CSV_PATH = Path("logs/performance.csv")
OUT_PATH = Path("logs/dashboard.html")

CHART_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"


def load_trades() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(CSV_PATH)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def compute_pnl(df: pd.DataFrame) -> list:
    """FIFO 配對計算逐筆 P&L，回傳 [{date, symbol, action, price, qty, pnl, cumulative}]"""
    if df.empty:
        return []
    lots = defaultdict(list)  # symbol -> [(buy_price, qty, buy_date)]
    results = []
    running_pnl = 0.0
    for _, row in df.iterrows():
        sym = row["symbol"]
        price = row["price"]
        qty = int(row["quantity"])
        ts = row["timestamp"]
        act = row["action"].upper()
        if act == "BUY":
            lots[sym].append((price, qty, ts))
        elif act == "SELL":
            remaining = qty
            total_pnl = 0.0
            total_qty = 0
            avg_cost = 0.0
            while remaining > 0 and lots[sym]:
                buy_price, buy_qty, _ = lots[sym][0]
                matched = min(buy_qty, remaining)
                trade_pnl = (price - buy_price) * matched
                total_pnl += trade_pnl
                total_qty += matched
                avg_cost = buy_price  # last matched lot cost for display
                remaining -= matched
                if matched >= buy_qty:
                    lots[sym].pop(0)
                else:
                    lots[sym][0] = (buy_price, buy_qty - matched, _)
            if total_qty > 0:
                running_pnl += total_pnl
                results.append({
                    "date": ts.strftime("%Y-%m-%d"),
                    "time": ts.strftime("%H:%M"),
                    "symbol": sym,
                    "action": "SELL",
                    "price": round(price, 2),
                    "qty": total_qty,
                    "pnl": round(total_pnl, 0),
                    "pnl_pct": round((price - avg_cost) / avg_cost * 100, 2) if avg_cost else 0,
                    "cumulative": round(running_pnl, 0),
                })
    return results


def compute_symbol_stats(df: pd.DataFrame, pnl_list: list) -> list:
    """各標的統計：交易次數、損益、勝率"""
    if df.empty:
        return []
    stats = {}
    for sym in df["symbol"].unique():
        sym_df = df[df["symbol"] == sym]
        buys = len(sym_df[sym_df["action"].str.upper() == "BUY"])
        sells = len(sym_df[sym_df["action"].str.upper() == "SELL"])
        sym_pnl = sum(p["pnl"] for p in pnl_list if p["symbol"] == sym)
        win_trades = sum(1 for p in pnl_list if p["symbol"] == sym and p["pnl"] > 0)
        total_trades = sum(1 for p in pnl_list if p["symbol"] == sym)
        win_rate = round(win_trades / total_trades * 100, 1) if total_trades else 0
        stats[sym] = {
            "trades": total_trades,
            "buys": buys,
            "sells": sells,
            "pnl": round(sym_pnl, 0),
            "win_rate": win_rate,
        }
    return [{"symbol": k, **v} for k, v in stats.items()]


def compute_daily_pnl(pnl_list: list) -> list:
    """逐日匯總損益 for 累積曲線"""
    daily = defaultdict(float)
    dates = []
    for p in pnl_list:
        daily[p["date"]] += p["pnl"]
    if not daily:
        return []
    cumulative = 0.0
    for d in sorted(daily):
        cumulative += daily[d]
        dates.append({"date": d, "daily": round(daily[d], 0), "cumulative": round(cumulative, 0)})
    return dates


def build_html(trades_df: pd.DataFrame) -> str:
    pnl_list = compute_pnl(trades_df)
    symbol_stats = compute_symbol_stats(trades_df, pnl_list)
    daily_pnl = compute_daily_pnl(pnl_list)

    if not trades_df.empty:
        total_trades = len(pnl_list)
        total_pnl = round(sum(p["pnl"] for p in pnl_list), 0)
        win_count = sum(1 for p in pnl_list if p["pnl"] > 0)
        lose_count = sum(1 for p in pnl_list if p["pnl"] <= 0)
        win_rate = round(win_count / total_trades * 100, 1) if total_trades else 0
        total_buy_qty = int(trades_df[trades_df["action"].str.upper() == "BUY"]["quantity"].sum())
        total_sell_qty = int(trades_df[trades_df["action"].str.upper() == "SELL"]["quantity"].sum())
        trade_days = trades_df["timestamp"].dt.date.nunique()
    else:
        total_trades = total_pnl = win_count = lose_count = win_rate = 0
        total_buy_qty = total_sell_qty = trade_days = 0

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    last_trades = sorted(pnl_list, key=lambda x: x["date"] + x["time"], reverse=True)[:50]\
        if pnl_list else []

    charts_json = json.dumps({
        "daily_pnl": daily_pnl,
        "symbol_stats": symbol_stats,
        "pnl_list": pnl_list[-30:] if len(pnl_list) > 30 else pnl_list,
    }, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TW AutoTrader — 績儀表板</title>
<script src="{CHART_CDN}"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f5f7fa; color: #1a1a2e; padding: 24px; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: 4px; }}
  .subtitle {{ color: #666; font-size: .85rem; margin-bottom: 24px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr)); gap: 12px; margin-bottom: 24px; }}
  .card {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .card .label {{ font-size: .75rem; color: #888; text-transform: uppercase; letter-spacing: .5px; }}
  .card .value {{ font-size: 1.5rem; font-weight: 700; margin-top: 4px; }}
  .card .value.positive {{ color: #e74c3c; }}  .card .value.negative {{ color: #3498db; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
  .chart-box {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .chart-box.full {{ grid-column: 1 / -1; }}
  .chart-box h3 {{ font-size: .9rem; color: #555; margin-bottom: 12px; }}
  .chart-box canvas {{ max-height: 320px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
  th {{ text-align: left; padding: 8px 10px; border-bottom: 2px solid #e8e8e8; color: #888; font-weight: 600; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #f0f0f0; }}
  .positive {{ color: #e74c3c; }}  .negative {{ color: #3498db; }}
  .section-title {{ font-size: 1.05rem; font-weight: 600; margin: 24px 0 12px; }}
  .empty {{ text-align: center; color: #999; padding: 48px 0; font-size: 1rem; }}
  @media (max-width: 640px) {{ .charts {{ grid-template-columns: 1fr; }}
     .cards {{ grid-template-columns: repeat(2, 1fr); }} }}
  footer {{ text-align: center; color: #aaa; font-size: .75rem; margin-top: 32px; }}
</style>
</head>
<body>
<div class="container">
  <h1>📊 TW AutoTrader 績效儀表板</h1>
  <div class="subtitle">最後更新：{updated_at} · 資料來源：logs/performance.csv</div>
"""

    if trades_df.empty:
        html += """  <div class="empty">📭 尚無交易紀錄</div>"""
    else:
        html += f"""
  <div class="cards">
    <div class="card"><div class="label">已實現損益</div><div class="value {"positive" if total_pnl >= 0 else "negative"}">{total_pnl:+,.0f}</div></div>
    <div class="card"><div class="label">總交易次數</div><div class="value">{total_trades}</div></div>
    <div class="card"><div class="label">勝率</div><div class="value">{win_rate}%</div></div>
    <div class="card"><div class="label">交易天數</div><div class="value">{trade_days}</div></div>
    <div class="card"><div class="label">買進總股數</div><div class="value">{total_buy_qty:,}</div></div>
    <div class="card"><div class="label">賣出總股數</div><div class="value">{total_sell_qty:,}</div></div>
  </div>

  <div class="charts">
    <div class="chart-box full"><h3>📈 累積損益曲線</h3><canvas id="chartPnl"></canvas></div>
    <div class="chart-box"><h3>📊 各標的損益</h3><canvas id="chartSymbols"></canvas></div>
    <div class="chart-box"><h3>🥧 多空比例</h3><canvas id="chartWinLoss"></canvas></div>
  </div>

  <div class="section-title">📋 近 50 筆交易</div>
  <table>
    <thead><tr><th>日期</th><th>時間</th><th>標的</th><th>價格</th><th>股數</th><th>損益</th><th>報酬率</th><th>累積損益</th></tr></thead>
    <tbody>"""
        for t in last_trades:
            cls = "positive" if t["pnl"] >= 0 else "negative"
            html += f"""<tr><td>{t["date"]}</td><td>{t["time"]}</td><td>{t["symbol"]}</td>
                <td>{t["price"]:,.0f}</td><td>{t["qty"]}</td>
                <td class="{cls}">{t["pnl"]:+,.0f}</td>
                <td class="{cls}">{t["pnl_pct"]:+.2f}%</td>
                <td class="{cls}">{t["cumulative"]:+,.0f}</td></tr>"""
        html += """</tbody></table>"""

    if symbol_stats:
        html += """
  <div class="section-title">🏷️ 各標的統計</div>
  <table><thead><tr><th>標的</th><th>交易次數</th><th>買進次數</th><th>賣出次數</th><th>損益</th><th>勝率</th></tr></thead><tbody>"""
        for s in symbol_stats:
            cls = "positive" if s["pnl"] >= 0 else "negative"
            html += f"""<tr><td>{s["symbol"]}</td><td>{s["trades"]}</td><td>{s["buys"]}</td><td>{s["sells"]}</td>
                <td class="{cls}">{s["pnl"]:+,.0f}</td><td>{s["win_rate"]}%</td></tr>"""
        html += "</tbody></table>"

    html += f"""
  <footer>TW AutoTrader · 資料不構成投資建議 · {updated_at}</footer>
</div>
<script>
const DATA = {charts_json};
if (DATA.daily_pnl && DATA.daily_pnl.length) {{
  new Chart(document.getElementById('chartPnl'), {{
    type: 'line',
    data: {{ labels: DATA.daily_pnl.map(d=>d.date),
            datasets: [{{ label: '累積損益', data: DATA.daily_pnl.map(d=>d.cumulative),
                        borderColor: '#e74c3c', backgroundColor: 'rgba(231,76,60,.08)',
                        fill: true, tension: .3, pointRadius: 4 }}] }},
    options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }},
               scales: {{ y: {{ ticks: {{ callback: v=>v+'元' }} }} }} }}
  }});
}}
if (DATA.symbol_stats && DATA.symbol_stats.length) {{
  new Chart(document.getElementById('chartSymbols'), {{
    type: 'bar',
    data: {{ labels: DATA.symbol_stats.map(s=>s.symbol),
            datasets: [{{ label: '損益', data: DATA.symbol_stats.map(s=>s.pnl),
                        backgroundColor: DATA.symbol_stats.map(s=>s.pnl>=0?'rgba(231,76,60,.7)':'rgba(52,152,219,.7)') }}] }},
    options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }},
               scales: {{ y: {{ ticks: {{ callback: v=>v+'元' }} }} }} }}
  }});
}}
if (DATA.pnl_list && DATA.pnl_list.length) {{
  const wins = DATA.pnl_list.filter(p=>p.pnl>0).length;
  const loss = DATA.pnl_list.length - wins;
  new Chart(document.getElementById('chartWinLoss'), {{
    type: 'doughnut',
    data: {{ labels: ['獲利', '虧損'],
            datasets: [{{ data: [wins, loss],
                        backgroundColor: ['#e74c3c','#3498db'] }}] }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }} }}
  }});
}}
</script>
</body>
</html>"""
    return html


def main():
    df = load_trades()
    if df.empty:
        print("⚠️  performance.csv 不存在或為空，產生空白儀表板")
    html = build_html(df)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    trade_count = len(compute_pnl(df))
    print(f"✅ dashboard.html 已產生（{trade_count} 筆交易）")


if __name__ == "__main__":
    main()
