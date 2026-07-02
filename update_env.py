#!/usr/bin/env python3
"""
update_env.py — .env 配置變更管理工具

根據使用者提供的新配置檔（env_new.txt），與當前 .env 比較差異，
自動分類變更類型（新增/刪除/修改策略/修改參數/資金變更），
並執行對應操作（備份、更新、清除歷史資料、提醒手動操作）。

使用方式：
  python update_env.py env_new.txt              # 比對差異並互動執行
  python update_env.py env_new.txt --dry-run     # 只顯示差異，不執行
  python update_env.py env_new.txt --yes         # 跳過確認，直接執行
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from difflib import unified_diff

# ── 常數 ──────────────────────────────────────────────────

ENV_PATH = Path(".env")
LOGS_DIR = Path("logs")
BACKUP_DIR = Path("backups")

# 需要清除的歷史資料檔案
HISTORY_FILES = [
    "logs/performance.csv",
    "logs/holdings.json",
    "logs/processed_capital.json",
    "logs/monthly_budget.json",
    "logs/dashboard.html",
    "data/inst_momentum_pnl.json",
]

# 系統級變數（非 PC_ 格式）
SYSTEM_VARS = {
    "TOTAL_CAPITAL", "DCA_AMOUNT", "INST_MOM_CAPITAL",
    "BROKER", "USE_REAL_API", "ESUN_ENVIRONMENT",
    "INITIAL_CAPITAL", "MAX_RISK_PER_TRADE", "MAX_DAILY_LOSS",
    "MAX_DAILY_TRADES", "MARKET_TREND_FILTER",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "LINE_NOTIFY_TOKEN", "GIT_PAGE",
    "PROFIT_ROLL_MONTHS", "PROFIT_ROLL_PERCENTAGE",
}

# 股票名稱對照
STOCK_NAMES = {
    "0050": "元大台灣50", "006208": "富邦台50", "00878": "國泰永續高股息",
    "2330": "台積電", "2454": "聯發科", "2382": "中華電信",
    "2881": "富邦金", "2882": "國泰金", "2886": "兆豐金",
    "3034": "聯詠", "2317": "鴻海", "6669": "緯穎",
    "2412": "中華電", "0056": "元大高股息",
}


# ── 解析 .env ─────────────────────────────────────────────

def parse_env(filepath: Path) -> tuple[dict, dict]:
    """
    解析 .env 檔案，回傳 (pc_vars, system_vars)
    
    pc_vars: { "2330": {"strategy": "ma_cross", ...}, ... }
    system_vars: { "TOTAL_CAPITAL": "500000", ... }
    """
    pc_vars = {}
    system_vars = {}
    raw_lines = {}
    
    if not filepath.exists():
        print(f"❌ 找不到 {filepath}")
        sys.exit(1)
    
    for line in filepath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        if "=" not in line:
            continue
        
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        
        # 移除行內註解
        if " #" in val:
            val = val[:val.index(" #")].strip()
        if "\t#" in val:
            val = val[:val.index("\t#")].strip()
        
        if key.startswith("PC_"):
            symbol = key[3:]
            try:
                parsed = json.loads(val)
                pc_vars[symbol] = parsed
            except json.JSONDecodeError:
                print(f"⚠️  {key} 的 JSON 格式錯誤，跳過: {val[:60]}...")
        elif key in SYSTEM_VARS:
            system_vars[key] = val
    
    return pc_vars, system_vars


def stock_label(symbol: str) -> str:
    """回傳 '代號 名稱' 格式"""
    name = STOCK_NAMES.get(symbol, "")
    return f"{symbol} {name}" if name else symbol


# ── 差異比較 ───────────────────────────────────────────────

def compare_configs(old_pc: dict, new_pc: dict, 
                    old_sys: dict, new_sys: dict) -> dict:
    """
    比較新舊配置，回傳分類後的差異
    
    回傳格式：
    {
        "added_stocks": [(symbol, config), ...],      # 新增股票
        "removed_stocks": [(symbol, config), ...],     # 刪除股票
        "strategy_changed": [(symbol, old, new), ...], # 策略變更
        "params_changed": [(symbol, old, new), ...],   # 參數變更
        "alloc_changed": [(symbol, old_alloc, new_alloc), ...],  # 資金變更
        "system_changed": [(key, old_val, new_val), ...],  # 系統變數變更
    }
    """
    diff = {
        "added_stocks": [],
        "removed_stocks": [],
        "strategy_changed": [],
        "params_changed": [],
        "alloc_changed": [],
        "system_changed": [],
    }
    
    old_symbols = set(old_pc.keys())
    new_symbols = set(new_pc.keys())
    
    # 新增的股票
    for sym in sorted(new_symbols - old_symbols):
        diff["added_stocks"].append((sym, new_pc[sym]))
    
    # 刪除的股票
    for sym in sorted(old_symbols - new_symbols):
        diff["removed_stocks"].append((sym, old_pc[sym]))
    
    # 既有股票的變更
    for sym in sorted(old_symbols & new_symbols):
        old = old_pc[sym]
        new = new_pc[sym]
        
        # 策略變更
        if old.get("strategy") != new.get("strategy"):
            diff["strategy_changed"].append((sym, old, new))
            continue  # 策略變更已涵蓋參數變更
        
        # 資金配置變更
        old_alloc = old.get("alloc")
        new_alloc = new.get("alloc")
        if old_alloc != new_alloc:
            diff["alloc_changed"].append((sym, old_alloc, new_alloc))
        
        # 參數變更（排除 strategy 和 alloc 後的其他欄位）
        old_params = {k: v for k, v in old.items() if k not in ("strategy", "alloc")}
        new_params = {k: v for k, v in new.items() if k not in ("strategy", "alloc")}
        if old_params != new_params:
            diff["params_changed"].append((sym, old, new))
    
    # 系統變數變更（只比較新配置中明確列出的變數）
    for key in sorted(new_sys.keys()):
        old_val = old_sys.get(key, "")
        new_val = new_sys[key]
        if old_val != new_val:
            diff["system_changed"].append((key, old_val, new_val))
    
    return diff


# ── 報告顯示 ───────────────────────────────────────────────

def print_diff_report(diff: dict):
    """顯示差異報告"""
    has_changes = False
    
    # 新增股票
    if diff["added_stocks"]:
        has_changes = True
        print("\n🟢 新增股票：")
        for sym, cfg in diff["added_stocks"]:
            print(f"   + {stock_label(sym):20s} 策略={cfg.get('strategy','?'):12s} alloc={cfg.get('alloc','?')}%")
    
    # 刪除股票
    if diff["removed_stocks"]:
        has_changes = True
        print("\n🔴 刪除股票：")
        for sym, cfg in diff["removed_stocks"]:
            print(f"   - {stock_label(sym):20s} 策略={cfg.get('strategy','?'):12s} alloc={cfg.get('alloc','?')}%")
            print(f"     ⚠️  若有餘股，請在券商平台手動賣出！")
    
    # 策略變更
    if diff["strategy_changed"]:
        has_changes = True
        print("\n🔄 策略變更：")
        for sym, old, new in diff["strategy_changed"]:
            print(f"   {stock_label(sym):20s} {old.get('strategy','?')} → {new.get('strategy','?')}")
            print(f"     ⚠️  策略變更需清除歷史資料！")
    
    # 參數變更
    if diff["params_changed"]:
        has_changes = True
        print("\n🔧 參數變更：")
        for sym, old, new in diff["params_changed"]:
            # 找出具體變更的參數
            changed_keys = []
            all_keys = set(old.keys()) | set(new.keys())
            for k in all_keys:
                if k in ("strategy", "alloc"):
                    continue
                old_v = old.get(k)
                new_v = new.get(k)
                if old_v != new_v:
                    changed_keys.append(f"{k}: {old_v}→{new_v}")
            print(f"   {stock_label(sym):20s} {', '.join(changed_keys)}")
    
    # 資金配置變更
    if diff["alloc_changed"]:
        has_changes = True
        print("\n💰 資金配置變更：")
        for sym, old_a, new_a in diff["alloc_changed"]:
            print(f"   {stock_label(sym):20s} alloc: {old_a}% → {new_a}%")
    
    # 系統變數變更
    if diff["system_changed"]:
        has_changes = True
        print("\n⚙️  系統變數變更：")
        for key, old_v, new_v in diff["system_changed"]:
            print(f"   {key}: {old_v} → {new_v}")
    
    if not has_changes:
        print("\n✅ 沒有差異，配置相同。")
    
    return has_changes


# ── 需要清除的判斷 ──────────────────────────────────────────

def needs_history_clear(diff: dict) -> bool:
    """判斷是否需要清除歷史資料"""
    return bool(
        diff["removed_stocks"]
        or diff["strategy_changed"]
        or diff["params_changed"]
        or diff["alloc_changed"]
    )


def needs_deploy(diff: dict) -> bool:
    """判斷是否需要部署到 VM"""
    return bool(
        diff["added_stocks"]
        or diff["removed_stocks"]
        or diff["strategy_changed"]
        or diff["params_changed"]
        or diff["alloc_changed"]
        or diff["system_changed"]
    )


# ── 執行操作 ───────────────────────────────────────────────

def backup_env():
    """備份當前 .env"""
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f".env.{timestamp}"
    shutil.copy2(ENV_PATH, backup_path)
    print(f"✅ 已備份 .env → {backup_path}")
    return backup_path


def apply_new_env(new_env_path: Path):
    """套用新配置到 .env（保留非 PC_ / 非系統變數的行）"""
    # 讀取舊 .env 的所有行
    old_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    
    # 讀取新配置的 PC_ 和系統變數
    new_pc_keys = set()
    new_sys_keys = set()
    new_values = {}
    
    for line in new_env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if key.startswith("PC_"):
            new_pc_keys.add(key)
            new_values[key] = val
        elif key in SYSTEM_VARS:
            new_sys_keys.add(key)
            new_values[key] = val
    
    # 建立新的 .env 內容
    result_lines = []
    old_pc_written = set()
    
    for line in old_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            result_lines.append(line)
            continue
        
        if "=" not in stripped:
            result_lines.append(line)
            continue
        
        key, _, _ = stripped.partition("=")
        key = key.strip()
        
        if key.startswith("PC_"):
            if key in new_pc_keys:
                # 更新為新值
                result_lines.append(f"{key}={new_values[key]}")
                old_pc_written.add(key)
            # else: 刪除的股票，不寫入
        elif key in SYSTEM_VARS:
            if key in new_sys_keys:
                result_lines.append(f"{key}={new_values[key]}")
            else:
                result_lines.append(line)
        else:
            result_lines.append(line)
    
    # 加入新增的 PC_ 變數（舊 .env 沒有的）
    for key in sorted(new_pc_keys - old_pc_written):
        result_lines.append(f"{key}={new_values[key]}")
    
    ENV_PATH.write_text("\n".join(result_lines) + "\n", encoding="utf-8")
    print(f"✅ 已更新 .env")


def clear_history():
    """清除歷史資料"""
    cleared = []
    for fpath in HISTORY_FILES:
        fp = Path(fpath)
        if fp.exists():
            fp.unlink()
            cleared.append(fpath)
    
    if cleared:
        print(f"✅ 已清除歷史資料：{', '.join(cleared)}")
    else:
        print("ℹ️  無歷史資料需清除")
    
    # 重新生成空白 dashboard
    try:
        from scripts.generate_dashboard import main as gen_dashboard
        gen_dashboard()
        print("✅ 已重新生成空白儀表板")
    except Exception:
        print("ℹ️  儀表板將在下次交易時自動生成")


def check_holdings(removed_symbols: list[str]):
    """檢查被刪除股票是否有持倉"""
    holdings_path = LOGS_DIR / "holdings.json"
    if not holdings_path.exists():
        return
    
    try:
        holdings = json.loads(holdings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    
    for sym in removed_symbols:
        if sym in holdings and holdings[sym].get("quantity", 0) > 0:
            qty = holdings[sym]["quantity"]
            avg = holdings[sym].get("avg_cost", 0)
            print(f"\n🚨 {stock_label(sym)} 仍有持倉：{qty} 股 @ {avg}")
            print(f"   請在券商平台手動賣出，或等待系統產生賣出訊號後再刪除！")


# ── 主流程 ─────────────────────────────────────────────────

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="update_env.py — .env 配置變更管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python update_env.py env_new.txt              # 比對差異並互動執行
  python update_env.py env_new.txt --dry-run     # 只顯示差異，不執行
  python update_env.py env_new.txt --yes         # 跳過確認，直接執行
        """,
    )
    parser.add_argument("new_env", help="新配置檔路徑（如 env_new.txt）")
    parser.add_argument("--dry-run", action="store_true", help="只顯示差異，不執行任何變更")
    parser.add_argument("--yes", "-y", action="store_true", help="跳過確認提示")
    args = parser.parse_args()
    
    new_env_path = Path(args.new_env)
    if not new_env_path.exists():
        print(f"❌ 找不到新配置檔：{new_env_path}")
        sys.exit(1)
    
    # 1. 解析新舊配置
    print("📋 正在比對配置...")
    old_pc, old_sys = parse_env(ENV_PATH)
    new_pc, new_sys = parse_env(new_env_path)
    
    # 2. 比較差異
    diff = compare_configs(old_pc, new_pc, old_sys, new_sys)
    
    # 3. 顯示差異報告
    print(f"\n{'='*60}")
    print(f"📊 配置變更報告")
    print(f"{'='*60}")
    print(f"當前配置：{len(old_pc)} 檔股票")
    print(f"新配置：  {len(new_pc)} 檔股票")
    
    has_changes = print_diff_report(diff)
    
    if not has_changes:
        sys.exit(0)
    
    # 4. 顯示所需操作摘要
    print(f"\n{'='*60}")
    print(f"📝 所需操作摘要")
    print(f"{'='*60}")
    
    actions = []
    if diff["removed_stocks"]:
        actions.append("⚠️  手動賣出刪除股票的餘股（券商平台）")
    actions.append("✅ 備份當前 .env")
    actions.append("✅ 套用新配置到 .env")
    if needs_history_clear(diff):
        actions.append("✅ 清除歷史資料（performance.csv, holdings.json 等）")
    actions.append("✅ 部署到 VM（./deploy.sh）")
    
    for i, action in enumerate(actions, 1):
        print(f"   {i}. {action}")
    
    # dry-run 模式
    if args.dry_run:
        print("\n🏃 --dry-run 模式，不執行任何變更")
        sys.exit(0)
    
    # 5. 檢查刪除股票的持倉
    if diff["removed_stocks"]:
        removed_symbols = [sym for sym, _ in diff["removed_stocks"]]
        check_holdings(removed_symbols)
    
    # 6. 確認執行
    if not args.yes:
        print()
        answer = input("是否執行上述操作？(y/N): ").strip().lower()
        if answer not in ("y", "yes"):
            print("❌ 已取消")
            sys.exit(0)
    
    # 7. 執行操作
    print(f"\n{'='*60}")
    print(f"🚀 開始執行")
    print(f"{'='*60}")
    
    # 7a. 備份
    backup_env()
    
    # 7b. 套用新配置
    apply_new_env(new_env_path)
    
    # 7c. 清除歷史資料
    if needs_history_clear(diff):
        clear_history()
    
    # 7d. 部署提醒
    if needs_deploy(diff):
        print(f"\n{'='*60}")
        print(f"📦 下一步：部署到 VM")
        print(f"{'='*60}")
        print("   請執行以下命令：")
        print("   ./deploy.sh")
        print()
        print("   部署後確認：")
        print("   sudo docker logs tw_autotrader_bot 2>&1 | tail -20")
    
    # 7e. 手動操作提醒
    if diff["removed_stocks"]:
        print(f"\n{'='*60}")
        print(f"⚠️  手動操作提醒")
        print(f"{'='*60}")
        for sym, cfg in diff["removed_stocks"]:
            print(f"   {stock_label(sym)}：請在券商平台賣出餘股")
    
    print(f"\n✅ update_env 完成！")


if __name__ == "__main__":
    main()
