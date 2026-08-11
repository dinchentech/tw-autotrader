import unittest
import pickle
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

import pandas as pd

from core.inst_data import (
    CACHE_SCHEMA_VERSION,
    _dump_cache,
    _load_cache,
    fetch_twse_inst_bulk,
    get_institutional_data,
    get_price_data,
)


class _ExplodingDL:
    """假 dl：任何方法被呼叫就失敗（證明快取命中路徑完全不碰 dl）。"""

    def __getattr__(self, name):
        raise AssertionError(f"dl.{name}() 不應被呼叫（此測試不應觸網）")


def _price_df(days=10, start="2026-01-01"):
    dates = pd.date_range(start, periods=days, freq="D")
    return pd.DataFrame({
        "date": dates,
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
        "volume": 100000,
    })


def _inst_df(days=10, start="2026-01-01"):
    dates = pd.date_range(start, periods=days, freq="D")
    return pd.DataFrame({
        "date": dates,
        "stock_id": "2330",
        "name": "Foreign_Investor",
        "buy": 1000, "sell": 500,
    })


class TestCacheSchema(unittest.TestCase):

    def test_old_unversioned_cache_rejected(self):
        """舊格式（未版本化的 plain pickle）→ _load_cache 拒絕"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "old.pkl"
            p.write_bytes(pickle.dumps(_price_df()))
            data, meta = _load_cache(p)
            self.assertIsNone(data)
            self.assertIsNone(meta)

    def test_wrong_version_rejected(self):
        """schema_version=1 → _load_cache 拒絕"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "v1.pkl"
            payload = {"schema_version": 1, "meta": {}, "data": _price_df()}
            p.write_bytes(pickle.dumps(payload))
            data, meta = _load_cache(p)
            self.assertIsNone(data)
            self.assertIsNone(meta)

    def test_roundtrip(self):
        """正確版本 round-trip → 資料與 meta 一致"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ok.pkl"
            df = _price_df()
            _dump_cache(p, df, meta={"source": "finmind", "stock_id": "2330"})
            data, meta = _load_cache(p)
            self.assertIsNotNone(data)
            pd.testing.assert_frame_equal(data, df)
            self.assertEqual(meta["source"], "finmind")
            self.assertEqual(meta["stock_id"], "2330")


class TestPriceCache(unittest.TestCase):

    def test_valid_cache_hit(self):
        """有效快取命中 → source=cache，dl 不被呼叫"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "price.pkl"
            _dump_cache(p, _price_df(), meta={"source": "finmind"})
            dl = _ExplodingDL()
            df, src = get_price_data(
                dl, "2330", "2026-01-01", "2026-01-31", cache_path=p,
                max_stale_days=5, ref_date=date(2026, 1, 15),
                sources=("finmind",))
            self.assertEqual(src, "cache")

    def test_stale_cache_rejected(self):
        """過期快取（ref_date 距最新 > max_stale_days）→ 拒絕並 fall through"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "price.pkl"
            _dump_cache(p, _price_df(), meta={"source": "finmind"})
            dl = _ExplodingDL()
            df, src = get_price_data(
                dl, "2330", "2026-01-01", "2026-01-31", cache_path=p,
                max_stale_days=5, ref_date=date(2026, 2, 1),
                sources=("finmind",))
            self.assertNotEqual(src, "cache")

    def test_short_history_rejected(self):
        """min_start 早於快取最早日期 → 拒絕（魚過濾回溯視窗不完整的防護）"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "price.pkl"
            _dump_cache(p, _price_df(days=10, start="2026-01-01"),
                        meta={"source": "finmind"})
            dl = _ExplodingDL()
            df, src = get_price_data(
                dl, "2330", "2025-06-01", "2026-01-31", cache_path=p,
                max_stale_days=30, ref_date=date(2026, 1, 15),
                sources=("finmind",), min_start="2025-06-01")
            self.assertNotEqual(src, "cache")

    def test_version_mismatch_cache_rejected(self):
        """版本不符的快取 → get_price_data 拒絕，不當作 cache 使用"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "price.pkl"
            payload = {"schema_version": 1, "meta": {}, "data": _price_df()}
            p.write_bytes(pickle.dumps(payload))
            dl = _ExplodingDL()
            df, src = get_price_data(
                dl, "2330", "2026-01-01", "2026-01-31", cache_path=p,
                max_stale_days=5, ref_date=date(2026, 1, 15),
                sources=("finmind",))
            self.assertNotEqual(src, "cache")


class TestInstCache(unittest.TestCase):

    def test_valid_cache_hit(self):
        """法人快取命中 → source=cache，dl 不被呼叫"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "inst.pkl"
            _dump_cache(p, _inst_df(), meta={"source": "finmind"})
            dl = _ExplodingDL()
            df, src, latest = get_institutional_data(
                dl, "2330", "2026-01-01", "2026-01-31", cache_path=p,
                max_stale_days=5, ref_date=date(2026, 1, 15),
                sources=("finmind",), twse_day_cache=None)
            self.assertEqual(src, "cache")
            self.assertEqual(latest, date(2026, 1, 10))


class TestBulkCache(unittest.TestCase):

    def test_version_mismatch_rebuilds(self):
        """TWSE 法人快取版本不符 → 重新下載並寫入新版快取"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "inst_bulk.pkl"
            p.write_bytes(pickle.dumps({"2026-01-02": {"2330": (1, 2)}}))  # 舊格式

            fake_day = {
                "2330": {
                    "外資": {"buy": 1, "sell": 2},
                    "投信": {"buy": 3, "sell": 4},
                    "自營商": {"buy": 5, "sell": 6},
                }
            }
            dates = [date(2026, 1, 2), date(2026, 1, 3)]
            with mock.patch("core.inst_data.fetch_twse_day", return_value=fake_day):
                inst = fetch_twse_inst_bulk(dates, cache_path=p, progress_every=0)

            self.assertEqual(inst["2026-01-02"]["2330"], (4, 6))   # 外資+投信買/賣
            self.assertEqual(inst["2026-01-03"]["2330"], (4, 6))

            data, meta = _load_cache(p)
            self.assertIsNotNone(data)
            self.assertEqual(data["2026-01-02"]["2330"], (4, 6))
            self.assertEqual(meta["source"], "TWSE_T86")
            self.assertEqual(meta["dates"], 2)


if __name__ == "__main__":
    unittest.main()
