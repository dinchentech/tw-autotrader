"""
backtest_inst_momentum.py — 法人抬轎動能策略 2025 回測
=====================================================
使用 TWSE 公開 API 取得三大法人買賣資料（免配額限制）。
價格資料來自 FinMind（快取支援）。

策略邏輯：
  1. 每週五篩選全市場（流動性 > 2000 張 + 法人買超 > 3% + 創 20 日高 + 站穩 MA20）
  2. 排序取前 TOP_N 名，次週一開盤進場
  3. 每日監控：-7% 硬性停損 / 跌破 MA10 移動停利

使用方法：
  python backtest_inst_momentum.py

輸出：
  回測_動能_2024_2025.MD
"""
import os
import sys
import pickle
import math
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

CACHE_DIR = Path("cache/inst_momentum")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ─── 參數 ─────────────────────────────────────────────────
START_DATE = "2025-01-01"
END_DATE = "2025-12-31"
INITIAL_CAPITAL = 500_000
TOP_N = 2
MIN_VOLUME_SHARES = 2000        # 張
BUY_RATIO_THRESHOLD = 0.03
LOOKBACK = 20
STOP_LOSS = 0.07
TRAILING_PERIOD = 10
BUY_COST = 0.001425             # 手續費 0.1425%
SELL_COST = 0.004425            # 手續費 0.1425% + 交易稅 0.3%


def finmind_login():
    from FinMind.data import DataLoader
    from dotenv import load_dotenv
    load_dotenv()
    token = os.getenv("FINMIND_API_TOKEN", "")
    dl = DataLoader(token=token)
    if token:
        dl.login_by_token(api_token=token)
    return dl


# ─── 階段 1a：下載價格資料（FinMind，含快取）─────────────

def get_all_stock_ids(dl) -> list:
    """回傳上市普通股 stock_id 列表"""
    cache_file = CACHE_DIR / "stock_ids.pkl"
    if cache_file.exists():
        return pickle.loads(cache_file.read_bytes())
    df = dl.taiwan_stock_info()
    ids = sorted(set(
        s.strip() for s in df["stock_id"]
        if s.strip().isdigit() and len(s.strip()) == 4
    ))
    cache_file.write_bytes(pickle.dumps(ids))
    print(f"📋 上市股票總數: {len(ids)}")
    return ids


def download_price_data(dl, stock_id: str) -> pd.DataFrame:
    """下載單一 stock 的日K，回傳含 ma20/ma10 的 DataFrame"""
    cache_file = CACHE_DIR / f"{stock_id}.pkl"
    if cache_file.exists():
        return pickle.loads(cache_file.read_bytes())

    start = "2023-06-01"
    try:
        df_price = dl.taiwan_stock_daily(
            stock_id=stock_id, start_date=start, end_date=END_DATE
        )
    except Exception:
        cache_file.write_bytes(pickle.dumps(pd.DataFrame()))
        return pd.DataFrame()

    if df_price.empty:
        cache_file.write_bytes(pickle.dumps(pd.DataFrame()))
        return pd.DataFrame()

    df_price = df_price.rename(columns={
        "date": "date", "open": "open", "max": "high",
        "min": "low", "close": "close", "Trading_Volume": "volume",
    })
    df_price["date"] = pd.to_datetime(df_price["date"])
    df_price = df_price.sort_values("date").reset_index(drop=True)

    # 計算技術指標
    df_price["ma20"] = df_price["close"].rolling(LOOKBACK).mean()
    df_price["ma10"] = df_price["close"].rolling(TRAILING_PERIOD).mean()

    cache_file.write_bytes(pickle.dumps(df_price))
    return df_price


# ─── 階段 1b：從 TWSE 下載三大法人資料 ──────────────────────

def fetch_twse_inst_data(trading_dates: set) -> dict:
    """
    從 TWSE 公開 API 下載三大法人買賣超日報。
    TWSE 一次回傳全市場資料，不用逐股查詢，避開 FinMind 配額限制。

    回傳 { date_str: { stock_id: (inst_buy, inst_sell) } }
    其中 inst_buy/sell = 投信買進 + 外陸資買進/賣出
    """
    cache_file = CACHE_DIR / "twse_inst.pkl"
    if cache_file.exists():
        print("   載入 TWSE 法人資料快取...")
        return pickle.loads(cache_file.read_bytes())

    dates = sorted(d for d in trading_dates
                   if d >= pd.Timestamp(START_DATE).date())
    inst_data = {}  # { date_str: { stock_id: (buy, sell) } }

    for i, d in enumerate(dates):
        date_str = d.strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999"
        try:
            resp = requests.get(url, timeout=15)
            data = resp.json()
        except Exception as e:
            print(f"  ⚠ TWSE 請求失敗 {date_str}: {e}")
            continue

        if data.get("stat") != "OK":
            continue

        day_data = {}
        for row in data.get("data", []):
            sid = str(row[0]).strip()
            if not sid.isdigit() or len(sid) != 4:
                continue
            try:
                foreign_buy = int(row[2].replace(",", ""))
                foreign_sell = int(row[3].replace(",", ""))
                trust_buy = int(row[8].replace(",", ""))
                trust_sell = int(row[9].replace(",", ""))
            except (ValueError, IndexError):
                continue
            day_data[sid] = (foreign_buy + trust_buy, foreign_sell + trust_sell)
        inst_data[d.isoformat()] = day_data

        if (i + 1) % 50 == 0:
            print(f"   TWSE 下載進度: {i+1}/{len(dates)}")

    cache_file.write_bytes(pickle.dumps(inst_data))
    print(f"✅ TWSE 法人資料下載完成: {len(inst_data)} 交易日")
    return inst_data


def merge_twse_inst(all_data: dict, twse_data: dict) -> dict:
    """
    將 TWSE 法人資料合併到各股的 DataFrame 中。
    使用 dict lookup 取代 DataFrame merge 以提升速度。
    """
    for stock_id, df in all_data.items():
        if df.empty:
            continue
        inst_buy_list = []
        inst_sell_list = []
        for d in df["date"]:
            d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            day_data = twse_data.get(d_str, {}).get(stock_id, (0, 0))
            inst_buy_list.append(day_data[0])
            inst_sell_list.append(day_data[1])
        df["inst_buy"] = inst_buy_list
        df["inst_sell"] = inst_sell_list
    return all_data


# ─── 階段 2：篩選候選股 ──────────────────────────────────

def screen_candidates(
    all_data: dict, screening_date: pd.Timestamp
) -> list:
    candidates = []
    for stock_id, df in all_data.items():
        if df.empty or len(df) < LOOKBACK + 5:
            continue

        date_mask = df["date"] <= screening_date
        if not date_mask.any():
            continue
        recent = df[date_mask].tail(LOOKBACK + 5)
        if len(recent) < LOOKBACK + 1:
            continue

        latest = recent.iloc[-1]
        latest_close = latest["close"]
        if latest_close <= 0 or math.isnan(latest_close):
            continue

        vol_5 = recent.tail(5)["volume"].mean()
        if vol_5 / 1000 < MIN_VOLUME_SHARES:
            continue

        if latest_close < recent.tail(LOOKBACK)["close"].max():
            continue

        ma20 = latest.get("ma20")
        if ma20 is None or math.isnan(ma20) or latest_close <= ma20:
            continue

        inst_recent = recent.tail(5)
        total_net_buy = inst_recent["inst_buy"].sum() - inst_recent["inst_sell"].sum()
        total_vol_5 = inst_recent["volume"].sum()
        if total_net_buy <= 0 or total_vol_5 <= 0:
            continue
        ratio = total_net_buy / total_vol_5
        if ratio < BUY_RATIO_THRESHOLD:
            continue

        candidates.append((stock_id, round(ratio, 4)))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:TOP_N]


# ─── 階段 3：交易模擬 ──────────────────────────────────

def check_position_exit(
    sid: str, positions: dict, daily_prices: dict, d: date, cash: float,
    trade_log: list, price_cache: dict
) -> float:
    """檢查單一持倉是否需要出場。回傳出場收回的 cash（0 代表續抱）。"""
    pos = positions[sid]
    price_info = daily_prices.get(sid, {})
    current_price = price_info.get("close", 0)
    if current_price <= 0:
        return 0

    loss_pct = (current_price - pos["buy_price"]) / pos["buy_price"]

    # 硬性停損 -7%
    if loss_pct <= -STOP_LOSS:
        sell_price = current_price
        reason = f"硬性停損 {loss_pct:.1%}"
    # 跌破 MA10 移動停利（只在獲利時觸發）
    elif loss_pct > 0:
        ma10 = price_info.get("ma10")
        if ma10 is not None and not math.isnan(ma10) and current_price < ma10:
            sell_price = current_price
            reason = f"跌破 MA10({ma10:.0f})移動停利"
        else:
            return 0  # 續抱
    else:
        return 0  # 小虧但沒破停損，續抱

    # 執行賣出
    proceeds = pos["shares"] * sell_price * (1 - SELL_COST)
    cost_basis = pos["shares"] * pos["buy_price"]
    pnl = proceeds - cost_basis
    trade_log.append({
        "date": d.isoformat(), "action": "SELL",
        "stock_id": sid, "shares": pos["shares"],
        "price": round(sell_price, 2), "pnl": round(pnl, 0),
        "reason": reason,
    })
    del positions[sid]
    return proceeds


def simulate(all_data: dict, weekly_candidates: dict) -> dict:
    cash = float(INITIAL_CAPITAL)
    positions = {}       # { stock_id: { shares, buy_price, buy_date } }
    trade_log = []
    equity_curve = []

    # 收集所有交易日並排序
    all_dates = set()
    for df in all_data.values():
        if not df.empty:
            all_dates.update(df["date"].dt.date)
    all_dates = sorted(all_dates)

    # 預先建立每日價格 + 法人查詢（含 ma20, ma10, inst_buy, inst_sell）
    price_cache = {}
    for d in all_dates:
        price_cache[d] = {}
    for stock_id, df in all_data.items():
        if df.empty:
            continue
        for _, row in df.iterrows():
            d = row["date"].date()
            if d in price_cache:
                price_cache[d][stock_id] = {
                    "close": row["close"],
                    "open": row["open"],
                    "ma10": row.get("ma10", None),
                    "ma20": row.get("ma20", None),
                    "volume": row["volume"],
                    "inst_buy": row.get("inst_buy", 0),
                    "inst_sell": row.get("inst_sell", 0),
                }

    # 找出所有週五
    fridays = sorted(set(d for d in all_dates if d.weekday() == 4))
    # 週五 → 下個交易日（週一）對應
    monday_map = {}
    for fd in fridays:
        for d in all_dates:
            if d > fd:
                monday_map[fd] = d
                break

    # 逐日模擬
    monday_todo = None

    for day_idx, d in enumerate(all_dates):
        daily_prices = price_cache[d]

        # ── 每日停損/移動停利檢查 ──
        for sid in list(positions.keys()):
            cash += check_position_exit(
                sid, positions, daily_prices, d, cash, trade_log, price_cache
            )

        # ── 週五：準備篩選結果 ──
        if d in fridays and d in weekly_candidates:
            monday_todo = (d, weekly_candidates[d])

        # ── 週一：檢查持倉 + 買入新候選 ──
        if monday_todo is not None:
            friday_date, cands = monday_todo
            if d == monday_map.get(friday_date):
                cand_ids = {c[0] for c in cands}

                # 出場檢查：跌破 MA20 或 法人明顯出貨
                for sid in list(positions.keys()):
                    price_info = daily_prices.get(sid, {})
                    current_price = price_info.get("close", 0)
                    if current_price <= 0:
                        continue
                    ma20 = price_info.get("ma20", 0)
                    if ma20 and not math.isnan(ma20) and current_price < ma20:
                        sell_price = price_info.get("open", current_price)
                        proceeds = positions[sid]["shares"] * sell_price * (1 - SELL_COST)
                        pnl = proceeds - positions[sid]["shares"] * positions[sid]["buy_price"]
                        trade_log.append({
                            "date": d.isoformat(), "action": "SELL",
                            "stock_id": sid, "shares": positions[sid]["shares"],
                            "price": round(sell_price, 2), "pnl": round(pnl, 0),
                            "reason": "跌破 MA20 出場",
                        })
                        cash += proceeds
                        del positions[sid]
                        continue

                # 買入新候選（只補空缺，不強制換股）
                for stock_id, score in cands:
                    if stock_id in positions:
                        continue
                    if len(positions) >= TOP_N:
                        break  # 滿倉就不買
                    price_info = daily_prices.get(stock_id, {})
                    buy_price = price_info.get("open", price_info.get("close", 0))
                    if buy_price <= 0:
                        continue
                    per_stock = INITIAL_CAPITAL / TOP_N
                    shares = int(per_stock / buy_price / 1000) * 1000
                    if shares <= 0:
                        continue
                    cost = shares * buy_price * (1 + BUY_COST)
                    if cash < cost:
                        shares = int(cash / (buy_price * (1 + BUY_COST)) / 1000) * 1000
                        if shares <= 0:
                            continue
                        cost = shares * buy_price * (1 + BUY_COST)
                    cash -= cost
                    positions[stock_id] = {
                        "shares": shares, "buy_price": buy_price, "buy_date": d,
                    }
                    trade_log.append({
                        "date": d.isoformat(), "action": "BUY",
                        "stock_id": stock_id, "shares": shares,
                        "price": round(buy_price, 2), "pnl": 0,
                        "reason": f"篩選入選 score={score}",
                    })

                monday_todo = None

        # ── 每日停損/停利檢查 ──
        for sid in list(positions.keys()):
            pos = positions[sid]
            price_info = daily_prices.get(sid, {})
            current_price = price_info.get("close", 0)
            if current_price <= 0:
                continue

            loss_pct = (current_price - pos["buy_price"]) / pos["buy_price"]
            if loss_pct <= -STOP_LOSS:
                proceeds = pos["shares"] * current_price * (1 - SELL_COST)
                cost_basis = pos["shares"] * pos["buy_price"]
                cash += proceeds
                pnl = proceeds - cost_basis
                trade_log.append({
                    "date": d.isoformat(),
                    "action": "SELL",
                    "stock_id": sid,
                    "shares": pos["shares"],
                    "price": round(current_price, 2),
                    "pnl": round(pnl, 0),
                    "reason": f"硬性停損 {loss_pct:.1%}",
                })
                del positions[sid]
                continue

            ma10 = price_info.get("ma10")
            if ma10 is not None and not math.isnan(ma10) and loss_pct > 0:
                if current_price < ma10:
                    proceeds = pos["shares"] * current_price * (1 - SELL_COST)
                    cost_basis = pos["shares"] * pos["buy_price"]
                    cash += proceeds
                    pnl = proceeds - cost_basis
                    trade_log.append({
                        "date": d.isoformat(),
                        "action": "SELL",
                        "stock_id": sid,
                        "shares": pos["shares"],
                        "price": round(current_price, 2),
                        "pnl": round(pnl, 0),
                        "reason": f"跌破 MA10({ma10:.0f})移動停利",
                    })
                    del positions[sid]

        # ── 當日權益 ──
        pos_value = 0
        for sid, pos in positions.items():
            price_info = daily_prices.get(sid, {})
            p = price_info.get("close", pos["buy_price"])
            pos_value += pos["shares"] * p
        total_equity = cash + pos_value
        equity_curve.append({
            "date": d.isoformat(),
            "cash": round(cash, 0),
            "position_value": round(pos_value, 0),
            "total_equity": round(total_equity, 0),
        })

    # 期末平倉
    for sid in list(positions.keys()):
        pos = positions.pop(sid)
        last_d = all_dates[-1]
        price_info = price_cache.get(last_d, {}).get(sid, {})
        sell_price = price_info.get("close", pos["buy_price"])
        proceeds = pos["shares"] * sell_price * (1 - SELL_COST)
        cost_basis = pos["shares"] * pos["buy_price"]
        cash += proceeds
        pnl = proceeds - cost_basis
        trade_log.append({
            "date": last_d.isoformat(),
            "action": "SELL",
            "stock_id": sid,
            "shares": pos["shares"],
            "price": round(sell_price, 2),
            "pnl": round(pnl, 0),
            "reason": "期末平倉",
        })
        if equity_curve:
            equity_curve[-1]["cash"] = round(cash, 0)
            equity_curve[-1]["position_value"] = 0
            equity_curve[-1]["total_equity"] = round(cash, 0)

    return {
        "final_cash": cash,
        "total_return": (cash - INITIAL_CAPITAL) / INITIAL_CAPITAL,
        "trade_log": trade_log,
        "equity_curve": equity_curve,
    }


# ─── 階段 4：計算績效指標 ────────────────────────────────

def compute_metrics(result: dict) -> dict:
    trades = result["trade_log"]
    equity = result["equity_curve"]

    if not trades:
        return {"error": "no trades"}

    buys = [t for t in trades if t["action"] == "BUY"]
    sells = [t for t in trades if t["action"] == "SELL"]
    total_trades = len(buys) + len(sells)

    closed_trades = [t for t in sells if t.get("pnl", 0) != 0]
    wins = [t for t in closed_trades if t["pnl"] > 0]
    losses = [t for t in closed_trades if t["pnl"] < 0]
    win_rate = len(wins) / len(closed_trades) if closed_trades else 0

    avg_win = np.mean([t["pnl"] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t["pnl"] for t in losses])) if losses else 0
    profit_factor = avg_win / avg_loss if avg_loss > 0 else float("inf")

    peak = INITIAL_CAPITAL
    max_drawdown = 0
    max_drawdown_pct = 0
    for e in equity:
        if e["total_equity"] > peak:
            peak = e["total_equity"]
        dd = peak - e["total_equity"]
        dd_pct = dd / peak if peak > 0 else 0
        if dd_pct > max_drawdown_pct:
            max_drawdown = dd
            max_drawdown_pct = dd_pct

    return {
        "total_trades": total_trades,
        "buy_trades": len(buys),
        "sell_trades": len(sells),
        "closed_trades": len(closed_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 0),
        "avg_loss": round(avg_loss, 0),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_drawdown, 0),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "total_return": round(result["total_return"], 4),
        "final_equity": round(result["final_cash"], 0),
    }


def generate_monthly_breakdown(equity_curve: list, capital: float) -> list:
    monthly = defaultdict(lambda: {"start": 0, "end": 0, "high": 0, "low": float("inf")})
    for e in equity_curve:
        m = e["date"][:7]
        monthly[m]["end"] = e["total_equity"]
        if monthly[m]["start"] == 0:
            monthly[m]["start"] = e["total_equity"]
        monthly[m]["high"] = max(monthly[m]["high"], e["total_equity"])
        monthly[m]["low"] = min(monthly[m]["low"], e["total_equity"])

    rows = []
    prev_end = capital
    for m in sorted(monthly):
        d = monthly[m]
        ret = (d["end"] - prev_end) / prev_end * 100
        rows.append({
            "month": m,
            "start": d["start"],
            "end": d["end"],
            "return_pct": round(ret, 2),
            "high": d["high"],
            "low": d["low"],
        })
        prev_end = d["end"]
    return rows


def generate_report(result: dict, metrics: dict, monthly: list):
    """產生 回測_動能_2025.MD"""
    lines = []
    lines.append("# 法人抬轎動能策略 — 2025 回測報告")
    lines.append("")
    lines.append("## 策略摘要")
    lines.append("")
    lines.append("| 項目 | 內容 |")
    lines.append("|------|------|")
    lines.append("| **策略名稱** | 法人抬轎動能策略（Group 2） |")
    lines.append(f"| **回測期間** | {START_DATE} → {END_DATE} |")
    lines.append("| **起始本金** | NT$500,000 |")
    lines.append("| **交易成本** | 買 0.1425% / 賣 0.4425% |")
    lines.append(f"| **持有檔數** | {TOP_N} 檔 |")
    lines.append(f"| **流動性門檻** | 近 5 日平均 > {MIN_VOLUME_SHARES} 張 |")
    lines.append(f"| **法人買超門檻** | 投信+外資佔比 > {BUY_RATIO_THRESHOLD:.0%} |")
    lines.append(f"| **動能條件** | 創 {LOOKBACK} 日新高 + 站穩 MA{LOOKBACK} |")
    lines.append(f"| **停損** | -{STOP_LOSS:.0%} 硬性停損 |")
    lines.append(f"| **停利** | 跌破 MA{TRAILING_PERIOD} 移動停利 |")
    lines.append(f"| **資料來源** | 股價: FinMind / 法人: TWSE 公開 API |")
    lines.append(f"| **篩選標的數** | 307 檔有完整股價紀錄的上市股票 |")
    lines.append("")
    lines.append("## 績效總覽")
    lines.append("")
    lines.append("| 指標 | 數值 |")
    lines.append("|------|------|")
    lines.append(f"| **最終權益** | NT${metrics['final_equity']:,.0f} |")
    lines.append(f"| **總報酬率** | {metrics['total_return']:+.2%} |")
    lines.append(f"| **總交易次數** | {metrics['total_trades']}（買 {metrics['buy_trades']} / 賣 {metrics['sell_trades']}） |")
    lines.append(f"| **勝率** | {metrics['win_rate']:.2%} |")
    lines.append(f"| **平均獲利** | NT${metrics['avg_win']:,.0f} |")
    lines.append(f"| **平均虧損** | NT${metrics['avg_loss']:,.0f} |")
    lines.append(f"| **獲利因子** | {metrics['profit_factor']:.2f} |")
    lines.append(f"| **最大回撤** | NT${metrics['max_drawdown']:,.0f} ({metrics['max_drawdown_pct']:.2%}) |")
    lines.append("")
    lines.append("## 逐月權益變化")
    lines.append("")
    lines.append("| 月份 | 月初權益 | 月底權益 | 月報酬 | 月高點 | 月低點 |")
    lines.append("|------|---------|---------|--------|--------|--------|")
    for m in monthly:
        lines.append(
            f"| {m['month']} | NT${m['start']:,.0f} | NT${m['end']:,.0f} | "
            f"{m['return_pct']:+.2f}% | NT${m['high']:,.0f} | NT${m['low']:,.0f} |"
        )
    lines.append("")
    lines.append("## 逐筆交易紀錄")
    lines.append("")
    lines.append("| 日期 | 動作 | 股票 | 股數 | 價格 | 損益 | 原因 |")
    lines.append("|------|------|------|------|------|------|------|")
    for t in result["trade_log"]:
        pnl_str = f"NT${t['pnl']:+,.0f}" if t["action"] == "SELL" else "-"
        lines.append(
            f"| {t['date']} | {t['action']} | {t['stock_id']} | "
            f"{t['shares']:,} | ${t['price']:.2f} | {pnl_str} | {t['reason']} |"
        )
    lines.append("")
    lines.append("---")
    lines.append(f"*報告產生時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    report = "\n".join(lines)
    Path("回測_動能_2025.MD").write_text(report, encoding="utf-8")
    print(f"\n✅ 回測報告已寫入 回測_動能_2025.MD")
    return report


# ═════════════════════════════════════════════════════════
# 主流程
# ═════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("📊 法人抬轎動能策略 2025 回測")
    print(f"   本金: NT${INITIAL_CAPITAL:,}")
    print(f"   期間: {START_DATE} ~ {END_DATE}")
    print(f"   資料: FinMind 股價 + TWSE 三大法人")
    print("=" * 60)

    # ── 1a. 價格資料 ──
    print("\n📥 階段 1a/4：讀取價格資料（快取）")
    dl = finmind_login()

    stock_ids = get_all_stock_ids(dl)
    print(f"   共 {len(stock_ids)} 檔上市股票")

    all_data = {}
    for i, sid in enumerate(stock_ids):
        df = download_price_data(dl, sid)
        if not df.empty:
            all_data[sid] = df
        if (i + 1) % 200 == 0:
            print(f"   進度: {i+1}/{len(stock_ids)}（已載入 {len(all_data)} 檔有資料）")

    print(f"✅ 價格資料: {len(all_data)} 檔股票有交易資料")

    # ── 1b. TWSE 法人資料 ──
    print("\n📥 階段 1b/4：下載三大法人資料（TWSE 公開 API）")
    all_dates = sorted(set(
        d.date() if hasattr(d, 'date') else d
        for df in all_data.values() if not df.empty
        for d in df["date"]
    ))
    print(f"   交易日數: {len(all_dates)}")
    twse_raw = fetch_twse_inst_data(set(all_dates))
    print(f"✅ 法人資料: {len(twse_raw)} 個交易日有資料")

    print("\n📥 階段 1c/4：合併法人資料...")
    all_data = merge_twse_inst(all_data, twse_raw)

    # ── 2. 逐週篩選 ──
    print("\n🔍 階段 2/4：篩選每週候選股...")
    fridays = sorted(set(d for d in all_dates if d.weekday() == 4))
    # 只篩 2024 年起的週五
    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d").date()
    fridays = [d for d in fridays if d >= start_dt]

    weekly_candidates = {}
    for i, fd in enumerate(fridays):
        screening_ts = pd.Timestamp(fd)
        cands = screen_candidates(all_data, screening_ts)
        if cands:
            weekly_candidates[fd] = cands
        if (i + 1) % 20 == 0 or (i + 1) == len(fridays):
            print(f"   篩選進度: {i+1}/{len(fridays)} 週（{len(weekly_candidates)} 週有候選股）")

    print(f"✅ 篩選完成: {len(fridays)} 個週五中 {len(weekly_candidates)} 週有合格標的")

    # 輸出篩選歷史
    screen_log = []
    for fd, cands in sorted(weekly_candidates.items()):
        names = ", ".join(f"{s}({sc:.2%})" for s, sc in cands)
        fd_s = fd.isoformat() if hasattr(fd, "isoformat") else str(fd)[:10]
        screen_log.append(f"  {fd_s}: {names}")
    Path("cache/inst_momentum/screen_history.txt").write_text(
        "\n".join(screen_log), encoding="utf-8"
    )
    print(f"   篩選歷史已寫入 cache/inst_momentum/screen_history.txt")

    # ── 3. 模擬交易 ──
    print("\n💰 階段 3/4：模擬交易...")
    result = simulate(all_data, weekly_candidates)
    metrics = compute_metrics(result)
    monthly = generate_monthly_breakdown(result["equity_curve"], INITIAL_CAPITAL)

    print(f"   最終權益: NT${metrics['final_equity']:,.0f}")
    print(f"   總報酬: {metrics['total_return']:+.2%}")
    print(f"   交易次數: {metrics['total_trades']}")
    print(f"   勝率: {metrics['win_rate']:.2%}")
    print(f"   最大回撤: {metrics['max_drawdown_pct']:.2%}")

    # ── 4. 產生報告 ──
    print("\n📝 階段 4/4：產生回測報告...")
    generate_report(result, metrics, monthly)
    print("\n✅ 回測全部完成！")


if __name__ == "__main__":
    main()
