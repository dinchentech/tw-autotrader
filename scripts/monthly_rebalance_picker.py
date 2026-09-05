#!/usr/bin/env python3
"""scripts/monthly_rebalance_picker.py — 每月換股選股工具（固定程式）

用法:
  python scripts/monthly_rebalance_picker.py --risk high_profit
  python scripts/monthly_rebalance_picker.py --risk normal
  python scripts/monthly_rebalance_picker.py --risk high_profit --strategy auto  # 每檔用自動感知
  python scripts/monthly_rebalance_picker.py --risk normal --no-inst  # 關閉法人確認

行為:
  - 只用「當時市值前 N」誠實池（歷史股本×當季股價重建，無倖存者偏差）。
  - 選股僅用「截至當下」資料（無事後之明）。
  - 使用者只選 高獲利(high_profit) / 正常(normal) 兩種風險。
  - 輸出: 目前持股 vs 新選股 → 建議賣出 / 維持 / 買入；每檔標的給「原固定策略」與「auto 自動感知」兩種建議，
    並輸出可直接貼進 .env 的 PC_<代號>=... 設定列。
"""
import os, sys, json, argparse
from datetime import datetime
sys.path.insert(0, "/home/frank/tw-autotrader")
os.chdir("/home/frank/tw-autotrader")
import numpy as np, pandas as pd
from pathlib import Path
from core.cache_io import load_cache_or_raw
import core.inst_strategy_core as ic
import scripts.stock_selector_grid as ssg
from strategies.auto_sensing import route_strategy, auto_sensing_strategy

GROUPS = {
    "high_profit": {"label": "高獲利(高風險)", "strats": ["ma_cross", "breakout"]},
    "normal": {"label": "正常", "strats": ["bollinger", "ma_cross", "vwap", "breakout"]},
}

LAST_PICK_FILE = os.getenv("MONTHLY_PICK_FILE", os.path.join("logs", "monthly_pick.json"))


# ── 載入誠實池與價量 ─────────────────────────────────────
def load_data(pool_n):
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
    hist_for_pool = {(sid, q): v for (sid, q), v in hist.items()}
    all_data_pool = {}
    for sid, df in data.items():
        d2 = df.reset_index()
        d2 = d2.rename(columns={d2.columns[0]: "date"})
        all_data_pool[sid] = d2
    pools = ic.build_quarterly_pool(hist_for_pool, all_data_pool, top_n=pool_n)
    return data, pools


def ma_pos(df, d, days=20):
    if d not in df.index:
        return None
    idx = df.index.get_loc(d)
    s = max(0, idx - days)
    ma = float(df.iloc[s:idx + 1]["close"].mean())
    cp = float(df.iloc[idx]["close"])
    return (cp - ma) / ma if ma > 0 else None


def vol(df, d, days=63):
    if d not in df.index:
        return None
    idx = df.index.get_loc(d)
    s = max(0, idx - days)
    px = df.iloc[s:idx + 1]["close"].values
    return float(np.std(px / np.mean(px))) if len(px) >= 5 else None


def snap(df, d):
    return ssg._snap_date(df, d)


# ── 人工降溫（過熱過濾）─────────────────────────────
# 門檻(env，可調)：MAX_PCT_FROM_HIGH=離52週高點%上限、MAX_YTD_GAIN=YTD漲幅%上限、
#                  MAX_PER=本益比上限、MIN_OVERHEAT=命中幾項才算過熱(預設2)
OV_PARAMS = {
    "max_from_high": float(os.getenv("MAX_PCT_FROM_HIGH", "7")),
    "max_ytd": float(os.getenv("MAX_YTD_GAIN", "100")),
    "max_per": float(os.getenv("MAX_PER", "45")),
    "min_count": int(os.getenv("MIN_OVERHEAT", "2")),
}
_PER_CACHE = {}
_DL = None


def _get_dl():
    global _DL
    if _DL is None:
        from FinMind.data import DataLoader
        _DL = DataLoader()
    return _DL


def _get_per(sid, sel_date):
    """FinMind TaiwanStockPER → 最近一筆 PER(≤sel_date)，快取；失敗回 None。"""
    if sid in _PER_CACHE:
        return _PER_CACHE[sid]
    per = None
    try:
        dl = _get_dl()
        end = pd.Timestamp(sel_date).strftime("%Y-%m-%d")
        start = (pd.Timestamp(sel_date) - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
        d = dl.taiwan_stock_per_pbr(stock_id=sid, start_date=start, end_date=end)
        if d is not None and len(d):
            d = d.copy()
            d["date"] = pd.to_datetime(d["date"])
            d = d[d["date"] <= pd.Timestamp(sel_date)].sort_values("date")
            per = float(d.iloc[-1]["PER"]) if len(d) else None
    except Exception:
        per = None
    _PER_CACHE[sid] = per
    return per


def overheat_flags(sid, sel_date):
    """回傳過熱旗標 dict(或 None)。過熱 = 近52週高點 + YTD 漲幅 + 高本益比。"""
    df = data.get(sid)
    if df is None:
        return None
    sd = snap(df, sel_date)
    if sd is None or sd not in df.index:
        return None
    idx = df.index.get_loc(sd)
    cp = float(df.loc[sd, "close"])
    if cp <= 0:
        return None
    win = df.iloc[max(0, idx - 251):idx + 1]
    hi = float(win["high"].max())
    pct_from_high = (hi - cp) / hi * 100 if hi > 0 else 0.0
    near_high = (hi > 0 and cp >= hi * (1 - OV_PARAMS["max_from_high"] / 100.0))
    ys = df[df.index <= pd.Timestamp(str(sd.year) + "-01-01")]
    ytd = (cp / float(ys.iloc[-1]["close"]) - 1) if len(ys) and float(ys.iloc[-1]["close"]) > 0 else 0.0
    huge_ytd = ytd > OV_PARAMS["max_ytd"] / 100.0
    per = _get_per(sid, sd) if (near_high or huge_ytd) else None  # 只在價量命中才抓PER(限流)
    high_pe = per is not None and per > OV_PARAMS["max_per"]
    cnt = int(near_high) + int(huge_ytd) + int(high_pe)
    return {"sid": sid, "near_high": near_high, "huge_ytd": huge_ytd, "high_pe": high_pe,
            "pct_from_high": round(pct_from_high, 1), "ytd": round(ytd * 100, 1),
            "per": per, "count": cnt, "overheated": cnt >= OV_PARAMS["min_count"]}


def is_overheated(sid, sel_date):
    f = overheat_flags(sid, sel_date)
    return bool(f and f["overheated"])


# ── 選股規則（與回測相同，無事後之明）────────────────────
def pick_high_profit(pool, sel_date, top_n, min_price, mom_days, inst_ok):
    cands = []
    for sid in pool:
        df = data.get(sid)
        if df is None:
            continue
        sd = snap(df, sel_date)
        if sd is None or sd not in df.index:
            continue
        cp = float(df.loc[sd, "close"])
        if cp < min_price:
            continue
        idx = df.index.get_loc(sd)
        ref = float(df.iloc[max(0, idx - mom_days)]["close"])
        r = (cp / ref - 1) if ref > 0 else None
        mp = ma_pos(df, sd, 20)
        if r is None or mp is None or mp < 0:
            continue
        if not inst_ok(sid):
            continue
        if is_overheated(sid, sel_date):   # 人工降溫：過熱(近52週高+高本益比+大漲) → 剔除
            continue
        cands.append((sid, r))
    cands.sort(key=lambda x: -x[1])
    return [s for s, _ in cands[:top_n]]


def pick_normal(pool, sel_date, top_n, inst_ok):
    scored = []
    for sid in pool:
        df = data.get(sid)
        if df is None:
            continue
        sd = snap(df, sel_date)
        if sd is None or sd not in df.index:
            continue
        if not inst_ok(sid):
            continue
        s = ssg.score_stock(sid, df, sd, dict(ssg.DEFAULT_PARAMS))
        if s is None:
            continue
        if is_overheated(sid, sel_date):   # 人工降溫：過熱 → 剔除
            continue
        scored.append(s)
    scored.sort(key=lambda x: -x["total"])
    return [s["symbol"] for s in scored[:top_n]]


PICKERS = {"high_profit": pick_high_profit, "normal": pick_normal}


# ── 讀目前持股（.env 的 PC_ 條目）──────────────────────
def read_current_holdings():
    holdings = {}
    env_path = Path(os.getenv("DOTENV_PATH", ".env"))
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("PC_") and "=" in s:
                sym = s[3:].split("=", 1)[0]
                val = s.split("=", 1)[1]
                if "#" in val:                 # 去除行內註解（.env 常帶 # 註解→會破壞 JSON）
                    val = val.split("#", 1)[0].strip()
                try:
                    cfg = json.loads(val)
                    holdings[sym] = cfg
                except Exception:
                    holdings[sym] = {"strategy": "?"}
    return holdings


# ── 讀實際持倉（logs/holdings.json 中 qty>0 = 已持倉）────────
def read_actual_holdings():
    hp = Path("logs/holdings.json")
    held = {}
    if hp.exists():
        try:
            data_h = json.loads(hp.read_text(encoding="utf-8"))
            for sid, h in data_h.items():
                if isinstance(h, dict) and h.get("qty", 0) > 0:
                    held[sid] = int(h["qty"])
        except Exception:
            pass
    return held


def main():
    p = argparse.ArgumentParser(description="每月換股選股工具（高獲利/正常）")
    p.add_argument("--risk", choices=["high_profit", "normal"], default="high_profit")
    p.add_argument("--pool-n", type=int, default=100)
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--min-price", type=float, default=5)
    p.add_argument("--mom-days", type=int, default=63)
    p.add_argument("--no-inst", action="store_true", help="關閉法人確認")
    p.add_argument("--inst-days", type=int, default=15)
    p.add_argument("--strategy", choices=["auto", "fixed"], default="auto",
                   help="每檔建議策略: auto=自動感知 / fixed=該組原固定池")
    p.add_argument("--as-of", default=None, help="選股基準日 YYYY-MM-DD（預設=最新交易日）")
    args = p.parse_args()

    global data
    data, pools = load_data(args.pool_n)

    # 基準日：最新交易日 ≤ as_of
    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
    else:
        as_of = pd.Timestamp.now()
    all_days = sorted({d for df in data.values() for d in df.index if pd.Timestamp(d) <= as_of})
    sel_date = all_days[-1] if all_days else as_of
    print(f"📅 選股基準日: {pd.Timestamp(sel_date).strftime('%Y-%m-%d')}  (資料: up to 當下, 無前瞻)")

    # 法人確認
    inst = None
    if not args.no_inst:
        inst = ssg.load_twse_inst_merged()
        from bisect import bisect_right
        dates = sorted(pd.Timestamp(d) for d in inst)
        idx = bisect_right(dates, sel_date)
        recent = dates[max(0, idx - args.inst_days):idx]
        acc = {}
        for ts in recent:
            for sid2, (b, s) in inst[ts.strftime("%Y-%m-%d")].items():
                acc[sid2] = acc.get(sid2, 0) + (b - s)
        net = pd.Series(acc)
        def inst_ok(sid):
            v = net.get(sid)
            return v is None or v > 0
    else:
        def inst_ok(sid):
            return True

    # 候選池（該季點 ≤ as_of）
    cand_pool = [q for q in sorted(pools) if pd.Timestamp(q + "-01").to_period("M").end_time <= sel_date]
    pool = pools[cand_pool[-1]] if cand_pool else []
    print(f"候選池: 當時市值前 {args.pool_n} 大（{len(pool)} 檔）")

    if args.risk == "high_profit":
        selected = pick_high_profit(pool, sel_date, args.top_n, args.min_price, args.mom_days, inst_ok)
    else:
        selected = pick_normal(pool, sel_date, args.top_n, inst_ok)

    current = read_current_holdings()      # .env PC_ 監控/設定中
    held = set(read_actual_holdings())     # logs/holdings.json 實際持倉(qty>0)
    sel_set = set(selected)
    # 規則：已持倉→不動（保留）；監控中未持倉且未再選中→汰換；新選中未持倉→買入
    # keep_wait=全輪替腿，不列入汰換（由輪替引擎自己管理）
    sell = sorted([s for s in current if s not in held and s not in sel_set
                   and current[s].get('strategy') != 'keep_wait'])
    keep = sorted(held)                    # 已持倉一律保留（即使掉出選股）
    buy = sorted([s for s in selected if s not in held])

    print(f"\n[{GROUPS[args.risk]['label']}] 選股完成 → 賣出/維持/買入")
    print(f"  🟢 賣出(汰換未持倉且未選中): {sell or '無'}")
    print(f"  🟡 維持(已持倉, 不動): {keep or '無'}")
    print(f"  🔵 買入(新選中未持倉): {buy or '無'}")

    # 每檔: 原固定策略建議 + 用 auto_sensing 路由看當下型態 + 過熱旗標
    print("\n📌 建議策略（'fixed'=原固定池, 'auto'=型態感知自動分派）")
    table = []
    ov_flags = []
    for i, sid in enumerate(selected):
        df = data.get(sid)
        fixed = GROUPS[args.risk]["strats"][i % len(GROUPS[args.risk]["strats"])]
        routed = route_strategy(df, sel_date) if df is not None else "ma_cross"
        name = ssg.POOL_LABELS.get(sid, "")
        sd = snap(df, sel_date) if df is not None else None
        px = float(df.loc[sd, "close"]) if sd is not None else 0.0
        table.append((sid, name, px, fixed, routed))
        ov = overheat_flags(sid, sel_date)
        ov_flags.append((sid, name, ov))
        ov_mark = ""
        if ov:
            parts = []
            if ov["near_high"]: parts.append(f"貼近52週高({ov['pct_from_high']}%)")
            if ov["huge_ytd"]: parts.append(f"YTD+{ov['ytd']}%")
            if ov["high_pe"]: parts.append(f"P/E{ov['per']:.0f}")
            if parts: ov_mark = "  ⚠️ 偏高:" + ",".join(parts)
        print(f"  {sid:>6} {name:<8} NT${px:>8,.0f}  fixed={fixed:<10} auto→{routed}{ov_mark}")

    # 過熱/偏高摘要：列出「被過熱排除」與「選中但偏高(任一旗標)」
    _warned = []
    for sid, name, ov in ov_flags:
        if ov and (ov["near_high"] or ov["huge_ytd"] or ov["high_pe"]):
            _warned.append(f"{sid} {name}(近高{ov['pct_from_high']}% / YTD+{ov['ytd']}% / P/E{ov['per']:.0f})")
    if _warned:
        print(f"\n⚠️ 【人工降溫】選中但偏高（近52週高 / YTD 大漲 / 高本益比，命中任一）：")
        for w in _warned:
            print("   ", w)
    print(f"   (設定: 近52週高上限 {OV_PARAMS['max_from_high']}% / YTD 上限 {OV_PARAMS['max_ytd']}% / P/E 上限 {OV_PARAMS['max_per']} / 命中 {OV_PARAMS['min_count']} 項即剔除)")

    # 輸出 PC_ 設定（貼進 .env）
    chosen = args.strategy
    alloc = round(100.0 / max(1, len(selected)), 1)
    print(f"\n📝 可貼進 .env 的 PC_ 設定（strategy={chosen}, 每檔 alloc={alloc}%）：")
    for sid, name, px, fixed, routed in table:
        strat = chosen if chosen == "auto" else fixed
        line = {'strategy': strat, 'alloc': alloc, 'max_entry_price': round(px, 2)}
        print(f"PC_{sid}={json.dumps(line, separators=(',', ':'))}")
    print("\n💡 strategy=auto 表示該股套用『型態感知自動分派』（strategies/auto_sensing.py，每天開盤前/收盤後計算）。")
    print("   fixed 表示沿用該組固定策略池。alloc 為建議等權資金比例，你可自行調整。")

    # ── 記錄本次建議 + 與上次比對 ──
    record = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "risk": args.risk, "risk_label": GROUPS[args.risk]["label"],
        "as_of": str(sel_date), "strategy_mode": args.strategy,
        "pool_n": args.pool_n, "top_n": args.top_n,
        "inst_days": (0 if args.no_inst else args.inst_days),
        "selected": [{"sid": sid, "name": name, "price": round(px, 2), "fixed": fixed, "auto": routed}
                     for sid, name, px, fixed, routed in table],
        "sell": sell, "keep": keep, "buy": buy, "current": list(current),
    }
    pc_lines = []
    for sid, name, px, fixed, routed in table:
        strat = chosen if chosen == "auto" else fixed
        line = {"strategy": strat, "alloc": alloc, "max_entry_price": round(px, 2)}
        pc_lines.append(f"PC_{sid}={json.dumps(line, separators=(',', ':'))}")
    record["pc_config"] = pc_lines

    prev = None
    if os.path.exists(LAST_PICK_FILE):
        try:
            prev = json.load(open(LAST_PICK_FILE, encoding="utf-8"))
        except Exception:
            prev = None
    if prev:
        p_sids = {x["sid"] for x in prev.get("selected", [])}
        n_sids = {x["sid"] for x in record["selected"]}
        added, removed, same = sorted(n_sids - p_sids), sorted(p_sids - n_sids), sorted(n_sids & p_sids)
        print(f"\n🔄 上次建議（{prev.get('generated_at', '?')}） vs 本次：")
        print(f"  新增: {added or '無'} | 移除: {removed or '無'} | 維持: {same or '無'}")
        for sid in same:
            pr = next((y["auto"] for y in prev["selected"] if y["sid"] == sid), None)
            nr = next((y["auto"] for y in record["selected"] if y["sid"] == sid), None)
            if pr != nr:
                print(f"    {sid} auto 策略: {pr} → {nr}")

    os.makedirs(os.path.dirname(LAST_PICK_FILE) or ".", exist_ok=True)
    with open(LAST_PICK_FILE, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"\n💾 已記錄本次建議 → {LAST_PICK_FILE}")


if __name__ == "__main__":
    main()
