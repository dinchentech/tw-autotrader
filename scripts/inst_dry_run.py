"""
inst_dry_run.py — 法人動能乾跑驗證

用與實盤完全相同的程式碼路徑（strategies/institutional_momentum.py + core/inst_data.py）
執行一次今日篩選，輸出觸發結果與資料健康度。

用途：實盤沒觸發時，先在這裡驗證是「資料壞」還是「真的沒訊號」；
      部署前也可以在 VM 上跑一次確認資料管線正常。

用法：
  python scripts/inst_dry_run.py
"""
import os
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from strategies.institutional_momentum import InstitutionalMomentumStrategy


def main():
    s = InstitutionalMomentumStrategy(
        capital=float(os.getenv("INST_MOM_CAPITAL", "500000")))
    print("=" * 60)
    print("🔍 法人動能乾跑（與實盤相同程式碼路徑）")
    print(f"   選股池: 市值前 {s.MAX_STOCKS} | 魚過濾: "
          f"{os.getenv('INST_MOM_FISH_DAYS','90')}天/{os.getenv('INST_MOM_FISH_MIN_SCORE','7.0')}分")
    print("=" * 60)

    candidates, near_misses = s.get_candidates()

    if candidates:
        print("\n✅ 今日觸發條件成立:")
        for sid, score in candidates:
            print(f"   {sid}  法人買超佔比 {score:.2%}")
    else:
        print("\n❌ 今日無觸發")
        if near_misses:
            print("   前三接近標的（未通過動能檢查）:")
            for sid, score in near_misses:
                print(f"   {sid}  momentum={score:.2f}")

    summary_path = PROJECT_ROOT / "logs" / "inst_momentum_screening.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        print("\n📊 資料健康度:")
        health = summary.get("data_health", {})
        print(f"   有股價資料: {health.get('stocks_with_price', 0)} 檔")
        print(f"   有法人資料: {health.get('stocks_with_inst', 0)} 檔 | "
              f"無法人資料: {health.get('stocks_missing_inst', 0)} 檔")
        print(f"   法人資料最新日期: {health.get('latest_inst_date')}")
        print(f"   法人來源分佈: {health.get('inst_source', {})}")
        print(f"   股價來源分佈: {health.get('price_source', {})}")
        print(f"\n   篩選日: {summary.get('screen_date')} | "
              f"has_qualified: {summary.get('has_qualified')}")


if __name__ == "__main__":
    main()
