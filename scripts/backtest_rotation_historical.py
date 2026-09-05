"""全輪替歷史池回測（消除倖存者偏差）— 2026-08-11 建立

用法: python scripts/backtest_rotation_historical.py <start> <end> [pool_n] [top_n]
例:   python scripts/backtest_rotation_historical.py 2015-01-01 2021-12-31 150 4
評分參數覆寫(環境變數): MW=momentum_weight TW=technical_weight SW=stability_weight MAF=use_ma_filter MP=min_price
其他: INST_CONFIRM=1 啟用法確認濾網（生產基線，預設停用）；INST_DAYS=法人回溯交易日(預設21)；
      MIN_DRAW_BACK=換股日總回撤門檻百分比(0=停用，>0 時該季不賣不買續抱、最多延長一季)

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
# MIN_DRAW_BACK：換股日總回撤超標時該季不換股（0=停用，>0=門檻百分比）
min_drawback = float(os.getenv("MIN_DRAW_BACK", "0"))
# MIN_DRAW_BACK_UNLIMITED=1：無限期延後換股（回撤未恢復就一直續抱）；預設=最多延長一季
min_drawback_unlimited = os.getenv("MIN_DRAW_BACK_UNLIMITED", "0") == "1"
# MAX_PROFIT：提前獲利出場（比例制，0=停用）。持股價達買入價*(1+MAX_PROFIT/100) 即提前賣出、不等季末
max_profit = float(os.getenv("MAX_PROFIT", "0")) / 100.0

bt = ssg.backtest_dual_quarterly(data, params, top_n=TOP_N, mode=mode,
                                 auto_momentum=auto_mom, market_data=mkt,
                                 qm_a=(2, 5, 8, 11), qm_b=(3, 6, 9, 12),
                                 quarterly_pool=pools,
                                 inst_conf=inst_conf, inst_days=inst_days,
                                 min_drawback=min_drawback,
                                 min_drawback_unlimited=min_drawback_unlimited,
                                 max_profit=max_profit)
import math
years = (pd.Timestamp(END) - pd.Timestamp(START)).days / 365.25
ann = (bt["total_return"] + 1) ** (1 / years) - 1 if bt["total_return"] > -1 else -1


# ── 日頻權益曲線重建（供 Sharpe / MDD 計算）─────────────────────
def schedule_daily_curve(records, data, commission=ssg.COMMISSION_RATE, initial=500000.0):
    """依每季 records 重建單一排程的日頻帳戶價值曲線（含交易成本）。

    backtest_selector 的 records[i] = {date: 選股日 q_i, holdings: 本季持股,
    value: 下個季末賣出後的帳戶價值}——所以 record i 的「部署資本」是
    前一筆 record 的 value（i=0 為 initial），segment 涵蓋 [q_i, q_{i+1})，
    季末以次筆 value 為稅後基準；最後一筆 record 直接取官方終值。
    段內多檔同日期先 groupby 加總；換股日 snap 早於季末日期時，
    重疊日以新股持倉為準（keep=last），與回測「同日賣舊買新」一致。
    """
    segs = []
    for i, rec in enumerate(records):
        qd, chosen = rec["date"], rec["holdings"]
        if i == len(records) - 1:
            segs.append(pd.Series({qd: rec["value"]}))
            continue
        nxt = records[i + 1]["date"]
        capital = records[i - 1]["value"] if i > 0 else initial
        alloc = capital / len(chosen) if chosen else 0.0
        parts = []
        for sym in chosen:
            if sym not in data:
                continue
            df = data[sym]
            buy_date = ssg._snap_date(df, qd)
            if buy_date is None:
                continue
            buy_px = float(df.loc[buy_date, "close"])
            if buy_px <= 0:
                continue
            shares = alloc / (buy_px * (1 + commission))
            sub = df.loc[buy_date:nxt, "close"] * shares
            sub = sub[sub.index < nxt]
            parts.append(sub)
        if parts:
            segs.append(pd.concat(parts).groupby(level=0).sum())
    if not segs:
        return pd.Series(dtype=float)
    curve = pd.concat(segs).sort_index()
    return curve[~curve.index.duplicated(keep="last")]


def benchmark_curve(mkt, start, end, capital=500000.0):
    """0050 買入持有（與策略同資料源/同區間，yfinance auto_adjust=True 含息）。

    2026-08-24 起公平扣除費用：
    - 買入手續費 0.1425%（一次）
    - 管理費 ~0.32%/年（逐交易日複利扣除）
    - 賣出手續費 0.1425% + 證交稅 0.1%（ETF 稅率，一次）
    """
    idx = mkt.index[(mkt.index >= pd.Timestamp(start)) & (mkt.index <= pd.Timestamp(end))]
    if len(idx) == 0:
        return pd.Series(dtype=float)
    t0 = idx[0]
    b0 = float(mkt.loc[t0, "close"])
    curve = mkt.loc[idx, "close"] * (capital / b0)
    curve = curve * (1 - ssg.COMMISSION_RATE)
    daily_fee = 0.0032 / 252.0
    curve = curve * ((1 - daily_fee) ** __import__("numpy").arange(len(curve)))
    curve = curve * (1 - ssg.COMMISSION_RATE - ssg.ETF_TAX)
    return curve


def sharpe_mdd(curve, rf=0.0, periods=252):
    """年化 Sharpe（日頻, rf=0 預設）與最大回撤（負值）。"""
    curve = curve.dropna()
    rets = curve.pct_change().dropna()
    if len(rets) < 3:
        return None, None
    ex = rets - rf / periods
    sd = ex.std(ddof=1)
    sharpe = float(ex.mean() / sd * math.sqrt(periods)) if sd > 0 else float("nan")
    run_max = curve.cummax()
    mdd = float(((curve - run_max) / run_max).min())
    return sharpe, mdd


def yearly_from_curve(curve):
    return {int(yr): float(grp.iloc[-1] / grp.iloc[0] - 1)
            for yr, grp in curve.groupby(curve.index.year)}


# 組合曲線 = 兩排程各 500k 帳戶的平均（與 final_val=(A+B)/2 語義一致）
ca = schedule_daily_curve(bt.get("records_a", []), data)
cb = schedule_daily_curve(bt.get("records_b", []), data)
idx = ca.index.union(cb.index)


def padded(s, idx, initial=500000.0):
    """對齊到共同日期軸：起始前視為現金 initial，之後 ffill 續抱（含尾部）。"""
    if len(s) == 0:
        return pd.Series(initial, index=idx)
    r = s.reindex(idx)
    r.loc[r.index < s.index[0]] = initial
    return r.ffill()


comb = (padded(ca, idx) + padded(cb, idx)) / 2.0
comb = comb.loc[comb.first_valid_index():].ffill().dropna()
bench = benchmark_curve(mkt, START, END)

sharpe, mdd = sharpe_mdd(comb)
b_sharpe, b_mdd = sharpe_mdd(bench)
comb_yearly = yearly_from_curve(comb)
bench_yearly = yearly_from_curve(bench)
bench_ann = (bench.iloc[-1] / 500000.0) ** (1 / years) - 1

# 存檔供稽核（日頻權益曲線）
import os
os.makedirs("results", exist_ok=True)
pd.DataFrame({"equity_rotate5": comb, "equity_0050": bench.reindex(comb.index).ffill()}) \
    .to_csv("results/rotate_mode5_2015_2025_daily_equity.csv")

def skipped_dates(records):
    return [r["date"].strftime("%Y-%m-%d") for r in records if r.get("skipped")]

print(json.dumps({"pool_n": POOL_N, "top_n": TOP_N, "min_drawback": min_drawback,
                   "min_drawback_unlimited": min_drawback_unlimited,
                   "final_value": round(bt["final_value"]),
                   "total_return": round(bt["total_return"], 4),
                   "annualized": round(ann, 4),
                   "sharpe_annualized": round(sharpe, 2) if sharpe is not None else None,
                   "max_drawdown": round(mdd, 4) if mdd is not None else None,
                   "skipped_quarters": {"A": skipped_dates(bt.get("records_a", [])),
                                        "B": skipped_dates(bt.get("records_b", []))},
                   "benchmark_0050": {"final_value": round(bench.iloc[-1]),
                                      "annualized": round(bench_ann, 4),
                                      "sharpe_annualized": round(b_sharpe, 2) if b_sharpe is not None else None,
                                      "max_drawdown": round(b_mdd, 4) if b_mdd is not None else None},
                   "yearly": {k: round(v["total_ret"], 4) for k, v in bt["yearly"].items()},
                   "yearly_curve": {k: round(v, 4) for k, v in comb_yearly.items()},
                   "benchmark_yearly_curve": {k: round(v, 4) for k, v in bench_yearly.items()}},
                  ensure_ascii=False))
