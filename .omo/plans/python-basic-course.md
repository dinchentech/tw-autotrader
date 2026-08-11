# Python 基礎教學課程 — 8 週產出計畫

## TL;DR
> **Summary**: 為非資訊科系的大學畢業生設計 8 週 Python 基礎課程，每週 1 小時，使其能讀懂 tw-autotrader 的策略與實盤程式碼，並能用 OpenCode（AI）輔助修改。
> **Deliverables**: 8 個 `.md` 教學檔 + 8 個小程式 `.py` + 測試資料 CSV + README.md
> **Effort**: Large (17 個檔案)
> **Parallel**: YES - 3 waves

## 檔案結構

```
python_basic/
├── README.md                          # 課程總覽
├── data/
│   ├── prices_short.csv               # 20 根 K 線（範例資料）
│   └── prices_medium.csv              # 60 根 K 線（練習資料）
├── week-01-認識Python.md
├── week-01-calc_return.py
├── week-02-資料容器.md
├── week-02-build_dataframe.py
├── week-03-條件判斷.md
├── week-03-simple_signal.py
├── week-04-移動平均.md
├── week-04-rolling_demo.py
├── week-05-四大策略拆解.md
├── week-05-tweak_params.py
├── week-06-live_trader流程.md
├── week-06-simple_live.py
├── week-07-用AI改程式.md
├── week-07-opencode_practice.py
├── week-08-整合回顧.md
└── week-08-final_exercise.py
```

## 各週內容規格

### 共同結構（每週 .md）
- 本週目標（1 句話）
- 原專案對應檔案（提示學習者打開哪個檔案看）
- 核心觀念（≤ 5 點，重點式）
- 小程式說明（連接到同週的 .py）
- 本週練習（打開原專案哪支檔案、找哪段程式碼）
- 學完自評清單（3~5 題是非題）

### 共同結構（每週 .py）
- 頂端註解說明本程式做什麼
- 使用 csv 或 pandas 讀取 data/ 下的測試資料
- 印出易懂的輸出結果
- 若使用 OpenCode，在腳本內以註解提示可以問 AI 什麼

### 週次內容

**第 1 週：認識 Python**
- md 教：變數、數字型態（int/float）、文字（string）、加減乘除、print()
- py：讀取 prices_short.csv，計算最後一根 K 線相對於第一根的報酬率
- 對應原專案：strategies/vwap_deviation.py 第 14 行 `df['VWAP'] = df['close']`

**第 2 週：資料容器**
- md 教：list、dict、pandas DataFrame 概念（不教語法細節）、df['column'] 讀取欄位
- py：用 pandas 讀 CSV → df.head() 觀察 → 計算本日 vs 昨日的漲跌
- 對應原專案：strategies/ma_cross.py 第 13~14 行 `df['MA_Fast'] = ...`

**第 3 週：條件判斷**
- md 教：if/elif/else、比較運算子（> < >= <= ==）、and/or
- py：讀取資料 → 判斷收盤價是否在 20 日均線上方 → 印出 buy/sell/hold
- 對應原專案：strategies/bollinger.py 第 27~28 行 `buy_condition = ...`

**第 4 週：移動平均與 rolling window**
- md 教：什麼是滑動視窗、period 參數的意義、為什麼要有 warm-up
- py：用 pandas rolling 算 5 日均線 → 與手算對比 → 觀察前 4 根為 NaN
- 對應原專案：所有策略的 rolling(window=XX)

**第 5 週：四大策略拆解**
- md 教：逐行導讀四支策略（vwap_deviation.py / ma_cross.py / bollinger.py / breakout.py）
- py：用 OpenCode 修改策略參數（例如把 bollinger 的 std_dev 從 2.0 改為 2.5），然後用 backtest.py 驗證
- 練習：打開每支策略，指出哪一行是買進條件、哪一行是賣出條件

**第 6 週：live_trader 流程**
- md 教：主迴圈 while True、time.sleep、broker API 概念、signal → 下單流程
- py：簡化版監控迴圈（每 5 秒檢查一次模擬資料，有訊號就印通知）
- 對應原專案：live_trader_finmind.py 的 run_live_trading() 函式

**第 7 週：用 AI 改程式**
- md 教：OpenCode 是什麼、怎麼問問題（提供 5 個實用 prompt 模板）
- py：3~4 個小練習題目（例如「把均線交叉的 fast_period 改成 12」、「在 breakout 中加入成交量過濾條件」）
- 練習：用 OpenCode 實際改一個策略參數並跑 backtest 驗證

**第 8 週：整合回顧**
- md 教：建立完整的參數 → 回測 → 調整 → 實盤心智模型
- py：自選一支策略，用 OpenCode 做一個修改 → 跑 backtest 回測 → 比較修改前後績效
- 練習：回答 5 個反思問題

## 測試資料規格

### prices_short.csv（20 根 K 線）
- 欄位：date, open, high, low, close, volume
- 模擬股價從 150 → 162.5 → 154.5 的波動走勢
- 包含上漲與下跌段，適合展示買賣訊號

### prices_medium.csv（60 根 K 線）
- 欄位同上
- 模擬更長的趨勢，含多次轉折
- 給第 5~6 週練習用

## Wave 1：基礎建設 + 第 1~4 週
Task 1：建立 data/prices_short.csv 與 data/prices_medium.csv
Task 2：第 1 週 .md + .py
Task 3：第 2 週 .md + .py
Task 4：第 3 週 .md + .py
Task 5：第 4 週 .md + .py

## Wave 2：策略 + 實盤（第 5~6 週）
Task 6：第 5 週 .md + .py
Task 7：第 6 週 .md + .py

## Wave 3：AI 改程式 + 整合（第 7~8 週 + README）
Task 8：第 7 週 .md + .py
Task 9：第 8 週 .md + .py
Task 10：README.md
