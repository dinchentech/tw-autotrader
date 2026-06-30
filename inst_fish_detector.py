"""
inst_fish_detector.py — 法人低檔吃貨觀測器
========================================
從價格行為 + 成交量 + 法人籌碼，找出可能被法人「默默吃貨」的低檔標的。

邏輯：
  法人吃貨的特色不是「拉漲停」，而是「低調收籌碼」：
    1. 價格在低檔（近 20 日低點、跌破 MA20/MA60）
    2. 成交量放大但價格沒噴（有量無價 = 有人在接）
    3. 收下影線或十字線（有支撐）
    4. 法人買超由負轉正，或維持買超（T+1 驗證）
    5. 融資減 / 融券增（散戶看空 = 籌碼集中）

使用方法：
  python inst_fish_detector.py                          # 掃描今日全市場
  python inst_fish_detector.py --top 50                 # 只看前 50 大
  python inst_fish_detector.py --min-score 5            # 只顯示 >= 5 分
  python inst_fish_detector.py --date 2025-06-18        # 指定日期
"""

import os, sys, argparse, pickle, math, time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path

# ─── 參數 ─────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="法人低檔吃貨觀測器")
parser.add_argument("--top", type=int, default=260, help="掃描標的數（預設 260）")
parser.add_argument("--min-score", type=int, default=3, help="最低顯示分數（預設 3）")
parser.add_argument("--date", default=None, help="觀測日期（預設最新交易日）")
parser.add_argument("--days", type=int, default=60, help="下載回溯天數（預設 60）")
args = parser.parse_args()

TOP_N = args.top
MIN_SCORE = args.min_score
OBSERVE_DATE = args.date
LOOKBACK_DAYS = args.days

CACHE_DIR = Path("cache/inst_momentum/price")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
MCAP_RANKING = Path("cache/inst_momentum/mcap_ranking.pkl")


def detect_latest_date(cache_dir: Path) -> str:
    """從快取中找出最新共同交易日"""
    from collections import Counter
    dates = Counter()
    for p in cache_dir.glob("*.pkl"):
        try:
            df = pickle.loads(p.read_bytes())
            if isinstance(df, pd.DataFrame) and not df.empty:
                d = df["date"].max().strftime("%Y-%m-%d")
                dates[d] += 1
        except Exception:
            continue
    if dates:
        return dates.most_common(1)[0][0]
    return date.today().isoformat()


def get_stock_ids() -> list:
    """按市值排序取前 TOP_N 檔"""
    if MCAP_RANKING.exists():
        ranked = pickle.loads(MCAP_RANKING.read_bytes())
        ranked = [s for s in ranked if s.isdigit() and len(s) == 4]
        return ranked[:TOP_N]
    print("⚠ 無市值排名檔，掃描全部有快取的標的")
    ids = sorted(set(p.stem for p in CACHE_DIR.glob("*.pkl")))
    return ids[:TOP_N]


def ensure_price_data(stock_ids: list) -> dict:
    """確保價格資料已快取，回傳 { stock_id: df }"""
    dl = None
    all_data = {}
    need_dl = []
    for sid in stock_ids:
        cache_file = CACHE_DIR / f"{sid}.pkl"
        if cache_file.exists():
            df = pickle.loads(cache_file.read_bytes())
            if isinstance(df, pd.DataFrame) and not df.empty:
                all_data[sid] = df
                continue
        need_dl.append(sid)

    if need_dl:
        try:
            from FinMind.data import DataLoader
            from dotenv import load_dotenv
            load_dotenv()
            token = os.getenv("FINMIND_API_TOKEN", "")
            dl = DataLoader(token=token)
            if token:
                dl.login_by_token(api_token=token)
        except Exception as e:
            print(f"⚠ FinMind 登入失敗: {e}")
            return all_data

        start = (datetime.strptime(OBSERVE_DATE, "%Y-%m-%d") - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d") if OBSERVE_DATE else (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        end = OBSERVE_DATE or datetime.now().strftime("%Y-%m-%d")

        for i, sid in enumerate(need_dl):
            try:
                df = dl.taiwan_stock_daily(stock_id=sid, start_date=start, end_date=end)
                if df.empty:
                    continue
                df = df.rename(columns={
                    "date": "date", "open": "open", "max": "high",
                    "min": "low", "close": "close", "Trading_Volume": "volume",
                })
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date").reset_index(drop=True)
                # 技術指標
                df["ma20"] = df["close"].rolling(20).mean()
                df["ma10"] = df["close"].rolling(10).mean()
                df["ma60"] = df["close"].rolling(60).mean()
                # 保存
                cache_file = CACHE_DIR / f"{sid}.pkl"
                cache_file.write_bytes(pickle.dumps(df))
                all_data[sid] = df
            except Exception:
                continue
            if (i + 1) % 50 == 0:
                print(f"   下載進度: {i+1}/{len(need_dl)}")

    return all_data


def fetch_twse_inst(trading_date: date) -> dict:
    """下載單日 TWSE 三大法人買賣超，回傳 { stock_id: (buy, sell) }"""
    date_str = trading_date.strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999"
    try:
        resp = requests.get(url, timeout=15)
        data = resp.json()
    except Exception:
        return {}
    if data.get("stat") != "OK":
        return {}

    result = {}
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
        result[sid] = (foreign_buy + trust_buy, foreign_sell + trust_sell)
    return result


def compute_score(sid: str, df: pd.DataFrame, inst_data: dict) -> dict:
    """計算法人低檔吃貨分數 (0-10)"""
    if df.empty or len(df) < 20:
        return {}

    latest = df.iloc[-1]
    close = latest["close"]
    volume = latest["volume"]
    low = latest["low"]
    high = latest["high"]
    open_p = latest["open"]

    # ── 近期價格區間 ──
    recent = df.tail(30)
    recent_low = recent["low"].min()
    recent_high = recent["high"].max()

    # ── 1. 價格位置分數 (0-3) ──
    price_score = 0
    price_detail = []

    # 近 20 日低點附近
    pct_from_low = (close - recent_low) / close
    if pct_from_low < 0.02:
        price_score += 1
        price_detail.append(f"距 30日低 ({pct_from_low:.1%})")
    # 跌破 MA20
    ma20 = latest.get("ma20", 0)
    if ma20 > 0 and not math.isnan(ma20) and close < ma20:
        price_score += 1
        price_detail.append(f"破 MA20({ma20:.1f})")
    # 跌破 MA60
    ma60 = latest.get("ma60", 0)
    if ma60 > 0 and not math.isnan(ma60) and close < ma60:
        price_score += 1
        price_detail.append(f"破 MA60({ma60:.1f})")
    # 連續下跌後止穩
    prev_5 = recent.tail(6).head(5)["close"]
    if len(prev_5) == 5:
        streaks = sum(1 for i in range(1, 5) if prev_5.iloc[i] < prev_5.iloc[i - 1])
        if streaks >= 3 and close >= recent.tail(3)["low"].min():
            price_score += 0.5  # bonus
            price_detail.append("連跌後止穩")

    price_score = min(price_score, 3)

    # ── 2. 成交量分數 (0-3) ──
    vol_score = 0
    vol_detail = []

    avg_vol_5 = recent.tail(5)["volume"].mean()
    avg_vol_20 = recent["volume"].mean()

    # 成交量放大（> 5日均量 1.3倍）
    vol_ratio_5 = volume / avg_vol_5 if avg_vol_5 > 0 else 1
    if vol_ratio_5 > 1.3:
        vol_score += 1
        vol_detail.append(f"量>5日均 {vol_ratio_5:.1f}x")
    if vol_ratio_5 > 2:
        vol_score += 1
        vol_detail.append(f"量>5日均 {vol_ratio_5:.1f}x")

    # 有量無價：量大但漲幅小 (< 2%)
    if vol_ratio_5 > 1.3:
        pct_change = (close - open_p) / open_p
        if -0.02 <= pct_change <= 0.02:
            vol_score += 1
            vol_detail.append(f"有量無價({pct_change:+.1%})")
        elif pct_change > 0.03:
            vol_score -= 0.5  # 量大又大漲 = 追價, 非低檔吃貨
            vol_detail.append("量大漲多")

    # 量能溫和放大趨勢（最近 5 日量 > 20 日均量）
    if avg_vol_5 > avg_vol_20 * 1.2:
        vol_score += 0.5
        vol_detail.append(f"5日均量>20日均 {avg_vol_5/avg_vol_20:.1f}x")

    vol_score = max(0, min(vol_score, 3))

    # ── 3. K線型態分數 (0-2) ──
    pattern_score = 0
    pattern_detail = []

    # 下影線：下影線長度 = min(open, close) - low
    body = abs(close - open_p)
    lower_shadow = min(open_p, close) - low
    upper_shadow = high - max(open_p, close)
    total_range = high - low

    if total_range > 0:
        # 下影線佔整根 K 棒超過 50%
        lower_ratio = lower_shadow / total_range
        if lower_ratio > 0.5 and body < total_range * 0.4:
            pattern_score += 1
            pattern_detail.append(f"下影線({lower_ratio:.0%})")
        # 紡錘線 + 下影線 = 錘子
        if lower_ratio > 0.6 and upper_shadow < total_range * 0.2:
            pattern_score += 1
            pattern_detail.append("錘子線")

    # 十字線（實體很小）
    if total_range > 0 and body / total_range < 0.1 and lower_shadow > 0 and upper_shadow > 0:
        pattern_score += 1
        pattern_detail.append("十字線")

    # 雙底 / 支撐測試
    recent_30 = df.tail(30)
    if len(recent_30) >= 10:
        lows_10 = recent_30.tail(10)["low"]
        lows_20 = recent_30.head(20)["low"]
        support_level = lows_20.min()
        if abs(low - support_level) / close < 0.03 and volume > avg_vol_20:
            pattern_score += 0.5
            pattern_detail.append(f"測支撐({support_level:.1f})")

    pattern_score = min(pattern_score, 2)

    # ── 4. 法人分數 (0-2) ──
    inst_score = 0
    inst_detail = []

    if inst_data:
        inst_buy, inst_sell = inst_data.get(sid, (0, 0))
        net = inst_buy - inst_sell
        if net > 0:
            inst_score += 1
            inst_detail.append(f"法買+{net/1000:.0f}張")
        if net > 1000:
            inst_score += 1
            inst_detail.append(f"大額買超{net/1000:.0f}張")
    else:
        inst_detail.append("無資料")

    inst_score = min(inst_score, 2)

    # ── 總分 ──
    total = round(price_score + vol_score + pattern_score + inst_score, 1)

    return {
        "sid": sid,
        "close": round(close, 2),
        "score": total,
        "price_detail": "; ".join(price_detail),
        "vol_detail": "; ".join(vol_detail),
        "pattern_detail": "; ".join(pattern_detail),
        "inst_detail": "; ".join(inst_detail),
        "pct_from_low": pct_from_low,
        "volume": volume,
        "ma20": round(ma20, 2) if ma20 > 0 else 0,
    }


# ════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  🐟 法人低檔吃貨觀測器")
    print("=" * 60)

    # 決定觀測日期
    if OBSERVE_DATE:
        obs_date = datetime.strptime(OBSERVE_DATE, "%Y-%m-%d").date()
    else:
        latest = detect_latest_date(CACHE_DIR)
        obs_date = datetime.strptime(latest, "%Y-%m-%d").date()
        print(f"  自動偵測最新交易日: {obs_date}")

    # 取得法人資料（前一天，T+1）
    inst_date = obs_date - timedelta(days=1)
    while inst_date.weekday() >= 5:
        inst_date -= timedelta(days=1)
    print(f"\n📡 觀測日: {obs_date}")
    print(f"📡 法人資料日: {inst_date} (T+1)")

    print(f"\n📥 載入標的列表（前 {TOP_N} 大）...")
    stock_ids = get_stock_ids()
    print(f"   共 {len(stock_ids)} 檔")

    print(f"\n📥 確保價格資料（回溯 {LOOKBACK_DAYS} 天）...")
    all_data = ensure_price_data(stock_ids)
    print(f"   成功載入 {len(all_data)} 檔")

    print(f"\n📥 下載法人買賣超 ({inst_date})...")
    inst_data = fetch_twse_inst(inst_date)
    if inst_data:
        print(f"   成功載入 {len(inst_data)} 檔")
    else:
        print(f"   ⚠ 法人資料無回應（可能非交易日或日期過遠），跳過法人評分")

    print(f"\n🔍 掃描低檔吃貨訊號...\n")

    results = []
    for sid, df in all_data.items():
        result = compute_score(sid, df, inst_data)
        if result and result["score"] >= MIN_SCORE:
            results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)

    # 輸出表格
    if not results:
        print("   沒有符合條件的標的。")
        return

    print(f"   找到 {len(results)} 檔 (score >= {MIN_SCORE})")
    print()
    print(f"  {'分數':>5s}  {'代號':>6s}  {'收盤':>8s}  {'距低點':>8s}  {'成交量':>10s}  {'價格面':<30s}  {'量能面':<30s}  {'型態':<20s}  {'法人':<20s}")
    print(f"  {'-'*5}  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*30}  {'-'*30}  {'-'*20}  {'-'*20}")
    for r in results:
        vol_str = f"{r['volume']/1000:.0f}張" if r['volume'] > 0 else ""
        print(f"  {r['score']:>5.1f}  {r['sid']:>6s}  {r['close']:>8.2f}  {r['pct_from_low']:>7.1%}  {vol_str:>10s}  {r['price_detail']:<30s}  {r['vol_detail']:<30s}  {r['pattern_detail']:<20s}  {r['inst_detail']:<20s}")

    # Top 5 摘要
    print(f"\n{'='*60}")
    print(f"  🏆 TOP {min(5, len(results))} 低檔吃貨嫌疑股")
    print(f"{'='*60}")
    for r in results[:5]:
        reasons = [d for d in [r['price_detail'], r['vol_detail'], r['pattern_detail'], r['inst_detail']] if d]
        print(f"  {r['sid']:>6s}  分數 {r['score']}/10 — 收 {r['close']} | {'; '.join(reasons)}")


if __name__ == "__main__":
    main()
