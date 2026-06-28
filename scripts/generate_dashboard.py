""" 讀取 logs/performance.csv（Group 1 + Group 2）→ logs/dashboard.html（Chart.js 儀表板）"""

import json
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime

import pandas as pd
import numpy as np

CSV_PATH = Path("logs/performance.csv")
OUT_PATH = Path("logs/dashboard.html")
GROUP2_PNL_PATH = Path("data/inst_momentum_pnl.json")

CHART_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"


def load_trades() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(CSV_PATH)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    if "group" not in df.columns:
        df["group"] = 1
    return df


def compute_pnl(df: pd.DataFrame) -> list:
    """FIFO 配對計算逐筆 P&L，回傳 [{date, symbol, action, price, qty, pnl, cumulative}]"""
    if df.empty:
        return []
    lots = defaultdict(list)
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
                avg_cost = buy_price
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
    for p in pnl_list:
        daily[p["date"]] += p["pnl"]
    if not daily:
        return []
    cumulative = 0.0
    dates = []
    for d in sorted(daily):
        cumulative += daily[d]
        dates.append({"date": d, "daily": round(daily[d], 0), "cumulative": round(cumulative, 0)})
    return dates


def _to_native(obj):
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_native(v) for v in obj]
    if isinstance(obj, (int, float)):
        if hasattr(obj, "item"):
            return obj.item()
        return obj
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    return obj


def load_group2_json_summary() -> dict:
    """從 inst_momentum_pnl.json 讀取 Group 2 摘要（資本、權益等）"""
    if not GROUP2_PNL_PATH.exists():
        return {}
    try:
        data = json.loads(GROUP2_PNL_PATH.read_text())
        capital = data.get("capital", 0)
        total_buy = data.get("total_buy_cost", 0)
        total_sell = data.get("total_sell_proceeds", 0)
        # 從 state 抓持倉市值（若可讀）
        pos_value = 0
        state_path = Path("data/inst_momentum_state.json")
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text())
                pos_value = sum(p.get("cost", 0) for p in state.get("positions", {}).values())
            except Exception:
                pass
        remaining = capital - total_buy + total_sell
        return {
            "capital": capital,
            "remaining_cash": round(remaining, 0),
            "position_value": round(pos_value, 0),
            "total_equity": round(remaining + pos_value, 0),
            "total_buy_cost": round(total_buy, 0),
            "total_sell_proceeds": round(total_sell, 0),
        }
    except Exception:
        return {}


def build_group_stats(pnl_list: list, df: pd.DataFrame) -> dict:
    """計算單一群組的摘要統計"""
    if not pnl_list:
        return {"total_trades": 0, "total_pnl": 0, "win_count": 0, "lose_count": 0,
                "win_rate": 0, "total_buy_qty": 0, "total_sell_qty": 0, "trade_days": 0}
    total_trades = len(pnl_list)
    total_pnl = round(sum(p["pnl"] for p in pnl_list), 0)
    win_count = sum(1 for p in pnl_list if p["pnl"] > 0)
    lose_count = sum(1 for p in pnl_list if p["pnl"] <= 0)
    win_rate = round(win_count / total_trades * 100, 1) if total_trades else 0
    total_buy_qty = int(df[df["action"].str.upper() == "BUY"]["quantity"].sum())
    total_sell_qty = int(df[df["action"].str.upper() == "SELL"]["quantity"].sum())
    trade_days = df["timestamp"].dt.date.nunique()
    return {
        "total_trades": total_trades,
        "total_pnl": total_pnl,
        "win_count": win_count,
        "lose_count": lose_count,
        "win_rate": win_rate,
        "total_buy_qty": total_buy_qty,
        "total_sell_qty": total_sell_qty,
        "trade_days": trade_days,
    }


def build_html(trades_df: pd.DataFrame) -> str:
    df_g1 = trades_df[trades_df["group"] == 1] if not trades_df.empty else pd.DataFrame()
    df_g2 = trades_df[trades_df["group"] == 2] if not trades_df.empty else pd.DataFrame()

    pnl_g1 = compute_pnl(df_g1)
    pnl_g2 = compute_pnl(df_g2)

    stats_g1 = build_group_stats(pnl_g1, df_g1)
    stats_g2 = build_group_stats(pnl_g2, df_g2)

    symbol_stats_g1 = compute_symbol_stats(df_g1, pnl_g1)
    symbol_stats_g2 = compute_symbol_stats(df_g2, pnl_g2)

    daily_g1 = compute_daily_pnl(pnl_g1)
    daily_g2 = compute_daily_pnl(pnl_g2)

    # Group 2 JSON PnL 補充資料
    g2_json = load_group2_json_summary()

    # 合併曲線資料：以日期為 key
    all_dates = set()
    for d in daily_g1:
        all_dates.add(d["date"])
    for d in daily_g2:
        all_dates.add(d["date"])
    pnl_curve_g1 = {d["date"]: d["cumulative"] for d in daily_g1}
    pnl_curve_g2 = {d["date"]: d["cumulative"] for d in daily_g2}
    combined_daily = sorted(all_dates)
    curve_g1_data = [pnl_curve_g1.get(d, None) for d in combined_daily]
    curve_g2_data = [pnl_curve_g2.get(d, None) for d in combined_daily]

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    last_trades_g1 = sorted(pnl_g1, key=lambda x: x["date"] + x["time"], reverse=True)[:50] if pnl_g1 else []
    last_trades_g2 = sorted(pnl_g2, key=lambda x: x["date"] + x["time"], reverse=True)[:50] if pnl_g2 else []

    charts_data = _to_native({
        "labels": combined_daily,
        "curve_g1": curve_g1_data,
        "curve_g2": curve_g2_data,
        "symbol_stats_g1": symbol_stats_g1,
        "symbol_stats_g2": symbol_stats_g2,
        "pnl_list_g1": pnl_g1[-30:] if len(pnl_g1) > 30 else pnl_g1,
        "pnl_list_g2": pnl_g2[-30:] if len(pnl_g2) > 30 else pnl_g2,
        "g2_json": g2_json,
    })
    charts_json = json.dumps(charts_data, ensure_ascii=False)

    has_g1 = stats_g1["total_trades"] > 0
    has_g2 = stats_g2["total_trades"] > 0

    total_pnl = stats_g1["total_pnl"] + stats_g2["total_pnl"]
    total_trades = stats_g1["total_trades"] + stats_g2["total_trades"]

    # ─── 數值格式化 helper ───
    def v(n):
        int_n = int(n)
        return f"{int_n:,}" if int_n < 0 else f"+{int_n:,}"

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TW AutoTrader — 績效儀表板</title>
<script src="{CHART_CDN}"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f5f7fa; color: #1a1a2e; padding: 24px; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: 4px; }}
  .subtitle {{ color: #666; font-size: .85rem; margin-bottom: 24px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr)); gap: 12px; margin-bottom: 16px; }}
  .card {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .card .label {{ font-size: .75rem; color: #888; text-transform: uppercase; letter-spacing: .5px; }}
  .card .value {{ font-size: 1.5rem; font-weight: 700; margin-top: 4px; }}
  .card .value.positive {{ color: #e74c3c; }}  .card .value.negative {{ color: #3498db; }}
  .group-label {{ font-size: .65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;
                  margin-bottom: 8px; padding: 2px 8px; border-radius: 4px; display: inline-block; }}
  .group-label.g1 {{ background: #fdeaea; color: #c0392b; }}
  .group-label.g2 {{ background: #eaf5ff; color: #2980b9; }}
  .group-label.total {{ background: #f0f0f0; color: #555; }}
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
  .group-section {{ background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 16px;
                    box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .strategy-section {{ background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 16px;
                        box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .strategy-links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }}
  .strategy-link {{ display: inline-block; padding: 10px 18px; border-radius: 8px;
                    background: #f0f4ff; color: #2563eb; text-decoration: none; font-weight: 500;
                    font-size: .9rem; transition: background .15s; }}
  .strategy-link:hover {{ background: #dbeafe; }}
  @media (max-width: 640px) {{ .charts {{ grid-template-columns: 1fr; }}
     .cards {{ grid-template-columns: repeat(2, 1fr); }} }}
  footer {{ text-align: center; color: #aaa; font-size: .75rem; margin-top: 32px; }}
</style>
</head>
<body>
<div class="container">
  <h1>📊 TW AutoTrader 績效儀表板</h1>
  <div class="subtitle">最後更新：{updated_at} · Group 1 + Group 2 雙群組</div>

  <!-- 總覽卡片 -->
  <div class="cards">
    <div class="card"><div class="label">總已實現損益</div><div class="value {"positive" if total_pnl >= 0 else "negative"}">{v(total_pnl)}</div></div>
    <div class="card"><div class="label">總交易次數</div><div class="value">{total_trades}</div></div>
    <div class="card"><div class="label">Group 1 損益</div><div class="value {"positive" if stats_g1['total_pnl'] >= 0 else "negative"}">{v(stats_g1['total_pnl'])}</div></div>
    <div class="card"><div class="label">Group 2 損益</div><div class="value {"positive" if stats_g2['total_pnl'] >= 0 else "negative"}">{v(stats_g2['total_pnl'])}</div></div>
  </div>
"""

    # Group 2 JSON 補充卡片（資本、權益）
    if g2_json.get("capital", 0) > 0:
        equity = g2_json.get("total_equity", 0)
        capital = g2_json.get("capital", 0)
        ret = ((equity - capital) / capital * 100) if capital > 0 else 0
        html += f"""
  <div class="cards">
    <div class="card"><div class="label">Group 2 起始資金</div><div class="value">{int(capital):,}</div></div>
    <div class="card"><div class="label">Group 2 總權益</div><div class="value {"positive" if equity >= capital else "negative"}">{int(equity):,}</div></div>
    <div class="card"><div class="label">Group 2 報酬率</div><div class="value {"positive" if ret >= 0 else "negative"}">{ret:+.2f}%</div></div>
  </div>
"""

    # ─── 圖表 ───
    html += """
  <div class="charts">
    <div class="chart-box full"><h3>📈 累積損益曲線</h3><canvas id="chartPnlCombined"></canvas></div>
    <div class="chart-box"><h3>📊 各標的損益 — Group 1</h3><canvas id="chartSymbolsG1"></canvas></div>
    <div class="chart-box"><h3>📊 各標的損益 — Group 2</h3><canvas id="chartSymbolsG2"></canvas></div>
  </div>
"""

    # ─── Group 1 明細 ───
    if has_g1:
        html += f"""
  <div class="group-section">
    <div class="group-label g1">Group 1 固定標的策略</div>
    <div class="cards">
      <div class="card"><div class="label">已實現損益</div><div class="value {"positive" if stats_g1['total_pnl'] >= 0 else "negative"}">{v(stats_g1['total_pnl'])}</div></div>
      <div class="card"><div class="label">交易次數</div><div class="value">{stats_g1['total_trades']}</div></div>
      <div class="card"><div class="label">勝率</div><div class="value">{stats_g1['win_rate']}%</div></div>
      <div class="card"><div class="label">交易天數</div><div class="value">{stats_g1['trade_days']}</div></div>
    </div>
    <div class="section-title">📋 近 50 筆交易</div>
    <table><thead><tr><th>日期</th><th>時間</th><th>標的</th><th>價格</th><th>股數</th><th>損益</th><th>報酬率</th><th>累積損益</th></tr></thead><tbody>"""
        for t in last_trades_g1:
            cls = "positive" if t["pnl"] >= 0 else "negative"
            cum_cls = "positive" if t["cumulative"] >= 0 else "negative"
            html += f"""<tr><td>{t["date"]}</td><td>{t["time"]}</td><td>{t["symbol"]}</td>
                <td>{t["price"]:,.0f}</td><td>{t["qty"]}</td>
                <td class="{cls}">{t["pnl"]:+,.0f}</td>
                <td class="{cls}">{t["pnl_pct"]:+.2f}%</td>
                <td class="{cum_cls}">{t["cumulative"]:+,.0f}</td></tr>"""
        html += "</tbody></table>"

        if symbol_stats_g1:
            html += """
    <div class="section-title">🏷️ 各標的統計</div>
    <table><thead><tr><th>標的</th><th>交易次數</th><th>買進</th><th>賣出</th><th>損益</th><th>勝率</th></tr></thead><tbody>"""
            for s in symbol_stats_g1:
                cls = "positive" if s["pnl"] >= 0 else "negative"
                html += f"""<tr><td>{s["symbol"]}</td><td>{s["trades"]}</td><td>{s["buys"]}</td><td>{s["sells"]}</td>
                    <td class="{cls}">{s["pnl"]:+,.0f}</td><td>{s["win_rate"]}%</td></tr>"""
            html += "</tbody></table>"
    else:
        html += """
  <div class="group-section">
    <div class="group-label g1">Group 1 固定標的策略</div>
    <div class="empty">📭 尚無交易紀錄</div>
  </div>"""

    # ─── Group 2 明細 ───
    if has_g2:
        html += f"""
  <div class="group-section">
    <div class="group-label g2">Group 2 法人抬轎動能策略</div>
    <div class="cards">
      <div class="card"><div class="label">已實現損益</div><div class="value {"positive" if stats_g2['total_pnl'] >= 0 else "negative"}">{v(stats_g2['total_pnl'])}</div></div>
      <div class="card"><div class="label">交易次數</div><div class="value">{stats_g2['total_trades']}</div></div>
      <div class="card"><div class="label">勝率</div><div class="value">{stats_g2['win_rate']}%</div></div>
      <div class="card"><div class="label">交易天數</div><div class="value">{stats_g2['trade_days']}</div></div>
    </div>
    <div class="section-title">📋 近 50 筆交易</div>
    <table><thead><tr><th>日期</th><th>時間</th><th>標的</th><th>價格</th><th>股數</th><th>損益</th><th>報酬率</th><th>累積損益</th></tr></thead><tbody>"""
        for t in last_trades_g2:
            cls = "positive" if t["pnl"] >= 0 else "negative"
            cum_cls = "positive" if t["cumulative"] >= 0 else "negative"
            html += f"""<tr><td>{t["date"]}</td><td>{t["time"]}</td><td>{t["symbol"]}</td>
                <td>{t["price"]:,.0f}</td><td>{t["qty"]}</td>
                <td class="{cls}">{t["pnl"]:+,.0f}</td>
                <td class="{cls}">{t["pnl_pct"]:+.2f}%</td>
                <td class="{cum_cls}">{t["cumulative"]:+,.0f}</td></tr>"""
        html += "</tbody></table>"

        if symbol_stats_g2:
            html += """
    <div class="section-title">🏷️ 各標的統計</div>
    <table><thead><tr><th>標的</th><th>交易次數</th><th>買進</th><th>賣出</th><th>損益</th><th>勝率</th></tr></thead><tbody>"""
            for s in symbol_stats_g2:
                cls = "positive" if s["pnl"] >= 0 else "negative"
                html += f"""<tr><td>{s["symbol"]}</td><td>{s["trades"]}</td><td>{s["buys"]}</td><td>{s["sells"]}</td>
                    <td class="{cls}">{s["pnl"]:+,.0f}</td><td>{s["win_rate"]}%</td></tr>"""
            html += "</tbody></table>"
    else:
        html += """
  <div class="group-section">
    <div class="group-label g2">Group 2 法人抬轎動能策略</div>
    <div class="empty">📭 尚無交易紀錄</div>
  </div>"""

    # ─── 六策略動畫連結 ───
    STRATEGY_VIDEOS = [
        ("布林通道反轉", "bollinger-animation.html"),
        ("VWAP 偏離反轉", "vwap-animation.html"),
        ("均線交叉", "ma_cross-animation.html"),
        ("唐奇安突破", "breakout-animation.html"),
        ("Keep & Wait 低接", "keep_wait策略說明.html"),
        ("法人抬轎動能", "法人動能策略說明.html"),
    ]
    video_links = "".join(
        f'<a href="{fname}" target="_blank" rel="noopener" class="strategy-link">{name}</a>'
        for name, fname in STRATEGY_VIDEOS
    )

    html += f"""
  <div class="strategy-section">
    <div class="section-title">🎬 六策略動畫說明</div>
    <div class="strategy-links">
      {video_links}
    </div>
  </div>
  <footer>TW AutoTrader · 資料不構成投資建議 · {updated_at}</footer>
</div>
<script>
const DATA = {charts_json};

// ─── 合併累積損益曲線 ───
(function() {{
  const canvas = document.getElementById('chartPnlCombined');
  if (!canvas || !DATA.labels || !DATA.labels.length) return;
  const ds = [];
  if (DATA.curve_g1 && DATA.curve_g1.some(v => v !== null))
    ds.push({{ label: 'Group 1', data: DATA.curve_g1, borderColor: '#e74c3c',
             backgroundColor: 'rgba(231,76,60,.08)', fill: 1, tension: .3, pointRadius: 3 }});
  if (DATA.curve_g2 && DATA.curve_g2.some(v => v !== null))
    ds.push({{ label: 'Group 2', data: DATA.curve_g2, borderColor: '#2980b9',
             backgroundColor: 'rgba(41,128,185,.08)', fill: 2, tension: .3, pointRadius: 3 }});
  if (!ds.length) return;
  new Chart(canvas, {{
    type: 'line',
    data: {{ labels: DATA.labels, datasets: ds }},
    options: {{ responsive: true,
               scales: {{ y: {{ ticks: {{ callback: v=>v+'元' }} }} }} }}
  }});
}})();

// ─── Group 1 各標的損益 ───
(function() {{
  const canvas = document.getElementById('chartSymbolsG1');
  if (!canvas || !DATA.symbol_stats_g1 || !DATA.symbol_stats_g1.length) return;
  new Chart(canvas, {{
    type: 'bar',
    data: {{ labels: DATA.symbol_stats_g1.map(s=>s.symbol),
            datasets: [{{ label: '損益', data: DATA.symbol_stats_g1.map(s=>s.pnl),
                         backgroundColor: DATA.symbol_stats_g1.map(s=>s.pnl>=0?'rgba(231,76,60,.7)':'rgba(52,152,219,.7)') }}] }},
    options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }},
               scales: {{ y: {{ ticks: {{ callback: v=>v+'元' }} }} }} }}
  }});
}})();

// ─── Group 2 各標的損益 ───
(function() {{
  const canvas = document.getElementById('chartSymbolsG2');
  if (!canvas || !DATA.symbol_stats_g2 || !DATA.symbol_stats_g2.length) return;
  new Chart(canvas, {{
    type: 'bar',
    data: {{ labels: DATA.symbol_stats_g2.map(s=>s.symbol),
            datasets: [{{ label: '損益', data: DATA.symbol_stats_g2.map(s=>s.pnl),
                         backgroundColor: DATA.symbol_stats_g2.map(s=>s.pnl>=0?'rgba(231,76,60,.7)':'rgba(52,152,219,.7)') }}] }},
    options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }},
               scales: {{ y: {{ ticks: {{ callback: v=>v+'元' }} }} }} }}
  }});
}})();
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
    # count total trades
    g1 = df[df["group"] == 1] if not df.empty else pd.DataFrame()
    g2 = df[df["group"] == 2] if not df.empty else pd.DataFrame()
    cnt = len(compute_pnl(g1)) + len(compute_pnl(g2))
    print(f"✅ dashboard.html 已產生（{cnt} 筆交易）")


if __name__ == "__main__":
    main()
