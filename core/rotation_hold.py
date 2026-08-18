"""core/rotation_hold.py — 全輪替 MIN_DRAW_BACK 重大回撤保護（實盤，2026-08-18）

語義（與回測 backtest_selector 的 min_drawback 一致，最多延長一季）：
- 換股日帳戶總回撤（自歷史峰值）> MIN_DRAW_BACK% → 該季不賣不買、續抱；
- 若上一季已延長且回撤仍超標 → 照常換股（強制）；回撤恢復 → 照常換股。

資產模型：equity = TOTAL_CAPITAL + 已實現損益（performance.csv 全歷史買賣差額）
           + Σ 持股市值（holdings × 現價）。不需成本基礎，避免分帳本重置的干擾。
峰值/延長狀態持久化於 logs/equity_peak.json 與 logs/rotation_hold.json。
"""
import csv
import json
import os
from pathlib import Path

PEAK_FILE = "logs/equity_peak.json"
HOLD_FILE = "logs/rotation_hold.json"


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def realized_pnl(performance_csv="logs/performance.csv"):
    """已實現損益 = Σ賣出金額 − Σ買進金額（performance.csv 全歷史）。"""
    buys = 0.0
    sells = 0.0
    if not os.path.exists(performance_csv):
        return 0.0
    with open(performance_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                px = float(row.get("price", 0))
                qty = float(row.get("quantity", 0))
            except (TypeError, ValueError):
                continue
            action = str(row.get("action", "")).strip().upper()
            if action == "BUY":
                buys += px * qty
            elif action == "SELL":
                sells += px * qty
    return sells - buys


def compute_equity(total_capital, holdings, prices, performance_csv="logs/performance.csv"):
    """總資產 = 資本 + 已實現損益 + 持股市值。"""
    mkt_value = sum(shares * prices.get(sym, 0.0) for sym, shares in holdings.items())
    return total_capital + realized_pnl(performance_csv) + mkt_value


def should_hold(min_drawback, equity, peak, state):
    """回傳 (hold, new_state)。min_drawback<=0 或資料異常 → 不延後（照常換股）。"""
    if min_drawback <= 0 or equity <= 0 or peak <= 0:
        return False, {"extended": False}
    dd = equity / peak - 1.0
    extended = bool((state or {}).get("extended"))
    if dd < -min_drawback / 100.0:
        if extended:
            return False, {"extended": False}
        return True, {"extended": True}
    return False, {"extended": False}


def check_rotation_hold(min_drawback, total_capital, broker, holdings, today_str):
    """換股日回撤檢查。回傳 (hold, dd)。hold=True → 該次換股應跳過。

    失敗時 fail-open（hold=False、dd=None）→ 照常換股，避免 bug 卡住排程。
    任一股價抓取失敗也視為資料異常 → fail-open。
    """
    if min_drawback <= 0:
        return False, None
    try:
        prices = {}
        for sym in holdings:
            px = broker.get_current_price(sym)
            if px is None or float(px) <= 0:
                print(f"⚠️ MIN_DRAW_BACK: {sym} 無法取得現價，本次檢查略過（照常換股）")
                return False, None
            prices[sym] = float(px)
        equity = compute_equity(total_capital, holdings, prices)
        peak = load_json(PEAK_FILE, {}) or {}
        peak_val = float(peak.get("peak", 0) or 0)
        if peak_val <= 0:
            peak_val = max(total_capital, equity)
        hold, new_state = should_hold(min_drawback, equity, peak_val, load_json(HOLD_FILE, {}) or {})
        save_json({"peak": max(peak_val, equity), "updated_at": today_str}, PEAK_FILE)
        save_json(new_state, HOLD_FILE)
        dd = equity / peak_val - 1.0
        return hold, dd
    except Exception as e:
        print(f"⚠️ MIN_DRAW_BACK 檢查失敗，照常換股: {e}")
        return False, None
