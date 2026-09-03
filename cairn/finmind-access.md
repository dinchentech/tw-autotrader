---
type: project_topic
status: active
summary: "查台股/FinMind 資料的標準流程與欄位陷阱——API 端點、dataset 對照、token 來源、max/min/Trading_Volume 陷阱。"
tags: [finmind, 資料, API, 台股, 券商資料, 陷阱]
contains: [reference, lesson]
created: "2026-09-03"
updated: "2026-09-03"
related:
  - cairn/backtest-data-pitfalls.md
authoring_mode: ai_generated
---
# FinMind 資料存取

## 一句話
查台股/FinMind 資料時，依本篇流程（API 端點、認證、dataset 對照、錯誤處理、中文繪圖）。**重點陷阱：FinMind `TaiwanStockPrice` 用 `max`/`min`/`Trading_Volume`，不是 high/low/volume。**

## 來源與 token
- 完整 recipe 來自機器全域 opencode skill：`~/.config/opencode/skills/finmind/SKILL.md`。
- **token**：專案 `.env` 用 **`FINMIND_API_TOKEN`**（skill 原文寫 `$FINMIND_TOKEN`，名稱不同，別搞混）。讀法：`FINMIND_API_TOKEN=` 的那行值。

## API
- Base：`https://api.finmindtrade.com/api/v4`
- 認證：header `Authorization: Bearer {token}`。
- 端點：`GET /data`（大部分 dataset）、`GET /datalist`（列 data_id）、`GET /translation`（欄位中英對照）。
- 特殊端點（不走 `/data`）：`TaiwanStockTradingDailyReport`→`/v4/taiwan_stock_trading_daily_report`（用 `date` 非 `start_date` 且要 `data_id`）；`taiwan_stock_tick_snapshot`、`taiwan_futures_snapshot`、`taiwan_options_snapshot`、`TaiwanStockTradingDailyReportSecIdAgg`。
- 配額：Free 600 req/hr。超額 HTTP 402。

## 常用 dataset 對照
| 需求 | dataset |
|---|---|
| 股價(未還原) | `TaiwanStockPrice` |
| 還原股價(除權息) | `TaiwanStockPriceAdj` |
| 三大法人買賣超 | `TaiwanStockInstitutionalInvestorsBuySell` |
| 融資融券 | `TaiwanStockMarginPurchaseShortSale` |
| 月營收 | `TaiwanStockMonthRevenue` |
| 損益表/EPS | `TaiwanStockFinancialStatements` |
| 股利/配息 | `TaiwanStockDividend` |
| 本益比/股價淨值比 | `TaiwanStockPER` |
| 查股票代號 | `TaiwanStockInfo` |
| 期貨/選擇權 | `TaiwanFuturesDaily` / `TaiwanOptionDaily` |

## ⚠️ 陷阱（lesson）
1. **`TaiwanStockPrice` 欄位**：`date, stock_id, Trading_Volume, Trading_money, open, max(高), min(低), close, spread, Trading_turnover`——K線取 `max`(高)/`min`(低)/`Trading_Volume`(量)，**不是** high/low/volume。2026-09-03 實測即死在此欄（見 LOG）。
2. **`_norm_price` 的 max/min → high/low** 轉換在 `core/inst_data.py`（回測價格語義）——與本篇的快取問題同源，見 `backtest-data-pitfalls.md`。
3. **token 名稱差異**：`.env` 是 `FINMIND_API_TOKEN`；skill 範例用 `$FINMIND_TOKEN`。
4. **中文繪圖字型**：matplotlib 畫圖前註冊 `/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc`（`fm.fontManager.addfont` + `plt.rcParams`）；HTML/ECharts 靠瀏覽器字型即可。

## 查詢範例
```python
import os, requests, pandas as pd
token = os.environ["FINMIND_API_TOKEN"]   # 或從 .env 讀
url = "https://api.finmindtrade.com/api/v4/data"
params = {"dataset": "TaiwanStockPrice", "data_id": "2884",
          "start_date": "2025-09-01", "end_date": "2026-09-03"}
r = requests.get(url, params=params, headers={"Authorization": f"Bearer {token}"}).json()
if r.get("status") != 200:
    print("Error:", r.get("msg"))
else:
    df = pd.DataFrame(r["data"])
```
錯誤處理：HTTP 402=配額超限；`status != 200` 看 `msg`；`data['data']==[]` = 代號錯/無交易日/需更高 tier；缺 token → 提醒 export。

## 其他
- 產生 K線 HTML 的可重用工具：`_gen_kline.py`（專案根，抓一檔近一年 K線 → ECharts HTML 至 `img/`）。
