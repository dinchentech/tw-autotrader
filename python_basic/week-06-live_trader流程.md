# 第 6 週：live_trader 是怎麼活的？

## 本週目標
> 能讀懂 live_trader_finmind.py 的主要流程：初始化 → 取得資料 → 跑策略 → 判斷訊號 → 下單 → 等一分鐘 → 繼續。

## 原專案對應檔案
- `live_trader_finmind.py` 第 28~127 行（run_live_trading 函式）
- `live_trader_multi.py` 第 75~180 行（main 函式的主迴圈）

## 核心觀念
1. **主迴圈（Main Loop）**：程式不是跑一次就結束，而是用 `while True` 一直重複執行。
2. **每分鐘檢查一次**：`time.sleep(60)` 讓程式暫停 60 秒，避免一直打 API 被擋。
3. **Broker API**：程式透過網路連到券商（或模擬器）取得即時股價。
4. **訊號 → 下單**：策略跑出 signal=1 就買進，signal=-1 就賣出。
5. **風險控管**：下單前會檢查（單筆風險、每日虧損上限、交易次數限制）。

## 小程式說明
`week-06-simple_live.py` 是一個簡化版的監控程式 — 它讀取 CSV 但用 `time.sleep` 控制速度，讓你感受「每分鐘檢查一次」是怎麼回事。

## 本週練習
1. 打開 `live_trader_finmind.py`，找出 `while True:`（第 65 行）
2. 找出 `time.sleep(60)`（第 120 行）
3. 找出風險控管的檢查（第 95 行）
4. 找出下單執行的程式碼（第 107 行）

## 學完自評清單
- [ ] 我知道 `while True` 代表程式會一直跑、不會自己停
- [ ] 我知道 `time.sleep(60)` 讓程式暫停 60 秒
- [ ] 我能在 live_trader_finmind.py 中找出策略判斷 → 風險控管 → 下單的流程
- [ ] 我執行過 week-06-simple_live.py 並看到模擬的監控輸出

## 下週預告
下週要學最重要的一招：用 AI（OpenCode）幫你改程式！
