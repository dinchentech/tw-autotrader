"""
2022-2025 市值前100 × 每季10萬 — 前10高獲利季的買賣持有時間分析

在季模擬器內記錄每筆買入/賣出（日期、價格、股數、持有天數），
輸出 MA CROSS 與 BREAKOUT 前 10 高獲利季的完整交易時間線。
"""
import sys, os, json, pickle
sys.path.insert(0, "/home/frank/tw-autotrader")
os.chdir("/home/frank/tw-autotrader")
import pandas as pd
import numpy as np

sys.path.insert(0, "scripts")
import stock_selector_grid as ssg
import core.inst_strategy_core as ic
from strategies.ma_cross import ma_cross_strategy
from strategies.breakout import breakout_strategy

COMMISSION = 0.001425
TAX = 0.003
PRINCIPAL = 100000.0

raw = pickle.loads(open("cache/inst_momentum/historical_shares.pkl", "rb").read())
hist = raw["data"]
union = sorted({k[0] for k in hist})

data = {}
for sid in union:
    try:
        df = ssg.load_stock(sid)
        if df is not None and not df.empty and len(df) > 300:
            df = df.reset_index()
            df = df.rename(columns={df.columns[0]: "date"})
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            data[sid] = df[["date", "open", "high", "low", "close", "volume"]]
    except Exception:
        continue

hist_for_pool = {(sid, q): v for (sid, q), v in hist.items()}
pools = ic.build_quarterly_pool(hist_for_pool, data, top_n=100)

QUARTERS = [
    ("2022-02","2022Q1",(1,3)), ("2022-05","2022Q2",(4,6)),
    ("2022-08","2022Q3",(7,9)), ("2022-11","2022Q4",(10,12)),
    ("2023-02","2023Q1",(1,3)), ("2023-05","2023Q2",(4,6)),
    ("2023-08","2023Q3",(7,9)), ("2023-11","2023Q4",(10,12)),
    ("2024-02","2024Q1",(1,3)), ("2024-05","2024Q2",(4,6)),
    ("2024-08","2024Q3",(7,9)), ("2024-11","2024Q4",(10,12)),
    ("2025-02","2025Q1",(1,3)), ("2025-05","2025Q2",(4,6)),
    ("2025-08","2025Q3",(7,9)), ("2025-11","2025Q4",(10,12)),
]

def simulate_stock_traced(df_full, start_date, end_date, strategy, **params):
    """模擬並回傳 (報酬%, 交易紀錄list) — 交易紀錄含買賣日期/價格/股數/持有天數"""
    hist_start = pd.Timestamp(start_date) - pd.Timedelta(days=400)
    win = df_full[(df_full["date"] >= hist_start) & (df_full["date"] <= end_date)].copy()
    if len(win) < 80:
        return None, []
    if strategy == "ma_cross":
        sig = ma_cross_strategy(win, **params)
    else:
        sig = breakout_strategy(win, **params)
    sig["date"] = win["date"].values
    sig = sig.reset_index(drop=True)
    mask = (sig["date"] >= pd.Timestamp(start_date)) & (sig["date"] <= pd.Timestamp(end_date))
    sig_q = sig[mask].reset_index(drop=True)
    if sig_q.empty:
        return 0.0, []

    cash = PRINCIPAL
    shares = 0
    trades = []
    last_buy = None
    for i, row in sig_q.iterrows():
        px = row["close"]; d = row["date"]
        if px <= 0:
            continue
        if row["signal"] == 1 and shares == 0:
            buy_qty = int(cash / (px * (1 + COMMISSION)))
            if buy_qty > 0:
                cost = buy_qty * px
                cash -= cost + cost * COMMISSION
                shares = buy_qty
                last_buy = {"date": d, "price": px, "shares": buy_qty}
                trades.append({"type": "BUY", "date": d, "price": px, "shares": buy_qty})
        elif row["signal"] == -1 and shares > 0:
            proceeds = shares * px
            cash += proceeds - proceeds * COMMISSION - proceeds * TAX
            trades.append({"type": "SELL", "date": d, "price": px, "shares": shares,
                           "pnl": px - last_buy["price"] if last_buy else None})
            # 計算持有天數（交易日數近似：用出場日 - 進場日，轉交易日）
            if last_buy:
                hold_days = len(sig_q[(sig_q["date"] >= last_buy["date"]) & (sig_q["date"] <= d)])
                trades[-1]["hold_days"] = hold_days
            shares = 0
            last_buy = None
    last = sig_q.iloc[-1]["close"]; last_d = sig_q.iloc[-1]["date"]
    if shares > 0 and last > 0:
        proceeds = shares * last
        cash += proceeds - proceeds * COMMISSION - proceeds * TAX
        trades.append({"type": "SELL(季末平倉)", "date": last_d, "price": last, "shares": shares,
                       "pnl": last - last_buy["price"] if last_buy else None})
        if last_buy:
            hold_days = len(sig_q[(sig_q["date"] >= last_buy["date"]) & (sig_q["date"] <= last_d)])
            trades[-1]["hold_days"] = hold_days
    total = cash
    return (total - PRINCIPAL) / PRINCIPAL * 100, trades

# ── 先重跑全部 16 季 × 100 檔，取得兩策略前 10 ──
results = []
trade_log = {}   # (qlabel, sid, strategy) -> trades
mc_params = {"fast_period": 9, "slow_period": 21, "atr_period": 14, "atr_threshold": 0.005}
bo_params = {"lookback": 20, "atr_period": 14, "atr_threshold": 0.02}

for qp, qlabel, (sm, em) in QUARTERS:
    start_date = f"{qp[:4]}-{sm:02d}-01"
    end_date = f"{qp[:4]}-{em:02d}-28"
    pool = pools.get(qp, [])
    for sid in pool:
        df = data.get(sid)
        if df is None:
            continue
        r_mc, t_mc = simulate_stock_traced(df, start_date, end_date, "ma_cross", **mc_params)
        r_bo, t_bo = simulate_stock_traced(df, start_date, end_date, "breakout", **bo_params)
        if r_mc is not None and r_bo is not None:
            results.append({"季標籤": qlabel, "季點": qp, "代號": sid,
                            "MA_CROSS報酬%": round(r_mc,2), "BREAKOUT報酬%": round(r_bo,2)})
            trade_log[(qlabel, sid, "MA")] = t_mc
            trade_log[(qlabel, sid, "BO")] = t_bo

res = pd.DataFrame(results)
names = pickle.loads(open("/tmp/opencode/finmind/names_map.pkl","rb").read()) if os.path.exists("/tmp/opencode/finmind/names_map.pkl") else {}
import requests
token = os.environ["FINMIND_TOKEN"]
r = requests.get("https://api.finmindtrade.com/api/v4/data", params={"dataset":"TaiwanStockInfo"},
                 headers={"Authorization": f"Bearer {token}"}, timeout=60)
info = pd.DataFrame(r.json()["data"])
names = {str(s).strip(): n for s, n in zip(info["stock_id"], info["stock_name"])}
res["名稱"] = res["代號"].astype(str).map(names)
res.to_csv("/tmp/opencode/finmind/quarter_results_with_names.csv", index=False)

top_mc = res.nlargest(10, "MA_CROSS報酬%")
top_bo = res.nlargest(10, "BREAKOUT報酬%")
print("═══ MA CROSS 前10高獲利季 — 交易時間線 ═══")
for _, row in top_mc.iterrows():
    sid = str(row["代號"]); q = row["季標籤"]; nm = row["名稱"]
    td = trade_log.get((q, sid, "MA"), [])
    print(f"\n[MA CROSS] {nm}({sid}) {q} → {row['MA_CROSS報酬%']:+.1f}%")
    for t in td:
        extra = f" | 持有 {t['hold_days']} 交易日" if t["type"]!="BUY" and "hold_days" in t else ""
        print(f"   {t['type']:<10} {pd.Timestamp(t['date']).strftime('%Y-%m-%d')} @ {t['price']:,.2f} x {t['shares']}股{extra}")

print("\n\n═══ BREAKOUT 前10高獲利季 — 交易時間線 ═══")
for _, row in top_bo.iterrows():
    sid = str(row["代號"]); q = row["季標籤"]; nm = row["名稱"]
    td = trade_log.get((q, sid, "BO"), [])
    print(f"\n[BREAKOUT] {nm}({sid}) {q} → {row['BREAKOUT報酬%']:+.1f}%")
    for t in td:
        extra = f" | 持有 {t['hold_days']} 交易日" if t["type"]!="BUY" and "hold_days" in t else ""
        print(f"   {t['type']:<10} {pd.Timestamp(t['date']).strftime('%Y-%m-%d')} @ {t['price']:,.2f} x {t['shares']}股{extra}")
