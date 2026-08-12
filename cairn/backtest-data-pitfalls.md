---
type: project_topic
status: active
summary: 回測資料完整性與快取陷阱——2026-08 官方數字無法重現事件的根因、現行防護與復發檢查清單
tags: [backtest, cache, data-integrity]
contains: [快取陷阱, 還原價, 快取版本, cache, 回測數字無法重現]
created: "2026-08-11"
updated: "2026-08-11"
related: []
authoring_mode: ai_generated
---
# 回測資料完整性與快取陷阱

## 症狀（2026-08 事件）

- 法人動能（方案三）舊官方數字：**+85.22%、勝率 71.72%、回撤 22%**，乾淨資料重測後無法重現，實際為 **-13.05%**。
- 舊數字**取決於當時快取狀態**——同一份程式碼、不同的快取內容會得到完全不同的績效數字。

## 根因

1. **價格快取混入 yfinance 還原價**：`auto_adjust` 預設為調整後價格（除權除息調整），系統性偏低，造成進場價/訊號失真。已改 `auto_adjust=False` 使用原始價。
2. **魚過濾回溯視窗不完整**：快取歷史深度不足 90 天時，魚過濾的「法人低吃分數」根本算不完整，舊數字因此無效。
3. **底層結構性根因**：快取僅以檔案路徑為 key、**無 schema 版本**——資料語義改變（欄位/價格調整/正規化）時，舊 pickle 被靜默載入，完全沒有警示。這正是同類 bug 反覆發生的原因。

## 現行防護（2026-08-11 導入）

- `core/inst_data.py`：`CACHE_SCHEMA_VERSION = 2` + `_dump_cache` / `_load_cache`。
  - 版本不符 → 印出 `⚠️ 快取版本不符` 並**自動重建**，不再靜默載入。
  - 寫入採 tmp + `os.replace` 原子替換，避免中途寫壞的殘缺 pickle。
  - 覆蓋三個快取函式：`fetch_twse_inst_bulk` / `get_price_data` / `get_institutional_data`。
  - 初次升級後，所有舊格式快取會自動重建一次（預期行為）。
- **零價髒點過濾**：`clean_price_df`（`core/inst_data.py`）剔除 `close<=0` 或 OHLC 全零的 row，載入與寫入快取前都過濾（july/bottomfish 同套）。
- `test/test_inst_data_cache.py`：12 案例鎖定「版本不符拒絕 / 過期拒絕 / 歷史深度不足拒絕 / 有效命中 / 版本不符自動重建 / 零價髒點過濾」。
- 主回測 `backtest_inst_momentum.py` 與實盤共用 `core/inst_data.py`，自動受惠。

## 已知未覆蓋

- ~~`backtest_inst_bottomfish.py`、`backtest_july.py`、`scripts/*.py` 各自的 inline pickle 快取~~ — 2026-08-11 已全部版本化，統一走 `core/cache_io.py`。
- 例外（未處理）：`plans/` 是獨立嵌套 git repo，其 `backtest_inst_momentum.py` 屬另一版本控制範圍；`mcap_ranking.pkl` 在 repo 內無寫入者（由外部/加密程式產生），讀取端一律用 `load_cache_or_raw` 遷移式讀取相容舊格式。

## 快取共用地圖（新快取前先查這裡）

| 快取 | 共用者 | 語義 | 寫入者 |
|---|---|---|---|
| `cache/inst_momentum/price/{sid}.pkl` | 法人動能三腳本（momentum/july/bottomfish） | 原始價（FinMind 為主，yfinance `auto_adjust=False`） | inst_data / july / bottomfish |
| `cache/inst_momentum/{year}/twse_inst_*.pkl`、`taiex_ma200_*.pkl` | 同上 | TWSE 法人逐日 / TAIEX MA200 | inst_data / july / bottomfish |
| `cache/inst_momentum/mcap_ranking.pkl` | 法人動能 + 全輪替選股工具 | 市值排名（寫入者在外部/加密程式） | 外部 |
| `cache/selector_prices/{sid}.pkl` | 僅 stock_selector_grid（全輪替） | **還原價**（`auto_adjust=True`）——與 inst_momentum/price 語義不同，禁止合併 | stock_selector_grid |
| `cache/inst_momentum/historical_shares.pkl` | 僅 build_historical_shares / 回測重現 | 歷史股本資料庫（累積型，遷移式讀取） | build_historical_shares |

**格式統一原則（2026-08-11 使用者指令）**：可共用的快取一律共用、格式統一，禁止不同策略各建一套。
已知待統一：`cache/inst_momentum/price/` 內 july/bottomfish 寫入含 `ma20/ma10[/ma60]` 欄位、inst_data 寫入不含——同一目錄格式不一致，應統一以 `core/inst_data.py` 為規範來源（見 ROADMAP）。

## 陷阱：偵測復發檢查清單

1. **回測數字突然劇變 → 先懷疑快取**，不要先懷疑策略邏輯。
2. 檢查 cache_path 檔的 `schema_version` 與 meta（來源標籤、日期範圍）是否符合預期。
3. 確認價格語義：原始價（`auto_adjust=False`）vs 還原價——兩者混用是最高頻陷阱。
4. **兩套股價快取禁止共用/合併**：全輪替選股工具（`cache/selector_prices/`，還原價 `auto_adjust=True`，算動能/報酬率用）與法人動能（`cache/inst_momentum/price/`，原始價 `auto_adjust=False`，算進場價/損益用）語義不同；合併 = 重演 2026-08 假數字事件。市值排名（`mcap_ranking.pkl`）兩邊共用，一律 `load_cache_or_raw` 遷移式讀取（寫入者在外部/加密程式）。
5. **權益單日暴崩 / 最大回撤異常大 → 檢查持倉股當日是否為零價髒點**（2025-07-30 鴻海 2317 事件：FinMind 短暫異常回傳全零 row，被舊快取凍結，回測權益當日 -52%、最大回撤 62.97%→22.68%，+114.96%→+142.71%）。新資料層已用 `clean_price_df` 過濾；懷疑時刪除該股 price cache 重抓即可。
6. 快取資料語義改變（欄位/正規化/調整方式）時，**必須遞增 `CACHE_SCHEMA_VERSION`**。
7. 新快取一律經 `dump_cache` 寫入，禁止直接 `pickle.dumps`。
8. 數字異常時，可刪除 `cache/` 下可疑快取強制重建，交叉驗證數字是否改變。
