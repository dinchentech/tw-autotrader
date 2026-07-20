# `scripts/` — 選股輔助工具

此目錄下的程式為獨立運作的選股輔助工具，**不屬於 `live_trader_multi.py` 的自動交易流程**，而是提供每季/每月人工檢討時的決策參考。

## 工具總覽

| 程式 | 定位 | 用途 | 使用時機 | 耗時 |
|------|------|------|---------|------|
| `find_catalyst_stocks.py` | 🔍 掃描全市場 | 找「長期盤整→近期突破」的翻倍潛力股 | **每月初** | ~5 分鐘 |
| `stock_selector_grid.py` | 📊 決定本季持股 | 從候選池用近季動能選最強 N 檔 | **每季初** | ~10 秒 |
| `selector_workflow.py` | 📈 工作流程比較 | 比較四種選股策略的歷史回測績效 | 參考用 | ~5 分鐘 |
| `generate_dashboard.py` | 📉 績效儀表板 | 產生 `logs/dashboard.html` 績效圖表 | 實盤每日自動 | — |

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

從候選股票池中，使用 **近季動能為主** 的評分系統選出最值得持有的 N 檔股票。內建 Grid Search 可自動找出歷史最佳參數。

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

**Grid Search 維度（7 個 × 1728 種組合）：**
- `momentum_days`：動能回看天數（21 / 63 / 125）
- `momentum_weight`：動能權重（0.5 / 1.0 / 2.0）
- `technical_weight`：技術面權重（0 / 0.3 / 0.5 / 1.0）
- `stability_weight`：穩定度權重（0 / 0.3 / 0.5）
- `catalyst_weight`：潛力股模式權重（0 / 0.3 / 0.5 / 1.0）
- `use_ma_filter`：MA20 強制過濾（開 / 關）
- `min_price`：最低股價門檻（5 / 10）

**候選股票池**（預設 16 檔 + `custom_pool.txt` 自訂）：
- 大型電子：2330（台積電）、2454（聯發科）、2317（鴻海）
- 電子：2382（廣達）、2376（技嘉）、2345（智邦）
- 金融：2881（富邦金）、2882（國泰金）、2886（兆豐金）
- 防禦：2412（中華電）
- 記憶體：2408（南亞科）、4967（十銓）
- 生技：6446（藥華藥）
- ETF：0050、006208、00878

**自訂候選股：** 編輯根目錄的 `custom_pool.txt`，一行一個股票代號，執行時會詢問是否合併。`find_catalyst_stocks.py` 每次執行完會自動把前 5 名寫入此檔。

---

### `selector_workflow.py` — 選股工作流程比較

比較四種選股策略在 2022~2025 的歷史績效，幫助你決定要用哪種方式管理持股。

**四種工作流程：**
| 流程 | 策略 | 2022→2025 終值 |
|------|------|---------------|
| **A｜純動能** 🥇 | 每季從固定 16 檔選近季動能最強 4 檔 | **NT$3,229,234 (+545.8%)** |
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

## 建議使用流程

詳見[使用手冊 — 選股工具工作流程](../使用手冊.md#🛠️-選股工具工作流程)。

```
每月初                                           每季初
find_catalyst_stocks.py  ─── 寫入前 5 名 ───→   stock_selector_grid.py
（掃描全市場找潛力股）     custom_pool.txt        （詢問是否合併，選最強 N 檔）
                                                → 決定本季持股
```

## 注意事項

1. **過去績效不代表未來獲利** — Grid Search 找到的最佳參數是歷史最佳，未來不一定有效
2. **獨立運作** — 這些工具不修改 `.env` 或交易系統，只產出建議清單
3. **手動調整** — 選股建議需要你自己研究後手動更新 `.env` 的 `PC_` 設定
