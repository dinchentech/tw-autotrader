"""
scripts/build_historical_shares.py — 建立「歷史股本資料庫」供回測重現

背景
----
回測「全輪替（ROTATE_MODE=5）」時，候選池必須是「每個選股季『當時』的市值前 N 大」，
不能用今天的市值排名套到過去（= 倖存者偏差 / 開卷考試）。
當時市值 = 歷史股本 × 當季股價，其中「歷史股本」這半邊就是本腳本產出的資料庫。

產出
    cache/inst_momentum/historical_shares.pkl
    格式: { (stock_id, 'YYYY-MM'): 發行股本(股) }，例: {('2330','2015-02'): 25929374956}
    季度點: 每年 2/5/8/11 月底（對應全輪替 A=2/5/8/11、B=3/6/9/12 排程的選股季）
    涵蓋範圍: mcap_ranking.pkl 市值前 TOP_N 檔（預設 150，即回測設定的候選池大小）

資料源
    FinMind TaiwanStockShareholding（每日更新）的 NumberOfSharesIssued 欄位 = 發行股本（股）。
    免費帳號可存取（已驗證）。

Usage:
  python scripts/build_historical_shares.py                          # 建立/更新 150 檔
  python scripts/build_historical_shares.py --top-n 300              # 擴大到市值前 300 檔
  python scripts/build_historical_shares.py --years 2015 2026        # 指定年份範圍（預設 2015~2025）
  python scripts/build_historical_shares.py --dry-run                # 預覽統計不寫檔
  python scripts/build_historical_shares.py --stock 2330 2454        # 只處理指定股票
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.cache_io import load_cache_or_raw, dump_cache

CAP_RANKING = ROOT / "cache" / "inst_momentum" / "mcap_ranking.pkl"
OUTPUT_PKL = ROOT / "cache" / "inst_momentum" / "historical_shares.pkl"

# 季度點（對應 2/5/8/11 選股排程）：每年度取這四個月「月底」的股本
QUARTER_MONTHS = (2, 5, 8, 11)
QUARTER_POINTS = [f"{y}-{m:02d}" for y in range(2015, 2026) for m in QUARTER_MONTHS]


def load_ranking_pool(top_n: int):
    """從市值排名快取取前 top_n 檔 4 碼上市股"""
    if not CAP_RANKING.exists():
        print(f"❌ 找不到市值排名 {CAP_RANKING}（先執行選股工具產生）")
        return []
    ranked, _ = load_cache_or_raw(CAP_RANKING)
    ranked = ranked or []
    pool = [s for s in ranked if s.isdigit() and len(s) == 4][:top_n]
    print(f"📋 候選池：市值前 {len(pool)} 大（來源 {CAP_RANKING.name}）")
    return pool


def build_quarterly_shares(dl, stock_id: str, years):
    """抓單一股票 in years 的歷史股本，回傳 {(stock_id, 'YYYY-MM'): 股數}"""
    start = f"{min(years)}-01-01"
    end = f"{max(years)}-12-31"
    df = dl.taiwan_stock_shareholding(stock_id, start, end)
    if df is None or df.empty:
        return {}
    df = df[["date", "NumberOfSharesIssued"]].sort_values("date")
    result = {}
    for y in years:
        for m in QUARTER_MONTHS:
            key = f"{y}-{m:02d}"
            month_data = df[
                (df["date"].astype(str) >= f"{y}-{m:02d}-01")
                & (df["date"].astype(str) <= f"{y}-{m:02d}-31")
            ]
            if month_data.empty:
                # 該月無資料（例：當時未上市）→ 跳過
                continue
            shares = int(month_data.iloc[-1]["NumberOfSharesIssued"])
            result[(stock_id, key)] = shares
    return result


def main():
    parser = argparse.ArgumentParser(description="建立歷史股本資料庫（回測用）")
    parser.add_argument("--top-n", type=int, default=150, help="取市值前 N 檔（預設 150）")
    parser.add_argument("--start", nargs="*", type=int, default=[2015, 2026], help="年份範圍（預設 2015 2026）")
    parser.add_argument("--dry-run", action="store_true", help="預覽不寫檔")
    parser.add_argument("--stock", nargs="*", help="只處理指定股票（除錯用）")
    args = parser.parse_args()

    years = list(range(min(args.start), max(args.start) + 1))
    print(f"🔬 FinMind 歷史股本建置 — 年份 {years[0]}~{years[-1]}")

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from FinMind.data import DataLoader

    dl = DataLoader()

    if args.stock:
        pool = [s.strip() for s in args.stock]
    else:
        pool = load_ranking_pool(args.top_n)
        if not pool:
            sys.exit(1)

    existing = {}
    if OUTPUT_PKL.exists():
        existing, _ = load_cache_or_raw(OUTPUT_PKL)
        existing = existing or {}
        print(f"既有資料庫：{len(existing)} 筆")

    errors, data = [], dict(existing)
    t0 = time.time()
    for i, sid in enumerate(pool, 1):
        if sid in {k[0] for k in data}:
            print(f"[{i:>3}/{len(pool)}] {sid} 已存在，跳過")
            continue
        try:
            result = build_quarterly_shares(dl, sid, years)
            data.update(result)
            print(f"[{i:>3}/{len(pool)}] {sid} → {len(result)} 季")
        except Exception as e:
            errors.append((sid, str(e)[:100]))
            print(f"[{i:>3}/{len(pool)}] {sid} 失敗: {str(e)[:100]}")
        time.sleep(0.15)  # API rate limit 緩衝

    print(f"\n完成: {len(pool)} 檔, 有效 {len(data)} 筆, 失敗 {len(errors)}, 耗時 {time.time()-t0:.0f}s")
    if errors:
        print("失敗清單:")
        for sid, err in errors:
            print(f"  {sid}: {err}")

    if args.dry_run:
        print("[dry-run] 未寫檔")
        return

    OUTPUT_PKL.parent.mkdir(parents=True, exist_ok=True)
    dump_cache(OUTPUT_PKL, data, meta={"source": "FinMind_TaiwanStockShareholding", "count": len(data)})
    print(f"已寫入: {OUTPUT_PKL} ({OUTPUT_PKL.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()