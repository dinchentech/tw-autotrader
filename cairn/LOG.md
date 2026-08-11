# Project Cairn 日誌

本檔案以倒序記錄實質進展——最新條目在最上方、緊接本行之下。每條保持精簡——只要摘要與指標；結論沉澱到 `cairn/<topic>.md`。

## 2026-08-11 · 快取共用規則確認

- 確認全輪替與法人動能快取關係：`mcap_ranking.pkl` 兩邊共用（遷移式讀取）；**股價快取兩套禁止共用**（selector_prices 還原價 vs inst_momentum/price 原始價，合併=重演 2026-08 事件）。
- `backtest.py / simulate_portfolio.py / trading_calendar.py / find_catalyst_stocks.py` 等確認無 pickle 快取，全 repo 覆蓋無漏網（僅 plans/ 嵌套 repo 除外）。

## 2026-08-11 · inline 快取全版本化 + .omo 進 git

- 新增 `core/cache_io.py`（CACHE_SCHEMA_VERSION=2 + load_cache/dump_cache/load_cache_or_raw），`core/inst_data.py` 改用並保留 `_load_cache`/`_dump_cache` 別名（測試相容）。
- 版本化覆蓋：backtest_inst_bottomfish.py（5 處）、backtest_july.py（4 處）、scripts/stock_selector_grid.py（3 處）、build_historical_shares.py（3 處）、selector_keep/workflow/full（各 1 處）。
- 累積資料庫（mcap_ranking.pkl / historical_shares.pkl）走 `load_cache_or_raw` 遷移式讀取，舊格式不丟棄。
- `.omo/` 移除 gitignore 並進版控；`cache/` 整目錄加入 gitignore（避免 `git add .` 誤加可重建快取）。
- 未處理：`plans/` 為獨立嵌套 repo（有自己 .git），其內檔案不在主 repo 版控範圍。

## 2026-08-11 · 快取版本化 + 回歸測試 + 知識沉澱（防跨 session bug 復發）

- `core/inst_data.py`：導入 `CACHE_SCHEMA_VERSION=2` + `_dump_cache`/`_load_cache`（版本不符自動重建並警告、tmp+replace 原子寫入），覆蓋 fetch_twse_inst_bulk / get_price_data / get_institutional_data 三個快取；舊格式快取首次執行會自動重建。
- 新增 `test/test_inst_data_cache.py`（9 案例：版本不符拒絕/過期拒絕/歷史深度不足拒絕/命中/自動重建），`test.test_strategies` 不受影響。
- 新增 `cairn/backtest-data-pitfalls.md`：2026-08 數字無法重現事件（+85.22%→-13.05%）根因、防護與復發檢查清單。
- AGENTS.md：Quirks 加「數字劇變先查快取」、知識沉澱規則加「Bug 修復三步曲」硬規則。
- 已知未覆蓋：backtest_inst_bottomfish / backtest_july / scripts/*.py 的 inline 快取（見 ROADMAP）。

## 2026-08-01 · Project Cairn 初始化

- 建立 Project Cairn 結構（AGENTS.md 合併版、CLAUDE.md、`.cairn/config.yaml`、`cairn/LOG.md`、`cairn/ROADMAP.md`）。
- 歷史遷移模式：`start_fresh`。
- 詳情：見 `AGENTS.md` 與 `.cairn/config.yaml`。
