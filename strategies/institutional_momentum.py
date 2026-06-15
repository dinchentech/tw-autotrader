"""
Institutional Momentum Strategy — 法人抬轎動能策略

不同於固定標的策略，此策略每週動態選股：
  1. 週五盤後篩選（流動性 > 2,000 張、法人買超 > 3%、創 20 日新高 + 站穩 MA20）
  2. 依投信+外資買超佔比排序，選前 N 名（預設 2 檔）
  3. 週一開盤買入，每檔配置 (alloc / N)
  4. 每日監控：硬性停損 -7%、跌破 MA10 移動停利
"""
import os
import json
import time
import requests
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path

from FinMind.data import DataLoader
from FinMind.schema.data import Dataset


class InstitutionalMomentumStrategy:
    """
    法人抬轎動能策略 — 動態選股 + 獨立資金池管理

    屬於 Group 2（獨立資金），有獨立的起始本金、損益追蹤。
    """

    def __init__(self, broker=None, capital=0, top_n=2):
        self.broker = broker
        self.capital = capital                     # 獨立起始資金（0 = 不啟用）
        self.top_n = top_n                         # 持有標的數量
        self.state_file = Path("data/inst_momentum_state.json")
        self.pnl_file = Path("data/inst_momentum_pnl.json")

        # 預設參數（可從 .env 覆蓋）
        self.min_volume = int(os.getenv("INST_MOM_MIN_VOLUME", "2000"))         # 張
        self.buy_ratio = float(os.getenv("INST_MOM_BUY_RATIO", "0.03"))         # 3%
        self.lookback = int(os.getenv("INST_MOM_LOOKBACK", "20"))               # 天
        self.stop_loss = float(os.getenv("INST_MOM_STOP_LOSS", "0.07"))         # -7%
        self.trailing_period = int(os.getenv("INST_MOM_TRAILING_PERIOD", "10")) # MA10
        self.exclude_etf = os.getenv("INST_MOM_EXCLUDE_ETF", "true").lower() == "true"  # 預設排除 ETF

        # 內部狀態
        self.state = self._load_state()
        self.finmind_token = os.getenv("FINMIND_API_TOKEN", "")

        # TWSE 備援快取（實例層級，避免跨篩選汙染）
        self._twse_cache = {}           # { date_str: { stock_id: { name: {buy, sell} } } }
        self._twse_cache_built = False
        self._data_fail_notified = {}   # { source_key: date_str } 同一來源一天只通知一次

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

    MAX_STOCKS = 270  # 前 270 大股票，控制 FinMind API 呼叫量（每檔 2 次 API → 270 * 2 = 540 < 600/hr）

    def _get_all_stock_ids(self) -> list:
        """回傳上市普通股 stock_id 列表（前 MAX_STOCKS 檔，控制 API 配額）"""
        dl = self._get_dataloader()
        df = dl.taiwan_stock_info()
        # 只保留上市普通股（type="twse" 且 stock_id 為 4 位數字）
        df = df[df["type"] == "twse"]
        ids = [s.strip() for s in df["stock_id"] if s.strip().isdigit() and len(s.strip()) == 4]
        # 排除 ETF（代號開頭為 0，如 0050、00878），由 .env INST_MOM_EXCLUDE_ETF 控制
        if self.exclude_etf:
            ids = [s for s in ids if not s.startswith("0")]
        return sorted(set(ids))[:self.MAX_STOCKS]

    def _get_price_data(self, stock_id: str, days: int = 30) -> pd.DataFrame:
        """取得個股日 K 資料，FinMind → TWSE 備援"""
        end = date.today()
        start = end - timedelta(days=days)
        df = self._fetch_price_finmind(stock_id, start, end)
        if not df.empty:
            return df.sort_values("date").reset_index(drop=True)
        df = self._fetch_price_twse(stock_id, start, end)
        if df.empty:
            self._notify_once("price_fail", f"股價資料全線失效：{stock_id}，FinMind 與 TWSE 皆無法取得")
        return df

    def _fetch_price_finmind(self, stock_id: str, start: date, end: date) -> pd.DataFrame:
        dl = self._get_dataloader()
        try:
            df = dl.taiwan_stock_daily(
                stock_id=stock_id,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
        except Exception:
            return pd.DataFrame()
        if df.empty:
            return df
        rename = {
            "Trading_Volume": "volume",
            "Trading_money": "amount",
            "Trading_turnover": "turnover",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        return df

    def _fetch_price_twse(self, stock_id: str, start: date, end: date) -> pd.DataFrame:
        """從 TWSE STOCK_DAY API 取得個股日 K（回傳格式與 FinMind 統一後一致）"""
        try:
            dt_str = start.strftime("%Y%m01")
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
                    # 日期格式: 115/06/01 → 2026-06-01（民國年+1911）
                    parts = row[0].split("/")
                    d = f"{int(parts[0])+1911}-{parts[1]}-{parts[2]}"
                    if d < start.isoformat() or d > end.isoformat():
                        continue
                    rows.append({
                        "date": d,
                        "stock_id": stock_id,
                        "open": float(row[3].replace(",", "")),
                        "max": float(row[4].replace(",", "")),
                        "min": float(row[5].replace(",", "")),
                        "close": float(row[6].replace(",", "")),
                        "volume": int(row[1].replace(",", "")),
                    })
                except (ValueError, IndexError):
                    continue
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame(rows)
            return df.sort_values("date").reset_index(drop=True)
        except Exception:
            return pd.DataFrame()

    def _get_institutional_data(self, stock_id: str, days: int = 10) -> pd.DataFrame:
        """取得個股法人買賣資料，FinMind → TWSE 備援"""
        dl = self._get_dataloader()
        end = date.today()
        start = end - timedelta(days=days)
        try:
            df = dl.taiwan_stock_institutional_investors(
                stock_id=stock_id,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
            if not df.empty:
                return df
        except Exception:
            pass
        # FinMind 失敗 → TWSE 備援
        df = self._get_institutional_data_twse(stock_id, days)
        if df.empty:
            self._notify_once("inst_fail", f"法人資料全線失效：{stock_id}，FinMind 與 TWSE 皆無法取得")
        return df

    # ================================================================
    # TWSE 法人資料備援（FinMind 額度用罄時自動切換）
    # ================================================================
    def _build_twse_inst_cache(self, end_date: date, lookback_days: int = 15):
        """初始建立 TWSE 快取：一次抓取近 N 天全市場法人買賣超。

        後續呼叫 _refresh_twse_cache() 只補最新一天、淘汰最舊一天。
        """
        self._twse_cache = {}
        for i in range(lookback_days):
            d = end_date - timedelta(days=i)
            dt_str = d.strftime("%Y%m%d")
            day_data = self._fetch_twse_day(dt_str)
            if day_data:
                self._twse_cache[dt_str] = day_data

        self._twse_cache_built = True
        print(f"✅ [INST_MOM] TWSE 快取建立 ({len(self._twse_cache)} 天, "
              f"{sum(len(v) for v in self._twse_cache.values())} 筆)")

    def _refresh_twse_cache(self, today: date, max_days: int = 15):
        """增量更新：只抓今天(或最近未緩存日期)的資料，淘汰最舊的一天。"""
        today_str = today.strftime("%Y%m%d")
        # 如果今天還未快取 → 抓
        if today_str not in self._twse_cache:
            day_data = self._fetch_twse_day(today_str)
            if day_data:
                self._twse_cache[today_str] = day_data
        # 超過 max_days → 刪最舊的
        keys = sorted(self._twse_cache.keys())
        while len(keys) > max_days:
            oldest = keys.pop(0)
            del self._twse_cache[oldest]

    def _fetch_twse_day(self, dt_str: str) -> dict:
        """呼叫 TWSE T86 API 抓單日全市場法人資料，回傳 {stock_id: {name: {buy, sell}}}"""
        try:
            url = "https://www.twse.com.tw/fund/T86"
            params = {"response": "json", "date": dt_str}
            resp = requests.get(url, params=params, headers={
                "User-Agent": "Mozilla/5.0",
            }, timeout=10)
            data = resp.json()
            if data.get("stat") != "OK" or not data.get("data"):
                return {}
            day_data = {}
            for row in data["data"]:
                stock_id = row[0].strip()
                buy_foreign = self._safe_int(row[2]) + (self._safe_int(row[8]) if len(row) > 8 else 0)
                sell_foreign = self._safe_int(row[3]) + (self._safe_int(row[9]) if len(row) > 9 else 0)
                day_data[stock_id] = {
                    "外資": {"buy": buy_foreign, "sell": sell_foreign},
                    "投信": {"buy": self._safe_int(row[4]), "sell": self._safe_int(row[5])},
                    "自營商": {"buy": self._safe_int(row[6]), "sell": self._safe_int(row[7])},
                }
            return day_data
        except Exception:
            return {}

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

    def _safe_int(self, val) -> int:
        if isinstance(val, str):
            val = val.replace(",", "").strip()
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    def _get_institutional_data_twse(self, stock_id: str, days: int = 10) -> pd.DataFrame:
        """從 TWSE 快取中取出個股法人買賣資料，回傳格式與 FinMind 一致"""
        today = date.today()
        if not self._twse_cache_built:
            self._build_twse_inst_cache(today, lookback_days=days + 5)
        else:
            self._refresh_twse_cache(today, max_days=days + 5)

        rows = []
        for date_str, stocks in self._twse_cache.items():
            if stock_id in stocks:
                d = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                for name, data in stocks[stock_id].items():
                    rows.append({
                        "date": d,
                        "stock_id": stock_id,
                        "name": name,
                        "buy": data["buy"],
                        "sell": data["sell"],
                    })

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    # ================================================================
    # 核心篩選邏輯
    # ================================================================
    def get_candidates(self) -> list:
        """
        篩選出符合條件的候選股票，依法人買超佔比排序，回傳前 N 名。
        回傳格式: [(stock_id, score), ...]
        """
        all_ids = self._get_all_stock_ids()
        candidates = []

        # 逐檔篩選（價格 + 法人資料，含 FinMind → TWSE 備援）
        for stock_id in all_ids:
            try:
                # 1. 價格資料
                df_price = self._get_price_data(stock_id, days=self.lookback + 10)
                if df_price.empty or len(df_price) < self.lookback:
                    continue

                # 最近 5 日
                recent_5 = df_price.tail(5)
                # 流動性：近 5 日平均成交量 > min_volume（張）
                avg_volume = recent_5["volume"].mean() / 1000  # 股 → 張
                if avg_volume < self.min_volume:
                    continue

                close = df_price["close"].values
                latest_close = close[-1]

                # 創 20 日新高
                if latest_close < close[-self.lookback:].max():
                    continue

                # 站穩 MA20
                ma20 = pd.Series(close).rolling(self.lookback).mean().iloc[-1]
                if latest_close <= ma20:
                    continue

                # 2. 法人資料（近 5 日，FinMind → TWSE 備援）
                df_inst = self._get_institutional_data(stock_id, days=10)
                if df_inst.empty:
                    continue

                # 只取近 5 日交易日
                inst_dates = sorted(df_inst["date"].unique())[-5:]
                df_inst_recent = df_inst[df_inst["date"].isin(inst_dates)]

                # 投信 + 外資 淨買超總額
                mask = df_inst_recent["name"].isin(["投信", "外資"])
                institutional_net_buy = df_inst_recent[mask]["buy"].sum() - df_inst_recent[mask]["sell"].sum()

                # 近 5 日總成交量（張）
                total_volume_5 = recent_5["volume"].sum() / 1000  # 股 → 張

                if institutional_net_buy <= 0 or total_volume_5 <= 0:
                    continue

                buy_ratio = institutional_net_buy / total_volume_5

                if buy_ratio < self.buy_ratio:
                    continue

                score = round(buy_ratio, 4)
                candidates.append((stock_id, score))

            except Exception:
                continue

        # 依分數降序排序，取前 N 名
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:self.top_n]

    # ================================================================
    # 停損/停利訊號
    # ================================================================
    def check_exit_signals(self, current_prices: dict) -> dict:
        """
        檢查所有持倉標的，回傳需要賣出的標的與原因。
        current_prices: { stock_id: current_price }
        回傳: { stock_id: "reason_string" }
        """
        signals = {}
        positions = self.state.get("positions", {})

        for stock_id, pos in positions.items():
            price = current_prices.get(stock_id)
            if price is None:
                continue

            buy_price = pos.get("buy_price", 0)
            if buy_price <= 0:
                continue

            # 硬性停損 -7%
            loss_pct = (price - buy_price) / buy_price
            if loss_pct <= -self.stop_loss:
                signals[stock_id] = f"硬性停損 {loss_pct:.1%}"
                continue

            # 移動停利：跌破 MA10
            try:
                df_price = self._get_price_data(stock_id, days=self.trailing_period + 5)
                if not df_price.empty and len(df_price) >= self.trailing_period:
                    ma10 = df_price["close"].rolling(self.trailing_period).mean().iloc[-1]
                    if price < ma10 and loss_pct > 0:
                        signals[stock_id] = f"跌破 MA10 ({ma10:.0f}) 移動停利 {loss_pct:.1%}"
            except Exception:
                continue

        return signals

    # ================================================================
    # 主流程 — 由 live_trader_multi.py 每分鐘呼叫
    # ================================================================
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

        self.broker = broker
        is_weekday = now.weekday() < 5
        pnl = self._load_pnl()
        today_str = now.strftime("%Y-%m-%d")
        last_screen = self.state.get("last_screen_date")

        # ================================================================
        # 週五 13:31-13:45 → 盤後篩選（只在未篩選過時執行）
        # ================================================================
        if is_weekday and now.weekday() == 4 and now.hour == 13 and 31 <= now.minute <= 45:
            if last_screen != today_str:
                print("📡 [INST_MOM] 週五盤後篩選法人抬轎標的...")
                candidates = self.get_candidates()
                self.state["candidates"] = [{"stock_id": s, "score": sc} for s, sc in candidates]
                self.state["last_screen_date"] = today_str
                self._save_state()

                if candidates:
                    names = ", ".join(f"{s}({sc:.2%})" for s, sc in candidates)
                    print(f"✅ [INST_MOM] 篩選結果: {names}")
                    from utils.telegram import send_telegram_message
                    send_telegram_message(
                        f"📡 *法人抬轎動能策略* 週篩選結果\n"
                        f"候選標的: {names}\n"
                        f"📅 週一開盤自動進場"
                    )
                else:
                    print("⚠️ [INST_MOM] 本週無符合標的")
                    from utils.telegram import send_telegram_message
                    send_telegram_message("⚠️ *法人抬轎動能策略* 本週無符合篩選條件的標的")

        # ================================================================
        # 週一 09:00-09:05 → 執行新倉位進場
        # ================================================================
        if is_weekday and now.weekday() == 0 and now.hour == 9 and now.minute < 5:
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

            exit_signals = self.check_exit_signals(current_prices)
            for sid, reason in exit_signals.items():
                shares = holdings.get(sid, 0)
                if shares <= 0:
                    continue

                try:
                    price = current_prices.get(sid, 0)
                    broker.place_order(sid, "sell", shares)
                    self._record_trade("SELL", sid, shares, price, pnl)
                    print(f"🛑 [INST_MOM] 觸發出場: {sid} ({reason}), 賣出 {shares} 股")
                    if sid in self.state["positions"]:
                        del self.state["positions"][sid]
                    self._save_state()

                    from utils.telegram import send_trade_alert
                    send_trade_alert(sid, "SELL", current_prices.get(sid, 0), shares, "INST_MOM")
                except Exception as e:
                    print(f"❌ [INST_MOM] 出場 {sid} 失敗: {e}")
