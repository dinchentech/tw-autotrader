#!/usr/bin/env python3
"""手動補救選股程式 — 全輪替選股的手動觸發版（2026-08-31 建立）

背景：v3.18 前主迴圈 13:31+ 區塊的 continue 擋死選股邏輯，ROTATE_MODE=5 自動選股從未執行
（2026-08-31 發現：backups/ 空、rotation_pending.json 從未存在）。v3.19 已修復主程式，
本程式提供「立即手動補跑選股」的路徑，行為與主程式 13:31~13:35 完全一致：
  should_rotate_today 判斷 → MIN_DRAW_BACK 檢查 → run_rotation_selection（selector +
  backup_env + update_env_section）→ 排定次日買賣日（rotation_pending.json）→ 重置分帳本。

**設計：local 執行，VM 主程式只負責明日買賣。**
  1. 在本機（local）執行本程式 → 更新 local .env 排程區段 + 產生 local logs/rotation_pending.json
  2. 加 --sync-vm 自動把 .env + logs/rotation_pending.json scp 到 VM（或手動複製）
  3. 明日 VM 主程式讀到 rotation_pending.buy_date → 09:00 自動清倉舊股/買入新股

用法：
  python scripts/manual_rotation_pick.py --dry-run          # 只預覽選出結果，不寫任何檔
  python scripts/manual_rotation_pick.py --sync-vm          # 正式執行 + scp 同步到 VM
  python scripts/manual_rotation_pick.py                    # 正式執行（僅 local，不同步）
  python scripts/manual_rotation_pick.py --schedule B --top-n 3   # 指定排程/檔數

注意：
  - 預設自動判斷「今天該選哪個排程」（should_rotate_today）；非選股日會拒絕執行。
  - --force 可跳過選股日檢查（例如補跑錯過的選股日）。
  - --sync-vm 需 gcloud 認證（VM 名稱/區域可經 --vm/--zone 指定，預設 tw-autotrader/asia-east1-b）。
  - 本程式需在 tw-autotrader 根目錄執行（讀 .env、寫 backups/、logs/）。
"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from core.rotate_scheduler import should_rotate_today, run_rotation_selection
from core.trading_calendar import TradingCalendar


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description="手動補救：全輪替選股（與主程式 13:31 行為一致）")
    parser.add_argument("--dry-run", action="store_true", help="只預覽選出結果，不寫任何檔案")
    parser.add_argument("--schedule", type=str, default=None, help="強制指定排程 A/B（預設自動判斷）")
    parser.add_argument("--top-n", type=int, default=None, help="選股檔數（預設讀 ROTATE_TOP_N）")
    parser.add_argument("--force", action="store_true", help="跳過選股日檢查（補跑錯過的選股日）")
    parser.add_argument("--env", type=str, default=".env", help=".env 路徑")
    parser.add_argument("--sync-vm", action="store_true",
                        help="選股後把 .env + logs/rotation_pending.json scp 到 VM（明日主程式執行買賣）")
    parser.add_argument("--vm", type=str, default="tw-autotrader", help="VM 名稱（--sync-vm 用）")
    parser.add_argument("--zone", type=str, default="asia-east1-b", help="VM 區域（--sync-vm 用）")
    args = parser.parse_args()

    env_path = args.env
    today = date.today()
    rotate_mode = int(os.getenv("ROTATE_MODE", "0"))
    nth_td = int(os.getenv("ROTATE_TRADING_DAY_N", "-1"))
    top_n = args.top_n or int(os.getenv("ROTATE_TOP_N", "4"))
    min_drawback = float(os.getenv("MIN_DRAW_BACK", "0"))
    calendar = TradingCalendar()

    if rotate_mode <= 0:
        print("❌ ROTATE_MODE <= 0，全輪替未啟用")
        sys.exit(1)

    # ── 1. 判斷今天該選哪個排程 ──
    schedule = args.schedule or should_rotate_today(today, rotate_mode, calendar, nth_td)
    if not schedule:
        if args.force:
            schedule = args.schedule or "A"
            print(f"⚠️ --force：今日({today})非選股日，強制以排程 {schedule} 執行")
        else:
            print(f"❌ 今日({today})非選股日（ROTATE_MODE={rotate_mode}、第{nth_td}個交易日=每月最後交易日）")
            print("   若要強制補跑：加上 --force 或 --schedule A/B")
            sys.exit(1)
    print(f"✅ 選股日確認：{today} → 排程 {schedule}（top {top_n}）")

    # ── 2. MIN_DRAW_BACK 股災防護檢查（與主程式一致）──
    if min_drawback > 0:
        try:
            from core.live_trader_helpers import get_stock_capital  # noqa: F401
            from core.rotation_hold import check_rotation_hold
            # 簡化檢查：讀持倉與 .env TOTAL_CAPITAL 估算總資產
            holdings = load_json("logs/holdings.json", {})
            total_capital = float(os.getenv("TOTAL_CAPITAL", "0"))
            # 借用主程式同款 check_rotation_hold（內部自己取價）
            held, dd = check_rotation_hold(min_drawback, total_capital, None, holdings, today.isoformat())
            if held:
                print(f"⚠️ 總回撤 {dd:+.1%} 超過 MIN_DRAW_BACK={min_drawback:g}% → 依規則本季續抱，跳過換股")
                print("   若確定要強制換股：先暫時設 MIN_DRAW_BACK=0 再執行")
                sys.exit(0)
            print(f"✅ MIN_DRAW_BACK 檢查通過（回撤 {dd:+.1%} < {min_drawback:g}%）")
        except Exception as e:
            print(f"⚠️ MIN_DRAW_BACK 檢查失敗（{e}），繼續執行（fail-open）")

    # ── 3. 執行選股（dry-run 只預覽）──
    print(f"🔄 執行選股：python scripts/stock_selector_grid.py --recommend --output-env --schedule-label {schedule} --top-n {top_n}")
    if args.dry_run:
        import subprocess
        result = subprocess.run(
            ["python", "scripts/stock_selector_grid.py", "--recommend", "--output-env",
             "--schedule-label", schedule, "--top-n", str(top_n)],
            capture_output=True, text=True, timeout=180,
            env={**os.environ, "SELECTOR_LOOKBACK_DAYS": os.getenv("ROTATE_LOOKBACK_DAYS", "250")},
        )
        if result.returncode != 0:
            print(f"❌ selector 失敗: {result.stderr[:800]}")
            sys.exit(1)
        pc_lines, seen = [], set()
        for l in result.stdout.strip().split("\n"):
            l = l.strip()
            if l.startswith("PC_") and l not in seen:
                pc_lines.append(l)
                seen.add(l)
        if not pc_lines:
            print("⚠️ selector 無輸出")
            sys.exit(1)
        print("\n─── 預覽：選出的 PC_ 條目（dry-run，未寫入 .env）───")
        for line in pc_lines:
            print(f"  {line}")
        print("\n執行正式版（不加 --dry-run）後將：")
        print(f"  1. 備份 .env → backups/")
        print(f"  2. 更新 .env 排程 {schedule} 區段")
        print(f"  3. 排定次日買賣日 → logs/rotation_pending.json")
        print("  4. 重置分帳本與每月預算")
        return

    # ── 4. 正式執行 ──
    try:
        stocks = run_rotation_selection(rotate_mode, schedule, env_path=env_path,
                                        backup_dir="backups", top_n=top_n)
    except Exception as e:
        print(f"❌ 選股失敗: {e}")
        sys.exit(1)

    print(f"✅ 選股完成：{', '.join(stocks)}")

    # ── 5. 排定次日買賣日（與主程式一致）──
    try:
        from core.live_utils import get_next_market_open
        from datetime import datetime
        next_buy = get_next_market_open(datetime.now()).strftime("%Y-%m-%d")
        save_json({"buy_date": next_buy}, "logs/rotation_pending.json")
        print(f"📅 買賣日已排定: {next_buy}")
    except Exception as e:
        print(f"⚠️ 排定買賣日失敗: {e}")

    # ── 6. 重置分帳本與每月預算（換季，與主程式一致）──
    try:
        stock_alloc = load_json("logs/stock_allocation.json", {})
        for sym in list(stock_alloc.keys()):
            stock_alloc[sym] = {"total_buy_cost": 0, "total_buy_shares": 0}
        save_json(stock_alloc, "logs/stock_allocation.json")
        save_json({}, "logs/monthly_budget.json")
        print("🧹 分帳本與每月預算已重置")
    except Exception as e:
        print(f"⚠️ 重置分帳本失敗: {e}")

    print("\n✅ 完成！明日開盤將依新配置清倉/買入。")
    print("   提醒：若 VM 上主程式尚未部署 v3.19，明日買入仍由主程式正常處理（選股只影響 .env）")

    # ── 7. 同步到 VM（可選：--sync-vm）──
    if args.sync_vm:
        import subprocess as _sp
        files = [env_path, "logs/rotation_pending.json"]
        print(f"\n🔄 同步到 VM {args.vm} ({args.zone})...")
        for f in files:
            r = _sp.run(["gcloud", "compute", "scp", f,
                         f"{args.vm}:~/tw-autotrader/{f}", "--zone", args.zone, "--quiet"],
                        capture_output=True, text=True)
            if r.returncode == 0:
                print(f"  ✅ {f} → VM")
            else:
                print(f"  ❌ {f} 同步失敗: {r.stderr[:200]}")
                sys.exit(1)
        print(f"\n✅ 同步完成！明日（{next_buy}）VM 主程式將自動清倉/買入。")
        print("   注意：若 VM 主程式仍是 v3.18，其選股 bug 不影響買賣（買賣由 rotation_pending 驅動）")
    else:
        print("\nℹ️ 未同步（未加 --sync-vm）。請自行將以下檔案複製到 VM：")
        print(f"   {env_path} → ~/tw-autotrader/{env_path}")
        print("   logs/rotation_pending.json → ~/tw-autotrader/logs/rotation_pending.json")
        print("   或直接加 --sync-vm 自動同步")


if __name__ == "__main__":
    main()
