# TW AutoTrader — Agent Guide

## Quick start

```bash
# Install
pip install -r requirements.txt
pip install python-dotenv yfinance tqdm

# Setup
cp .env.example.txt .env  # fill in your API keys

# Backtest (Yahoo Finance)
python backtest.py --strategy ma_cross --fast_period 5 --slow_period 30

# Backtest (FinMind)
python backtest_finmind.py          # defaults: 2330, 2023-01-01

# Live trading — multi-symbol (recommended entrypoint)
python live_trader_multi.py         # reads PORTFOLIO from .env

# Live trading — single symbol
python live_trader_finmind.py --symbol 2330 --strategy vwap

# Tests
python -m unittest test.test_strategies
```

## Entrypoints

| File | Purpose |
|------|---------|
| `live_trader_multi.py` | **Primary live trader** — multi-symbol, multi-strategy, monthly budget, pyramid scaling, dual notifications (Telegram + LINE) |
| `live_trader_finmind.py` | Single-symbol FinMind live trader (older, uses FinMind class-based strategies) |
| `backtest.py` | Yahoo Finance backtest with CLI param override |
| `backtest_finmind.py` | FinMind backtest (uses function-based strategies) |

## ⚠️ Dual strategy system (biggest gotcha)

There are **two parallel strategy implementations** — they are NOT interchangeable:

| Location | Style | Where used |
|----------|-------|-----------|
| `strategies/*.py` (e.g. `vwap_deviation.py`, `ma_cross.py`, `bollinger.py`, `breakout.py`) | **Function-based**: takes `pd.DataFrame`, returns `pd.DataFrame` with `signal` column | `backtest.py`, `live_trader_multi.py`, `backtest_finmind.py` |
| `strategies/*_strategy.py` (e.g. `vwap_strategy.py`, `ma_cross_strategy.py`, `bollinger_strategy.py`, `breakout_strategy.py`) | **Class-based**: extends `FinMind.strategies.BackTest`, has `.trade()` method returning -1/0/1 | `live_trader_finmind.py`, `test/test_strategies.py` |

When modifying a strategy, check which files import it. The function-based ones live under the plain name (e.g. `strategies/ma_cross.py`), the class-based ones have `_strategy` suffix.

## Config

All config goes in `.env`. No hardcoded secrets. The file is loaded via `dotenv.load_dotenv()` at each entrypoint's `if __name__ == "__main__"` block. Every strategy parameter can be overridden via `.env` keys (see `.env.example.txt`).

Key env vars:
- `BROKER=kgi|esun` — broker selection: `kgi` (default, uses KGI mock/real) or `esun` (uses E.Sun API for market data + trading)
- `USE_REAL_API=true` — switches from `kgi_mock` to `kgi_real` (only meaningful when `BROKER=kgi`)
- `FINMIND_API_TOKEN` — required for FinMind data (market filter, backtest)
- `MARKET_TREND_FILTER=true` — enables MA200 index filter before buying
- `PORTFOLIO=0050:bollinger,2330:ma_cross,...` — multi-trader stock allocation

## Architecture notes

- **Broker selection**: `BROKER=kgi` (default) or `BROKER=esun` in `.env`. When `BROKER=esun`, both market data and order execution go through E.Sun API; `USE_REAL_API` is forced `true`.
- **KGI API**: `data/kgi_mock.py` (mock) / `data/kgi_real.py` (real). Selected via `BROKER=kgi` + `USE_REAL_API` env var. `kgi_real.py` has placeholder endpoints — real URLs must be confirmed with KGI.
- **E.Sun API** (`BROKER=esun`): `data/esun_provider.py` wraps `esun_marketdata` + `esun_trade` SDKs. Requires `.p12` cert, API key/secret, and two passwords stored in system keyring. Supports both simulation and real environments.
- **Data sources**: Yahoo Finance (`yfinance`) for backtest data, FinMind for market filter index data, KGI/E.Sun API for live minute bars (volume included — VWAP works correctly).
- **Risk manager** (`core/risk_manager.py`): limits daily trades, daily loss, checks limit up/down. Logs to `logs/performance.csv`.
- **Market filter** (`core/market_filter.py`): checks TAIEX > MA200 before buying. Falls back safely if FinMind fails.
- **Budget control** (`live_trader_multi.py` only): per-strategy monthly cap tracked in `logs/monthly_budget.json`.
- **Notifications**: Telegram via `utils/telegram.py` (always), LINE Notify inline in `live_trader_multi.py` (optional, `LINE_NOTIFY_TOKEN` env var).

## Docker deployment

```bash
docker compose up -d --build
```

- Base image: `python:3.10-slim`
- Default CMD: `python live_trader_multi.py`
- Current dir mounted to `/app` — `.env` changes take effect on container restart, no rebuild needed
- Logging capped at 10MB per file, 3 rotated files (prevents disk fill on cheap VMs)

## File organization

```
strategies/         # Strategy implementations (function-based + class-based)
core/               # StrategyEngine, RiskManager, MarketTrendFilter
data/               # Data loaders (yahoo, kgi_mock, kgi_real)
utils/              # Telegram, Plotter, Logger
config/symbols.py   # Stock symbol lists + Yahoo suffix logic
test/               # Unit tests (unittest)
logs/               # Runtime: trade log CSV + monthly budget JSON
results/            # Backtest export CSV
```

## Tests

Single test file: `test/test_strategies.py` — uses `unittest`, tests the **FinMind class-based strategies** (`*_strategy.py`). Run:

```bash
python -m unittest test.test_strategies
```

## Quirks & gotchas

1. **Missing deps in requirements.txt**: `requirements.txt` is missing `python-dotenv`, `yfinance`, and `tqdm` (FinMind needs it). Always install extras after `pip install -r requirements.txt`.
2. **ATR threshold param discrepancy**: `ma_cross_strategy.py` (class-based) calls it `atr_threshold`, `ma_cross.py` (function-based) also uses `atr_threshold`. `breakout.py` uses hardcoded `df['close'] * 0.01` instead of the `atr_threshold` param. Check before changing.
3. **`min_periods=1` in rolling windows**: Strategy functions use `min_periods=1` which produces values from the first row. This differs from the class-based strategies that default to `min_periods=window` (NaN until enough data). When comparing signals between the two, this causes mismatches.
4. **VWAP calculation**: Both function-based (`vwap_deviation.py`) and class-based (`vwap_strategy.py`) now use volume-weighted calculation (`Σ(close×volume)/Σ(volume)`, rolling 20 periods). Requires `volume` column — all data sources (Yahoo, FinMind, mock) provide it.
5. **`.omo/` is gitignored**: Boulder/plan tracking data stays local.
6. **Modular strategy engine** (`core/strategy_engine.py`) is a thin wrapper — used only by `backtest.py`. The multi-trader and finmind trader instantiate strategy classes directly.
7. **E.Sun keyring in Docker**: When running `BROKER=esun` in Docker, set `PYTHON_KEYRING_BACKEND=keyrings.cryptfile.cryptfile.CryptFileKeyring` and `KEYRING_CRYPTFILE_PASSWORD` in the container environment. If passwords aren't in keyring, login will prompt interactively and fail.

## Development workflow

- Python 3.10+ (Docker uses 3.10-slim, but 3.14 works for local dev)
- `.venv/` directory exists but is empty — recreate if needed
- No formatter/linter config files found — match existing style (spaces, no type hints in most files)
