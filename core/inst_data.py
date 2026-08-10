"""
inst_data.py — 法人動能策略共用資料層（回測與實盤唯一資料來源）

回測（backtest_inst_momentum.py）與實盤（strategies/institutional_momentum.py）共用此模組，
確保 TWSE T86 參數/欄位、FinMind 正規化、快取新鮮度、選股池定義一致，
避免兩套資料程式各自演進造成實盤靜默失效（2026-08 事件的教訓）。

提供：
  - fetch_twse_day / fetch_twse_inst_bulk   TWSE T86 三大法人（唯一實作）
  - get_price_data                          股價（finmind / twse / yfinance），含快取新鮮度
  - get_institutional_data                  法人買賣（finmind / twse），含快取新鮮度與 TWSE 逐日快取
  - TwseDayCache                            TWSE 逐日快取（實盤備援避免逐股逐日重複呼叫）
  - aggregate_institutional                 投信+外資每日加總（core 格式）
  - get_all_stock_ids                       市值前 N 選股池（與回測一致）
"""
import os
import pickle
import requests
import pandas as pd
from datetime import date, timedelta
from pathlib import Path

FINMIND_TOKEN_KEY = "FINMIND_API_TOKEN"

TWSE_T86_URL = "https://www.twse.com.tw/fund/T86"

# T86 欄位定義（唯一來源；回測與實盤共用）：
#   0 證券代號 | 1 證券名稱 | 2 外陸資買進 | 3 外陸資賣出 | 4 外陸資買賣超
#   5 外資自營商買進 | 6 外資自營商賣出 | 7 外資自營商買賣超
#   8 投信買進 | 9 投信賣出 | 10 投信買賣超
#   11 自營商買賣超 | 12 自營商(自行)買進 | 13 自營商(自行)賣出 | 14 自營商(自行)買賣超
#   15 自營商(避險)買進 | 16 自營商(避險)賣出 | 17 自營商(避險)買賣超 | 18 三大法人買賣超

FINMIND_INST_NAME_MAP = {
    "Foreign_Investor": "外資",
    "Investment_Trust": "投信",
    "Foreign_Dealer_Self": "自營商",
    "Dealer_self": "自營商",
    "Dealer_Hedging": "自營商",
}


def _safe_int(val) -> int:
    if isinstance(val, str):
        val = val.replace(",", "").strip()
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


# ─── TWSE T86 三大法人（唯一實作）────────────────────────

def fetch_twse_day(dt_str: str) -> dict:
    """TWSE T86 單日全市場法人資料。

    回傳 { stock_id: {"外資": {buy, sell}, "投信": {buy, sell}, "自營商": {buy, sell}} }
    失敗或 stat != OK 回傳 {}。
    """
    try:
        params = {"response": "json", "date": dt_str, "selectType": "ALLBUT0999"}
        resp = requests.get(TWSE_T86_URL, params=params,
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = resp.json()
        if data.get("stat") != "OK" or not data.get("data"):
            return {}
        day = {}
        for row in data["data"]:
            sid = row[0].strip()
            day[sid] = {
                "外資": {"buy": _safe_int(row[2]), "sell": _safe_int(row[3])},
                "投信": {"buy": _safe_int(row[8]), "sell": _safe_int(row[9])},
                "自營商": {"buy": _safe_int(row[12]) + _safe_int(row[15]),
                           "sell": _safe_int(row[13]) + _safe_int(row[16])},
            }
        return day
    except Exception:
        return {}


def fetch_twse_inst_bulk(trading_dates, cache_path=None, progress_every=50) -> dict:
    """逐日抓 T86 並聚合為 { date_str: { stock_id: (inst_buy, inst_sell) } }（投信+外資）。

    回測使用；cache_path 存在時直接載入，否則下載後寫入快取。
    trading_dates: date/datetime 集合。
    """
    if cache_path is not None and cache_path.exists():
        print(f"   載入 TWSE 法人資料快取（{Path(cache_path).name}）...")
        return pickle.loads(Path(cache_path).read_bytes())

    inst_data = {}
    dates = sorted(trading_dates)
    for i, d in enumerate(dates):
        if hasattr(d, "strftime"):
            dt_str = d.strftime("%Y%m%d")
            key = d.isoformat()
        else:
            dt_str = str(d).replace("-", "")
            key = str(d)[:10]
        day = fetch_twse_day(dt_str)
        if not day:
            continue
        inst_data[key] = {
            sid: (v["外資"]["buy"] + v["投信"]["buy"], v["外資"]["sell"] + v["投信"]["sell"])
            for sid, v in day.items()
        }
        if progress_every and (i + 1) % progress_every == 0:
            print(f"   TWSE 下載進度: {i+1}/{len(dates)}")

    if cache_path is not None:
        Path(cache_path).write_bytes(pickle.dumps(inst_data))
        print(f"✅ TWSE 法人資料下載完成: {len(inst_data)} 交易日")
    return inst_data


class TwseDayCache:
    """TWSE 逐日快取（實盤備援用）：先建立近 N 天快取，之後只補最新一天、淘汰最舊一天。"""

    def __init__(self, max_days: int = 20):
        self._cache = {}
        self._max_days = max_days
        self._built = False

    def ensure_range(self, end_date, lookback_days: int = 15):
        for i in range(lookback_days):
            d = end_date - timedelta(days=i)
            dt_str = d.strftime("%Y%m%d")
            if dt_str not in self._cache:
                day = fetch_twse_day(dt_str)
                if day:
                    self._cache[dt_str] = day
        keys = sorted(self._cache.keys())
        while len(keys) > self._max_days:
            del self._cache[keys.pop(0)]
        if not self._built:
            self._built = True
            print(f"✅ [INST_MOM] TWSE 快取建立 ({len(self._cache)} 天, "
                  f"{sum(len(v) for v in self._cache.values())} 筆)")

    def stock_rows(self, stock_id: str) -> pd.DataFrame:
        """回傳個股在快取內的法人資料：date/stock_id/name/buy/sell（name 為中文）。"""
        rows = []
        for date_str, stocks in self._cache.items():
            if stock_id in stocks:
                d = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                for name, data in stocks[stock_id].items():
                    rows.append({"date": d, "stock_id": stock_id, "name": name,
                                 "buy": data["buy"], "sell": data["sell"]})
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return df


# ─── 股價 ─────────────────────────────────────────────

def _norm_price(df: pd.DataFrame) -> pd.DataFrame:
    rename = {"Trading_Volume": "volume", "Trading_money": "amount",
              "Trading_turnover": "turnover", "max": "high", "min": "low"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _fetch_price_finmind(dl, stock_id: str, start: str, end: str) -> pd.DataFrame:
    try:
        df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start, end_date=end)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    return _norm_price(df)


def _fetch_price_twse(stock_id: str, start: str, end: str) -> pd.DataFrame:
    """TWSE STOCK_DAY（民國年轉換）。"""
    try:
        dt_str = pd.Timestamp(start).strftime("%Y%m01")
        url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
        params = {"response": "json", "date": dt_str, "stockNo": stock_id}
        resp = requests.get(url, params=params, headers={
            "User-Agent": "Mozilla/5.0",
        }, timeout=10)
        data = resp.json()
        if data.get("stat") != "OK" or not data.get("data"):
            return pd.DataFrame()
        rows = []
        for row in data["data"]:
            try:
                parts = row[0].split("/")
                d = f"{int(parts[0]) + 1911}-{parts[1]}-{parts[2]}"
                if d < start or d > end:
                    continue
                rows.append({
                    "date": d, "stock_id": stock_id,
                    "open": float(row[3].replace(",", "")),
                    "high": float(row[4].replace(",", "")),
                    "low": float(row[5].replace(",", "")),
                    "close": float(row[6].replace(",", "")),
                    "volume": int(row[1].replace(",", "")),
                })
            except (ValueError, IndexError):
                continue
        if not rows:
            return pd.DataFrame()
        return _norm_price(pd.DataFrame(rows))
    except Exception:
        return pd.DataFrame()


def _fetch_price_yfinance(stock_id: str, start: str, end: str) -> pd.DataFrame:
    try:
        import yfinance as yf
        tk = yf.Ticker(f"{stock_id}.TW")
        df = tk.history(start=start, end=end)
        if df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        df["date"] = pd.to_datetime(df["Date"].dt.date)
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                                "Close": "close", "Volume": "volume"})
        df = df[["date", "open", "high", "low", "close", "volume"]]
        return _norm_price(df)
    except Exception:
        return pd.DataFrame()


def get_price_data(dl, stock_id: str, start, end, cache_path=None,
                   max_stale_days: int = 5, ref_date=None,
                   sources=("finmind", "twse")) -> tuple:
    """取得個股日 K（date/open/high/low/close/volume）。

    cache_path 提供時做新鮮度檢查（ref_date 與 max_stale_days 可設定）。
    回傳 (df, source)，source ∈ cache / finmind / twse / yfinance / none。
    """
    if ref_date is None:
        ref_date = date.today()
    ref_ts = pd.Timestamp(ref_date)

    if cache_path is not None and Path(cache_path).exists():
        try:
            df = pickle.loads(Path(cache_path).read_bytes())
            if isinstance(df, pd.DataFrame) and not df.empty:
                latest = pd.Timestamp(df["date"].max())
                if (ref_ts - latest).days <= max_stale_days:
                    return df, "cache"
        except Exception:
            pass

    start_s, end_s = str(start)[:10], str(end)[:10]
    fetchers = {
        "finmind": lambda: _fetch_price_finmind(dl, stock_id, start_s, end_s),
        "twse": lambda: _fetch_price_twse(stock_id, start_s, end_s),
        "yfinance": lambda: _fetch_price_yfinance(stock_id, start_s, end_s),
    }
    for src in sources:
        try:
            df = fetchers[src]()
        except Exception:
            continue
        if df is not None and not df.empty:
            if cache_path is not None:
                try:
                    Path(cache_path).write_bytes(pickle.dumps(df))
                except Exception:
                    pass
            return df, src
    return pd.DataFrame(), "none"


# ─── 法人買賣 ─────────────────────────────────────────

def _norm_inst(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["name"] = df["name"].replace(FINMIND_INST_NAME_MAP)
    return df


def aggregate_institutional(df: pd.DataFrame) -> pd.DataFrame:
    """投信+外資每日加總 → { date, inst_buy, inst_sell }（core 格式）。"""
    mask = df["name"].isin(["投信", "外資"])
    agg = df[mask].groupby("date").agg(
        inst_buy=("buy", "sum"), inst_sell=("sell", "sum")).reset_index()
    agg["date"] = pd.to_datetime(agg["date"])
    return agg


def get_institutional_data(dl, stock_id: str, start, end, cache_path=None,
                           max_stale_days: int = 5, ref_date=None,
                           sources=("finmind", "twse"),
                           twse_day_cache: TwseDayCache = None) -> tuple:
    """取得個股法人買賣資料（date/stock_id/name/buy/sell，name 為中文）。

    cache_path 提供時做新鮮度檢查（同股價快取）。
    twse_day_cache 提供時，TWSE 備援會走逐日快取避免逐股重複呼叫。
    回傳 (df, source, latest_date)，source ∈ cache / finmind / twse / none。
    """
    if ref_date is None:
        ref_date = date.today()
    ref_ts = pd.Timestamp(ref_date)

    if cache_path is not None and Path(cache_path).exists():
        try:
            df = pickle.loads(Path(cache_path).read_bytes())
            if isinstance(df, pd.DataFrame) and not df.empty:
                latest = pd.Timestamp(df["date"].max())
                if (ref_ts - latest).days <= max_stale_days:
                    return df, "cache", latest.date()
        except Exception:
            pass

    for src in sources:
        if src == "finmind":
            try:
                df = dl.taiwan_stock_institutional_investors(
                    stock_id=stock_id,
                    start_date=str(start)[:10],
                    end_date=str(end)[:10],
                )
                if df is not None and not df.empty:
                    df = _norm_inst(df)
                    if cache_path is not None:
                        try:
                            Path(cache_path).write_bytes(pickle.dumps(df))
                        except Exception:
                            pass
                    return df, "finmind", pd.Timestamp(df["date"].max()).date()
            except Exception:
                pass
        elif src == "twse":
            if twse_day_cache is None:
                continue
            start_dt = pd.Timestamp(start).date()
            end_dt = pd.Timestamp(end).date()
            twse_day_cache.ensure_range(end_dt, lookback_days=(end_dt - start_dt).days + 5)
            df = twse_day_cache.stock_rows(stock_id)
            if not df.empty:
                return df, "twse", pd.Timestamp(df["date"].max()).date()
    return pd.DataFrame(), "none", None


# ─── 選股池 ───────────────────────────────────────────

def get_all_stock_ids(dl, n: int, exclude_etf: bool = True, mcap_file=None) -> list:
    """市值前 N 選股池（與回測一致）。

    mcap_file 存在時優先使用市值排名，否則退回 stock_id 排序。
    """
    if mcap_file is not None and Path(mcap_file).exists():
        try:
            ranked = pickle.loads(Path(mcap_file).read_bytes())
            ranked = [s.strip() for s in ranked
                      if s.strip().isdigit() and len(s.strip()) == 4]
            if exclude_etf:
                ranked = [s for s in ranked if not s.startswith("0")]
            if ranked:
                return ranked[:n]
        except Exception:
            pass
    df = dl.taiwan_stock_info()
    df = df[df["type"] == "twse"]
    ids = [s.strip() for s in df["stock_id"]
           if s.strip().isdigit() and len(s.strip()) == 4]
    if exclude_etf:
        ids = [s for s in ids if not s.startswith("0")]
    return sorted(set(ids))[:n]
