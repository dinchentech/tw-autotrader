import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import stock_selector_grid as ssg


class TestInstConfirm(unittest.TestCase):

    def _inst(self):
        return {
            "2026-01-05": {"2330": (1000, 200), "2317": (100, 500)},
            "2026-01-06": {"2330": (800, 100), "2317": (0, 100)},
            "2026-01-07": {"2330": (500, 300), "2317": (600, 0)},
            "2026-01-08": {"2330": (100, 900), "2317": (50, 50)},
        }

    def test_net_buy_positive(self):
        inst = self._inst()
        net = ssg.inst_net_buy(inst, "2330", "2026-01-08", days=3)
        # 01-06~01-08: (800-100)+(500-300)+(100-900) = 700+200-800 = 100
        self.assertIsNotNone(net)
        self.assertGreater(net, 0)

    def test_net_buy_negative(self):
        inst = self._inst()
        net = ssg.inst_net_buy(inst, "2317", "2026-01-08", days=3)
        # 01-06~01-08: -100 + 600 - 0 = 500... 用單日窗測負值
        net1 = ssg.inst_net_buy(inst, "2317", "2026-01-06", days=1)
        self.assertEqual(net1, -100)

    def test_unknown_stock_pass_through(self):
        inst = self._inst()
        net = ssg.inst_net_buy(inst, "9999", "2026-01-08", days=3)
        self.assertIsNone(net)

    def test_no_data_before_coverage(self):
        inst = self._inst()
        net = ssg.inst_net_buy(inst, "2330", "2016-06-30", days=21)
        self.assertIsNone(net)

    def test_pick_top_stocks_filters_by_inst(self):
        dates = pd.date_range("2026-01-01", periods=10, freq="D")
        base = pd.DataFrame({
            "open": [10.0] * 10, "high": [11.0] * 10, "low": [9.0] * 10,
            "close": [10.0 + i * 0.1 for i in range(10)],
            "volume": [1000000] * 10,
        }, index=dates)
        data = {"2330": base, "2317": base.copy(), "0050": base.copy()}
        inst = self._inst()
        params = dict(ssg.DEFAULT_PARAMS)
        params["use_ma_filter"] = False
        # 2317 近 3 日淨買超為 500（正），2330 也正；兩者都應入選
        picked = ssg.pick_top_stocks(data, dates[-1], params, top_n=2,
                                     inst_conf=inst, inst_days=3)
        self.assertEqual(len(picked), 2)
        # 若 inst_days=1（01-08 當日 2330 淨 -800、2317 0）→ 2330 被濾掉
        picked1 = ssg.pick_top_stocks(data, dates[-1], params, top_n=2,
                                      inst_conf=inst, inst_days=1)
        syms1 = {p["symbol"] for p in picked1}
        self.assertNotIn("2330", syms1)

    def test_load_twse_inst_merged_skips_pool_caches(self):
        merged = ssg.load_twse_inst_merged()
        self.assertGreater(len(merged), 1000)
        keys = sorted(merged.keys())
        self.assertLessEqual(keys[0], "2018-01-01")
        self.assertGreaterEqual(keys[-1], "2025-12-31")

    def test_refresh_live_skips_fresh_data(self):
        merged = {"2026-08-10": {"2330": (1, 0)}}
        out = ssg._refresh_inst_live(merged)
        self.assertEqual(out, merged)


if __name__ == "__main__":
    unittest.main()
