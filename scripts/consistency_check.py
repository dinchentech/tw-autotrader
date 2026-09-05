#!/usr/bin/env python3
"""scripts/consistency_check.py — 跨檔一致性檢查（V4.00 每月換股/auto/混合分析）"""
import os, re, sys, py_compile, subprocess
sys.path.insert(0, "/home/frank/tw-autotrader")
os.chdir("/home/frank/tw-autotrader")

ok = True


def chk(name, cond, detail=""):
    global ok
    flag = "✅" if cond else "❌"
    if not cond:
        ok = False
    print(f"  {flag} {name}" + (f"  ({detail})" if detail and not cond else ""))


def readf(p):
    try:
        return open(p, encoding="utf-8").read()
    except Exception:
        return ""


print("═" * 60)
print("1) 版本單一來源")
ver = readf("core/version.py")
_m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', ver)
CUR_VER = _m.group(1) if _m else "?"
chk("core/version.py 有 APP_VERSION 字串", CUR_VER != "?", CUR_VER)
chk("core/version.py APP_VERSION", 'APP_VERSION = "' + CUR_VER + '"' in ver)
helpers = readf("core/live_trader_helpers.py")
chk("live_trader_helpers 用共用版本(import)", "from core.version import APP_VERSION" in helpers)
chk("live_trader_helpers 無殘留 2.03", 'APP_VERSION = "2.03"' not in helpers)
manual = readf("使用手冊.md")
chk(f"使用手冊 版本={CUR_VER}", f"**版本**：{CUR_VER}" in manual or f"版本：{CUR_VER}" in manual)

print("═" * 60)
print("2) auto 策略接線")
chk("strategies/auto_sensing.py 存在", os.path.exists("strategies/auto_sensing.py"))
asrc = readf("strategies/auto_sensing.py")
chk("auto_sensing.py 有 route_strategy", "def route_strategy" in asrc)
chk("auto_sensing.py 有 auto_sensing_strategy", "def auto_sensing_strategy" in asrc)
cfg = readf("core/config_loader.py")
chk("config_loader STRATEGY_PARAM_KEYS 有 auto", '"auto": []' in cfg or '"auto":[]' in cfg)
lt = readf("live_trader_multi.py")
chk("live_trader STRATEGY_FUNCS 有 'auto'", "'auto': auto_sensing_strategy" in lt)
chk("live_trader 單一 STRATEGY_FUNCS 定義", readf("live_trader_multi.py").count("STRATEGY_FUNCS =") == 1)
chk(".env.example.txt 提到 auto", "auto" in readf(".env.example.txt"))

print("═" * 60)
print("3) 每月選股工具 argparse 參數")
pk = readf("scripts/monthly_rebalance_picker.py")
for opt in ["--risk", "--strategy", "--top-n", "--pool-n", "--min-price", "--mom-days",
            "--no-inst", "--inst-days", "--as-of"]:
    chk(f"picker 有 {opt}", opt in pk)
chk("picker risk 只含 high_profit/normal(無 stable)", 'choices=["high_profit", "normal"]' in pk)
chk("picker 有 ~/auto|fixed 選項", "choices=[\"auto\", \"fixed\"]" in pk)
chk("picker 記錄上次建議(monthly_pick)", "MONTHLY_PICK_FILE" in pk and "monthly_pick.json" in pk)

print("═" * 60)
print("4) 回測腳本環境變數")
bt = readf("scripts/backtest_plan2_monthly_3group.py")
for var in ["STRAT_MODE", "SWAP_MODE", "INST_CONFIRM", "INST_DAYS", "MIN_DRAW_BACK",
            "MDB_UNLIMITED", "POOL_N", "TOP_N", "STRAT_MODE"]:
    chk(f"backtest 有 {var}", var in bt)
chk("backtest 有 SWAP_MODE=addonly(C)", '"addonly"' in bt)

print("═" * 60)
print("5) 文件內『本地 .md 連結』是否存在")
docs = ["使用手冊.md", "策略說明.md", "README.md", "回測_方案二_每月換股_三組.md", "全輪替與模型C混合分析_2015-2025.md"]
md_links = set()
for doc in docs:
    for m in re.findall(r"\]\(([^)#\s]+\.md)", readf(doc)):
        md_links.add(m)
for link in sorted(md_links):
    base = link.split("#")[0]
    chk(f"連結存在: {link}", os.path.exists(base), f"缺 {base}")

print("═" * 60)
print("6) 引用的關鍵檔案/曲線存在")
for f in ["strategies/auto_sensing.py", "scripts/monthly_rebalance_picker.py",
          "scripts/blend_rotation_vs_modelC.py", "scripts/backtest_plan2_monthly_3group.py",
          "全輪替與模型C混合分析_2015-2025.md", "回測_方案二_每月換股_三組.md",
          "每月選股明細_三組.md", "results/rotate_mode5_2015_2025_daily_equity.csv",
          "results/daily_normal.csv", "results/daily_stable.csv", "results/daily_high_profit.csv"]:
    chk(f"存在: {f}", os.path.exists(f))

print("═" * 60)
print("7) Python 編譯")
for f in ["scripts/monthly_rebalance_picker.py", "strategies/auto_sensing.py",
          "scripts/blend_rotation_vs_modelC.py", "scripts/backtest_plan2_monthly_3group.py",
          "core/config_loader.py", "core/version.py", "core/live_trader_helpers.py",
          "live_trader_multi.py"]:
    try:
        py_compile.compile(f, doraise=True)
        chk(f"compile: {f}", True)
    except Exception as e:
        chk(f"compile: {f}", False, str(e))

print("═" * 60)
print("8) 策略名稱一致性（文件 vs 現有 strategy 函式）")
strat_files = {"bollinger": "strategies/bollinger.py", "ma_cross": "strategies/ma_cross.py",
               "vwap": "strategies/vwap_deviation.py", "breakout": "strategies/breakout.py",
               "keep_wait": "strategies/keep_wait.py"}
for name, f in strat_files.items():
    chk(f"策略檔案: {name}", os.path.exists(f))
doc_all = readf("使用手冊.md") + readf("策略說明.md")
for name in list(strat_files) + ["auto"]:
    chk(f"文件提及策略: {name}", name in doc_all)

print("═" * 60)
print("結果:", "✅ 全部通過" if ok else "❌ 有項目未通過")
