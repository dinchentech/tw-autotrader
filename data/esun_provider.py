"""E.Sun (玉山證券) broker provider — market data + order execution

Wraps esun_marketdata + esun_trade SDKs into the same interface as kgi_mock/kgi_real.
Used when BROKER=esun in .env.

Config sources (priority order):
  1. ESUN_CONFIG_INI env var → read that .ini file directly
  2. esun_sdk/config.simulation.ini.example (auto-detect, if exists)
  3. Individual ESUN_* env vars (fallback)

The .p12 cert path in the loaded .ini is overridden by ESUN_CERT_PATH (if set)
or auto-resolved to esun_sdk/*.p12 (if the default ini is used).

Passwords are stored in system keyring. Can be pre-populated via env vars:
  ESUN_ACCOUNT_PASSWORD=...
  ESUN_CERT_PASSWORD=...

One-time interactive password setup:
  python -c "from data.esun_provider import EsunProvider; EsunProvider().interactive_setup()"
"""

import os
import sys
import time
import glob
import pandas as pd
import requests
from datetime import datetime, timedelta
from configparser import ConfigParser

from esun_marketdata import EsunMarketdata
from esun_trade.sdk import SDK as EsunTrade
from esun_trade.order import OrderObject
from esun_trade.constant import Action, APCode, PriceFlag, Trade, BSFlag

# Default path relative to project root
_DEFAULT_INI = "esun_sdk/config.simulation.ini"


def _resolve_cert_path(cfg):
    """Resolve .p12 cert path: env override > auto-detect in esun_sdk/ > ini value."""
    env_path = os.getenv("ESUN_CERT_PATH")
    if env_path:
        return env_path
    # Auto-detect: if using default ini, look for any .p12 in esun_sdk/
    ini_path = cfg.get("Cert", "Path", fallback="")
    if not ini_path or ini_path.strip().startswith(";"):
        p12_files = glob.glob("esun_sdk/*.p12")
        if p12_files:
            return os.path.abspath(p12_files[0])
    return ini_path


def load_config():
    """Load E.Sun SDK config from best available source."""
    cfg = ConfigParser()

    # Source 1: explicit ESUN_CONFIG_INI env var
    ini_file = os.getenv("ESUN_CONFIG_INI")
    if ini_file and os.path.exists(ini_file):
        cfg.read(ini_file)
        _apply_cert_override(cfg)
        return cfg

    # Source 2: auto-detect default ini
    if os.path.exists(_DEFAULT_INI):
        cfg.read(_DEFAULT_INI)
        _apply_cert_override(cfg)
        return cfg

    # Source 2b: fallback to .example (使用者還沒複製 .ini 時可暫用)
    example_ini = "esun_sdk/config.simulation.ini.example"
    if os.path.exists(example_ini):
        cfg.read(example_ini)
        _apply_cert_override(cfg)
        return cfg

    # Source 3: build from individual env vars
    cfg.add_section("Core")
    cfg.set("Core", "Entry", os.getenv("ESUN_ENTRY", ""))
    cfg.set("Core", "Environment", os.getenv("ESUN_ENVIRONMENT", "simulation"))
    cfg.add_section("Cert")
    cfg.set("Cert", "Path", _resolve_cert_path(cfg))
    cfg.add_section("Api")
    cfg.set("Api", "Key", os.getenv("ESUN_API_KEY", ""))
    cfg.set("Api", "Secret", os.getenv("ESUN_API_SECRET", ""))
    cfg.add_section("User")
    cfg.set("User", "Account", os.getenv("ESUN_ACCOUNT", ""))
    return cfg


def _apply_cert_override(cfg):
    """Override cert path in loaded config with resolved value."""
    if not cfg.has_section("Cert"):
        cfg.add_section("Cert")
    resolved = _resolve_cert_path(cfg)
    if resolved:
        cfg.set("Cert", "Path", resolved)


class EsunProvider:
    """玉山證券 broker provider — 符合 KGI 相容介面"""

    def __init__(self):
        self.config = load_config()
        self._marketdata = None
        self._trade_sdk = None
        self._logged_in = False

        # Pre-populate keyring from env vars (for headless/Docker usage)
        self._seed_keyring_from_env()

    # ── keyring helpers ──────────────────────────────────────────

    @staticmethod
    def _ensure_keyring():
        """Force CryptFileKeyring globally so both our code and SDK use the same backend + key."""
        from keyring import set_keyring
        from keyrings.cryptfile.cryptfile import CryptFileKeyring
        os.environ.setdefault("PYTHON_KEYRING_BACKEND",
                              "keyrings.cryptfile.cryptfile.CryptFileKeyring")
        os.environ.setdefault("KEYRING_CRYPTFILE_PASSWORD", "tw-autotrader-esun")
        kr = CryptFileKeyring()
        kr.keyring_key = os.environ["KEYRING_CRYPTFILE_PASSWORD"]
        set_keyring(kr)

    def _seed_keyring_from_env(self):
        """If ESUN_ACCOUNT_PASSWORD / ESUN_CERT_PASSWORD set, store in keyring."""
        from keyring import set_password, get_password
        from esun_marketdata.util import TRADE_SDK_ACCOUNT_KEY, TRADE_SDK_CERT_KEY

        account = self.config.get("User", "Account", fallback="") if self.config.has_section("User") else ""
        if not account:
            return

        self._ensure_keyring()

        ap = os.getenv("ESUN_ACCOUNT_PASSWORD")
        if ap and not get_password(TRADE_SDK_ACCOUNT_KEY, account):
            set_password(TRADE_SDK_ACCOUNT_KEY, account, ap)

        cp = os.getenv("ESUN_CERT_PASSWORD")
        if cp and not get_password(TRADE_SDK_CERT_KEY, account):
            set_password(TRADE_SDK_CERT_KEY, account, cp)

    @classmethod
    def interactive_setup(cls):
        """Interactive password setup (run once)."""
        from esun_marketdata.util import ft_set_password as md_setpwd
        from esun_trade.util import ft_set_password as tr_setpwd
        cfg = load_config()
        account = cfg.get("User", "Account", fallback="") if cfg.has_section("User") else ""
        if not account:
            print("Cannot determine ESUN_ACCOUNT. Check that esun_sdk/config.simulation.ini.example exists or set ESUN_ACCOUNT env var.")
            return
        print(f"Setting keyring passwords for account {account}…")
        md_setpwd(account)
        tr_setpwd(account)
        print("Done. Passwords stored in system keyring.")

    # ── login ────────────────────────────────────────────────────

    def login(self):
        """Login to both market-data and trade SDKs."""
        if self._logged_in:
            return
        try:
            self._marketdata = EsunMarketdata(self.config)
            self._marketdata.login()
        except ValueError as e:
            error_msg = str(e)
            if "AGA0000" in error_msg or "系統維護" in error_msg:
                print(f"\n❌ 玉山 API 維護中（08:00-13:00）")
                print(f"   錯誤訊息: {error_msg}")
                print(f"   程式將在 3 分鐘後自動退出，請避開維護時間再重啟")

                # 發送 Telegram 通知
                bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
                chat_id = os.getenv("TELEGRAM_CHAT_ID")
                if bot_token and chat_id:
                    msg = (
                        f"⚠️ *玉山 API 維護中*\n\n"
                        f"錯誤: {error_msg}\n\n"
                        f"維護時間: 08:00-13:00\n"
                        f"程式將在 3 分鐘後退出\n"
                        f"請避開維護時間再重啟\n\n"
                        f"⏰ 當前時間: {datetime.now().strftime('%H:%M')}"
                    )
                    try:
                        requests.post(
                            f"https://api.telegram.org/bot{bot_token}/sendMessage",
                            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                            timeout=10)
                    except Exception:
                        pass  # 通知失敗不影響主流程

                # 延遲 3 分鐘後退出
                time.sleep(180)
                sys.exit(1)
            else:
                # 其他 ValueError 直接拋出
                raise
        try:
            self._trade_sdk = EsunTrade(self.config)
            self._trade_sdk.login()
        except Exception as e:
            print(f"⚠️  E.Sun trade SDK login failed (market data still works): {e}")
        self._logged_in = True

    # ── data helpers ─────────────────────────────────────────────

    @staticmethod
    def _candles_to_df(data_list):
        """Convert E.Sun candles JSON → DataFrame with columns open/high/low/close/volume."""
        rows = []
        for d in data_list:
            rows.append({
                "open":   float(d.get("open", 0)),
                "high":   float(d.get("high", 0)),
                "low":    float(d.get("low", 0)),
                "close":  float(d.get("close", 0)),
                "volume": float(d.get("volume", 0)),
            })
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, index=[pd.to_datetime(d["date"]) for d in data_list])
        return df

    # ── market data interface ────────────────────────────────────

    def get_current_price(self, symbol: str) -> float:
        """即時報價（最後成交價）"""
        self.login()
        try:
            q = self._marketdata.rest_client.stock.intraday.quote(symbol=symbol)
            return float(q.get("lastPrice", 0))
        except Exception as e:
            print(f"❌ E.Sun get_current_price error: {e}")
            return 0.0

    def get_historical_data(self, symbol: str, days: int = 30) -> pd.DataFrame:
        """歷史日 K (OHLCV) — 用於初始化累積資料"""
        return self.get_historical_range(symbol, 
            start=(datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"))

    def get_historical_range(self, symbol: str, start: str = "2023-01-01",
                              end: str = "") -> pd.DataFrame:
        """歷史日 K 起訖日期版 — 用於回測"""
        self.login()
        try:
            resp = self._marketdata.rest_client.stock.historical.candles(
                symbol=symbol,
                **{"from": start},
                to=end or datetime.now().strftime("%Y-%m-%d"),
                timeframe="D",
                fields="open,high,low,close,volume",
            )
            df = self._candles_to_df(resp.get("data", []))
            if not df.empty:
                df = df.sort_index()
            return df
        except Exception as e:
            print(f"❌ E.Sun get_historical_range error: {e}")
            return pd.DataFrame()

    def get_minute_bars(self, symbol: str, minutes: int = 60) -> pd.DataFrame:
        """盤中分鐘 K (OHLCV) — 用於即時訊號計算"""
        self.login()
        try:
            resp = self._marketdata.rest_client.stock.intraday.candles(
                symbol=symbol, timeframe="1"
            )
            data = resp.get("data", [])
            if not data:
                return pd.DataFrame()
            if len(data) > minutes:
                data = data[-minutes:]
            return self._candles_to_df(data)
        except Exception as e:
            print(f"❌ E.Sun get_minute_bars error: {e}")
            return pd.DataFrame()

    # ── order execution interface ────────────────────────────────

    def place_order(self, symbol: str, action: str, quantity: int):
        """下單（限價），依股數自動選擇盤中零股或整股"""
        if self._trade_sdk is None:
            print("❌ E.Sun trade SDK not available – login failed earlier")
            return {"error": "trade SDK not available"}

        self.login()
        try:
            buy_sell = Action.Buy if action.upper() == "BUY" else Action.Sell
            price = self.get_current_price(symbol)
            if price <= 0:
                return {"error": "cannot get current price"}

            # 999 股以下走盤中零股，以上走整股
            if quantity <= 999:
                ap_code = APCode.IntradayOdd
                order_type = "盤中零股"
            else:
                ap_code = APCode.Common
                order_type = "整股"
                # 整股四捨五入至整張，ESun Common APCode 以「張」為單位
                if quantity % 1000 >= 500:
                    quantity = (quantity // 1000) + 1
                    print(f"↻  {symbol} {quantity * 1000} 股餘數 ≥500，進位至 {quantity} 張")
                else:
                    lots = quantity // 1000
                    if lots == 0:
                        return {"error": "quantity too small for board lot order"}
                    if quantity % 1000 > 0:
                        print(f"↻  {symbol} {quantity} 股餘數 <500，捨去為 {lots} 張")
                    quantity = lots

            order = OrderObject(
                buy_sell=buy_sell,
                price=price,
                stock_no=symbol,
                quantity=quantity,
                ap_code=ap_code,
                bs_flag=BSFlag.ROD,
                price_flag=PriceFlag.Limit,
                trade=Trade.Cash,
                user_def="tw-autotrader",
            )
            result = self._trade_sdk.place_order(order)
            display_qty = quantity * 1000 if ap_code == APCode.Common else quantity
            print(f"✅ E.Sun 下單成功: {order_type} {action} {symbol} {display_qty} 股 @ {price:.2f}")
            return result
        except Exception as e:
            print(f"❌ E.Sun 下單失敗: {e}")
            return {"error": str(e)}
