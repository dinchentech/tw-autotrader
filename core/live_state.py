import json
import os
from datetime import datetime

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return default

def save_json(data, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_monthly_budget() -> dict: return load_json("logs/monthly_budget.json", {})
def save_monthly_budget(spent: dict): save_json(spent, "logs/monthly_budget.json")

def check_monthly_budget(symbol: str, cost: float, spent: dict, limit: float) -> bool:
    if limit <= 0: return True
    return spent.get(symbol, 0.0) + cost <= limit

def update_monthly_spending(symbol: str, cost: float, spent: dict):
    spent[symbol] = spent.get(symbol, 0.0) + cost
    save_monthly_budget(spent)

def load_stock_allocation() -> dict: return load_json("logs/stock_allocation.json", {})
def save_stock_allocation(alloc: dict): save_json(alloc, "logs/stock_allocation.json")

def check_stock_cap(symbol: str, cost: float, alloc: dict, cap: float) -> bool:
    return alloc.get(symbol, 0.0) + cost <= cap

def update_stock_allocation(symbol: str, cost: float, action: str, alloc: dict):
    if action == "buy": alloc[symbol] = alloc.get(symbol, 0.0) + cost
    elif action == "sell": alloc[symbol] = max(0.0, alloc.get(symbol, 0.0) - cost)
    save_stock_allocation(alloc)

def load_holdings() -> dict: return load_json("logs/holdings.json", {})
def save_holdings(h: dict): save_json(h, "logs/holdings.json")

def update_holdings(symbol: str, qty: int, price: float, action: str, h: dict):
    if symbol not in h: h[symbol] = {"qty": 0, "avg_price": 0.0}
    current = h[symbol]
    if action == "buy":
        total_cost = current["qty"] * current["avg_price"] + qty * price
        current["qty"] += qty
        current["avg_price"] = total_cost / current["qty"] if current["qty"] > 0 else 0
    elif action == "sell":
        current["qty"] -= qty
        if current["qty"] <= 0:
            current["qty"] = 0
            current["avg_price"] = 0.0
    save_holdings(h)

def load_last_trade_times() -> dict: return load_json("logs/last_trade_times.json", {})
def save_last_trade_times(times: dict): save_json(times, "logs/last_trade_times.json")

def load_daily_trades():
    data = load_json("logs/daily_trades.json", {})
    if isinstance(data, dict):
        return (data, data.get("_date"))
    return (data, None)

def save_daily_trades(trades: dict, date_str: str):
    trades["_date"] = date_str
    save_json(trades, "logs/daily_trades.json")
    
def load_processed_capital(filepath: str = "logs/processed_capital.json") -> list:
    return load_json(filepath, [])
    
def save_processed_capital(processed: list, filepath: str = "logs/processed_capital.json"):
    save_json(processed, filepath)
