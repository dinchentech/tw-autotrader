"""
Institutional Momentum Strategy — 法人抬轎動能策略

不同於固定標的策略，此策略動態選股（由 INST_MOM_DAILY_SCREENING 控制頻率）：
  1. 盤後篩選（流動性 > 2,000 張、法人買超 > 8%、創 10 日新高 + 站穩 MA10（2026-08 walk-forward 全天候預設））
     每週（預設）：週五 13:31-13:45
     每日（INST_MOM_DAILY_SCREENING=true）：每個交易日 13:31-13:45
  2. 依投信+外資買超佔比排序，選前 N 名（預設 2 檔）
  3. 隔日開盤 09:00-09:05 買入（每週模式為週一，每日模式為下個交易日）
  4. 每日監控：硬性停損 -10%、跌破 MA10 移動停利

共用核心邏輯來自 core/inst_strategy_core.py，確保回測與實盤一致性。
"""
import os
import math
import json
import time
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path

from loguru import logger as _loguru_logger
# FinMind 使用 loguru，不是 Python 的 logging 模組
# loguru.logger.add(sys.stderr, level="INFO") 在模組載入時就會設好，
# 必須用 disable() 來關閉所有 FinMind 模組的 loguru 輸出
_loguru_logger.disable("FinMind")

from FinMind.data import DataLoader
from FinMind.schema.data import Dataset

import core.inst_strategy_core as inst_core
import core.inst_data as inst_data
from core.inst_strategy_core import (
    check_momentum_entry as _core_check_momentum_entry,
    check_position_exit as _core_check_position_exit,
    compute_profit_roll as _core_compute_profit_roll,
    log_capital_roll as _core_log_capital_roll,
)


class InstitutionalMomentumStrategy:
    """
    法人抬轎動能策略 — 動態選股 + 獨立資金池管理

    屬於 Group 2（獨立資金），有獨立的起始本金、損益追蹤。
    """

    def __init__(self, broker=None, capital=0, top_n=3):
        self.broker = broker
        self.capital = capital                     # 獨立起始資金（0 = 不啟用）
        self.top_n = top_n                         # 持有標的數量
        self.state_file = Path("data/inst_momentum_state.json")
        self.pnl_file = Path("data/inst_momentum_pnl.json")

        # 預設參數（可從 .env 覆蓋）
        self.min_volume = int(os.getenv("INST_MOM_MIN_VOLUME", "2000"))         # 張
        self.buy_ratio = float(os.getenv("INST_MOM_BUY_RATIO", "0.08"))         # 8%（2026-08 walk-forward 全天候預設）
        self.lookback = int(os.getenv("INST_MOM_LOOKBACK", "10"))               # 天（2026-08 walk-forward 全天候預設）
        self.stop_loss = float(os.getenv("INST_MOM_STOP_LOSS", "0.10"))         # -10%
        self.trailing_period = int(os.getenv("INST_MOM_TRAILING_PERIOD", "20")) # MA20（誠實池雙窗驗證：等久一點讓低吃發酵，2026-08-11）
        self.exclude_etf = os.getenv("INST_MOM_EXCLUDE_ETF", "true").lower() == "true"  # 預設排除 ETF
        self.daily_screening = os.getenv("INST_MOM_DAILY_SCREENING", "false").lower() == "true"  # 每日篩選

        # 內部狀態
        self.state = self._load_state()
        self.finmind_token = os.getenv("FINMIND_API_TOKEN", "")

        # TWSE 備援逐日快取（共用資料層，避免跨篩選汙染）
        self._twse_day_cache = inst_data.TwseDayCache(max_days=20)
        self._data_fail_notified = {}   # { source_key: date_str } 同一來源一天只通知一次
        # 資料健康度（篩選摘要用，讓 0 觸發可區分「資料壞」與「沒訊號」）
        self._data_stats = {}

        # 磁碟快取（避免重複呼叫 FinMind API，免費版每小時 600 次上限）
        self._price_cache_dir = Path("cache/inst_momentum/price")
        self._price_cache_dir.mkdir(parents=True, exist_ok=True)
        self._inst_cache_dir = Path("cache/inst_momentum/inst")
        self._inst_cache_dir.mkdir(parents=True, exist_ok=True)

    # ================================================================
    # 狀態持久化
    # ================================================================
    def _load_state(self) -> dict:
        """載入策略狀態（持有標的、成本、篩選日期等）"""
        default = {
            "candidates": [],         # 最近一次篩選出的前 N 名
            "positions": {},          # { stock_id: { buy_price, shares, cost, entry_date } }
            "last_screen_date": None, # 上次篩選日期 "YYYY-MM-DD"
            "last_entry_date": None,  # 上次進場日期 "YYYY-MM-DD"
            "loser_ban": {},          # { stock_id: "YYYY-MM-DD" } 停損禁入清單
            "last_roll_date": None,   # 上次獲利滾入日期 "YYYY-MM-DD"
        }
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                for k, v in default.items():
                    data.setdefault(k, v)
                return data
            except Exception:
                pass
        return default

    def _save_state(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))

    # ================================================================
    # 獨立損益追蹤（Group 2 獨立核算）
    # ================================================================
    def _load_pnl(self) -> dict:
        default = {
            "capital": self.capital,
            "total_buy_cost": 0.0,
            "total_sell_proceeds": 0.0,
            "trades": [],
        }
        if self.pnl_file.exists():
            try:
                data = json.loads(self.pnl_file.read_text())
                for k, v in default.items():
                    data.setdefault(k, v)
                return data
            except Exception:
                pass
        return default

    def _save_pnl(self, pnl: dict):
        self.pnl_file.parent.mkdir(parents=True, exist_ok=True)
        self.pnl_file.write_text(json.dumps(pnl, indent=2, ensure_ascii=False))

    def _record_trade(self, action: str, stock_id: str, shares: int, price: float, pnl: dict):
        trade = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "action": action.upper(),
            "stock_id": stock_id,
            "shares": shares,
            "price": price,
            "amount": price * shares,
        }
        pnl.setdefault("trades", []).append(trade)
        if action.upper() == "BUY":
            pnl["total_buy_cost"] += price * shares
        else:
            pnl["total_sell_proceeds"] += price * shares
        self._save_pnl(pnl)
        # 同步寫入 performance.csv（Group 2），讓 dashboard 看得到
        self._log_to_performance_csv(action, stock_id, shares, price)

    def _log_to_performance_csv(self, action: str, stock_id: str, shares: int, price: float):
        import csv
        csv_path = Path("logs/performance.csv")
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_exists = csv_path.exists()
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "symbol", "signal", "price", "quantity", "action", "group"])
            signal = 1 if action.upper() == "BUY" else -1
            writer.writerow([timestamp, stock_id, signal, round(price, 2), shares, action.upper(), 2])

    def get_pnl_summary(self) -> dict:
        pnl = self._load_pnl()
        capital = pnl.get("capital", self.capital)
        total_buy = pnl.get("total_buy_cost", 0)
        total_sell = pnl.get("total_sell_proceeds", 0)

        # 計算目前持倉市值（用 state 中的最新價格）
        positions = self.state.get("positions", {})
        position_value = sum(p["cost"] for p in positions.values())

        # 總權益 = 已實現損益（賣出 - 買出成本）+ 目前持倉市值
        # 已實現損益 = total_sell - (與已賣出對應的買入成本)
        # 簡化：權益 = 剩餘資金 + 持倉市值
        # 剩餘資金 ≈ 起始資金 - 總買入 + 總賣出
        remaining = capital - total_buy + total_sell

        return {
            "capital": capital,
            "remaining_cash": round(remaining, 0),
            "position_value": round(position_value, 0),
            "total_equity": round(remaining + position_value, 0),
            "total_buy_cost": round(total_buy, 0),
            "total_sell_proceeds": round(total_sell, 0),
            "realized_pnl": round(total_sell - 0, 0),  # simplified
            "trade_count": len(pnl.get("trades", [])),
        }

    # ================================================================
    # FinMind 資料輔助
    # ================================================================
    def _get_dataloader(self) -> DataLoader:
        return DataLoader(token=self.finmind_token)

    MAX_STOCKS = int(os.getenv("STOCK_NO", "150"))  # 前 N 大股票，控制 FinMind API 呼叫量

    def _get_all_stock_ids(self) -> list:
        """回傳上市普通股 stock_id 列表（前 MAX_STOCKS 檔，控制 API 配額）

        與回測一致：共用資料層依市值排名（cache/inst_momentum/mcap_ranking.pkl）。
        """
        return inst_data.get_all_stock_ids(
            self._get_dataloader(), self.MAX_STOCKS,
            exclude_etf=self.exclude_etf,
            mcap_file=Path("cache/inst_momentum/mcap_ranking.pkl"))

    def _get_price_data(self, stock_id: str, days: int = 30) -> pd.DataFrame:
        """取得個股日 K 資料（共用資料層：FinMind → TWSE 備援，快取 5 天新鮮度）"""
        end = date.today()
        start = end - timedelta(days=days)
        df, source = inst_data.get_price_data(
            self._get_dataloader(), stock_id, start, end,
            cache_path=self._price_cache_dir / f"{stock_id}.pkl",
            max_stale_days=5, sources=("finmind", "twse"))
        self._data_stats.setdefault("price_source", {})
        self._data_stats["price_source"][source] = self._data_stats["price_source"].get(source, 0) + 1
        if not df.empty:
            self._data_stats["stocks_with_price"] = self._data_stats.get("stocks_with_price", 0) + 1
        else:
            self._notify_once("price_fail", f"股價資料全線失效：{stock_id}，FinMind 與 TWSE 皆無法取得")
        return df

    def _get_institutional_data(self, stock_id: str, days: int = 10) -> pd.DataFrame:
        """取得個股法人買賣資料（共用資料層：FinMind → TWSE 備援，快取 5 天新鮮度）"""
        end = date.today()
        start = end - timedelta(days=days)
        df, source, latest = inst_data.get_institutional_data(
            self._get_dataloader(), stock_id, start, end,
            cache_path=self._inst_cache_dir / f"{stock_id}.pkl",
            max_stale_days=5, sources=("finmind", "twse"),
            twse_day_cache=self._twse_day_cache)
        self._data_stats.setdefault("inst_source", {})
        self._data_stats["inst_source"][source] = self._data_stats["inst_source"].get(source, 0) + 1
        if not df.empty:
            self._data_stats["stocks_with_inst"] = self._data_stats.get("stocks_with_inst", 0) + 1
            if latest is not None:
                cur = self._data_stats.get("latest_inst_date")
                if cur is None or latest.isoformat() > cur:
                    self._data_stats["latest_inst_date"] = latest.isoformat()
        else:
            self._data_stats["stocks_missing_inst"] = self._data_stats.get("stocks_missing_inst", 0) + 1
            self._notify_once("inst_fail", f"法人資料全線失效：{stock_id}，FinMind 與 TWSE 皆無法取得")
        return df

    def _notify_once(self, key: str, msg: str):
        """同一 source_key 一天只發一次 TG 通知"""
        today = date.today().isoformat()
        if self._data_fail_notified.get(key) == today:
            return
        self._data_fail_notified[key] = today
        try:
            from utils.telegram import send_telegram_message
            send_telegram_message(f"⚠️ *法人抬轎動能策略*\n{msg}")
        except Exception:
            pass

    # ================================================================
    # 核心篩選邏輯（使用共用核心，確保回測與實盤一致性）
    # ================================================================
    def _build_core_dataframe(self, stock_id: str) -> pd.DataFrame:
        """
        將個股的價格資料與法人資料合併為 core 所需格式。
        回傳 DataFrame 含 columns: date, close, volume, ma20, inst_buy, inst_sell
        """
        # 1. 價格資料
        #   ⚠️  fish 評分需要至少 30 個交易日（~42 日曆天）熱身，
        #       且魚過濾回溯視窗為 FISH_DAYS 天 → 價格資料必須涵蓋 fish_days+60 天，
        #       否則實盤魚視窗不完整（與回測不一致，2026-08 發現）
        fish_days = int(os.getenv("INST_MOM_FISH_DAYS", "120"))
        min_days = max(self.lookback + 10, fish_days + 60, 60)
        df_price = self._get_price_data(stock_id, days=min_days)
        if df_price.empty or len(df_price) < self.lookback:
            return pd.DataFrame()

        # 統一 date 為 datetime（FinMind 回傳字串，check_momentum_entry 需要 datetime 比對）
        df_price = df_price.copy()
        df_price["date"] = pd.to_datetime(df_price["date"])

        # 計算 MA20
        df_price["ma20"] = pd.Series(df_price["close"].values).rolling(self.lookback).mean().values

        # 2. 法人資料
        df_inst = self._get_institutional_data(stock_id, days=15)
        if df_inst.empty:
            # 法人資料缺失時保留價格資料（近 5 日漲幅備援排名仍要能列出前三），
            # inst 欄位以 0 填充 — 動能/魚分檢查會因法人全 0 而判定不通過（不會誤入選）
            df = df_price.copy()
            df["inst_buy"] = 0
            df["inst_sell"] = 0
            return df

        # 聚合法人資料為每日 inst_buy / inst_sell（投信+外資，共用資料層正規化名稱）
        inst_agg = inst_data.aggregate_institutional(df_inst)
        inst_agg["date"] = pd.to_datetime(inst_agg["date"])

        # 3. 合併
        df = pd.merge(df_price, inst_agg, on="date", how="left")
        df["inst_buy"] = df["inst_buy"].fillna(0)
        df["inst_sell"] = df["inst_sell"].fillna(0)

        return df

    def get_candidates(self) -> tuple:
        """
        篩選出符合條件的候選股票，依法人買超佔比排序。

        Returns:
            (qualified, near_misses)
            qualified:    [(stock_id, score), ...] — 通過所有篩選條件的標的
            near_misses:  [(stock_id, score), ...] — 未完全通過但最高分的前 N 名
                          （只在 qualified 為空時有值，讓使用者知道篩選有正常執行）
        """
        # 同步 instance 參數到共用核心模組（乾跑/直呼 get_candidates 時與 run() 一致）
        inst_core.MIN_VOLUME_SHARES = self.min_volume
        inst_core.BUY_RATIO_THRESHOLD = self.buy_ratio
        inst_core.LOOKBACK = self.lookback
        inst_core.STOP_LOSS = self.stop_loss
        inst_core.TRAILING_PERIOD = self.trailing_period

        all_ids = self._get_all_stock_ids()
        check_date = date.today()
        loser_ban = self.state.get("loser_ban", {})

        # 重置資料健康度統計（本次篩選的資料來源/覆蓋率）
        self._data_stats = {
            "inst_source": {}, "price_source": {},
            "stocks_with_inst": 0, "stocks_missing_inst": 0,
            "stocks_with_price": 0, "latest_inst_date": None,
        }

        fish_enabled = os.getenv("INST_MOM_FISH_FILTER", "true").lower() == "true"
        fish_days = int(os.getenv("INST_MOM_FISH_DAYS", "120"))
        fish_min = float(os.getenv("INST_MOM_FISH_MIN_SCORE", "7.0"))

        all_data = {}
        for stock_id in all_ids:
            if inst_core.is_banned(stock_id, check_date, loser_ban):
                continue
            df = self._build_core_dataframe(stock_id)
            if not df.empty:
                all_data[stock_id] = df

        if fish_enabled and all_data:
            fish_scores = inst_core.precompute_fish_scores(all_data)
            fish_qualified = inst_core.screen_fish_qualified(
                all_data, check_date, fish_scores, fish_days, fish_min)
        else:
            fish_scores = {}
            fish_qualified = {sid: None for sid in all_data.keys()}

        candidates = []
        all_evaluated = []

        for stock_id, accum_price in fish_qualified.items():
            try:
                single = {stock_id: all_data[stock_id]}
                ok, score = _core_check_momentum_entry(
                    single, stock_id, check_date, accum_price=accum_price)
                all_evaluated.append((stock_id, score))
                if ok:
                    candidates.append((stock_id, score))
            except Exception:
                continue

        candidates.sort(key=lambda x: x[1], reverse=True)
        all_evaluated.sort(key=lambda x: x[1], reverse=True)

        # 若魚過濾濾掉全部股票，all_evaluated 為空 → 直接對 all_data 評分一次
        # 這樣收盤/休眠報告至少能顯示當日最高分的股票
        if not all_evaluated and all_data:
            for stock_id in all_data:
                try:
                    single = {stock_id: all_data[stock_id]}
                    ok, score = _core_check_momentum_entry(
                        single, stock_id, check_date, accum_price=None)
                    all_evaluated.append((stock_id, score))
                except Exception:
                    continue
            all_evaluated.sort(key=lambda x: x[1], reverse=True)

        # 若 momentum check 也全掛（缺 inst_buy 等欄位），用 fish score 直接排
        if not all_evaluated and fish_scores:
            fish_ranked = []
            for stock_id, score_by_date in fish_scores.items():
                if not score_by_date: continue
                latest_date = max(score_by_date.keys())
                val = score_by_date[latest_date]
                latest_fish = val[0] if isinstance(val, tuple) else val
                fish_ranked.append((stock_id, latest_fish))
            fish_ranked.sort(key=lambda x: x[1], reverse=True)
            # 取前 3 名作為 near_misses（momentum_score=0 代表未通過動能檢查）
            all_evaluated = [(s, 0.0) for s, _ in fish_ranked[:self.top_n]]

        # 最終備援：法人資料全失敗時，依近 5 日漲幅列出前三（價格存在即可）
        # 確保收盤/睡前報告「無符合標的」時仍有前三名可看
        if not all_evaluated and all_data:
            all_evaluated = inst_core.rank_by_price_return(all_data, top_n=self.top_n)

        self._save_screening_summary(candidates, all_evaluated, fish_scores, check_date.isoformat())

        # 資料降級警報：FinMind 失敗改用 TWSE 備援、或法人資料缺損過多時通知（一天一次）
        twse_cnt = self._data_stats.get("inst_source", {}).get("twse", 0)
        missing = self._data_stats.get("stocks_missing_inst", 0)
        have = self._data_stats.get("stocks_with_inst", 0)
        if twse_cnt > 0 or (have + missing > 0 and missing / (have + missing) > 0.2):
            self._notify_once(
                "inst_degraded",
                f"法人資料降級：{twse_cnt} 檔來自 TWSE 備援、{missing} 檔無資料"
                f"（FinMind 法人資料可能異常，最新日期: {self._data_stats.get('latest_inst_date')}）")

        if not candidates:
            return [], all_evaluated[:self.top_n]

        return candidates[:self.top_n], []

    # ================================================================
    # 篩選摘要（供收盤報告用）
    # ================================================================
    def _save_screening_summary(self, candidates, all_evaluated, fish_scores, screen_date):
        qualified_ids = {s for s, _ in candidates}
        evaluated_list = []
        seen = set()
        for stock_id, mom_score in all_evaluated:
            # 已入選的股票不進未達標前三（避免 2633 同時出現在 ✅ 與 ⚠️）
            if stock_id in qualified_ids or stock_id in seen:
                continue
            seen.add(stock_id)
            stock_fish = fish_scores.get(stock_id, {})
            latest_fish = 0.0
            if stock_fish:
                latest_date = max(stock_fish.keys())
                val = stock_fish[latest_date]
                latest_fish = val[0] if isinstance(val, tuple) else val
            evaluated_list.append({
                "stock_id": stock_id,
                "momentum_score": round(mom_score, 4),
                "fish_score": round(latest_fish, 1),
            })

        summary = {
            "screen_date": screen_date,
            "has_qualified": len(candidates) > 0,
            "qualified": [{"stock_id": s, "score": round(sc, 4)} for s, sc in candidates],
            "near_misses": evaluated_list[:self.top_n],
            "data_health": {
                "stocks_with_price": self._data_stats.get("stocks_with_price", 0),
                "stocks_with_inst": self._data_stats.get("stocks_with_inst", 0),
                "stocks_missing_inst": self._data_stats.get("stocks_missing_inst", 0),
                "latest_inst_date": self._data_stats.get("latest_inst_date"),
                "inst_source": self._data_stats.get("inst_source", {}),
                "price_source": self._data_stats.get("price_source", {}),
            },
        }

        summary_path = Path("logs/inst_momentum_screening.json")
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    # ================================================================
    # 停損/停利訊號
    # ================================================================
    def check_exit_signals(self, current_prices: dict) -> dict:
        """
        檢查所有持倉標的，回傳需要賣出的標的與原因。
        使用共用核心 check_position_exit 確保停損/停利邏輯一致。
        current_prices: { stock_id: current_price }
        回傳: { stock_id: "reason_string" }
        """
        signals = {}
        positions = self.state.get("positions", {})
        dl = self._get_dataloader()

        for stock_id, pos in list(positions.items()):
            price = current_prices.get(stock_id)
            if price is None or price <= 0:
                continue

            buy_price = pos.get("buy_price", 0)
            if buy_price <= 0:
                continue

            # 移動停利需要 MA（共用資料層，與回測一致；抓不到時只做硬性停損）
            ma = None
            try:
                end = date.today()
                df, _src = inst_data.get_price_data(
                    dl, stock_id, end - timedelta(days=self.trailing_period + 20), end,
                    cache_path=self._price_cache_dir / f"{stock_id}.pkl",
                    max_stale_days=5, sources=("finmind", "twse"))
                if not df.empty and len(df) >= self.trailing_period:
                    ma = df["close"].rolling(self.trailing_period).mean().iloc[-1]
            except Exception:
                ma = None

            core_positions = {
                stock_id: {
                    "buy_price": buy_price,
                    "shares": pos.get("shares", 0),
                    "buy_date": pos.get("entry_date", ""),
                    "last_roll_date": self.state.get("last_roll_date"),
                }
            }
            price_info = {"close": price}
            if ma is not None and not math.isnan(ma):
                price_info["ma10"] = ma
            tmp_log = []
            proceeds, cost_basis, _ = _core_check_position_exit(
                stock_id, core_positions, price_info, date.today(), 0, tmp_log
            )
            if proceeds > 0 and tmp_log:
                signals[stock_id] = tmp_log[0].get("reason", "出場訊號")

        return signals

    def check_daily_review(self, current_prices: dict) -> dict:
        """每日檢討（本策略停損/停利統一由 check_exit_signals 處理）"""
        return {}

    # ================================================================
    # 主流程 — 由 live_trader_multi.py 每分鐘呼叫
    # ================================================================
    def debug_screen(self, now: datetime):
        """IM_DEBUG=1 且法人動能未啟用（capital=0）時：仍於盤後 13:31-13:45 執行每日
        篩選並寫入 logs/inst_momentum_screening.json，供睡前 TG 報告檢查
        （只搜尋不交易、不主動發 TG；結果由 send_sleep_notification 帶出）。
        """
        is_weekday = now.weekday() < 5
        today_str = now.strftime("%Y-%m-%d")
        if not is_weekday:
            return
        if not (now.hour == 13 and 31 <= now.minute <= 45):
            return
        if not (self.daily_screening or now.weekday() == 4):
            return
        if self.state.get("last_screen_date") == today_str:
            return
        print(f"📡 [INST_MOM][DEBUG] 法人動能未啟用（capital=0），仍執行篩選（IM_DEBUG=1）...")
        candidates, near_misses = self.get_candidates()
        self.state["candidates"] = [{"stock_id": s, "score": sc} for s, sc in candidates]
        self.state["last_screen_date"] = today_str
        self._save_state()
        if candidates:
            names = ", ".join(f"{s}({sc:.2%})" for s, sc in candidates)
            print(f"✅ [INST_MOM][DEBUG] 篩選結果: {names}")
        elif near_misses:
            names = ", ".join(f"{s}({sc:.2%})" for s, sc in near_misses)
            print(f"⚠️ [INST_MOM][DEBUG] 無通過標的，前三候選: {names}")
        else:
            print(f"⚠️ [INST_MOM][DEBUG] 無符合標的")

    def run(self, broker, risk_manager, holdings: dict, now: datetime):
        """
        每分鐘執行一次（由主迴圈呼叫），根據時間觸發不同動作。

        Args:
            broker: 券商 API 實例
            risk_manager: RiskManager 實例
            holdings: 目前庫存 dict { symbol: shares }
            now: 當前時間
        """
        if self.capital <= 0:
            return

        # 同步 instance 參數到共用核心模組（確保回測與實盤一致）
        inst_core.MIN_VOLUME_SHARES = self.min_volume
        inst_core.BUY_RATIO_THRESHOLD = self.buy_ratio
        inst_core.LOOKBACK = self.lookback
        inst_core.STOP_LOSS = self.stop_loss
        inst_core.TRAILING_PERIOD = self.trailing_period

        self.broker = broker
        is_weekday = now.weekday() < 5
        pnl = self._load_pnl()
        today_str = now.strftime("%Y-%m-%d")
        last_screen = self.state.get("last_screen_date")

        # ================================================================
        # 盤後 13:31-13:45 → 篩選候選股
        #   每週模式（預設）：週五執行
        #   每日模式（INST_MOM_DAILY_SCREENING=true）：每個交易日執行
        # ================================================================
        screen_cond = (
            is_weekday and now.hour == 13 and 31 <= now.minute <= 45
            and (self.daily_screening or now.weekday() == 4)
        )
        if screen_cond and last_screen != today_str:
            freq = "每日" if self.daily_screening else "週"
            entry_hint = "明日開盤自動進場" if self.daily_screening else "週一開盤自動進場"
            print(f"📡 [INST_MOM] {freq}盤後篩選法人抬轎標的...")
            candidates, near_misses = self.get_candidates()
            self.state["candidates"] = [{"stock_id": s, "score": sc} for s, sc in candidates]
            self.state["last_screen_date"] = today_str
            self._save_state()

            if candidates:
                names = ", ".join(f"{s}({sc:.2%})" for s, sc in candidates)
                print(f"✅ [INST_MOM] 篩選結果: {names}")
                from utils.telegram import send_telegram_message
                send_telegram_message(
                    f"📡 *法人抬轎動能策略* {freq}篩選結果\n"
                    f"候選標的: {names}\n"
                    f"📅 {entry_hint}"
                )
            elif near_misses:
                names = ", ".join(f"{s}({sc:.2%})" for s, sc in near_misses)
                print(f"⚠️ [INST_MOM] 本{freq}無通過標的，前三列舉（法人買超比）: {names}")
                from utils.telegram import send_telegram_message
                send_telegram_message(
                    f"📡 *法人抬轎動能策略* {freq}篩選結果\n"
                    f"⚠️ 無通過篩選條件標的\n"
                    f"前三候選: {names}\n"
                    f"（搜尋引擎正常運作，惟所有標的均未滿足全部進場條件）"
                )
            else:
                print(f"⚠️ [INST_MOM] 本{freq}無符合標的")
                from utils.telegram import send_telegram_message
                send_telegram_message(f"⚠️ *法人抬轎動能策略* 本{freq}無符合篩選條件的標的")

        # ================================================================
        # 開盤 09:00-09:05 → 執行新倉位進場
        #   每週模式（預設）：週一進場
        #   每日模式（INST_MOM_DAILY_SCREENING=true）：每個交易日進場
        # ================================================================
        entry_cond = (
            is_weekday and now.hour == 9 and now.minute < 5
            and (self.daily_screening or now.weekday() == 0)
        )
        if entry_cond:
            candidates = self.state.get("candidates", [])
            last_entry = self.state.get("last_entry_date")
            positions = self.state.get("positions", {})

            if candidates and last_entry != today_str:
                candidate_ids = {c["stock_id"] for c in candidates}
                current_positions = set(positions.keys())

                # 賣出不再候選的標的
                for old_id in current_positions - candidate_ids:
                    shares = holdings.get(old_id, 0)
                    if shares > 0:
                        try:
                            price = 0
                            if hasattr(broker, "get_current_price"):
                                price = broker.get_current_price(old_id)
                            if price <= 0:
                                df = broker.get_historical_data(old_id, days=1)
                                price = df["close"].iloc[-1] if not df.empty else 0
                            broker.place_order(old_id, "sell", shares)
                            self._record_trade("SELL", old_id, shares, price, pnl)
                            print(f"📤 [INST_MOM] 換股賣出 {old_id} {shares} 股")
                        except Exception as e:
                            print(f"❌ [INST_MOM] 賣出 {old_id} 失敗: {e}")

                # 買入新候選標的（若不在庫存中）
                per_stock_cap = self.capital / self.top_n
                for cand in candidates:
                    sid = cand["stock_id"]
                    if sid in positions:
                        continue  # 已有倉位

                    # 取得現價
                    try:
                        if hasattr(broker, "get_current_price"):
                            price = broker.get_current_price(sid)
                        else:
                            df = broker.get_historical_data(sid, days=5)
                            price = df["close"].iloc[-1] if not df.empty else 0
                    except Exception:
                        continue

                    if price <= 0:
                        continue

                    shares = int(per_stock_cap / price)
                    if shares <= 0:
                        continue

                    try:
                        broker.place_order(sid, "buy", shares)
                        self._record_trade("BUY", sid, shares, price, pnl)
                        print(f"📥 [INST_MOM] 買入 {sid} {shares} 股 @ {price:.0f} (預算 {per_stock_cap:.0f})")
                        positions[sid] = {
                            "buy_price": price,
                            "shares": shares,
                            "cost": price * shares,
                            "entry_date": today_str,
                        }
                    except Exception as e:
                        print(f"❌ [INST_MOM] 買入 {sid} 失敗: {e}")

                self.state["positions"] = positions
                self.state["last_entry_date"] = today_str
                self._save_state()

        # ================================================================
        # 盤中每日 → 停損/停利監控
        # ================================================================
        if is_weekday and (now.hour >= 9 and now.hour < 13 or (now.hour == 13 and now.minute <= 30)):
            positions = self.state.get("positions", {})
            if not positions:
                return

            # 取得所有持倉標的現價
            current_prices = {}
            for sid in positions:
                try:
                    if hasattr(broker, "get_current_price"):
                        price = broker.get_current_price(sid)
                    else:
                        df = broker.get_historical_data(sid, days=1)
                        price = df["close"].iloc[-1] if not df.empty else 0
                    if price > 0:
                        current_prices[sid] = price
                except Exception:
                    continue

            if not current_prices:
                return

            profit_roll_months = int(os.getenv("INST_MOM_PROFIT_ROLL_MONTHS",
                                        os.getenv("PROFIT_ROLL_MONTHS", "0")))
            profit_roll_pct = float(os.getenv("INST_MOM_PROFIT_ROLL_PCT",
                                       os.getenv("PROFIT_ROLL_PERCENTAGE", "1.0")))
            loser_ban_days = int(os.getenv("INST_MOM_LOSER_BAN_DAYS", "0"))

            def _execute_sell(sid, reason):
                shares = holdings.get(sid, 0)
                if shares <= 0:
                    return
                pos = self.state.get("positions", {}).get(sid)
                if not pos:
                    return

                price = current_prices.get(sid, 0)
                broker.place_order(sid, "sell", shares)
                self._record_trade("SELL", sid, shares, price, pnl)
                print(f"🛑 [INST_MOM] 觸發出場: {sid} ({reason}), 賣出 {shares} 股")
                if sid in self.state["positions"]:
                    del self.state["positions"][sid]

                buy_price = pos.get("buy_price", 0)
                pnl_amount = (price - buy_price) * shares if price > 0 and buy_price > 0 else 0

                if loser_ban_days > 0 and pnl_amount < 0:
                    inst_core.add_loser_ban(sid, now.date(),
                                            self.state.setdefault("loser_ban", {}),
                                            loser_ban_days)

                if pnl_amount > 0:
                    roll_months = profit_roll_months
                    roll_pct = profit_roll_pct
                    can_roll, rolled = _core_compute_profit_roll(
                        pnl_amount, roll_months, roll_pct,
                        self.state.get("last_roll_date"), now.date())
                    if can_roll and rolled > 0:
                        self.capital += rolled
                        self.state["last_roll_date"] = now.date().isoformat()
                        print(f"💰 [INST_MOM] 獲利滾入: {sid} +{rolled:.0f} → 資金池 {self.capital:.0f} (M={roll_months}, P={roll_pct:.0%})")
                        _core_log_capital_roll("INST_MOM_ROLL", sid, rolled, self.capital,
                                               now.strftime("%Y-%m-%d %H:%M"))

                self._save_state()

                from utils.telegram import send_trade_alert
                send_trade_alert(sid, "SELL", current_prices.get(sid, 0), shares, "INST_MOM")

            exit_signals = self.check_exit_signals(current_prices)
            for sid, reason in exit_signals.items():
                try:
                    _execute_sell(sid, reason)
                except Exception as e:
                    print(f"❌ [INST_MOM] 出場 {sid} 失敗: {e}")
