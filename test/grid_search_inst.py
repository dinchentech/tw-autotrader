"""
grid_search_inst.py — 法人抬轎參數搜尋（純快取，無網路）
"""
import pickle, time, sys, os
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.inst_strategy_core import precompute_fish_scores, screen_fish_qualified

# ═══════════════════════════════════════════════════════
# 1. 載入快取
# ═══════════════════════════════════════════════════════
print("=" * 60)
print("📊 Grid Search — 法人抬轎策略（純快取）")
print("=" * 60)

PRICE_CACHE = Path("cache/inst_momentum/price")
TWSE_CACHE  = Path("cache/inst_momentum/2022/twse_inst_2022-01-01_2025-12-31.pkl")
MCAP        = Path("cache/inst_momentum/mcap_ranking.pkl")

if MCAP.exists():
    stock_ids = [s for s in pickle.loads(MCAP.read_bytes()) if s.isdigit() and len(s) == 4][:270]
else:
    stock_ids = pickle.loads((PRICE_CACHE / "stock_ids.pkl").read_bytes())[:270]
print(f"\n📂 股票：{len(stock_ids)} 檔")

print("📥 載入價格...")
all_data = {}
for i, sid in enumerate(stock_ids):
    pf = PRICE_CACHE / f"{sid}.pkl"
    if pf.exists():
        df = pickle.loads(pf.read_bytes())
        if not df.empty:
            all_data[sid] = df
    if (i + 1) % 100 == 0:
        print(f"   {i+1}/{len(stock_ids)}")
print(f"   ✅ {len(all_data)} 檔")

all_dates = sorted(set(
    d.date() if hasattr(d, "date") else d
    for df in all_data.values() if not df.empty
    for d in df["date"]
))
print(f"   交易日：{len(all_dates)} 天")

print("📥 載入法人...")
twse_data = pickle.loads(TWSE_CACHE.read_bytes())
print(f"   ✅ {len(twse_data)} 交易日")

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

# ═══════════════════════════════════════════════════════
# 2. 魚分 + 觀察池（固定 fish_score=4, days=60）
# ═══════════════════════════════════════════════════════
print("\n🔢 魚分計算...")
fish_scores = precompute_fish_scores(all_data)

print("🔍 觀察池...")
fridays = sorted(d for d in all_dates if d.weekday() == 4)
start_dt = datetime(2022, 1, 1).date()
fridays = [d for d in fridays if d >= start_dt]

fish_qualified = {}
for fd in fridays:
    q = screen_fish_qualified(all_data, pd.Timestamp(fd), fish_scores, 60, 4.0)
    if q:
        fish_qualified[fd] = q
print(f"   ✅ {len(fish_qualified)}/{len(fridays)} 週有觀察池")

# ═══════════════════════════════════════════════════════
# 2.5 共用價格快取 + nxt map（只建一次）
# ═══════════════════════════════════════════════════════
print("\n📦 建立共用價格快取...")

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
            "inst_buy": getattr(row, "inst_buy", 0),
            "inst_sell": getattr(row, "inst_sell", 0),
            "ma5":  getattr(row, "ma5",  np.nan),
            "ma10": getattr(row, "ma10", np.nan),
            "ma20": getattr(row, "ma20", np.nan),
            "ma30": getattr(row, "ma30", np.nan),
            "high20": getattr(row, "high20", np.nan),
            "high30": getattr(row, "high30", np.nan),
            "vol5":   getattr(row, "vol5",  0),
            "inet5":  getattr(row, "inet5", 0),
            "ivol5":  getattr(row, "ivol5", 0),
        }
    row_by_date[sid] = rd

nxt = {}
for i, d in enumerate(all_dates):
    if i + 1 < len(all_dates):
        nxt[d] = all_dates[i + 1]

fkeys = sorted(fish_qualified.keys())

print(f"   ✅ {len(row_by_date)} 檔 × {len(all_dates)} 交易日")

# ═══════════════════════════════════════════════════════
# 3. Grid Search
# ═══════════════════════════════════════════════════════
INITIAL_CAPITAL = 500_000.0
BUY_COST  = 0.001425
SELL_COST = 0.004425
TOP_N     = 3
BUY_RATIO = 0.03
MIN_VOL   = 2000

print(f"\n🚀 Grid Search：3×4×2=24 組")
print(f"   固定：fish_score=4.0, fish_days=60, M=0, P=100%")
print()

results = []

for sl in [0.05, 0.07, 0.10]:
    for tm in [5, 10, 20, 30]:
        for lb in [20, 30]:
            t0 = time.time()
            ma_lb_key = f"ma{lb}"
            ma_tm_key = f"ma{tm}"

            cash = float(INITIAL_CAPITAL)
            positions = {}
            marked = {}
            equity = []
            fidx = 0
            cur_q = set()

            for d in all_dates:
                # --- Sell check ---
                sell_list = []
                for sid, pos in positions.items():
                    rd = row_by_date.get(sid, {}).get(d)
                    if not rd:
                        continue
                    cp = rd["close"]
                    if cp <= 0:
                        continue
                    loss = (cp - pos["buy_price"]) / pos["buy_price"]
                    if loss <= -sl:
                        sell_list.append(sid)
                    elif loss > 0:
                        ma_v = rd.get(ma_tm_key, np.nan)
                        if not np.isnan(ma_v) and cp < ma_v:
                            sell_list.append(sid)
                for sid in sell_list:
                    rd = row_by_date.get(sid, {}).get(d, {})
                    cp = rd.get("close", positions[sid]["buy_price"])
                    cash += positions[sid]["shares"] * cp * (1 - SELL_COST)
                    del positions[sid]

                # --- Update fish pool ---
                if fidx < len(fkeys) and d >= fkeys[fidx]:
                    cur_q = fish_qualified[fkeys[fidx]]
                    fidx += 1

                # --- Buy screening ---
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
                        high_key = f"high{lb}"
                        if cp < rd.get(high_key, cp):
                            continue
                        ma_v = rd.get(ma_lb_key, np.nan)
                        if np.isnan(ma_v) or cp <= ma_v:
                            continue
                        if rd["vol5"] / 1000 < MIN_VOL:
                            continue
                        inet5 = rd["inet5"]
                        ivol5 = rd["ivol5"]
                        if inet5 <= 0 or ivol5 <= 0 or inet5 / ivol5 < BUY_RATIO:
                            continue
                        if nd not in marked:
                            marked[nd] = []
                        marked[nd].append(sid)

                # --- Execute marked buys ---
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
                    del marked[d]

                # --- Equity ---
                pv = 0
                for sid, pos in positions.items():
                    rd = row_by_date.get(sid, {}).get(d)
                    cp = rd["close"] if rd else pos["buy_price"]
                    pv += pos["shares"] * cp
                equity.append({"date": d, "total": cash + pv})

            # --- Record trade log ---
            trade_log = []
            def record_trade(date, action, stock_id, shares, price, reason="", pnl=0):
                if action in ("BUY", "SELL"):
                    trade_log.append({
                        "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10],
                        "action": action,
                        "stock_id": stock_id,
                        "shares": shares,
                        "price": round(price, 2),
                        "reason": reason,
                        "pnl": round(pnl, 0),
                    })

            final_eq = cash

            monthly = {}
            for e in equity:
                m = e["date"].strftime("%Y-%m")
                if m not in monthly:
                    monthly[m] = {"s": e["total"], "e": e["total"], "h": e["total"], "l": e["total"]}
                else:
                    monthly[m]["e"] = e["total"]
                    monthly[m]["h"] = max(monthly[m]["h"], e["total"])
                    monthly[m]["l"] = min(monthly[m]["l"], e["total"])

            def yr_pnl(year):
                items = sorted(monthly.items())
                rows = [v for k, v in items if k.startswith(str(year))]
                if not rows:
                    return None
                if year == 2022:
                    start = INITIAL_CAPITAL
                else:
                    prev = [v for k, v in items if k.startswith(str(year - 1))]
                    start = prev[-1]["e"] if prev else rows[0]["s"]
                return rows[-1]["e"] - start

            yr = {y: yr_pnl(y) for y in [2022, 2023, 2024, 2025]}
            all_pos = all(v is not None and v > 0 for v in yr.values())
            ret = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL
            tag = "✅" if all_pos else "  "

            elapsed = time.time() - t0
            print(f"{tag} SL={sl:.0%} TM={tm:2d} LB={lb:2d} | "
                  f"2022:{yr[2022]:+8.0f} 2023:{yr[2023]:+8.0f} "
                  f"2024:{yr[2024]:+8.0f} 2025:{yr[2025]:+8.0f} | "
                  f"總:{ret:+6.2%} 終值:NT${final_eq:,.0f} | {elapsed:.1f}s")

            results.append({
                "sl": sl, "tm": tm, "lb": lb,
                **{f"yr{y}": v for y, v in yr.items()},
                "ret": ret, "final_eq": final_eq,
                "all_pos": all_pos,
                "trade_log": trade_log,
                "equity": equity,
            })

            if all_pos and ret == winners[0]["ret"]:
                print("\n--- 生成最佳參數完整回測報告 ---")
                # Compute metrics
                trades = trade_log
                if not trades:
                    print("   ⚠️  無交易記錄，跳過報告")
                else:
                    buys = [t for t in trades if t["action"] == "BUY"]
                    sells = [t for t in trades if t["action"] == "SELL"]
                    closed_trades = [t for t in sells if t.get("pnl", 0) != 0]
                    wins = [t for t in closed_trades if t["pnl"] > 0]
                    losses = [t for t in closed_trades if t["pnl"] < 0]
                    win_rate = len(wins) / len(closed_trades) if closed_trades else 0
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

                    # Generate report
                    report_lines = []
                    report_lines.append(f"# 法人抬轎動能策略 — Grid Search 最佳參數回測報告")
                    report_lines.append("")
                    report_lines.append("## 策略摘要")
                    report_lines.append("")
                    report_lines.append("| 項目 | 內容 |")
                    report_lines.append("|------|------|")
                    report_lines.append(f"| **策略名稱** | 法人抬轎動能策略（Group 2） |")
                    report_lines.append(f"| **回測期間** | 2022-01-01 → 2025-12-31 |")
                    report_lines.append(f"| **起始本金** | NT${INITIAL_CAPITAL:,.0f} |")
                    report_lines.append("| **交易成本** | 買 0.1425% / 賣 0.4425% |")
                    report_lines.append(f"| **持有檔數** | {TOP_N} 檔 |")
                    report_lines.append(f"| **流動性門檻** | 近 5 日平均 > {MIN_VOL} 張 |")
                    report_lines.append(f"| **法人買超門檻** | 投信+外資佔比 > {BUY_RATIO_THRESHOLD:.0%} |")
                    report_lines.append(f"| **動能條件** | 創 {lb} 日新高 + 站穩 MA{lb} |")
                    report_lines.append(f"| **停損** | {sl:.0%} 硬性停損 |")
                    report_lines.append(f"| **停利** | 跌破 MA{tm} 移動停利 |")
                    report_lines.append(f"| **資料來源** | 股價: FinMind 快取 + TWSE 三大法人 |")
                    report_lines.append("")
                    report_lines.append("## 績效總覽")
                    report_lines.append("")
                    report_lines.append("| 指標 | 數值 |")
                    report_lines.append("|------|------|")
                    report_lines.append(f"| **最終權益** | NT${final_eq:,.0f} |")
                    report_lines.append(f"| **總報酬率** | {ret:+.2%} |")
                    report_lines.append(f"| **總交易次數** | {len(trades)}（買 {len(buys)} / 賣 {len(sells)}） |")
                    report_lines.append(f"| **勝率** | {win_rate:.2%} |")
                    report_lines.append(f"| **平均獲利** | NT${avg_win:,.0f} |")
                    report_lines.append(f"| **平均虧損** | NT${avg_loss:,.0f} |")
                    report_lines.append(f"| **獲利因子** | {profit_factor:.2f} |")
                    report_lines.append(f"| **最大回撤** | NT${max_dd:,.0f} ({max_dd_pct:.2%}) |")
                    report_lines.append("")
                    report_lines.append("## 逐月權益變化")
                    report_lines.append("")
                    report_lines.append("| 月份 | 月初權益 | 月底權益 | 月報酬 | 月高點 | 月低點 |")
                    report_lines.append("|------|---------|---------|--------|--------|--------|")
                    prev_end = INITIAL_CAPITAL
                    for m in sorted(monthly):
                        row = monthly[m]
                        ret_pct = (row["end"] - prev_end) / prev_end * 100
                        report_lines.append(
                            f"| {m['month']} | NT${m['start']:,.0f} | NT${m['end']:,.0f} | "
                            f"{ret_pct:+.2f}% | NT${m['high']:,.0f} | NT${m['low']:,.0f} |"
                        )
                        prev_end = m["end"]
                    report_lines.append("")
                    report_lines.append("## 逐筆交易紀錄")
                    report_lines.append("")
                    report_lines.append("| 日期 | 動作 | 股票 | 股數 | 價格 | 損益 | 原因 |")
                    report_lines.append("|------|------|------|------|------|------|------|")
                    for t in trade_log:
                        if t["action"] == "BUY":
                            pnl_str = "-"
                        else:
                            pnl_str = f"NT${t['pnl']:+,.0f}"
                        report_lines.append(
                            f"| {t['date']} | {t['action']} | {t['stock_id']} | "
                            f"{t['shares']:,} | ${t['price']:.2f} | {pnl_str} | {t['reason']} |"
                        )
                    report_lines.append("")
                    report_lines.append("---")
                    report_lines.append(f"*報告產生時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
                    report_lines.append("")
                    report = "\n".join(report_lines)
                    report_file = Path("回測_動能_2022-2025_GridSearch.md")
                    report_file.write_text(report, encoding="utf-8")
                    print(f"✅ 完整回測報告已寫入 {report_file}")
                    print(f"   最終權益: NT${final_eq:,.0f}")
                    print(f"   總報酬: {ret:+.2%}")
                    print(f"   勝率: {win_rate:.2%}")
                    print(f"   交易次數: {len(trades)}")
                    print(f"   最大回撤: {max_dd_pct:.2%}")

print()
print("=" * 60)
winners = sorted([r for r in results if r["all_pos"]], key=lambda x: x["ret"], reverse=True)
print(f"🏆 每年都獲利（共 {len(winners)} 組）：")
for i, r in enumerate(winners[:10]):
    print(f"  {i+1}. SL={r['sl']:.0%} TM={r['tm']:2d} LB={r['lb']:2d} | "
          f"2022:{r['yr2022']:+8.0f} 2023:{r['yr2023']:+8.0f} "
          f"2024:{r['yr2024']:+8.0f} 2025:{r['yr2025']:+8.0f} | 總:{r['ret']:+6.2%}")

if winners:
    b = winners[0]
    print(f"\n📌 最佳：SL={b['sl']:.0%} TM={b['tm']} LB={b['lb']}  總:{b['ret']:+6.2%}  終值:NT${b['final_eq']:,.0f}")
    print(f"   2022:{b['yr2022']:+,.0f} | 2023:{b['yr2023']:+,.0f} | 2024:{b['yr2024']:+,.0f} | 2025:{b['yr2025']:+,.0f}")
else:
    print("❌ 無年年正報酬組合，前5名：")
    for r in sorted(results, key=lambda x: x["ret"], reverse=True)[:5]:
        print(f"  SL={r['sl']:.0%} TM={r['tm']:2d} LB={r['lb']:2d} | "
              f"2022:{r['yr2022']:+8.0f} 總:{r['ret']:+6.2%}")
