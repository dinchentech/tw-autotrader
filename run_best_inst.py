"""
run_best_inst.py — 法人抬轎最佳參數完整回測
SL=10%, TM=10, LB=20, fish_score=4.0, fish_days=60, M=0, P=100%
"""
import pickle, time, sys, os
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from core.inst_strategy_core import precompute_fish_scores, screen_fish_qualified

SL = 0.10
TM = 10
LB = 20
INITIAL_CAPITAL = 500_000.0
TOP_N = 3
MIN_VOL = 2000
BUY_RATIO = 0.03
BUY_COST = 0.001425
SELL_COST = 0.004425
FISH_SCORE = 4.0
FISH_DAYS = 60

PRICE_CACHE = Path("cache/inst_momentum/price")
TWSE_CACHE  = Path("cache/inst_momentum/2022/twse_inst_2022-01-01_2025-12-31.pkl")
MCAP        = Path("cache/inst_momentum/mcap_ranking.pkl")

print("=" * 60)
print("📊 法人抬轎動能策略 — 最佳參數回測")
print(f"   參數: SL={SL:.0%} TM={TM} LB={LB} fish={FISH_SCORE} days={FISH_DAYS} M=0 P=100%")
print(f"   本金: NT${INITIAL_CAPITAL:,}")
print("=" * 60)

STOCK_NO = int(os.getenv("STOCK_NO", "150"))

# 1. Load cache
if MCAP.exists():
    stock_ids = [s for s in pickle.loads(MCAP.read_bytes()) if s.isdigit() and len(s) == 4][:STOCK_NO]
else:
    stock_ids = pickle.loads((PRICE_CACHE / "stock_ids.pkl").read_bytes())[:STOCK_NO]
print(f"\n📂 股票：{len(stock_ids)} 檔")

all_data = {}
for i, sid in enumerate(stock_ids):
    pf = PRICE_CACHE / f"{sid}.pkl"
    if pf.exists():
        df = pickle.loads(pf.read_bytes())
        if not df.empty:
            all_data[sid] = df
print(f"✅ 載入 {len(all_data)} 檔")

all_dates = sorted(set(
    d.date() if hasattr(d, "date") else d
    for df in all_data.values() if not df.empty
    for d in df["date"]
))
print(f"   交易日：{len(all_dates)} 天")

twse_data = pickle.loads(TWSE_CACHE.read_bytes())

def merge_twse(data_dict, twse):
    for sid, df in data_dict.items():
        if df.empty:
            continue
        ib, is_ = [], []
        for d in df["date"]:
            ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            day = twse.get(ds, {}).get(sid, (0, 0))
            ib.append(day[0])
            is_.append(day[1])
        df["inst_buy"] = ib
        df["inst_sell"] = is_
    return data_dict

all_data = merge_twse(all_data, twse_data)

# 2. Fish scores + pool
print("\n🔢 魚分計算...")
fish_scores = precompute_fish_scores(all_data)

print("🔍 觀察池...")
fridays = sorted(d for d in all_dates if d.weekday() == 4)
start_dt = datetime(2022, 1, 1).date()
fridays = [d for d in fridays if d >= start_dt]

fish_qualified = {}
for fd in fridays:
    q = screen_fish_qualified(all_data, pd.Timestamp(fd), fish_scores, FISH_DAYS, FISH_SCORE)
    if q:
        fish_qualified[fd] = q
print(f"   ✅ {len(fish_qualified)}/{len(fridays)} 週有觀察池")

# 3. Pre-compute rolling windows
print("\n📦 建立價格快取...")
for sid, df in all_data.items():
    if df.empty:
        continue
    for w in [5, 10, 20, 30]:
        df[f"ma{w}"] = df["close"].rolling(w, min_periods=1).mean()
    df["high20"] = df["close"].rolling(20, min_periods=1).max()
    df["high30"] = df["close"].rolling(30, min_periods=1).max()
    df["vol5"]   = df["volume"].rolling(5, min_periods=1).mean()
    df["inet5"]  = (df["inst_buy"] - df["inst_sell"]).rolling(5, min_periods=1).sum()
    df["ivol5"]  = df["volume"].rolling(5, min_periods=1).sum()

row_by_date = {}
for sid, df in all_data.items():
    if df.empty:
        continue
    rd = {}
    for row in df.itertuples(index=False):
        d = row.date.date() if hasattr(row.date, "date") else row.date
        rd[d] = {
            "close": row.close, "open": row.open, "volume": row.volume,
            "ma10": getattr(row, "ma10", np.nan),
            "ma20": getattr(row, "ma20", np.nan),
            "high20": getattr(row, "high20", np.nan),
            "vol5":  getattr(row, "vol5", 0),
            "inet5": getattr(row, "inet5", 0),
            "ivol5": getattr(row, "ivol5", 0),
        }
    row_by_date[sid] = rd

nxt = {}
for i, d in enumerate(all_dates):
    if i + 1 < len(all_dates):
        nxt[d] = all_dates[i + 1]

fkeys = sorted(fish_qualified.keys())
print(f"   ✅ {len(row_by_date)} 檔 × {len(all_dates)} 交易日")

# 4. Simulation
print("\n💰 模擬交易...")
t0 = time.time()

cash = float(INITIAL_CAPITAL)
positions = {}
marked = {}
equity = []
trade_log = []
fidx = 0
cur_q = set()
ma_lb_key = f"ma{LB}"
ma_tm_key = f"ma{TM}"

for d in all_dates:
    # Sell check
    for sid in list(positions.keys()):
        pos = positions[sid]
        rd = row_by_date.get(sid, {}).get(d)
        if not rd:
            continue
        cp = rd["close"]
        if cp <= 0:
            continue
        loss = (cp - pos["buy_price"]) / pos["buy_price"]
        sell_reason = None
        if loss <= -SL:
            sell_reason = f"硬性停損 {loss:.1%}"
        elif loss > 0:
            ma_v = rd.get(ma_tm_key, np.nan)
            if not np.isnan(ma_v) and cp < ma_v:
                sell_reason = f"跌破 MA{TM}({ma_v:.0f})移動停利"
        if sell_reason:
            proceeds = pos["shares"] * cp * (1 - SELL_COST)
            cost_basis = pos["shares"] * pos["buy_price"]
            pnl = proceeds - cost_basis
            trade_log.append({
                "date": d.isoformat() if hasattr(d, "isoformat") else str(d)[:10],
                "action": "SELL", "stock_id": sid,
                "shares": pos["shares"], "price": round(cp, 2),
                "pnl": round(pnl, 0), "reason": sell_reason,
            })
            cash += proceeds
            del positions[sid]

    # Update fish pool
    if fidx < len(fkeys) and d >= fkeys[fidx]:
        cur_q = fish_qualified[fkeys[fidx]]
        fidx += 1

    # Buy screening
    if cur_q:
        for sid in list(cur_q):
            if sid in positions or len(positions) >= TOP_N:
                continue
            nd = nxt.get(d)
            if not nd:
                continue
            rd = row_by_date.get(sid, {}).get(d)
            if not rd:
                continue
            cp = rd["close"]
            if cp <= 0:
                continue
            if cp < rd.get("high20", cp):
                continue
            ma_v = rd.get(ma_lb_key, np.nan)
            if np.isnan(ma_v) or cp <= ma_v:
                continue
            if rd["vol5"] / 1000 < MIN_VOL:
                continue
            if rd["inet5"] <= 0 or rd["ivol5"] <= 0 or rd["inet5"] / rd["ivol5"] < BUY_RATIO:
                continue
            if nd not in marked:
                marked[nd] = []
            marked[nd].append(sid)

    # Execute marked buys
    if d in marked:
        for sid in marked[d]:
            if sid in positions or len(positions) >= TOP_N:
                continue
            rd = row_by_date.get(sid, {}).get(d, {})
            bp = rd.get("open", rd.get("close", 0))
            if bp <= 0:
                continue
            shares = int(INITIAL_CAPITAL / TOP_N / bp / 1000) * 1000
            if shares <= 0:
                continue
            cost = shares * bp * (1 + BUY_COST)
            if cash < cost:
                shares = int(cash / (bp * (1 + BUY_COST)) / 1000) * 1000
                if shares <= 0:
                    continue
                cost = shares * bp * (1 + BUY_COST)
            cash -= cost
            positions[sid] = {"shares": shares, "buy_price": bp}
            trade_log.append({
                "date": d.isoformat() if hasattr(d, "isoformat") else str(d)[:10],
                "action": "BUY", "stock_id": sid,
                "shares": shares, "price": round(bp, 2),
                "pnl": 0, "reason": "魚分池動能入場",
            })
        del marked[d]

    # Equity
    pv = 0
    for sid, pos in positions.items():
        rd = row_by_date.get(sid, {}).get(d)
        cp = rd["close"] if rd else pos["buy_price"]
        pv += pos["shares"] * cp
    equity.append({"date": d, "total": cash + pv})

# Liquidate remaining
ld = all_dates[-1]
for sid, pos in list(positions.items()):
    rd = row_by_date.get(sid, {}).get(ld, {})
    sp = rd.get("close", pos["buy_price"])
    proceeds = pos["shares"] * sp * (1 - SELL_COST)
    cost_basis = pos["shares"] * pos["buy_price"]
    pnl = proceeds - cost_basis
    trade_log.append({
        "date": ld.isoformat() if hasattr(ld, "isoformat") else str(ld)[:10],
        "action": "SELL", "stock_id": sid,
        "shares": pos["shares"], "price": round(sp, 2),
        "pnl": round(pnl, 0), "reason": "期末平倉",
    })
    cash += proceeds

final_eq = cash
ret = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL
elapsed = time.time() - t0

print(f"   最終權益: NT${final_eq:,.0f}")
print(f"   總報酬: {ret:+.2%}")
print(f"   交易次數: {len(trade_log)}")
print(f"   耗時: {elapsed:.1f}s")

# 5. Monthly breakdown
monthly = {}
for e in equity:
    m = e["date"].strftime("%Y-%m")
    if m not in monthly:
        monthly[m] = {"s": e["total"], "e": e["total"], "h": e["total"], "l": e["total"]}
    else:
        monthly[m]["e"] = e["total"]
        monthly[m]["h"] = max(monthly[m]["h"], e["total"])
        monthly[m]["l"] = min(monthly[m]["l"], e["total"])

# 6. Yearly P&L
def yr_pnl(year):
    items = [(k, v) for k, v in sorted(monthly.items()) if k.startswith(str(year))]
    if not items:
        return None
    if year == 2022:
        start = INITIAL_CAPITAL
    else:
        prev = [(k, v) for k, v in sorted(monthly.items()) if k.startswith(str(year - 1))]
        start = prev[-1][1]["e"] if prev else items[0][1]["s"]
    return items[-1][1]["e"] - start

yr = {y: yr_pnl(y) for y in [2022, 2023, 2024, 2025]}
print(f"\n   各年: 2022:{yr[2022]:+8.0f} 2023:{yr[2023]:+8.0f} 2024:{yr[2024]:+8.0f} 2025:{yr[2025]:+8.0f}")

# 7. Metrics
buys = [t for t in trade_log if t["action"] == "BUY"]
sells = [t for t in trade_log if t["action"] == "SELL"]
closed = [t for t in sells if t.get("pnl", 0) != 0]
wins = [t for t in closed if t["pnl"] > 0]
losses = [t for t in closed if t["pnl"] < 0]
win_rate = len(wins) / len(closed) if closed else 0
avg_win = np.mean([t["pnl"] for t in wins]) if wins else 0
avg_loss = abs(np.mean([t["pnl"] for t in losses])) if losses else 0
profit_factor = avg_win / avg_loss if avg_loss > 0 else float("inf")

peak = INITIAL_CAPITAL
max_dd = 0
max_dd_pct = 0
for e in equity:
    if e["total"] > peak:
        peak = e["total"]
    dd = peak - e["total"]
    dd_pct = dd / peak if peak > 0 else 0
    if dd_pct > max_dd_pct:
        max_dd = dd
        max_dd_pct = dd_pct

print(f"   勝率: {win_rate:.2%}")
print(f"   最大回撤: {max_dd_pct:.2%}")

# 8. Generate report
print("\n📝 產生回測報告...")
lines = []
lines.append(f"# 法人抬轎動能策略 — 最佳參數回測報告（{SL:.0%}/{TM}/{LB}）")
lines.append("")
lines.append("## 策略摘要")
lines.append("")
lines.append("| 項目 | 內容 |")
lines.append("|------|------|")
lines.append(f"| **策略名稱** | 法人抬轎動能策略（Group 2） |")
lines.append("| **回測期間** | 2022-01-01 → 2025-12-31 |")
lines.append(f"| **起始本金** | NT${INITIAL_CAPITAL:,.0f} |")
lines.append("| **交易成本** | 買 0.1425% / 賣 0.4425% |")
lines.append(f"| **持有檔數** | {TOP_N} 檔 |")
lines.append(f"| **流動性門檻** | 近 5 日平均 > {MIN_VOL} 張 |")
lines.append(f"| **法人買超門檻** | 投信+外資佔比 > {BUY_RATIO:.0%} |")
lines.append(f"| **動能條件** | 創 {LB} 日新高 + 站穩 MA{LB} |")
lines.append(f"| **停損** | {SL:.0%} 硬性停損 |")
lines.append(f"| **停利** | 跌破 MA{TM} 移動停利 |")
lines.append(f"| **資料來源** | 股價: FinMind + 法人: TWSE 公開 API |")
lines.append(f"| **篩選標的數** | 全市場前 270 檔（市值排序）|")
lines.append(f"| **法人低吃過濾** | 篩選日前 {FISH_DAYS} 天內低吃分數 ≥ {FISH_SCORE} |")
lines.append("| **獲利滾入** | M=0, P=100%（每筆獲利即時滾入）|")
lines.append("")
lines.append("## 績效總覽")
lines.append("")
lines.append("| 指標 | 數值 |")
lines.append("|------|------|")
lines.append(f"| **最終權益** | NT${final_eq:,.0f} |")
lines.append(f"| **總報酬率** | {ret:+.2%} |")
lines.append(f"| **總交易次數** | {len(trade_log)}（買 {len(buys)} / 賣 {len(sells)}） |")
lines.append(f"| **勝率** | {win_rate:.2%} |")
lines.append(f"| **平均獲利** | NT${avg_win:,.0f} |")
lines.append(f"| **平均虧損** | NT${avg_loss:,.0f} |")
lines.append(f"| **獲利因子** | {profit_factor:.2f} |")
lines.append(f"| **最大回撤** | NT${max_dd:,.0f} ({max_dd_pct:.2%}) |")
lines.append("")
lines.append("## 各年績效")
lines.append("")
lines.append("| 年份 | 年初價值 → 年底價值 | 該年損益 | 說明 |")
lines.append("|------|-------------------|---------|------|")
for year, label in [(2022, "🐻 熊市"), (2023, "🐂 多頭"), (2024, "🐂 多頭"), (2025, "震盪")]:
    items = [(k, v) for k, v in sorted(monthly.items()) if k.startswith(str(year))]
    if not items:
        continue
    start_v = INITIAL_CAPITAL if year == 2022 else \
              [(k, v) for k, v in sorted(monthly.items()) if k.startswith(str(year - 1))][-1][1]["e"]
    end_v = items[-1][1]["e"]
    pnl = end_v - start_v
    lines.append(f"| {year} {label} | NT${start_v:,.0f} → NT${end_v:,.0f} | **{pnl:+,.0f} ({pnl/start_v:+.2%})** |  |")
lines.append("")
lines.append("## 逐月權益變化")
lines.append("")
lines.append("| 月份 | 月初權益 | 月底權益 | 月報酬 | 月高點 | 月低點 |")
lines.append("|------|---------|---------|--------|--------|--------|")
prev_end = INITIAL_CAPITAL
for m_key, m_data in sorted(monthly.items()):
    ret_pct = (m_data["e"] - prev_end) / prev_end * 100 if prev_end else 0
    lines.append(
        f"| {m_key} | NT${m_data['s']:,.0f} | NT${m_data['e']:,.0f} | "
        f"{ret_pct:+.2f}% | NT${m_data['h']:,.0f} | NT${m_data['l']:,.0f} |"
    )
    prev_end = m_data["e"]
lines.append("")
lines.append("## 逐筆交易紀錄")
lines.append("")
lines.append("| 日期 | 動作 | 股票 | 股數 | 價格 | 損益 | 原因 |")
lines.append("|------|------|------|------|------|------|------|")
for t in trade_log:
    if t["action"] == "BUY":
        pnl_str = "-"
    else:
        pnl_str = f"NT${t['pnl']:+,.0f}"
    lines.append(
        f"| {t['date']} | {t['action']} | {t['stock_id']} | "
        f"{t['shares']:,} | ${t['price']:.2f} | {pnl_str} | {t['reason']} |"
    )
lines.append("")
lines.append("---")
lines.append(f"*報告產生時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
lines.append("")

report = "\n".join(lines)
report_file = Path("回測_動能_2022-2025.MD")
report_file.write_text(report, encoding="utf-8")

print(f"✅ 回測報告已寫入 {report_file}")
print(f"\n✅ 回測全部完成！")