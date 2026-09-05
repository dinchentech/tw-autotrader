"""方案二改「每月換股」+ 三組獨立選股策略回測（2022-2025, NT$500,000 單筆）— 訊號執行版

用法: python scripts/backtest_plan2_monthly_3group.py
環境覆寫: START END POOL_N TOP_N INITIAL MIN_PRICE MOM_DAYS

設計（誠實、無事後之明、依使用者修正）:
- 候選池 = 誠實池：每季以「當時市價 × 歷史股本」重建當時市值前 POOL_N 大（無倖存者偏差）。
- 每月換股：月初選股（僅用「上個月最後交易日」及以前資料），
  **選定即買入**（等權分配當下可用資金）；持股「依策略訊號進出」——
  賣出訊號(-1) 才會出場，**不做月底強制平倉**。
- 月內賣出空出的資金回到該股 bucket；當月被剔除（deselect）的股票的 bucket 併回現金池，
  於**下個月重新選股**時分配給新選標的。
- 三組 = 三套獨立選股規則（各有不同策略池），各跑一次完整回測。
- 計入交易成本：手續費 0.1425% + 證交稅 0.3%（ETF 0.1%）。
- 每月最多 TOP_N 檔（預設 5，≤10 限制內）。
"""
import os, sys, json as _json, math
sys.path.insert(0, "/home/frank/tw-autotrader")
os.chdir("/home/frank/tw-autotrader")
import pandas as pd, numpy as np
from core.cache_io import load_cache_or_raw
import core.inst_strategy_core as ic
import scripts.stock_selector_grid as ssg
from strategies.bollinger import bollinger_reverse_strategy
from strategies.ma_cross import ma_cross_strategy
from strategies.vwap_deviation import vwap_deviation_strategy
from strategies.breakout import breakout_strategy

START = os.getenv("START", "2022-01-01")
END = os.getenv("END", "2025-12-31")
POOL_N = int(os.getenv("POOL_N", "100"))
TOP_N = int(os.getenv("TOP_N", "5"))
INITIAL = float(os.getenv("INITIAL", "500000"))
MIN_PRICE = float(os.getenv("MIN_PRICE", "5"))
MOM_DAYS = int(os.getenv("MOM_DAYS", "63"))
COMMISSION = ssg.COMMISSION_RATE
# ── 方案三濾網（可選）──────────────────────────────────
INST_CONFIRM = os.getenv("INST_CONFIRM", "1") == "1"   # 法人確認：近 N 日法人淨買超 > 0 才入選
INST_DAYS = int(os.getenv("INST_DAYS", "15"))
MIN_DRAW_BACK = float(os.getenv("MIN_DRAW_BACK", "30"))  # 股災防護：選股日總回撤 > N% 則該月不換股（續抱）
MDB_UNLIMITED = os.getenv("MDB_UNLIMITED", "0") == "1"   # 1=無限延長(>門檻就一直續抱)；0=最多延長一輪
STRAT_MODE = os.getenv("STRAT_MODE", "group")            # group=策略綁組別；form=依個股型態自適應(四種開放)
SWAP_MODE = os.getenv("SWAP_MODE", "full")               # full=每月掉出前N就賣(現狀)；addonly=只依訊號出場、不強賣仍持的(C)

GROUPS = {
    "high_profit": {"label": "高獲利(高風險)", "strats": ["ma_cross", "breakout"]},
    "normal":      {"label": "正常",          "strats": ["bollinger", "ma_cross", "vwap", "breakout"]},
    "stable":      {"label": "高穩定(低風險)", "strats": ["bollinger", "vwap"]},
}

STRAT_FUNCS = {
    "bollinger": bollinger_reverse_strategy,
    "ma_cross": ma_cross_strategy,
    "vwap": vwap_deviation_strategy,
    "breakout": breakout_strategy,
}


# ── 載入資料 ─────────────────────────────────────────────
hist, _ = load_cache_or_raw("cache/inst_momentum/historical_shares.pkl")
union = sorted({k[0] for k in hist})
data = {}
for sid in union:
    df = ssg.load_stock(sid)
    if df is None or df.empty:
        continue
    df = df.dropna(subset=["close"])
    if len(df) > 60:
        data[sid] = df
print(f"價格載入: {len(data)} 檔 (聯集池 {len(union)})")

hist_for_pool = {(sid, q): v for (sid, q), v in hist.items()}
all_data_pool = {}
for sid, df in data.items():
    d2 = df.reset_index()
    d2 = d2.rename(columns={d2.columns[0]: "date"})
    all_data_pool[sid] = d2
pools = ic.build_quarterly_pool(hist_for_pool, all_data_pool, top_n=POOL_N)
print(f"逐季池: {len(pools)} 季點, 空池 {sum(1 for p in pools.values() if not p)}")

# 法人確認資料（可選）
inst_conf = None
INST_CONFDATES = []
if INST_CONFIRM:
    inst_conf = ssg.load_twse_inst_merged()
    INST_CONFDATES = sorted(pd.Timestamp(d) for d in inst_conf)
    print(f"法人確認啟用: {len(INST_CONFDATES)} 交易日, DAYS={INST_DAYS}")

# 全期交易日曆（取 0050 為基準，並涵蓋全部資料日）
_mkt0full = ssg.load_stock("0050").dropna(subset=["close"])
FULLCAL = sorted(set(_mkt0full.index))          # 完整日曆（含 2022 前，供選股日查詢）
_mkt0 = _mkt0full[(_mkt0full.index >= pd.Timestamp(START)) & (_mkt0full.index <= pd.Timestamp(END))]
MASTER = sorted(set(_mkt0.index))
ALL_DATES = sorted(set(
    d for df in data.values() for d in df.index
    if pd.Timestamp(START) <= d <= pd.Timestamp(END)
))
MONTH_STARTS = {}
for d in ALL_DATES:
    ym = (d.year, d.month)
    if ym not in MONTH_STARTS:
        MONTH_STARTS[ym] = d
MONTH_START_SET = set(MONTH_STARTS.values())


def pool_for_date(d):
    cand = [q for q in sorted(pools) if pd.Timestamp(q + "-01").to_period("M").end_time <= d]
    return pools[cand[-1]] if cand else []


# ── 技術工具（只用 ≤ 指定日期的資料）────────────────────────
def snap(df, d):
    return ssg._snap_date(df, d)


def trailing_ret(df, d, days):
    if d not in df.index:
        return None
    idx = df.index.get_loc(d)
    s = max(0, idx - days)
    sp = float(df.iloc[s]["close"]); ep = float(df.iloc[idx]["close"])
    return (ep - sp) / sp if sp > 0 else None


def vol(df, d, days=63):
    if d not in df.index:
        return None
    idx = df.index.get_loc(d)
    s = max(0, idx - days)
    px = df.iloc[s:idx + 1]["close"].values
    return float(np.std(px / np.mean(px))) if len(px) >= 5 else None


def ma_pos(df, d, days=20):
    if d not in df.index:
        return None
    idx = df.index.get_loc(d)
    s = max(0, idx - days)
    ma = float(df.iloc[s:idx + 1]["close"].mean()); cp = float(df.iloc[idx]["close"])
    return (cp - ma) / ma if ma > 0 else None


def inst_ok(sid, sel_date):
    """法人確認濾網：近 INST_DAYS 法人累計淨買超 > 0。None（未知）→ pass-through。
    每個選股日只算一次全市場向量並快取；各股查表。"""
    if not INST_CONFIRM:
        return True
    import bisect
    key = pd.Timestamp(sel_date)
    if key not in _INST_NET_CACHE:
        idx = bisect.bisect_right(INST_CONFDATES, key)
        recent = INST_CONFDATES[max(0, idx - INST_DAYS):idx]
        acc = {}
        for ts in recent:
            row = inst_conf[ts.strftime("%Y-%m-%d")]
            for sid2, (b, s) in row.items():
                acc[sid2] = acc.get(sid2, 0) + (b - s)
        _INST_NET_CACHE[key] = pd.Series(acc) if acc else pd.Series(dtype=float)
    ser = _INST_NET_CACHE[key]
    net = ser.get(sid)
    return net is None or net > 0


_INST_NET_CACHE = {}


# ── 三組選股規則 ─────────────────────────────────────────
def pick_high_profit(pool, sel_date):
    cands = []
    for sid in pool:
        df = data.get(sid)
        if df is None:
            continue
        sd = snap(df, sel_date)
        if sd is None or sd not in df.index:
            continue
        cp = float(df.loc[sd, "close"])
        if cp < MIN_PRICE:
            continue
        r = trailing_ret(df, sd, MOM_DAYS)
        mp = ma_pos(df, sd, 20)
        if r is None or mp is None or mp < 0:
            continue
        if not inst_ok(sid, sel_date):
            continue
        cands.append((sid, r))
    cands.sort(key=lambda x: -x[1])
    return [s for s, _ in cands[:TOP_N]]


def pick_normal(pool, sel_date):
    scored = []
    for sid in pool:
        df = data.get(sid)
        if df is None:
            continue
        sd = snap(df, sel_date)
        if sd is None or sd not in df.index:
            continue
        if not inst_ok(sid, sel_date):
            continue
        s = ssg.score_stock(sid, df, sd, dict(ssg.DEFAULT_PARAMS))
        if s is None:
            continue
        scored.append(s)
    scored.sort(key=lambda x: -x["total"])
    return [s["symbol"] for s in scored[:TOP_N]]


def pick_stable(pool, sel_date):
    cands = []
    for sid in pool:
        df = data.get(sid)
        if df is None:
            continue
        sd = snap(df, sel_date)
        if sd is None or sd not in df.index:
            continue
        cp = float(df.loc[sd, "close"])
        if cp < MIN_PRICE:
            continue
        v = vol(df, sd, 63)
        mp200 = ma_pos(df, sd, 200)
        if v is None or mp200 is None or mp200 < 0:
            continue
        if not inst_ok(sid, sel_date):
            continue
        cands.append((sid, v))
    cands.sort(key=lambda x: x[1])
    return [s for s, _ in cands[:TOP_N]]


PICKERS = {"high_profit": pick_high_profit, "normal": pick_normal, "stable": pick_stable}


# ── 訊號快取（全期一次算，rolling 皆回看歷史 → 無未來函數）──
_SIG = {}
_ROLL = {}
_STRATS = set(s for s in STRAT_FUNCS)


def _roll(sid):
    if sid not in _ROLL:
        df = data[sid]
        r = df.reindex(ALL_DATES)
        r["close"] = r["close"].ffill()
        _ROLL[sid] = r
    return _ROLL[sid]


def sig_at(sid, strat, d):
    if (sid, strat) not in _SIG:
        df = data[sid]
        _SIG[(sid, strat)] = STRAT_FUNCS[strat](df)["signal"].reindex(ALL_DATES).ffill().fillna(0)
    return int(_SIG[(sid, strat)].get(d, 0))


def close_at(sid, d):
    r = _roll(sid)
    return float(r.loc[d, "close"]) if d in r.index else 0.0


def strat_for(group, idx):
    return GROUPS[group]["strats"][idx % len(GROUPS[group]["strats"])]


def pick_strategy_by_form(sid, sel_date):
    """依個股當下型態自適應選策略（四種全開放，只用 ≤ 選股日資料）。
    型態=趨勢/盤整，選順勢(ma_cross/breakout)或回歸(bollinger/vwap)。
    """
    df = data.get(sid)
    if df is None:
        return "ma_cross"
    sd = snap(df, sel_date)
    if sd is None or sd not in df.index:
        return "ma_cross"
    idx = df.index.get_loc(sd)
    cp = float(df.loc[sd, "close"])
    ma20 = float(df.iloc[max(0, idx - 19):idx + 1]["close"].mean())
    ma60 = float(df.iloc[max(0, idx - 59):idx + 1]["close"].mean())
    mom20 = trailing_ret(df, sd, 20) or 0.0
    trend_up = (cp > ma20) and (ma20 > ma60) and (mom20 > 0)
    if trend_up:
        # 順勢：強勢(20d>5%)用突破，否則均線交叉
        return "breakout" if mom20 > 0.05 else "ma_cross"
    # 盤整/下跌 → 回歸：回檔超跌用布林(買低)，否則 VWAP
    return "bollinger" if cp < ma20 else "vwap"


def buy_cost(cash, px):
    return cash - cash * COMMISSION  # 實際可用於買股（預留手續費）


def sell_net(proceeds, sid):
    return proceeds * (1 - COMMISSION - ssg.tax_rate(sid))


def run_group(gkey):
    cash = INITIAL
    positions = {}   # sid -> {'strat': s, 'shares': float}
    bucket = {}      # sid -> 未投資的該股資金（可再進場）
    curve = {}
    selection_log = []
    peak = 0.0
    extended_once = False

    def equity(dts):
        e = cash + sum(bucket.values())
        for sid, p in positions.items():
            if p["shares"] > 0:
                e += p["shares"] * close_at(sid, dts)
        return e

    for d in ALL_DATES:
        dts = pd.Timestamp(d)

        # 日初權益（供股災防護回撤評估）
        eq0 = equity(dts)
        peak = max(peak, eq0)

        # ── 每月選股事件（月初第一個交易日）──
        if dts in MONTH_START_SET:
            # 股災防護：選股日總回撤 > MIN_DRAW_BACK% 時「最多延長一輪」續抱未換。
            # 邏輯同原版 backtest_selector：首次觸發才延長(extended_once)，下輪恢復正常換倉。
            skip = False
            if MIN_DRAW_BACK > 0 and peak > 0:
                dd = eq0 / peak - 1.0
                if dd < -MIN_DRAW_BACK / 100.0:
                    if MDB_UNLIMITED:
                        skip = True
                    elif not extended_once:
                        skip = True
                        extended_once = True
                    else:
                        extended_once = False
                else:
                    extended_once = False
            if skip:
                selection_log.append({"date": dts.strftime("%Y-%m-%d"), "S": None, "skipped": True})
            else:
                prior = [x for x in FULLCAL if x < dts]
                sel_date = prior[-1] if prior else None
                S = PICKERS[gkey](pool_for_date(sel_date), sel_date) if sel_date is not None else []
                selection_log.append({"date": dts.strftime("%Y-%m-%d"), "S": list(S), "skipped": False})

                # Drop（A=full）：剔除未再選入的持股 → 賣出並把 bucket 併回現金池。
                # C=addonly：不強制賣出「仍在持(shares>0)」的股票；只清理「已出場(flat)且不在新選股」的。
                if SWAP_MODE == "full":
                    for sid in list(positions.keys()):
                        if sid not in S:
                            sh = positions[sid]["shares"]
                            px = close_at(sid, dts)
                            if sh > 0 and px > 0:
                                bucket[sid] = bucket.get(sid, 0) + sell_net(sh * px, sid)
                            cash += bucket.pop(sid, 0.0)
                            del positions[sid]
                else:  # addonly (C)
                    for sid in list(positions.keys()):
                        if positions[sid]["shares"] == 0 and sid not in S:
                            cash += bucket.pop(sid, 0.0)
                            del positions[sid]

                # Add：新選入且未持有 → 用現金池等權分配本金。
                # C 只補到 TOP_N（active 未滿才加），不強制賣出/換出。
                new = [sid for sid in S if sid not in positions]
                if SWAP_MODE == "addonly":
                    active = sum(1 for s in positions if positions[s]["shares"] > 0)
                    new = new[:max(0, TOP_N - active)]
                if new and cash > 0:
                    alloc = cash / len(new)
                    for i, sid in enumerate(new):
                        px = close_at(sid, dts)
                        _st = pick_strategy_by_form(sid, sel_date) if STRAT_MODE == "form" else strat_for(gkey, i)
                        positions[sid] = {"strat": _st, "shares": 0.0}
                        bucket[sid] = alloc
                        cash -= alloc
                        if px > 0 and bucket[sid] > 5:
                            budget = bucket[sid]
                            bought = buy_cost(budget, px)
                            positions[sid]["shares"] = bought / px
                            bucket[sid] = 0.0

            # 記錄實際持有（代號＋策略）
            selection_log[-1]["holdings"] = [
                {"sid": s, "strat": positions[s]["strat"]} for s in positions
            ]

        # ── 逐日訊號進出 ──
        for sid in list(positions.keys()):
            px = close_at(sid, dts)
            if px <= 0:
                continue
            sig = sig_at(sid, positions[sid]["strat"], dts)
            sh = positions[sid]["shares"]
            if sh > 0 and sig == -1:
                proceeds = sell_net(sh * px, sid)
                bucket[sid] = bucket.get(sid, 0.0) + proceeds
                positions[sid]["shares"] = 0.0
            elif sh == 0 and sig == 1 and bucket.get(sid, 0.0) > 5:
                budget = bucket[sid]
                bought = buy_cost(budget, px)
                positions[sid]["shares"] = bought / px
                bucket[sid] = 0.0

        # ── 權益紀錄 ──
        curve[dts] = equity(dts)

    curve = pd.Series(curve).sort_index()
    return {"curve": curve, "final": curve.iloc[-1] if len(curve) else cash,
            "selection_log": selection_log}


# ── 0050 基準 ───────────────────────────────────────────
def benchmark(initial=INITIAL):
    df = _mkt0
    idx = df.index[(df.index >= pd.Timestamp(START)) & (df.index <= pd.Timestamp(END))]
    if len(idx) == 0:
        return pd.Series(dtype=float)
    t0 = idx[0]; b0 = float(df.loc[t0, "close"])
    curve = df.loc[idx, "close"] * (initial / b0)
    curve = curve * (1 - ssg.COMMISSION_RATE)
    daily = 0.0032 / 252.0
    curve = curve * ((1 - daily) ** np.arange(len(curve)))
    curve = curve * (1 - ssg.COMMISSION_RATE - ssg.ETF_TAX)
    return curve


def perf(curve):
    curve = curve.dropna()
    if len(curve) < 3:
        return None
    rets = curve.pct_change().dropna()
    sd = rets.std(ddof=1)
    sharpe = float(rets.mean() / sd * math.sqrt(252)) if sd and sd > 0 else float("nan")
    run_max = curve.cummax()
    mdd = float(((curve - run_max) / run_max).min())
    return {"sharpe": sharpe, "mdd": mdd}


def yearly(curve):
    if curve is None or len(curve) == 0:
        return {}
    return {int(yr): float(grp.iloc[-1] / grp.iloc[0] - 1)
            for yr, grp in curve.groupby(curve.index.year)}


def main():
    results = {}
    for gkey, meta in GROUPS.items():
        res = run_group(gkey)
        curve = res["curve"]
        years = (pd.Timestamp(END) - pd.Timestamp(START)).days / 365.25
        total = res["final"] / INITIAL - 1
        ann = (res["final"] / INITIAL) ** (1 / years) - 1 if total > -1 else -1
        p = perf(curve) or {}
        results[gkey] = {
            "label": meta["label"],
            "final_value": round(res["final"]),
            "total_return": round(total, 4),
            "annualized": round(ann, 4),
            "sharpe": round(p.get("sharpe", float("nan")), 2),
            "max_drawdown": round(p.get("mdd", float("nan")), 4),
            "yearly": {k: round(v, 4) for k, v in yearly(curve).items()},
            "selection_log": res["selection_log"],
        }
        curve.to_csv(f"results/daily_{gkey}.csv")
        print(f"\n[{meta['label']}] NT${INITIAL:,.0f} → NT${res['final']:,.0f}  "
              f"總報酬 {total:+.2%} 年化 {ann:+.2%} MDD {p.get('mdd', float('nan')):.2%} "
              f"夏普 {p.get('sharpe', float('nan')):.2f}")
        print("  年度:", {k: f"{v:+.2%}" for k, v in yearly(curve).items()})

    bench = benchmark()
    years = (pd.Timestamp(END) - pd.Timestamp(START)).days / 365.25
    b_total = bench.iloc[-1] / INITIAL - 1
    b_ann = (bench.iloc[-1] / INITIAL) ** (1 / years) - 1
    bp = perf(bench) or {}
    print(f"\n[0050 買進持有] NT${INITIAL:,.0f} → NT${bench.iloc[-1]:,.0f}  "
          f"總報酬 {b_total:+.2%} 年化 {b_ann:+.2%} MDD {bp.get('mdd', float('nan')):.2%} "
          f"夏普 {bp.get('sharpe', float('nan')):.2f}")

    out = {"start": START, "end": END, "initial": INITIAL, "pool_n": POOL_N, "top_n": TOP_N,
           "momentum_days": MOM_DAYS, "inst_confirm": INST_CONFIRM, "inst_days": INST_DAYS,
           "min_draw_back": MIN_DRAW_BACK, "strat_mode": STRAT_MODE, "swap_mode": SWAP_MODE,
           "groups": results,
           "benchmark_0050": {"final_value": round(bench.iloc[-1]), "total_return": round(b_total, 4),
                              "annualized": round(b_ann, 4), "sharpe": round(bp.get("sharpe", float("nan")), 2),
                              "max_drawdown": round(bp.get("mdd", float("nan")), 4)}}
    os.makedirs("results", exist_ok=True)
    with open("results/plan2_monthly_3group.json", "w", encoding="utf-8") as f:
        _json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n已存 results/plan2_monthly_3group.json")


if __name__ == "__main__":
    main()
