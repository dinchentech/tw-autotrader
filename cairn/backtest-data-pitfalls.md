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

## 快取共用地圖（新快取前先查這裡；回測前先確認對應快取存在）

> **回測前的快取檢查順序（2026-08-28 沉澱）**：跑任何回測前，先確認下列快取是否存在且範圍涵蓋回測窗口，缺則先重建（避免回測中途才發現資料殘缺 → 假數字）：
> 1. 價格：`cache/inst_momentum/bt_price/{sid}.pkl`（回測專用）或 `cache/inst_momentum/price/{sid}.pkl`（實盤/三腳本共用）
> 2. 法人：`cache/inst_momentum/{year}/twse_inst_{START}_{END}.pkl`（TWSE T86 bulk，**2015-2025 完整**）
> 3. 歷史股本：`cache/inst_momentum/historical_shares.pkl`（逐季池，消除倖存者偏差）
> 4. 市值排名：`cache/inst_momentum/mcap_ranking.pkl`
>
> **2026-08-29 起：跑 `python scripts/verify_cache.py`（離線完整性 + 除息跳空原始價檢測）；懷疑資料時加 `--online` 對比 FinMind/TWSE 即時 API。** 六項檢查對應六次歷史事故（bt_price 範圍=短歷史覆寫、selector 涵蓋=殘缺、twse_inst 天數=反爬 428、除息跳空=還原價混入、線上價格/法人=混合狀態與欄位格式）。

| 快取 | 共用者 | 語義 | 寫入者 | git 狀態 |
|---|---|---|---|---|
| `cache/inst_momentum/price/{sid}.pkl` | 實盤法人動能 + july/bottomfish | **原始價**（FinMind 為主，yfinance `auto_adjust=False`），近期短歷史 | inst_data / 實盤 / july / bottomfish | ❌ gitignore |
| `cache/inst_momentum/bt_price/{sid}.pkl` | 回測專用（backtest_inst_momentum） | **原始價**（FinMind `taiwan_stock_daily`），長歷史 2014-2025 | fetch_price_history_bulk | ✅ **上 git**（回測長歷史，避免重抓撞配額） |
| `cache/inst_momentum/{year}/twse_inst_{START}_{END}.pkl` | 法人動能回測（momentum/july/bottomfish） | TWSE T86 法人逐日（外資+投信+自營），**2015-2025 完整** | fetch_twse_inst_bulk | ✅ **上 git**（2026-08-28 起，24 檔 144MB — TWSE 無配額但仍省重抓時間） |
| `cache/inst_momentum/inst_history/{sid}.pkl` | 歷史殘留（2026-08-26 曾用 FinMind 補 2015-2017） | FinMind 法人逐股 | fetch_inst_history_bulk | ✅ 上 git（**已不再需要** — TWSE 完整，保留相容） |
| `cache/inst_momentum/inst/{sid}.pkl` | 實盤法人動能 | FinMind/TWSE 法人近期 | get_institutional_data | ❌ gitignore |
| `cache/inst_momentum/mcap_ranking.pkl` | 法人動能 + 全輪替選股工具 | 市值排名（寫入者在外部/加密程式） | 外部 | ❌ |
| `cache/selector_prices/{sid}.pkl` | 僅 stock_selector_grid（全輪替） | **還原價**（`auto_adjust=True`）——與 inst_momentum 系列語義不同，**禁止合併** | stock_selector_grid | ❌ |
| `cache/inst_momentum/historical_shares.pkl` | 僅 build_historical_shares / 回測重現 | 歷史股本資料庫（累積型，遷移式讀取） | build_historical_shares | ❌ |
| `cache/inst_momentum/mcap_dict_new.pkl` | 全輪替選股 | 市值字典 | stock_selector_grid | ❌ |
| `cache/inst_momentum/screen_history.txt` | 法人動能報告 | 歷史篩選結果文字 | backtest_inst_momentum | ❌ |

**格式統一原則（2026-08-11 使用者指令）**：可共用的快取一律共用、格式統一，禁止不同策略各建一套。
已知待統一：`cache/inst_momentum/price/` 內 july/bottomfish 寫入含 `ma20/ma10[/ma60]` 欄位、inst_data 寫入不含——同一目錄格式不一致，應統一以 `core/inst_data.py` 為規範來源（見 ROADMAP）。

**上 git 原則（2026-08-25 起）**：回測專用長歷史快取（`bt_price/`、`inst_history/`）上 git — FinMind 免費配額 600/hr 逐股下載太慢（500 檔會等數小時），上 git 讓重跑/換機器 0 秒載入、不碰配額。實盤短歷史（`price/`、`inst/`）與 VM 不下載（.dockerignore 排除）。

## 陷阱：偵測復發檢查清單

1. **回測數字突然劇變 → 先懷疑快取**，不要先懷疑策略邏輯。
2. 檢查 cache_path 檔的 `schema_version` 與 meta（來源標籤、日期範圍）是否符合預期。
3. 確認價格語義：原始價（`auto_adjust=False`）vs 還原價——兩者混用是最高頻陷阱。
4. **兩套股價快取禁止共用/合併**：全輪替選股工具（`cache/selector_prices/`，還原價 `auto_adjust=True`，算動能/報酬率用）與法人動能（`cache/inst_momentum/price/`，原始價 `auto_adjust=False`，算進場價/損益用）語義不同；合併 = 重演 2026-08 假數字事件。市值排名（`mcap_ranking.pkl`）兩邊共用，一律 `load_cache_or_raw` 遷移式讀取（寫入者在外部/加密程式）。
5. **權益單日暴崩 / 最大回撤異常大 → 檢查持倉股當日是否為零價髒點**（2025-07-30 鴻海 2317 事件：FinMind 短暫異常回傳全零 row，被舊快取凍結，回測權益當日 -52%、最大回撤 62.97%→22.68%，+114.96%→+142.71%）。新資料層已用 `clean_price_df` 過濾；懷疑時刪除該股 price cache 重抓即可。
6. 快取資料語義改變（欄位/正規化/調整方式）時，**必須遞增 `CACHE_SCHEMA_VERSION`**。
7. 新快取一律經 `dump_cache` 寫入，禁止直接 `pickle.dumps`。
8. 數字異常時，可刪除 `cache/` 下可疑快取強制重建，交叉驗證數字是否改變。

## 追加案例（2026-08-26 ~ 08-28 稽核）：README 法人動能 +49.37% 無法重現 → 真相

- 症狀演進：2015-2021 窗口重跑一度 **-4.15%** vs README **+49.37%**；2022-2026-07 接近（+107.31% vs +103.66%）。**2026-08-28 TWSE 欄位格式 bug 修正後，完整資料重跑為 2015-2021 **+21.98%**、2015-2025 **+52.54%**（勝率 61.15%、回撤 40.36%）。**
- 四層根因（全部在資料層，策略邏輯無誤）：
  1. **❌ 錯誤結論已推翻：TWSE T86 完整涵蓋 2015-2025！** 之前實測「2015/2016 EMPTY」是 `fetch_twse_day` 硬編碼 19 欄索引（2017+ 格式）解析 16 欄（2015-2016 格式：投信在 [5]/[6] 非 [8]/[9]）→ `row[16]` IndexError → 整個函式回 `{}` → **誤判「TWSE 無 2015 資料」**。修：以 API 回傳 `fields` 標題動態定位欄位（2026-08-28）。→ 回測不再需要 FinMind 補抓，無配額限制。
  2. **回測/實盤共用 `cache/inst_momentum/price/`**：實盤寫入短歷史（yfinance 2021-06 起）覆寫回測長歷史 → 2015-2020 無價格；`min_start` span_ok 例外誤放行。修：回測價格快取獨立 `bt_price/`（`fetch_price_history_bulk`，快取命中採「請求範圍 ⊆ 快取範圍」，避免不同窗口互相覆寫 — 2026-08-28 修正）。
  3. **舊快取混入 yfinance 還原價**（`auto_adjust=True` 修正前的歷史快取）→ 歷史買入價被系統性調低 → 虛增報酬。7 年除息累積讓 1101 買入價 27.55 vs 真實 37.55（差 10 元）。這是 README 數字虛胖的真正來源 — **任何長窗口回測都必須確認價格語義為原始價**。
  4. **FinMind 免費配額 600/hr**：500 檔逐股下載必爆 402（曾誤判需補抓 2015-2017 而繞道）。TWSE 欄位 bug 修正後法人全走 TWSE（無配額）；價格走 bt_price（上 git，0 秒載入）。
- 教訓：① **長窗口（5+ 年）回測數字對價格語義極度敏感**（還原價 bug：2022 窗 +3.65% 無感、2015-2021 窗 +49%→翻轉）；稽核務必抽查歷史買入價 vs 真實成交價。② **外部 API「回 EMPTY」先懷疑解析器欄位格式**，別急著斷言「資料不存在」— TWSE 2015/2017 欄位數不同（16 vs 19），務必用 fields 標題動態定位。③ 回測數字異常 → 先查快取完整性（範圍是否涵蓋窗口），再查邏輯。④ **「好得太不真實」的數字（如勝率 100%）→ 先查資料覆蓋** — TWSE 反爬 428 會讓 bulk 下載靜默殘缺（2026-08-28：1712 天只成功 44 天 → 2015-2021 假 +21.98%）；現已偵測 428 → TwseBlockedError → 自動 FinMind 補段。⑤ TWSE 大量連續請求會觸發反爬（428/HTML），逐日 bulk 下載必須有重試 + 封鎖偵測，不能靜默回 {}。
