#!/usr/bin/env python3
"""
find_catalyst_stocks.py — 每月掃瞄台股「翻倍潛力股」

尋找類似藥華藥(6446)的模式：
  ① 長期穩定盤整（6個月以上，價格在窄幅區間內）
  ② 近期出現催化劑（營收加速、新藥/新產品、轉虧為盈等）
  ③ 股價開始突破盤整區間
  ④ 成交量配合增加
  ⑤ 基本面改善（營收成長 YoY、本益比合理）

每月跑一次，輸出排名報告。

Usage:
  python scripts/find_catalyst_stocks.py                  # 完整掃描（全部股票）
  python scripts/find_catalyst_stocks.py --top-n 20        # 只看前20名
  python scripts/find_catalyst_stocks.py --output-html     # 輸出 HTML 報告
  python scripts/find_catalyst_stocks.py --watchlist-only  # 只掃目前持股
  python scripts/find_catalyst_stocks.py --min-score 30    # 最低評分門檻

Data Sources:
  - yfinance: 歷史股價、營收、基本面資料
  - TWSE BWIBBU_ALL: 本益比/淨值比/殖利率
  - 使用 藥華藥 6446 的歷史模式作為參考
"""

import argparse
import csv
import json
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore", category=FutureWarning)

# ============================================================
# Configuration
# ============================================================

CATALYST_REFERENCE = {
    "stock_id": "6446",
    "name": "藥華藥",
    "pattern": {
        "stable_start": "2025-01",
        "stable_end": "2025-11",
        "stable_price_low": 200,
        "stable_price_high": 350,
        "catalyst_start": "2026-01",
        "price_pre_catalyst": 250,
        "price_post_catalyst_3m": 518,
        "price_peak": 1570,
    },
}

SCREEN_CONFIG = {
    "stable_months_min": 5,
    "stable_range_max_pct": 0.40,
    "breakout_min_pct": 0.15,
    "breakout_period_days": 60,
    "breakout_volume_surge_min": 1.5,
    "revenue_growth_yoy_min": 0.15,
    "pe_max": 60,
    "pe_min": 3,
    "w_stability": 0.20,
    "w_breakout": 0.30,
    "w_volume": 0.15,
    "w_revenue": 0.25,
    "w_pe": 0.10,
    "yfinance_batch_size": 50,
    "yfinance_delay": 0.5,
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ============================================================
# Data Fetching
# ============================================================

def fetch_all_stock_list() -> pd.DataFrame:
    """從 TWSE BWIBBU_ALL 取得所有上市股票的基本資料"""
    log("下載 BWIBBU_ALL（所有上市股票 PE/PB/殖利率）...")
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    r = requests.get(url, timeout=30)
    data = r.json()
    df = pd.DataFrame(data)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={
        "Code": "stock_id", "Name": "name",
        "PEratio": "pe_ratio", "DividendYield": "dividend_yield", "PBratio": "pb_ratio",
    })
    df["stock_id"] = df["stock_id"].str.strip()
    df["name"] = df["name"].str.strip()
    for col in ["pe_ratio", "dividend_yield", "pb_ratio"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    log(f"  取得 {len(df)} 檔股票資料")
    return df

def fetch_yfinance_prices(stock_ids: List[str], period: str = "1y") -> pd.DataFrame:
    """批次下載歷史股價"""
    if not stock_ids:
        return pd.DataFrame()
    tickers = [f"{sid}.TW" for sid in stock_ids]
    log(f"  下載 {len(tickers)} 檔歷史股價（{period}）...")
    try:
        data = yf.download(tickers, period=period, progress=False, auto_adjust=True)
        return data
    except Exception as e:
        log(f"  ⚠️ 下載失敗: {e}")
        return pd.DataFrame()

def fetch_yfinance_info(stock_ids: List[str]) -> Dict[str, dict]:
    """取得個股基本面資訊（營收、產業等）"""
    result = {}
    bs = SCREEN_CONFIG["yfinance_batch_size"]
    for i in range(0, len(stock_ids), bs):
        batch = stock_ids[i:i+bs]
        log(f"  基本面 {i+1}-{min(i+bs, len(stock_ids))}/{len(stock_ids)}...")
        try:
            tickers = yf.Tickers(" ".join(f"{s}.TW" for s in batch))
            for sid in batch:
                try:
                    t = tickers.tickers.get(f"{sid}.TW")
                    if t and t.info:
                        info = t.info
                        result[sid] = {
                            "sector": info.get("sector", ""),
                            "industry": info.get("industry", ""),
                            "total_revenue": info.get("totalRevenue"),
                            "revenue_growth": info.get("revenueGrowth"),
                            "net_income": info.get("netIncomeToCommon"),
                            "profit_margins": info.get("profitMargins"),
                            "market_cap": info.get("marketCap"),
                            "target_price": info.get("targetMeanPrice"),
                            "recommendation": info.get("recommendationKey"),
                        }
                except:
                    pass
        except Exception as e:
            log(f"  ⚠️ 批次失敗: {e}")
        time.sleep(SCREEN_CONFIG["yfinance_delay"])
    log(f"  取得 {len(result)} 檔基本面資料")
    return result

# ============================================================
# Pattern Detection — 兩段式分析
# ============================================================

def _safe_tail(series, n):
    """安全取最後 n 筆（支援 Series 和 DatetimeIndex）"""
    if isinstance(series, pd.DatetimeIndex):
        return series[-n:]
    return series.tail(n)

def analyze_breakout_pattern(prices: pd.Series, volumes: pd.Series, dates) -> Optional[dict]:
    """
    核心分析：偵測「長期盤整 → 近期突破」的潛力股模式。

    做法：
    1. 將過去1年資料分成前後兩半
    2. 前半段：計算是否處於低波動盤整
    3. 後半段：計算是否突破前半段高點
    4. 回傳結構化結果供後續評分

    Returns: dict 或 None
    """
    if len(prices) < 120:
        return None

    n = min(252, len(prices))
    p_all = _safe_tail(prices, n).values
    v_all = _safe_tail(volumes, n).values if len(volumes) >= n else None
    d_all = _safe_tail(dates, n)
    if isinstance(d_all, pd.DatetimeIndex):
        d_all = d_all.to_series()

    mid = n // 2

    # === 前半段（盤整偵測）===
    first_half_p = p_all[:mid]
    fh_mean = np.mean(first_half_p)
    fh_min = np.min(first_half_p)
    fh_max = np.max(first_half_p)
    fh_range_pct = (fh_max - fh_min) / fh_mean * 100 if fh_mean > 0 else 999

    # 前半段成交量
    if v_all is not None:
        fh_vol = np.mean(v_all[:mid])
        sh_vol = np.mean(v_all[mid:]) if len(v_all) > mid else fh_vol
        vol_change_ratio = sh_vol / fh_vol if fh_vol > 0 else 1.0
    else:
        fh_vol = None
        vol_change_ratio = 1.0

    # === 後半段（突破偵測）===
    second_half_p = p_all[mid:]
    sh_min = np.min(second_half_p) if len(second_half_p) > 0 else 0
    sh_max = np.max(second_half_p) if len(second_half_p) > 0 else 0
    current_price = float(p_all[-1])

    # 突破幅度（當前價 vs 前半段高點）
    pct_above_fh_high = (current_price - fh_max) / fh_max * 100 if fh_max > 0 else 0
    pct_above_fh_mean = (current_price - fh_mean) / fh_mean * 100 if fh_mean > 0 else 0

    # 近期動能
    recent_20d = p_all[-20:] if len(p_all) >= 20 else p_all
    recent_60d = p_all[-60:] if len(p_all) >= 60 else p_all
    chg_20d = (recent_20d[-1] - recent_20d[0]) / recent_20d[0] * 100 if recent_20d[0] > 0 else 0
    chg_60d = (recent_60d[-1] - recent_60d[0]) / recent_60d[0] * 100 if recent_60d[0] > 0 else 0

    # 月線分析（用來確定盤整月數）
    df_tmp = pd.DataFrame({
        "price": p_all,
        "date": pd.to_datetime(d_all.values) if hasattr(d_all, 'values') else pd.to_datetime(d_all)
    })
    df_tmp["month"] = df_tmp["date"].dt.to_period("M")
    monthly = df_tmp.groupby("month")["price"].agg(["mean", "std", "min", "max", "count"])

    # 找出最低波動的月份群組（連續N個月低波動）
    months_volatility = []
    for m in monthly.iterrows():
        r = (m[1]["max"] - m[1]["min"]) / m[1]["mean"] * 100 if m[1]["mean"] > 0 else 999
        months_volatility.append((m[0], r))
    months_volatility.sort(key=lambda x: x[1])

    is_stable = fh_range_pct <= 40 and len(months_volatility) >= 5
    is_breakout = pct_above_fh_high > 10

    return {
        "is_stable": is_stable,
        "is_breakout": is_breakout,
        # 盤整資訊
        "stable_mean": float(fh_mean),
        "stable_high": float(fh_max),
        "stable_low": float(fh_min),
        "stable_range_pct": float(fh_range_pct),
        "stable_months": len(monthly),
        "fh_vol": float(fh_vol) if fh_vol else 0,
        # 突破資訊
        "current_price": current_price,
        "pct_above_stable_high": float(pct_above_fh_high),
        "pct_above_stable_mean": float(pct_above_fh_mean),
        "chg_20d": float(chg_20d),
        "chg_60d": float(chg_60d),
        "vol_change_ratio": float(vol_change_ratio),
    }

def assess_fundamentals(info: dict, bwibbu_row: Optional[dict]) -> dict:
    """基本面評估：營收成長 + 本益比 + 利潤率"""
    details = {"score": 0}
    rev_g = info.get("revenue_growth")
    if rev_g is not None and rev_g > 0:
        rev_score = min(rev_g * 2, 0.5)
        details["revenue_growth"] = float(rev_g)
        details["rev_score"] = rev_score
    else:
        details["revenue_growth"] = rev_g
        details["rev_score"] = 0
    margins = info.get("profit_margins")
    if margins is not None and margins > 0:
        details["profit_margins"] = float(margins)
        details["margin_score"] = min(margins, 0.3) / 0.3 * 0.3
    else:
        details["profit_margins"] = margins
        details["margin_score"] = 0
    pe = bwibbu_row.get("pe_ratio") if bwibbu_row else None
    if pe and SCREEN_CONFIG["pe_min"] < pe < SCREEN_CONFIG["pe_max"]:
        pe_score = max(0, 1 - (pe - SCREEN_CONFIG["pe_min"]) / (SCREEN_CONFIG["pe_max"] - SCREEN_CONFIG["pe_min"])) * 0.2
        details["pe_ratio"] = float(pe)
        details["pe_score"] = pe_score
    else:
        details["pe_ratio"] = float(pe) if pe else None
        details["pe_score"] = 0
    details["score"] = details.get("rev_score", 0) + details.get("margin_score", 0) + details.get("pe_score", 0)
    return details

def calculate_score(sid: str, name: str, pattern: dict, fundamentals: dict, bwibbu: Optional[dict]) -> Optional[dict]:
    """綜合評分 — 使用 analyze_breakout_pattern 的結果"""
    if not pattern:
        return None
    scores = {}
    reasons = []
    # 1. 盤整品質
    range_pct = pattern["stable_range_pct"]
    scores["stability"] = max(0, 1 - range_pct / 40)
    if scores["stability"] > 0.7:
        reasons.append(f"盤整品質佳（振幅{range_pct:.1f}%/{pattern['stable_months']}月）")
    # 2. 突破力道
    bm = pattern["pct_above_stable_mean"]
    if bm > 0:
        s = min(bm / 80, 1.0)
        if bm > 30:
            s *= 1.2
        scores["breakout"] = min(s, 1.0)
    else:
        scores["breakout"] = 0
    if bm > 20:
        reasons.append(f"強勢突破（高於盤整均價{bm:.1f}%）")
    elif bm > 10:
        reasons.append(f"初步突破（+{bm:.1f}%）")
    if pattern["chg_60d"] > 30 and pattern["chg_20d"] > 5:
        reasons.append(f"動能持續（20日+{pattern['chg_20d']:.1f}%/60日+{pattern['chg_60d']:.1f}%）")
    # 3. 量能
    vcr = pattern.get("vol_change_ratio", 1.0)
    if vcr and vcr > SCREEN_CONFIG["breakout_volume_surge_min"]:
        scores["volume"] = min(vcr / 5, 1.0)
        reasons.append(f"後半段量能為前半段{vcr:.1f}倍")
    else:
        scores["volume"] = 0
    # 4. 營收
    rev_score = fundamentals.get("rev_score", 0)
    scores["revenue"] = rev_score
    rg = fundamentals.get("revenue_growth")
    if rg and rg > SCREEN_CONFIG["revenue_growth_yoy_min"]:
        reasons.append(f"營收年增{rg*100:.0f}%")
    # 5. PE
    pe_score = fundamentals.get("pe_score", 0)
    scores["pe"] = pe_score
    pe_val = fundamentals.get("pe_ratio")
    if pe_val and 0 < pe_val < 15:
        reasons.append(f"本益比偏低（{pe_val:.1f}）")
    elif pe_val and 15 <= pe_val < 30:
        reasons.append(f"本益比合理（{pe_val:.1f}）")
    w = SCREEN_CONFIG
    total = (scores["stability"] * w["w_stability"] + scores["breakout"] * w["w_breakout"]
             + scores["volume"] * w["w_volume"] + scores["revenue"] * w["w_revenue"]
             + scores["pe"] * w["w_pe"])
    # 藥華藥相似度
    sim = 0
    if pattern["stable_months"] >= 6:
        sim += 20
    if bm > 30:
        sim += 25
    if vcr and vcr > 2:
        sim += 15
    if rg and rg > 0.20:
        sim += 25
    if pe_val and 10 < pe_val < 40:
        sim += 15
    return {
        "stock_id": sid, "name": name,
        "total_score": round(total * 100, 1),
        "similar_pct": sim,
        "scores": scores, "fundamentals": fundamentals, "reasons": reasons,
        "pe_ratio": pe_val, "revenue_growth": rg,
        "current_price": pattern.get("current_price"),
        "stable_mean": pattern["stable_mean"],
    }

def load_watchlist() -> Optional[List[str]]:
    """從 .env 讀取持股清單（PC_開頭的變數）"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if not os.path.exists(env_path):
        return None
    watch = []
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("PC_") and "=" in line:
                watch.append(line.split("=")[0].replace("PC_", ""))
    return watch if watch else None

def generate_html(results, all_scanned, scan_date, output_path):
    """生成 HTML 報告"""
    high = [r for r in results if r["total_score"] >= 60]
    med = [r for r in results if 40 <= r["total_score"] < 60]
    html = f"""<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8"><title>台股潛力股掃瞄 {scan_date}</title>
<style>
body{{font-family:-apple-system,'Microsoft JhengHei',sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;background:#f5f5f5}}
h1{{color:#1a1a2e;border-bottom:3px solid #e94560;padding-bottom:10px}}
.meta{{color:#666;font-size:14px;margin:20px 0}}
.card{{background:#fff;border-radius:12px;padding:20px;margin:16px 0;box-shadow:0 2px 8px rgba(0,0,0,.08);border-left:4px solid #e94560}}
.card.mid{{border-left-color:#f5a623}}
.shdr{{display:flex;justify-content:space-between;align-items:center}}
.sid{{font-size:22px;font-weight:bold}}
.sc{{font-size:28px;font-weight:bold;color:#e94560}}
.tags{{margin:10px 0}}
.tag{{display:inline-block;background:#e94560;color:#fff;padding:3px 10px;border-radius:12px;font-size:12px;margin:3px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:10px}}
.gi{{text-align:center;padding:10px;background:#f0f0f0;border-radius:8px}}
.gv{{font-size:18px;font-weight:bold}}
.gl{{font-size:11px;color:#888}}
table{{width:100%;border-collapse:collapse;margin-top:16px}}
th{{background:#1a1a2e;color:#fff;padding:8px;text-align:left;font-size:13px}}
td{{padding:8px;border-bottom:1px solid #eee;font-size:13px}}
tr:hover td{{background:#f8f9fa}}
</style></head><body>
<h1>📊 台股翻倍潛力股掃瞄</h1>
<div class="meta">日期: {scan_date} | 掃瞄 {all_scanned} 檔 | 參考: {CATALYST_REFERENCE['name']} 模式</div>
<div class="section"><h2>🔴 高潛力 (≥60)</h2>{_cards(high,'') if high else '<p>無</p>'}</div>
<div class="section"><h2>🟡 中潛力 (40-59)</h2>{_cards(med,'mid') if med else '<p>無</p>'}</div>
<div class="section"><h2>📋 完整排名</h2>
<table><tr><th>#</th><th>代號</th><th>名稱</th><th>評分</th><th>相似度</th><th>盤整</th><th>突破</th><th>量能</th><th>營收</th><th>PE</th><th>股價</th></tr>
"""
    for i, r in enumerate(results[:50]):
        s = r["scores"]
        html += f"<tr><td>{i+1}</td><td><b>{r['stock_id']}</b></td><td>{r['name']}</td><td><b>{r['total_score']:.0f}</b></td><td>{r['similar_pct']}%</td><td>{(s.get('stability',0)*100):.0f}</td><td>{(s.get('breakout',0)*100):.0f}</td><td>{(s.get('volume',0)*100) if s.get('volume',0)>0 else '-'}</td><td>{(s.get('revenue',0)*100) if s.get('revenue',0)>0 else '-'}</td><td>{(s.get('pe',0)*100) if s.get('pe',0)>0 else '-'}</td><td>{r['current_price']:.0f}</td></tr>"
    html += "</table></div>"
    html += f'<div class="meta" style="margin-top:40px;padding:20px;background:#f8f9fa;border-radius:8px;"><p><b>⚠️ 免責聲明</b> 僅為技術面+基本面篩選參考，不構成投資建議。</p><p>產生: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p></div></body></html>'
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"✅ HTML報告: {output_path}")

def _cards(results, cls):
    html = ""
    for r in results:
        s = r["scores"]
        tags = " ".join(f'<span class="tag">{t}</span>' for t in r.get("reasons",[]))
        html += f"""<div class="card {cls}">
<div class="shdr"><div><span class="sid">{r['stock_id']}</span> {r['name']}</div><div class="sc">{r['total_score']:.0f}</div></div>
<div class="tags">{tags}</div>
<div class="grid"><div class="gi"><div class="gv">{r['current_price']:.0f}</div><div class="gl">股價</div></div>
<div class="gi"><div class="gv">{r['stable_mean']:.0f}</div><div class="gl">盤整均價</div></div>
<div class="gi"><div class="gv">{r['revenue_growth']*100:.0f}%</div><div class="gl">營收年增</div></div>
<div class="gi"><div class="gv">{r.get('pe_ratio','-') if r.get('pe_ratio') else '-'}</div><div class="gl">本益比</div></div>
<div class="gi"><div class="gv" style="color:#e94560">{r['similar_pct']}%</div><div class="gl">相似度</div></div></div></div>"""
    return html

# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="台股翻倍潛力股每月掃瞄")
    parser.add_argument("--top-n", type=int, default=0)
    parser.add_argument("--output-html", action="store_true")
    parser.add_argument("--watchlist-only", action="store_true")
    parser.add_argument("--min-score", type=float, default=20)
    parser.add_argument("--batch-size", type=int, default=SCREEN_CONFIG["yfinance_batch_size"])
    args = parser.parse_args()
    SCREEN_CONFIG["yfinance_batch_size"] = args.batch_size
    scan_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    t0 = time.time()
    log("="*50)
    log("📊 台股翻倍潛力股掃瞄")
    log(f"   日期: {scan_date}")
    log("="*50)

    # 1. 取得股票清單
    bwibbu = fetch_all_stock_list()
    if bwibbu.empty:
        log("❌ 無法取得股票清單")
        sys.exit(1)
    bwibbu = bwibbu.dropna(subset=["stock_id","name"])
    all_ids = bwibbu["stock_id"].tolist()
    names = dict(zip(bwibbu["stock_id"], bwibbu["name"]))
    log(f"   可篩選: {len(all_ids)} 檔")

    # 2. Watchlist
    watch = None
    if args.watchlist_only:
        watch = load_watchlist()
        if watch:
            log(f"   僅掃描持股: {', '.join(watch)} ({len(watch)} 檔)")
        else:
            log("⚠️ 無持股清單，掃描全市場")

    target_ids = watch if watch else all_ids
    bs = SCREEN_CONFIG["yfinance_batch_size"]
    n_batches = (len(target_ids) + bs - 1) // bs
    bwibbu_dict = {r["stock_id"]: r.to_dict() for _, r in bwibbu.iterrows()}
    all_results = []

    for bi in range(n_batches):
        s = bi * bs
        e = min(s + bs, len(target_ids))
        batch = target_ids[s:e]
        log(f" 批次 {bi+1}/{n_batches} ({s+1}-{e})")
        try:
            pdf = fetch_yfinance_prices(batch)
            info = fetch_yfinance_info(batch)
        except Exception as ex:
            log(f"  ⚠️ 批次失敗: {ex}")
            time.sleep(2)
            continue
        if pdf.empty:
            time.sleep(SCREEN_CONFIG["yfinance_delay"])
            continue
        if isinstance(pdf.columns, pd.MultiIndex):
            avail = pdf.columns.levels[1]
        else:
            continue
        for ticker in avail:
            sid = ticker.replace(".TW", "")
            if sid not in batch:
                continue
            nm = names.get(sid, sid)
            inf = info.get(sid, {})
            try:
                close = pdf["Close"][ticker].dropna()
                volume = pdf["Volume"][ticker].dropna()
                dates = close.index
                if len(close) < 60:
                    continue
                pattern = analyze_breakout_pattern(close, volume, dates)
                if not pattern or not pattern.get("is_stable") or not pattern.get("is_breakout"):
                    continue
                fund = assess_fundamentals(inf, bwibbu_dict.get(sid))
                res = calculate_score(sid, nm, pattern, fund, bwibbu_dict.get(sid))
                if res:
                    all_results.append(res)
            except Exception as ex:
                log(f"  ⚠️ {sid} 分析失敗: {ex}")
                continue
        time.sleep(SCREEN_CONFIG["yfinance_delay"])

    all_results.sort(key=lambda r: r["total_score"], reverse=True)
    elapsed = time.time() - t0
    log(f"\n✅ 完成! {elapsed:.0f}s | 掃瞄 {len(target_ids)} → 篩出 {len(all_results)} 檔")

    if not all_results:
        log("\n無符合條件的股票。可放寬 SCREEN_CONFIG 參數。")
        return

    # 輸出文字報告
    print(f"\n{'='*70}")
    print(f" 📊 台股翻倍潛力股掃瞄結果  {scan_date}")
    print(f"    符合: {len(all_results)} 檔")
    print(f"{'='*70}\n")
    cnt = args.top_n if args.top_n > 0 else len(all_results)
    for i, r in enumerate(all_results[:cnt]):
        if r["total_score"] < args.min_score:
            continue
        s = r["scores"]
        reasons = " | ".join(r.get("reasons",[]))
        print(f"  #{i+1:2d} {r['stock_id']:6s} {r['name']:10s}  "
              f"評分:{r['total_score']:5.1f}  相似:{r['similar_pct']:2d}%  "
              f"股價:{r['current_price']:>8.0f}")
        print(f"      ├─ 盤整:{s.get('stability',0)*20:.1f}/20  "
              f"突破:{s.get('breakout',0)*30:.1f}/30  "
              f"量能:{s.get('volume',0)*15 if s.get('volume',0)>0 else 0:.1f}/15  "
              f"營收:{s.get('revenue',0)*25 if s.get('revenue',0)>0 else 0:.1f}/25  "
              f"PE:{s.get('pe',0)*10 if s.get('pe',0)>0 else 0:.1f}/10")
        if reasons:
            print(f"      └─ 💡 {reasons}")
        print()

    # CSV
    csv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(csv_dir, exist_ok=True)
    csv_path = os.path.join(csv_dir, f"catalyst_scan_{datetime.now().strftime('%Y%m%d')}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["排名","代號","名稱","綜合評分","相似度","股價","盤整均價","營收年增","本益比","盤整/20","突破/30","量能/15","營收/25","PE/10","備註"])
        for i, r in enumerate(all_results):
            s = r["scores"]
            w.writerow([i+1, r["stock_id"], r["name"], f"{r['total_score']:.1f}",
                        f"{r['similar_pct']}%", f"{r['current_price']:.0f}", f"{r['stable_mean']:.0f}",
                        f"{r['revenue_growth']*100:.0f}%" if r.get("revenue_growth") else "N/A",
                        f"{r['pe_ratio']:.1f}" if r.get("pe_ratio") else "N/A",
                        f"{(s.get('stability',0)*100):.0f}", f"{(s.get('breakout',0)*100):.0f}",
                        f"{(s.get('volume',0)*100):.0f}" if s.get("volume",0) > 0 else "0",
                        f"{(s.get('revenue',0)*100):.0f}" if s.get("revenue",0) > 0 else "0",
                        f"{(s.get('pe',0)*100):.0f}" if s.get("pe",0) > 0 else "0",
                        " | ".join(r.get("reasons",[]))])
    log(f"📁 CSV: {csv_path}")

    # HTML
    if args.output_html:
        html_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img")
        os.makedirs(html_dir, exist_ok=True)
        html_path = os.path.join(html_dir, f"catalyst_report_{datetime.now().strftime('%Y%m%d')}.html")
        generate_html(all_results[:50], len(target_ids), scan_date, html_path)

if __name__ == "__main__":
    main()
