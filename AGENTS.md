# TW AutoTrader 協作規則

> 本專案使用 Project Cairn 組織專案知識：`AGENTS.md` 是規則與導覽的入口，`cairn/` 是專案知識/狀態層。
> 同目錄下的 `CLAUDE.md` 只應包含一行 `@AGENTS.md`，讓 Claude Code 讀取相同的規則；Codex 直接讀取本檔案。

## 專案一句話

台股量化自動交易系統 — 整合多策略回測、風險控管與券商 API 自動下單的 Python 工具

> 本檔案由 `cairn init` 產生，已填入本專案自身的定位與 provider 設定；其他專案應先執行自己的 init 再重複使用。

## 初始化設定

- 畢業 provider：暫緩對接（第一次畢業時再接知識庫）
- 知識庫索引：尚未設定
- 畢業目標：尚未設定

## 進入專案後的閱讀順序

> ⚠️ **開啟任一 session 的第一步（STEP 0，硬規則）**：先讀 `cairn/CURRENT.md`（當前狀態索引，指向正式 cairn 文件）。若該檔不存在，改讀 `cairn/LOG.md` 最新條目 + `cairn/ROADMAP.md`。

1. 先讀本檔案（AGENTS.md）。
2. 若 `cairn/ROADMAP.md` 存在，閱讀它以了解路線圖、目前焦點與開放問題（ROADMAP 為選用；最小化初始化的專案可能沒有）。
3. 閱讀 `cairn/LOG.md` 最新的條目（最新在上方）了解近期進度與關鍵決策。
4. 依任務需要閱讀相關的 `cairn/` 知識專題文件（**部署/加密/版本發布**相關任務：先讀 `cairn/deploy-pipeline.md` — root 是混淆版、plans/ 是源碼）。
5. **依任務類型讀對應章節**（文件很大，勿全文載入，用 grep 找章節）：
   - **策略/選股/回測相關** → `策略說明.md`（全輪替 §5.1、法人動能 §6、買入金額計算、MIN_DRAW_BACK）+ `scripts/README.md`（選股工具）
   - **操作/參數/部署相關** → `使用手冊.md`（PC_ 設定、deploy 腳本選擇、參數表、驗證結果）
   - **資料/快取/回測數字驗證** → `cairn/backtest-data-pitfalls.md`（快取共用地圖、回測前跑 `scripts/verify_cache.py`）
   - **資金/資本操作** → `cairn/capital-ops.md`
   - **環境/資金口徑** → 先讀 `cairn/environment-scope.md`（「實盤」=用玉山 API 實際執行路徑；本目錄用玉山**模擬**key → 模擬資金無真金，真錢=real key 待另開分支）

## 文件職責

| 檔案 | 角色 | 維護方式 |
|---|---|---|
| `AGENTS.md`（根目錄） | 規則與導覽 | 很少變更，≤ 60 行 |
| `CLAUDE.md`（根目錄） | 一行 `@AGENTS.md` stub | 寫一次，之後不再動 |
| `cairn/ROADMAP.md` | 路線圖與進度 | 原地更新，保持精簡 |
| `cairn/LOG.md` | 時間序日誌 | 新條目加在最上方（新的在前），每條 ≤ 20 行，只要摘要 + 指標 |
| `cairn/CURRENT.md` | session 引導索引（開啟 session 的 STEP 0 先讀） | 隨現況更新；只做索引、不取代專題文件 |
| `cairn/<topic>.md` | 知識專題文件（當前真相） | 原地更新；陷阱放在內文區段，用 `contains` 標記；修訂加 LOG 指標 |
| `cairn/Reference/` | 外部原始輸入 | 需要時才建立；只增不改 |
| `cairn/Cited.md` | 知識庫引用清單 | 只有指標，絕不複製來源內容 |

> 其他一切都只在出現具體訊號時才建立（有決策要記錄、解決了某個陷阱、某個目標跨 session）——不是預先建空殼。工程資產（程式/流程消費的合約/設定/規格）不由本系統管理；它們留在程式碼樹中，不進 `cairn/`。

## 衝突仲裁規則

- 優先級：**知識專題文件 > LOG 歷史**；規則層級的衝突由本檔案解決。
- 業務/設計結論以 `cairn/` 知識專題文件的最新紀錄為準，而不是較舊的 LOG 條目。

## 知識庫消費反射

- 在進行其可複用內核——任何產出或依賴的結論——夠格畢業的工作前，先查閱本專案自身的 `cairn/` 知識專題文件；目前尚未連接外部知識庫（provider 暫緩對接——見上方初始化設定），外部索引檢查與 `cairn/Cited.md` 引用會在接上後啟用。

## 文件協作規則

- **對話回覆一律使用繁體中文**（除非使用者指定其他語言）；本專案文件（`.cairn/config.yaml` 的 `language: zh`、`cairn/`、`使用手冊.md`、`策略說明.md` 等）皆為繁體中文，`zh` 即指繁體中文。
- 變更前判斷使用者要的是「討論/建議」還是「直接改文件」；當他們說「先看看/先評估」時，先給分析——不要直接改寫正式文件。
- 修正過去的判斷時，附加修正說明；不要默默覆寫。
- 不要把未經確認的判斷寫成既成事實。

## 知識沉澱規則

- 每有實質進展，就在 `cairn/LOG.md` 最上方加一條（摘要 + 指標）；讓結論沉澱到 `cairn/` 知識專題文件。
- 跨專案可複用的經驗，待接上知識庫後再透過畢業機制沉澱（provider 暫緩對接——見上方初始化設定）。
- **Bug 修復三步曲（硬規則）**：修 bug 前先寫會失敗的回歸測試 → 修復 → 當下在 `cairn/LOG.md` 記一條並更新對應知識專題。未寫測試、未記 cairn 的修復視為未完成。

## 快取使用規則（硬規則）

- 回測與實盤的快取一律經 `core/cache_io.py` 版本化讀寫；**可以共用的就共用、格式統一**，禁止各策略自建一套。共用基準：`cache/inst_momentum/price/`（法人動能三腳本共用股價）、`cache/inst_momentum/{year}/`（TWSE 法人/TAIEX）。
- 新增快取前先查共用地圖（`cairn/backtest-data-pitfalls.md`）；股價語義不同（還原價 vs 原始價）不得合併。

## 部署安全規則（硬規則）

- **deploy 一律由「人工」執行，不要自動代跑！** 任何 agent（AI）**不得執行** `./deploy.sh` / `./deploy_source.sh` / `docker compose` 於 VM 重啟等高風險操作（2026-08-31 使用者明示）。
- agent 的職責止於：改 `plans/`（或 root 源碼）→ 跑測試 → 更新 cairn → 告知「準備就緒，請人工執行 deploy」。詳見 `cairn/deploy-pipeline.md` 鐵則。

---

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
python backtest_finmind.py          # defaults: 2xx0, 2023-01-01

# Live trading — multi-symbol (recommended entrypoint)
python live_trader_multi.py         # reads PORTFOLIO from .env

# Tests
python -m unittest test.test_strategies
```

## Entrypoints

| File | Purpose |
|------|---------|
| `live_trader_multi.py` | **Primary live trader** — multi-symbol, multi-strategy, monthly budget, pyramid scaling, dual notifications (Telegram + LINE) |
| `backtest.py` | Yahoo Finance backtest with CLI param override |
| `backtest_finmind.py` | FinMind backtest (uses function-based strategies) |

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
strategies/         # Strategy implementations (function-based)
core/               # StrategyEngine, RiskManager, MarketTrendFilter
data/               # Data loaders (yahoo, kgi_mock, kgi_real)
utils/              # Telegram, Plotter, Logger
config/symbols.py   # Stock symbol lists + Yahoo suffix logic
test/               # Unit tests (unittest)
logs/               # Runtime: trade log CSV + monthly budget JSON
results/            # Backtest export CSV
```

## Tests

Single test file: `test/test_strategies.py` — uses `unittest`, tests the **function-based strategies** (`strategies/*.py`). Run:

```bash
python -m unittest test.test_strategies
```

## Quirks & gotchas

1. **Missing deps in requirements.txt**: `requirements.txt` is missing `python-dotenv`, `yfinance`, and `tqdm` (FinMind needs it). Always install extras after `pip install -r requirements.txt`.
2. **`min_periods=1` in rolling windows**: Strategy functions use `min_periods=1` which produces values from the first row. Be aware when comparing against other implementations.
3. **`.omo/` 是 git 版控的一部分**: Boulder/plan tracking data 已進 git（2026-08-11 起），跨機器可同步；機密（`.env`、`backups/`、`esun_sdk/*.p12`）仍被 .gitignore 排除。
4. **Modular strategy engine** (`core/strategy_engine.py`) is a thin wrapper — used only by `backtest.py`. The multi-trader instantiates strategy functions directly.
5. **E.Sun keyring in Docker**: When running `BROKER=esun` in Docker, set `PYTHON_KEYRING_BACKEND=keyrings.cryptfile.cryptfile.CryptFileKeyring` and `KEYRING_CRYPTFILE_PASSWORD` in the container environment. If passwords aren't in keyring, login will prompt interactively and fail.
6. **回測數字突然劇變 → 先懷疑快取**: 檢查 cache_path 檔的 `schema_version` 與來源標籤，確認價格語義（原始價 vs 還原價）符合預期；`core/inst_data.py` 的 `CACHE_SCHEMA_VERSION` 在快取語義改變時必須遞增，否則舊快取會被靜默載入。詳見 `cairn/backtest-data-pitfalls.md`。

## Development workflow

- Python 3.10+ (Docker uses 3.10-slim, but 3.14 works for local dev)
- `.venv/` directory exists but is empty — recreate if needed
- No formatter/linter config files found — match existing style (spaces, no type hints in most files)
