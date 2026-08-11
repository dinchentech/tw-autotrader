"""
cache_io.py — 版本化 pickle 快取讀寫（全專案共用）

快取資料語義改變（欄位/價格調整/正規化方式）時必須遞增 CACHE_SCHEMA_VERSION，
否則舊快取會被靜默載入——2026-08 回測數字無法重現事件（價格快取混入 yfinance 還原價）的根因。

用法：
  - 可重建快取（股價/法人/選股池）→ load_cache / dump_cache；版本不符自動重建。
  - 累積資料庫（mcap_ranking / historical_shares）→ load_cache_or_raw；
    舊格式原樣讀入（不丟棄無法重建的歷史資料），下次寫入時自動升級為版本化。
"""
import os
import pickle
from pathlib import Path

CACHE_SCHEMA_VERSION = 2


def dump_cache(path, data, meta=None):
    payload = {"schema_version": CACHE_SCHEMA_VERSION, "meta": meta or {}, "data": data}
    tmp = Path(path).with_suffix(Path(path).suffix + ".tmp")
    tmp.write_bytes(pickle.dumps(payload))
    os.replace(tmp, path)


def load_cache(path):
    try:
        payload = pickle.loads(Path(path).read_bytes())
        if not isinstance(payload, dict) or payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            v = payload.get("schema_version") if isinstance(payload, dict) else "?"
            print(f"⚠️  快取版本不符（{Path(path).name}）: 快取 v{v} != 目前 v{CACHE_SCHEMA_VERSION}，重建中...")
            return None, None
        return payload.get("data"), payload.get("meta", {})
    except Exception:
        return None, None


def load_cache_or_raw(path):
    data, meta = load_cache(path)
    if data is not None:
        return data, meta
    try:
        data = pickle.loads(Path(path).read_bytes())
        print(f"⚠️  {Path(path).name} 為舊格式（無版本），原樣讀入；下次寫入時自動升級")
        return data, {}
    except Exception:
        return None, None
