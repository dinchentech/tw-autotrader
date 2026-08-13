"""全輪替歷史池回測（消除倖存者偏差）— 2026-08-11 建立

用法: python scripts/backtest_rotation_historical.py <start> <end> [pool_n] [top_n]
例:   python scripts/backtest_rotation_historical.py 2015-01-01 2021-12-31 150 4
評分參數覆寫(環境變數): MW=momentum_weight TW=technical_weight SW=stability_weight MAF=use_ma_filter MP=min_price

以 historical_shares.pkl（今天前 300 大的歷史股本）重建「逐季當時市值前 N」候選池，
取代 stock_selector_grid 原生的固定池（今天市值排名，含倖存者偏差）。
回測設定與實盤一致: ROTATE=5 雙排程各半、每排程 4 檔、auto_momentum（0050 年線斜率切 21d/63d）、計入交易成本。
"""
import os, sys, json
sys.path.insert(0, "/home/frank/tw-autotrader")
os.chdir("/home/frank/tw-autotrader")
import pandas as pd
from core.cache_io import load_cache_or_raw
import core.inst_strategy_core as ic
sys.path.insert(0, "scripts")
import stock_selector_grid as ssg

START, END = sys.argv[1], sys.argv[2]
POOL_N = int(sys.argv[3]) if len(sys.argv) > 3 else 150
TOP_N = int(sys.argv[4]) if len(sys.argv) > 4 else 4
ssg.START_DATE = START
ssg.END_DATE = END

hist, _ = load_cache_or_raw("cache/inst_momentum/historical_shares.pkl")
union = sorted({k[0] for k in hist})
print(f"聯集池 {len(union)} 檔, 逐季前 {POOL_N}")

# 載入價格(selector 快取, yfinance auto_adjust=True)
data = {}
for sid in union:
    df = ssg.load_stock(sid)
    if not df.empty and len(df) > 60:
        data[sid] = df
print(f"價格載入: {len(data)} 檔")

# 逐季池(用 selector 的價格 df: index=date)
hist_for_pool = {(sid, q): v for (sid, q), v in hist.items()}
# build_quarterly_pool 需 df["date"] 欄位; selector df 是 date index → 轉換
all_data_pool = {}
for sid, df in data.items():
    d2 = df.reset_index()
    d2 = d2.rename(columns={d2.columns[0]: "date"})
    all_data_pool[sid] = d2
pools = ic.build_quarterly_pool(hist_for_pool, all_data_pool, top_n=POOL_N)
empty = sum(1 for p in pools.values() if not p)
print(f"逐季池: {len(pools)} 季, 空池 {empty} 季")

# 0050 市場資料(auto_momentum)
mkt = ssg.load_stock("0050")
mkt = mkt.rename(columns={"close": "close"}) if "close" not in mkt.columns else mkt

params = dict(ssg.DEFAULT_PARAMS)
if os.getenv("MW"): params["momentum_weight"] = float(os.getenv("MW"))
if os.getenv("TW"): params["technical_weight"] = float(os.getenv("TW"))
if os.getenv("SW"): params["stability_weight"] = float(os.getenv("SW"))
if os.getenv("MAF"): params["use_ma_filter"] = os.getenv("MAF") == "1"
if os.getenv("MP"): params["min_price"] = float(os.getenv("MP"))
mode = os.getenv("MODE", "momentum")
auto_mom = os.getenv("AUTO", "1") == "1"
if os.getenv("MOM_DAYS"):
    params["momentum_days"] = int(os.getenv("MOM_DAYS"))

# 法人確認濾網（B 方案）：INST_CONFIRM=1 啟用，INST_DAYS 控制回溯交易日
inst_conf = None
if os.getenv("INST_CONFIRM") == "1":
    inst_conf = ssg.load_twse_inst_merged()
    covered = sorted(inst_conf.keys())
    print(f"法人確認啟用: {len(covered)} 交易日 ({covered[0]} ~ {covered[-1]})；2015-2017 前段 pass-through")
inst_days = int(os.getenv("INST_DAYS", "21"))

bt = ssg.backtest_dual_quarterly(data, params, top_n=TOP_N, mode=mode,
                                 auto_momentum=auto_mom, market_data=mkt,
                                 qm_a=(2, 5, 8, 11), qm_b=(3, 6, 9, 12),
                                 quarterly_pool=pools,
                                 inst_conf=inst_conf, inst_days=inst_days)
import math
years = (pd.Timestamp(END) - pd.Timestamp(START)).days / 365.25
ann = (bt["total_return"] + 1) ** (1 / years) - 1 if bt["total_return"] > -1 else -1
print(json.dumps({"pool_n": POOL_N, "top_n": TOP_N, "final_value": round(bt["final_value"]),
                   "total_return": round(bt["total_return"], 4),
                   "annualized": round(ann, 4),
                   "yearly": {k: round(v["total_ret"], 4) for k, v in bt["yearly"].items()}},
                  ensure_ascii=False))
