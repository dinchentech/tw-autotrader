"""
backtest_inst_bottomfish.py — 法人低接策略回測 (Group 2)
======================================================
使用 TWSE 公開 API + FinMind 資料，篩選法人低檔吃貨標的。

策略邏輯：
  1. 每週五篩選全市場：計算「法人低檔吃貨分數」(0-10)
     - 價格低檔（近低點 / 破 MA20/60）
     - 有量無價（量放大但價不漲 / 下影線 / 槌子）
     - 法人買超驗證
  2. 分數 >= SCORE_THRESHOLD 者，取前 TOP_N 名，次交易日開盤進場
  3. 出場條件：
     - 反彈站上 MA20 → 獲利了結（均值回歸完成）
     - -7% 硬性停損
     - 跌破 MA10 移動停利（只在獲利時觸發）

使用方法：
  python backtest_inst_bottomfish.py
  python backtest_inst_bottomfish.py --start 2022-01-01 --end 2022-12-31
  python backtest_inst_bottomfish.py --score 4   # 放寬分數門檻
"""

import os, sys, argparse, pickle, math, time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

# ─── 參數 ─────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="法人低接策略回測")
parser.add_argument("--start", default="2025-01-01", help="起始日期")
parser.add_argument("--end", default="2025-12-31", help="結束日期")
parser.add_argument("--top", type=int, default=0, help="篩選標的數（預設 270）")
parser.add_argument("--score", type=float, default=4.0, help="低檔吃貨分數門檻（預設 4.0）")
parser.add_argument("--stop-loss", type=float, default=None, help="停損幅度（預設 0.07）")
parser.add_argument("--lookback", type=int, default=None, help="價格回溯期（預設 20）")
parser.add_argument("--market-filter", action="store_true", help="啟用大盤年線過濾（TAIEX > MA200 才買）")
args = parser.parse_args()

START_DATE = args.start
END_DATE = args.end
SCORE_THRESHOLD = args.score
TOP_N_STOCKS = args.top if args.top > 0 else 270
STOP_LOSS = args.stop_loss if args.stop_loss is not None else 0.07
LOOKBACK = args.lookback if args.lookback is not None else 20
MARKET_FILTER = args.market_filter

CACHE_DIR = Path(f"cache/inst_momentum/{START_DATE[:4]}")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
PRICE_CACHE_DIR = Path("cache/inst_momentum/price")
PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
INITIAL_CAPITAL = 500_000
TOP_N = 3
TRAILING_PERIOD = 10
BUY_COST = 0.001425
SELL_COST = 0.004425

def finmind_login():
    from FinMind.data import DataLoader
    from dotenv import load_dotenv
    load_dotenv()
    token = os.getenv("FINMIND_API_TOKEN", "")
    dl = DataLoader(token=token)
    if token:
        dl.login_by_token(api_token=token)
    return dl

def get_all_stock_ids(dl) -> list:
    MCAP_RANKING = Path("cache/inst_momentum/mcap_ranking.pkl")
    if MCAP_RANKING.exists():
        ranked = pickle.loads(MCAP_RANKING.read_bytes())
        ranked = [s for s in ranked if s.isdigit() and len(s) == 4]
        return ranked[:TOP_N_STOCKS]
    cache_file = PRICE_CACHE_DIR / "stock_ids.pkl"
    if cache_file.exists():
        ids = pickle.loads(cache_file.read_bytes())
        return ids[:TOP_N_STOCKS]
    df = dl.taiwan_stock_info()
    ids = sorted(set(s.strip() for s in df["stock_id"]
                      if s.strip().isdigit() and len(s.strip()) == 4))
    ids = ids[:TOP_N_STOCKS]
    cache_file.write_bytes(pickle.dumps(ids))
    return ids

def download_price_data(dl, stock_id: str) -> pd.DataFrame:
    cache_file = PRICE_CACHE_DIR / f"{stock_id}.pkl"
    if cache_file.exists():
        df = pickle.loads(cache_file.read_bytes())
        if not df.empty and df["date"].max() >= pd.Timestamp(END_DATE):
            return df
        last_date = df["date"].max().strftime("%Y-%m-%d") if not df.empty else None
    else:
        last_date = None
    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d") - timedelta(days=90)
    if last_date and last_date > start_dt.strftime("%Y-%m-%d"):
        start_dt = datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=1)
    start = start_dt.strftime("%Y-%m-%d")
    try:
        df_new = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start, end_date=END_DATE)
        if df_new.empty:
            return pd.DataFrame()
        df_new = df_new.rename(columns={
            "date": "date", "open": "open", "max": "high",
            "min": "low", "close": "close", "Trading_Volume": "volume",
        })
        df_new["date"] = pd.to_datetime(df_new["date"])
        df_new = df_new.sort_values("date").reset_index(drop=True)
    except Exception:
        try:
            import yfinance as yf
            tk = yf.Ticker(f"{stock_id}.TW")
            df_new = tk.history(start=start, end=END_DATE)
            if df_new.empty:
                return pd.DataFrame()
            df_new = df_new.reset_index()
            df_new["date"] = pd.to_datetime(df_new["Date"].dt.date)
            df_new = df_new.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
            })
        except Exception:
            return pd.DataFrame()
    if last_date:
        df_old = pickle.loads(cache_file.read_bytes())
        if not df_old.empty:
            df_old = df_old[df_old["date"] < df_new["date"].min()]
            df_new = pd.concat([df_old, df_new], ignore_index=True).drop_duplicates(
                subset=["date"], keep="last"
            ).sort_values("date").reset_index(drop=True)
    df_new["ma20"] = df_new["close"].rolling(20).mean()
    df_new["ma10"] = df_new["close"].rolling(LOOKBACK).mean()
    df_new["ma60"] = df_new["close"].rolling(60).mean()
    cache_file.write_bytes(pickle.dumps(df_new))
    return df_new

def fetch_twse_inst_data(trading_dates: set) -> dict:
    cache_key = f"twse_inst_{START_DATE}_{END_DATE}.pkl"
    cache_file = CACHE_DIR / cache_key
    if cache_file.exists():
        print(f"   載入 TWSE 法人資料快取 ...")
        return pickle.loads(cache_file.read_bytes())
    dates = sorted(d for d in trading_dates
                   if pd.Timestamp(START_DATE).date() <= d <= pd.Timestamp(END_DATE).date())
    inst_data = {}
    for i, d in enumerate(dates):
        date_str = d.strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999"
        try:
            resp = requests.get(url, timeout=15)
            data = resp.json()
        except Exception:
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
    return inst_data

def merge_twse_inst(all_data: dict, twse_data: dict) -> dict:
    for stock_id, df in all_data.items():
        if df.empty:
            continue
        df["inst_buy"] = 0
        df["inst_sell"] = 0
        for idx, row in df.iterrows():
            d = row["date"]
            try:
                d_str = d.isoformat() if hasattr(d, "isoformat") else str(d)
            except Exception:
                continue
            day_data = twse_data.get(str(d.date()) if hasattr(d, "date") else d_str, {})
            if stock_id in day_data:
                df.at[idx, "inst_buy"] = day_data[stock_id][0]
                df.at[idx, "inst_sell"] = day_data[stock_id][1]
    return all_data

# ─── 階段 2：低檔吃貨分數篩選 ──────────────────────────

def compute_fish_score(latest: pd.Series, recent: pd.DataFrame, inst_buy: int, inst_sell: int) -> tuple:
    """回傳 (分數, 原因字串)"""
    close = latest["close"]
    volume = latest["volume"]
    low = latest["low"]
    high = latest["high"]
    open_p = latest["open"]
    reasons = []

    # 價格分數 (0-3)
    ps = 0
    recent_low = recent["low"].min()
    pct_from_low = (close - recent_low) / close if close > 0 else 1
    if pct_from_low < 0.02:
        ps += 1
        reasons.append(f"近低({pct_from_low:.1%})")
    ma20 = latest.get("ma20", 0)
    if ma20 > 0 and not math.isnan(ma20) and close < ma20:
        ps += 1
        reasons.append(f"破MA20")
    ma60 = latest.get("ma60", 0)
    if ma60 > 0 and not math.isnan(ma60) and close < ma60:
        ps += 1
        reasons.append(f"破MA60")
    # 連跌止穩 bonus
    if len(recent) >= 10:
        closes_5 = recent.tail(6).head(5)["close"].values
        if len(closes_5) >= 4:
            drops = sum(1 for i in range(1, 5) if closes_5[i] < closes_5[i - 1])
            if drops >= 3 and close >= recent.tail(3)["low"].min():
                ps += 0.5
                reasons.append("止穩")
    ps = min(ps, 3)

    # 量能分數 (0-3)
    vs = 0
    avg_vol_5 = recent.tail(5)["volume"].mean()
    avg_vol_20 = recent["volume"].mean()
    vol_ratio = volume / avg_vol_5 if avg_vol_5 > 0 else 1
    if vol_ratio > 1.3:
        vs += 1
    if vol_ratio > 2.0:
        vs += 1
    if vol_ratio > 1.3:
        pct_chg = (close - open_p) / open_p
        if -0.02 <= pct_chg <= 0.02:
            vs += 1
            reasons.append("有量無價")
        elif pct_chg > 0.03:
            vs -= 0.5
            reasons.append("量大漲多")
    if avg_vol_5 > avg_vol_20 * 1.2:
        vs += 0.5
    vs = max(0, min(vs, 3))

    # 型態分數 (0-2)
    pts = 0
    total_range = high - low
    if total_range > 0:
        body = abs(close - open_p)
        lower_shadow = min(open_p, close) - low
        lower_ratio = lower_shadow / total_range
        if lower_ratio > 0.5 and body < total_range * 0.4:
            pts += 1
            reasons.append("下影線")
        if lower_ratio > 0.6 and (high - max(open_p, close)) < total_range * 0.2:
            pts += 1
            reasons.append("槌子")
        if body / total_range < 0.1 and lower_shadow > 0:
            pts += 1
            reasons.append("十字線")
    pts = min(pts, 2)

    # 法人分數 (0-2)
    ins = 0
    net = inst_buy - inst_sell
    if net > 0:
        ins += 1
        reasons.append(f"法買{net/1000:.0f}張")
    if net > 1000:
        ins += 1
    ins = min(ins, 2)

    total = round(ps + vs + pts + ins, 1)
    return total, "; ".join(reasons)


def screen_candidates(all_data: dict, screening_date: date, twse_data: dict) -> list:
    """回傳 [(stock_id, score, reason), ...] 按分數降冪"""
    candidates = []
    sd_str = screening_date.isoformat()
    sd_pd = pd.Timestamp(screening_date)

    for stock_id, df in all_data.items():
        if df.empty or len(df) < 30:
            continue

        # 篩選日當天的資料
        mask = df["date"] <= sd_pd
        hist = df[mask]
        if hist.empty or len(hist) < 20:
            continue

        latest = hist.iloc[-1]
        close = latest["close"]
        volume = latest["volume"]

        # 流動性門檻
        last_5_vol = hist.tail(5)["volume"]
        if last_5_vol.mean() < 2000_000:  # 2000 張
            continue

        # 近 30 日資料（含篩選日）
        recent = hist.tail(30)

        # 法人資料
        day_data = twse_data.get(sd_str, {})
        inst_buy, inst_sell = day_data.get(stock_id, (0, 0))

        score, reason = compute_fish_score(latest, recent, inst_buy, inst_sell)

        if score >= SCORE_THRESHOLD:
            candidates.append((stock_id, score, reason))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:TOP_N]


# ─── 階段 3：交易模擬 ──────────────────────────────────

def check_position_exit(
    sid: str, positions: dict, daily_prices: dict, d: date,
    trade_log: list
) -> float:
    """回傳出場收回的 cash（0 = 續抱）"""
    pos = positions[sid]
    price_info = daily_prices.get(sid, {})
    current_price = price_info.get("close", 0)
    if current_price <= 0:
        return 0

    loss_pct = (current_price - pos["buy_price"]) / pos["buy_price"]

    # -7% 停損
    if loss_pct <= -STOP_LOSS:
        proceeds = pos["shares"] * current_price * (1 - SELL_COST)
        pnl = proceeds - pos["shares"] * pos["buy_price"]
        trade_log.append({
            "date": d.isoformat(), "action": "SELL",
            "stock_id": sid, "shares": pos["shares"],
            "price": round(current_price, 2), "pnl": round(pnl, 0),
            "reason": f"硬性停損 {loss_pct:.1%}",
        })
        del positions[sid]
        return proceeds

    # 跌破 MA10 移動停利（只在獲利時）
    if loss_pct > 0:
        ma10 = price_info.get("ma10")
        if ma10 is not None and not math.isnan(ma10) and current_price < ma10:
            proceeds = pos["shares"] * current_price * (1 - SELL_COST)
            pnl = proceeds - pos["shares"] * pos["buy_price"]
            trade_log.append({
                "date": d.isoformat(), "action": "SELL",
                "stock_id": sid, "shares": pos["shares"],
                "price": round(current_price, 2), "pnl": round(pnl, 0),
                "reason": f"跌破 MA10({ma10:.0f})移動停利",
            })
            del positions[sid]
            return proceeds

    return 0


def fetch_taiex_ma200() -> dict:
    """下載加權指數日線，計算 MA200，回傳 { date_str: is_above }"""
    cache_key = f"taiex_ma200_{START_DATE}_{END_DATE}.pkl"
    cache_file = CACHE_DIR / cache_key
    if cache_file.exists():
        return pickle.loads(cache_file.read_bytes())

    all_rows = []
    seen = set()
    sd = datetime.strptime(START_DATE, "%Y-%m-%d") - timedelta(days=400)
    end_dt = datetime.strptime(END_DATE, "%Y-%m-%d")
    for i in range(20):
        d = end_dt - timedelta(days=i * 40)
        dt = d.strftime("%Y%m%d")
        try:
            url = "https://www.twse.com.tw/en/exchangeReport/FMTQIK"
            resp = requests.get(url, params={"response": "json", "date": dt}, timeout=15)
            data = resp.json()
            for row in data.get("data", []):
                if row[0] not in seen:
                    seen.add(row[0])
                    all_rows.append(row)
        except Exception:
            continue

    if len(all_rows) < 200:
        print("  ⚠ TAIEX 資料不足 200 筆，跳過市場過濾")
        return {}

    df = pd.DataFrame(all_rows, columns=["date","volume","value","trades","TAIEX","change"])
    df["close"] = pd.to_numeric(df["TAIEX"].str.replace(",",""), errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    df["ma200"] = df["close"].rolling(200).mean()
    df["date"] = pd.to_datetime(df["date"], format="%Y/%m/%d")

    result = {}
    for _, row in df.iterrows():
        d = row["date"].date()
        if pd.notna(row["ma200"]) and row["close"] > row["ma200"]:
            result[d.isoformat()] = True
        else:
            result[d.isoformat()] = False

    cache_file.write_bytes(pickle.dumps(result))
    print(f"  ✅ TAIEX MA200 快取: {sum(result.values())}/{len(result)} 天在年線上")
    return result


def simulate(all_data: dict, twse_data: dict, taiex_filter: dict | None = None) -> dict:
    cash = float(INITIAL_CAPITAL)
    positions = {}
    trade_log = []
    equity_curve = []

    sd = pd.Timestamp(START_DATE).date()
    ed = pd.Timestamp(END_DATE).date()

    # 交易日（限制在指定區間內）
    all_dates = set()
    for df in all_data.values():
        if not df.empty:
            all_dates.update(
                d for d in df["date"].dt.date
                if sd <= d <= ed
            )
    all_dates = sorted(all_dates)

    # 每日價格快取
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
                    "ma10": row.get("ma10"),
                    "ma20": row.get("ma20"),
                    "volume": row["volume"],
                }

    # 每週五篩選（找出所有週五）
    screening_dates = []
    for d in all_dates:
        if d.weekday() == 4:  # 週五
            screening_dates.append(d)

    next_day_map = {}
    for sd in screening_dates:
        for d in all_dates:
            if d > sd:
                next_day_map[sd] = d
                break

    pending_entry = None  # (screening_date, candidates_list)

    for day_idx, d in enumerate(all_dates):
        daily_prices = price_cache[d]

        # 每日停損 / 移動停利
        for sid in list(positions.keys()):
            cash += check_position_exit(sid, positions, daily_prices, d, trade_log)

        # 篩選日
        if d in screening_dates:
            # 市場過濾：大盤跌破年線就不進場
            if taiex_filter is not None:
                d_str = d.isoformat()
                if not taiex_filter.get(d_str, True):
                    pending_entry = None
                    print(f"   篩選 {d} ... 大盤 < MA200，跳過買進")
                    continue
            print(f"   篩選 {d} ... ({len(pending_entry[1]) if pending_entry else 0} 待入)", end="\r")
            cands = screen_candidates(all_data, d, twse_data)
            if cands:
                pending_entry = (d, cands)

        # 執行日
        if pending_entry is not None:
            sd, cands = pending_entry
            if d == next_day_map.get(sd):
                # 出場：站上 MA20 → 均值回歸獲利了結
                for sid in list(positions.keys()):
                    pi = daily_prices.get(sid, {})
                    cp = pi.get("close", 0)
                    if cp <= 0:
                        continue
                    ma20 = pi.get("ma20", 0)
                    pos = positions[sid]
                    # 站上 MA20 且買入價低於 MA20（代表是低接進場的）
                    if ma20 > 0 and not math.isnan(ma20) and cp > ma20 and pos["buy_price"] < ma20:
                        sp = pi.get("open", cp)
                        proceeds = pos["shares"] * sp * (1 - SELL_COST)
                        pnl = proceeds - pos["shares"] * pos["buy_price"]
                        trade_log.append({
                            "date": d.isoformat(), "action": "SELL",
                            "stock_id": sid, "shares": pos["shares"],
                            "price": round(sp, 2), "pnl": round(pnl, 0),
                            "reason": f"站上 MA20({ma20:.1f})出場",
                        })
                        cash += proceeds
                        del positions[sid]

                # 買入新候選
                for stock_id, score, reason in cands:
                    if stock_id in positions:
                        continue
                    if len(positions) >= TOP_N:
                        break
                    pi = daily_prices.get(stock_id, {})
                    bp = pi.get("open", pi.get("close", 0))
                    if bp <= 0:
                        continue
                    per_stock = INITIAL_CAPITAL / TOP_N
                    shares = int(per_stock / bp / 1000) * 1000
                    if shares <= 0:
                        continue
                    cost = shares * bp * (1 + BUY_COST)
                    if cash < cost:
                        shares = int(cash / (bp * (1 + BUY_COST)) / 1000) * 1000
                        if shares <= 0:
                            continue
                        cost = shares * bp * (1 + BUY_COST)
                    cash -= cost
                    positions[stock_id] = {
                        "shares": shares, "buy_price": bp, "buy_date": d,
                    }
                    trade_log.append({
                        "date": d.isoformat(), "action": "BUY",
                        "stock_id": stock_id, "shares": shares,
                        "price": round(bp, 2), "pnl": 0,
                        "reason": f"低檔吃貨 score={score}: {reason}",
                    })

        # 當日權益
        pos_value = 0
        for sid, pos in positions.items():
            pi = daily_prices.get(sid, {})
            p = pi.get("close", pos["buy_price"])
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
        pi = price_cache.get(last_d, {}).get(sid, {})
        sp = pi.get("close", pos["buy_price"])
        proceeds = pos["shares"] * sp * (1 - SELL_COST)
        cash += proceeds
        pnl = proceeds - pos["shares"] * pos["buy_price"]
        trade_log.append({
            "date": last_d.isoformat(), "action": "SELL",
            "stock_id": sid, "shares": pos["shares"],
            "price": round(sp, 2), "pnl": round(pnl, 0),
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


# ─── 階段 4：績效指標 ──────────────────────────────────

def compute_metrics(result: dict) -> dict:
    trades = result["trade_log"]
    equity = result["equity_curve"]
    if not trades:
        return {
            "total_trades": 0, "buy_trades": 0, "sell_trades": 0,
            "closed_trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "avg_win": 0, "avg_loss": 0,
            "profit_factor": 0.0, "max_drawdown": 0, "max_drawdown_pct": 0.0,
            "total_return": 0.0, "final_equity": INITIAL_CAPITAL,
        }
    buys = [t for t in trades if t["action"] == "BUY"]
    sells = [t for t in trades if t["action"] == "SELL"]
    closed = [t for t in sells if t.get("pnl", 0) != 0]
    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] < 0]
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    pf = abs(sum(t["pnl"] for t in wins) / sum(t["pnl"] for t in losses)) if losses and sum(t["pnl"] for t in losses) != 0 else 0
    max_dd = 0
    max_dd_pct = 0.0
    peak = INITIAL_CAPITAL
    for e in equity:
        val = e["total_equity"]
        if val > peak:
            peak = val
        dd = peak - val
        dd_pct = (peak - val) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd_pct
    total_eq = equity[-1]["total_equity"] if equity else INITIAL_CAPITAL
    return {
        "total_trades": len(trades),
        "buy_trades": len(buys),
        "sell_trades": len(sells),
        "closed_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(closed) * 100, 2) if closed else 0,
        "avg_win": round(avg_win, 0),
        "avg_loss": round(avg_loss, 0),
        "profit_factor": round(pf, 2),
        "max_drawdown": round(max_dd, 0),
        "max_drawdown_pct": round(max_dd_pct * 100, 2),
        "total_return": round((total_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL, 4),
        "final_equity": round(total_eq, 0),
    }


# ─── 階段 5：報表 ──────────────────────────────────────

def generate_report(result: dict, metrics: dict):
    year_label = f"{START_DATE[:4]}_{END_DATE[:4]}" if START_DATE[:4] != END_DATE[:4] else START_DATE[:4]
    out_file = f"回測_低接_{year_label}.MD"
    trades = result["trade_log"]
    eq = result["equity_curve"]
    m = metrics

    lines = []
    lines.append(f"# 法人低接策略 — {START_DATE[:4]} 回測報告\n")
    lines.append("## 策略摘要\n")
    lines.append("| 項目 | 內容 |")
    lines.append("|------|------|")
    lines.append(f"| **策略名稱** | 法人低接策略（Group 2） |")
    lines.append(f"| **回測期間** | {START_DATE} → {END_DATE} |")
    lines.append(f"| **起始本金** | NT${INITIAL_CAPITAL:,} |")
    lines.append(f"| **交易成本** | 買 {BUY_COST:.4%} / 賣 {SELL_COST:.4%} |")
    lines.append(f"| **持有檔數** | {TOP_N} 檔 |")
    lines.append(f"| **流動性門檻** | 近 5 日平均 > 2000 張 |")
    lines.append(f"| **進場條件** | 低檔吃貨分數 >= {SCORE_THRESHOLD} |")
    lines.append(f"| **停損** | {STOP_LOSS:.0%} 硬性停損 |")
    lines.append(f"| **停利** | 站上 MA20 出場 / 跌破 MA10 移動停利 |")
    lines.append(f"| **資料來源** | 股價: FinMind / 法人: TWSE 公開 API |")
    lines.append(f"| **篩選標的數** | 前 {TOP_N_STOCKS} 檔（市值排序）|\n")

    lines.append("## 績效總覽\n")
    lines.append("| 指標 | 數值 |")
    lines.append("|------|------|")
    lines.append(f"| **最終權益** | NT${m['final_equity']:,} |")
    lines.append(f"| **總報酬率** | {m['total_return']:+.2%} |")
    lines.append(f"| **總交易次數** | {m['total_trades']}（買 {m['buy_trades']} / 賣 {m['sell_trades']}） |")
    lines.append(f"| **勝率** | {m['win_rate']:.2f}% |")
    lines.append(f"| **平均獲利** | NT${m['avg_win']:,.0f} |")
    lines.append(f"| **平均虧損** | NT${m['avg_loss']:,.0f} |")
    lines.append(f"| **獲利因子** | {m['profit_factor']:.2f} |")
    lines.append(f"| **最大回撤** | NT${m['max_drawdown']:,} ({m['max_drawdown_pct']:.2f}%) |\n")

    if trades:
        lines.append("## 交易明細\n")
        lines.append("| 日期 | 動作 | 代號 | 股數 | 價格 | 損益 | 原因 |")
        lines.append("|------|:----:|:----:|:----:|:----:|:----:|------|")
        for t in trades:
            pnl_str = f"{t['pnl']:+,.0f}" if t.get("pnl", 0) != 0 else ""
            lines.append(f"| {t['date']} | {t['action']} | {t['stock_id']} | {t['shares']:,} | {t['price']:.2f} | {pnl_str} | {t.get('reason','')} |")

    if eq:
        lines.append("\n## 權益曲線\n")
        lines.append("| 日期 | 現金 | 持倉市值 | 總權益 |")
        lines.append("|------|:----:|:--------:|:------:|")
        for e in eq:
            lines.append(f"| {e['date']} | NT${e['cash']:,.0f} | NT${e['position_value']:,.0f} | NT${e['total_equity']:,.0f} |")

    out_text = "\n".join(lines)
    Path(out_file).write_text(out_text, encoding="utf-8")
    print(f"\n✅ 回測報告已寫入 {out_file}")


# ════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print(f"  🐟 法人低接策略 {START_DATE[:4]} 回測")
    print(f"    本金: NT${INITIAL_CAPITAL:,}")
    print(f"    期間: {START_DATE} ~ {END_DATE}")
    print(f"    分數門檻: {SCORE_THRESHOLD}")
    print("=" * 60)

    print("\n📥 載入價格資料...")
    dl = finmind_login()
    stock_ids = get_all_stock_ids(dl)
    print(f"   共 {len(stock_ids)} 檔上市股票")
    all_data = {}
    for i, sid in enumerate(stock_ids):
        df = download_price_data(dl, sid)
        if not df.empty:
            all_data[sid] = df
        if (i + 1) % 50 == 0:
            print(f"   進度: {i+1}/{len(stock_ids)}")
    print(f"✅ 價格資料: {len(all_data)} 檔有交易資料")

    print("\n📥 下載三大法人資料...")
    trading_dates = set()
    for df in all_data.values():
        if not df.empty:
            trading_dates.update(df["date"].dt.date)
    twse_data = fetch_twse_inst_data(trading_dates)
    print(f"✅ 法人資料: {len(twse_data)} 交易日")

    print("\n📥 合併法人資料...")
    all_data = merge_twse_inst(all_data, twse_data)

    # 市場過濾
    taiex_filter = None
    if MARKET_FILTER:
        print("\n📥 下載 TAIEX 指數計算 MA200...")
        taiex_filter = fetch_taiex_ma200()

    print(f"\n💰 模擬交易...")
    result = simulate(all_data, twse_data, taiex_filter)

    final_eq = result["final_cash"]
    total_ret = result["total_return"]
    print(f"   最終權益: NT${final_eq:,.0f}")
    print(f"   總報酬: {total_ret:+.2%}")
    print(f"   交易次數: {len(result['trade_log'])}")

    print(f"\n📝 產生回測報告...")
    metrics = compute_metrics(result)
    generate_report(result, metrics)

    print(f"\n✅ 回測全部完成！")


if __name__ == "__main__":
    main()
