# `scripts/` — 選股輔助工具

此目錄下的程式為選股輔助工具，支援兩種使用方式：

- **🔄 自動化模式（V3.0+）**：`live_trader_multi.py` 在每月第 N 個交易日盤後自動呼叫 `stock_selector_grid.py` 選股 → 更新 `.env` → 次日自動換股。**不需要人工執行**。
- **✋ 手動模式**：自行執行工具，作為每季/每月人工檢討時的決策參考。

## 工具總覽

| 程式 | 定位 | 用途 | 使用時機 | 耗時 |
|------|------|------|---------|------|
| `stock_selector_grid.py` | 📊 **決定本季持股（自動化核心）** | 從候選池用近季動能選最強 N 檔 | 每月第 N 個交易日盤後（自動）| ~10 秒 |
| `find_catalyst_stocks.py` | 🔍 掃描全市場 | 找「長期盤整→近期突破」的翻倍潛力股 | **每月初** | ~5 分鐘 |
| `selector_workflow.py` | 📈 工作流程比較 | 比較四種選股策略的歷史回測績效 | 參考用 | ~5 分鐘 |
| `update_taiwan_holidays.py` | 📅 休市日曆更新 | 從 TWSE API 自動更新休市日 | 每日 08:40（自動）| ~1 秒 |
| `generate_dashboard.py` | 📉 績效儀表板 | 產生 `logs/dashboard.html` 績效圖表 | 實盤每日自動 | — |

---

## 🔄 自動化模式（V3.0+）

全輪替選股已整合進 `live_trader_multi.py` 自動交易流程，**不需要手動執行任何選股工具**：

```
每月第 N 個交易日 13:31~13:35（自動）
  └─ live_trader_multi.py 偵測到排程月份
       └─ 自動執行 stock_selector_grid.py --recommend --output-env
            ├─ 自動更新 .env 的排程 A/B 區段
            ├─ 舊 .env 自動備份到 backups/
            └─ Telegram 通知「全輪替 X排程 選股完成」

次日 08:40（自動）
  └─ 熱重載 .env → 清倉舊股 → 買入新股
```

**自動化由 `.env` 參數控制**（詳見[使用手冊 — 全輪替自動化](../使用手冊.md#全輪替自動化)）：

| `.env` 參數 | 預設 | 說明 |
|-------------|:---:|------|
| `ROTATE_MODE` | `0` | 0=不啟用，1~3=單排程，4~5=雙排程各半（推薦 5）|
| `ROTATE_TRADING_DAY_N` | `1` | 選股日 = 每月第 N 個交易日（N=1~20）|
| `STOCK_NO` | `50` | 候選池大小 = 市值前 N 大股票 |
| `TOTAL_CAPITAL` | `500000` | 資金池（自動化依此計算 alloc）|

**手動預覽選股結果**（不修改 `.env`）：

```bash
python scripts/stock_selector_grid.py --recommend --output-env --schedule-label A --top-n 4
python scripts/stock_selector_grid.py --recommend --output-env --schedule-label B --top-n 4
```

---

## 詳細說明

### `find_catalyst_stocks.py` — 翻倍潛力股掃瞄

模仿藥華藥（6446）的「長期盤整 → 催化劑 → 翻倍」模式，掃描全市場 ~1078 檔上市股票，找出具有類似型態的潛力標的。

**評分維度：** 盤整品質（20%）+ 突破力道（35%）+ 量能確認（15%）+ 動能延續（30%）

```bash
python scripts/find_catalyst_stocks.py                     # 完整掃描
python scripts/find_catalyst_stocks.py --top-n 20           # 只看前 20 名
python scripts/find_catalyst_stocks.py --output-html        # 輸出 HTML 報告
python scripts/find_catalyst_stocks.py --min-score 30       # 最低評分門檻
```

**輸出：** `img/catalyst_report_YYYYMMDD.html`（HTML 報告）+ `data/catalyst_scan_YYYYMMDD.csv`

**自動更新候選清單：** 執行完後會自動把前 5 名寫入根目錄的 `custom_pool.txt`（同時備份舊檔為 `custom_pool.txt.bak`）。`stock_selector_grid.py` 執行時會偵測此檔案，詢問是否合併到候選池。

> ⚠️ 此工具是「發現機會」用的，不是「決定買入」用的。看到高分標的應該先研究基本面，再確認 `custom_pool.txt` 內容後，交給 `stock_selector_grid.py` 做最終篩選。

---

### `stock_selector_grid.py` — 每季 Grid Search 選股

從候選股票池中，使用 **近季動能為主** 的評分系統選出最值得持有的 N 檔股票。內建 Grid Search 可自動找出歷史最佳參數。**此工具是全輪替自動化的核心選股引擎。**

**評分維度（可調權重）：** 短天期動能 + 技術面（均線位置）+ 穩定度（低波動）+ 催化劑評分

```bash
# Grid Search 找最佳參數（預設）
python scripts/stock_selector_grid.py --grid

# 查看本季推薦持股（純動能，預設）
python scripts/stock_selector_grid.py --recommend

# 純催化劑模式
python scripts/stock_selector_grid.py --recommend --mode catalyst

# 核心+衛星（80%動能 + 20%催化劑）
python scripts/stock_selector_grid.py --recommend --mode core-satellite

# 產出 HTML 報告
python scripts/stock_selector_grid.py --grid
```

**輸出：** `img/stock_selector_grid_report.html`（完整報告 + 參數排名）

---

#### 選股參數（使用者可自行調整）

以下參數決定選股行為，可透過 **CLI 參數** 或 **`.env` 環境變數** 調整：

**① 候選池與持股數**

| 參數 | 預設 | 說明 |
|------|:---:|------|
| `STOCK_NO`（.env）| `50` | 候選池大小 = 市值前 N 大股票（50/100/150）|
| `--top-n` | 依資金自動 | 每次選幾檔持股（自動化固定 4 檔）|
| `custom_pool.txt` | — | 自訂候選股，一行一個代號，執行時詢問是否合併 |

**② 選股模式（--mode）**

| 模式 | 說明 |
|------|------|
| `momentum`（預設）| 純動能：21d/63d 動能 + 技術面 + 穩定度 |
| `catalyst` | 純催化劑：長期盤整→近期突破的潛力股 |
| `core-satellite` | 核心+衛星：80% 動能 + 20% 催化劑 |

**③ 評分權重（Grid Search 維度，預設為歷史最佳解）**

| 參數 | 預設 | 可調範圍 | 說明 |
|------|:---:|:---:|------|
| `momentum_days` | 21 | 21 / 63 / 125 | 動能回看天數（auto_momentum 時自動切換 21/63）|
| `momentum_weight` | 2.0 | 0.5 / 1.0 / 2.0 | 動能權重 |
| `technical_weight` | 0.3 | 0 / 0.3 / 0.5 / 1.0 | 技術面（均線位置）權重 |
| `stability_weight` | 0.0 | 0 / 0.3 / 0.5 | 穩定度（低波動）權重 |
| `catalyst_weight` | 0.0 | 0 / 0.3 / 0.5 / 1.0 | 潛力股模式權重 |
| `use_ma_filter` | False | 開 / 關 | MA20 強制過濾（跌破 MA20 評分打 5 折）|
| `min_price` | 5 | 5 / 10 | 最低股價門檻（排除低價股）|

**④ 排程與資金**

| 參數 | 預設 | 說明 |
|------|:---:|------|
| `--rotate-mode` | 0（由 .env ROTATE_MODE 控制）| 0~5 排程模式 |
| `--quarter` | 3,6,9,12 | 季度檢討月份（被 --rotate-mode 優先覆蓋）|
| `--capital` | 讀取 .env TOTAL_CAPITAL | 起始資金 |
| `--auto-momentum` | 關 | 依 0050 MA200 自動切換 21d/63d（自動化預設開啟）|

**⑤ 自動化輸出（V3.0+）**

| 參數 | 說明 |
|------|------|
| `--output-env` | 輸出 PC_* .env 格式（供自動化寫入 .env）|
| `--schedule-label` | 排程標籤 A/B，用於 .env 區段標記 |

> 💡 **調整建議**：先跑 `--grid` 用歷史資料找最佳權重，再套用到自動化（`.env` 不需改權重，自動化使用內建最佳參數）。

**候選股票池**：**市值前 50 大股票**（從 TWSE 公開市值排名載入，非人為挑選）。可透過 `STOCK_NO` 環境變數調整檔數（預設 50）。

**自訂候選股：** 編輯根目錄的 `custom_pool.txt`，一行一個股票代號，執行時會詢問是否合併。`find_catalyst_stocks.py` 每次執行完會自動把前 5 名寫入此檔。

---

### `selector_workflow.py` — 選股工作流程比較

比較四種選股策略在 2022~2025 的歷史績效，幫助你決定要用哪種方式管理持股。

**四種工作流程（候選池：市值前 150 大，非人為挑選）：**
| 流程 | 策略 | 2022→2025 終值 |
|------|------|---------------|
| **A｜純動能** 🥇 | 每季從市值前 50 大選近季動能最強 4 檔 | **NT$2,944,313 (+488.9%)** |
| B｜純催化劑 | 每季選潛力股模式評分最高 4 檔 | NT$1,897,443 (+279.5%) |
| C｜動能+催化劑混合 | 先擴池再套動能 | NT$45,405（-90.9%） |
| D｜核心+衛星 | 80% 動能 + 20% 催化劑 | NT$3,143,593 (+528.7%) |

```bash
python scripts/selector_workflow.py
```

---

### `generate_dashboard.py` — 績效儀表板

由 `live_trader_multi.py` 每日自動呼叫，產生 `logs/dashboard.html`。一般不需要手動執行。

---

### `update_taiwan_holidays.py` — 休市日曆自動更新

從 TWSE 官方 API 抓取每年開休市日期，更新 `config/taiwan_holidays.json`。`live_trader_multi.py` 每天 08:40 自動檢查，日曆超過 30 天未更新時自動執行。

```bash
python scripts/update_taiwan_holidays.py            # 更新今年 + 明年
python scripts/update_taiwan_holidays.py --years 2027 2028   # 指定年份
python scripts/update_taiwan_holidays.py --year 2026 --dry-run  # 預覽不寫檔
```

> ⚠️ TWSE 每年 11~12 月才公布隔年行事曆，未公布年份 API 會回傳舊年資料，程式自動跳過。

---

## 建議使用流程

詳見[使用手冊 — 選股工具工作流程](../使用手冊.md#🛠️-選股工具工作流程)。

### 自動化模式（推薦，V3.0+）

```
設定 .env 的 ROTATE_MODE=5 → 部署 → 之後完全自動
  └─ 每月第 N 個交易日盤後：自動選股 → 更新 .env → 次日自動換股
```

### 手動模式

```
每月初                                           每季初
find_catalyst_stocks.py  ─── 寫入前 5 名 ───→   stock_selector_grid.py
（掃描全市場找潛力股）     custom_pool.txt        （詢問是否合併，選最強 N 檔）
                                                → 決定本季持股
```

## 注意事項

1. **過去績效不代表未來獲利** — Grid Search 找到的最佳參數是歷史最佳，未來不一定有效
2. **自動化模式會修改 `.env`** — 但只改排程 A/B 區段，且更新前會自動備份到 `backups/`
3. **手動模式不修改交易系統** — 只產出建議清單
4. **`update_taiwan_holidays.py` 需網路** — 從 TWSE 官方 API 抓取，無網路時沿用現有日曆
