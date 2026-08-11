# 課程 B 投影片大綱 — 有程式背景加速班（3 堂 × 3hr = 9hr）

> **核心理念**：學員會 Python，直接深入程式碼，但同時充分利用 OpenCode + OMO + FinMind Skill 加速開發。  
> 重點不在「怎麼手動打指令」，而是「怎麼指揮 AI 幫你寫程式」。

---

## 第 1 堂：AI 加速策略開發（3hr）

### 1.1 OMO + OpenCode 開發流程（15 min, ~7 slides）

| # | 標題 | 內容 | 講師筆記 |
|---|------|------|---------|
| 1 | 開場：這 3 堂你能做到的事 | 讀懂全部策略 → 用 AI 修改策略 → 用 AI 新增策略 → AI 協助擴充 broker → 部署 production | 工程師的成就感 |
| 2 | AI 開發工作流 | **你不寫程式，你指揮 AI 寫程式**。Prometheus(規劃) → Sisyphus(實作) → Oracle(除錯) → Explore(搜尋) | 展示 OMO 架構 |
| 3 | 實戰場景 | 🎤「幫我在 ma_cross.py 加一個 volume filter」→ Prometheus 規劃 → Sisyphus 改程式碼 → 你 review | 你的角色轉為 QA |
| 4 | FinMind Skill 戰力全開 | 🎤「查 2330 最近一季營收趨勢，並跟股價做 overlay」→ AI 自動抓資料+畫圖 | 基本面+技術面一次搞定 |
| 5 | OpenCode 開發者模式 | 除了中文對話，也可以直接編輯檔案 + `/debugging` 除錯 + `/refactor` 重構 | 內建開發工具 |
| 6 | 專案架構快速鳥瞰 | 入口點對照、strategies/ 雙軌設計（function vs class）、三大核心模組 | 跟 AGENTS.md 對照 |
| 7 | ⚠️ 最大坑：雙軌策略系統 | Function-based（strategies/*.py）用在多股主力。Class-based（*_strategy.py）用在舊版單股。min_periods 預設不同導致 signal 不一致 | 一定要讓學員知道 |

### 1.2 用 AI 讀懂策略程式碼（30 min, ~12 slides）

| # | 標題 | 內容 | 講師筆記 |
|---|------|------|---------|
| 8 | 🎤 AI 解說策略 | 「幫我解釋 ma_cross.py 的每一行在做什麼」→ AI 逐行註解 | AI 可以當助教 |
| 9 | 🎤 AI 比較雙版本差異 | 「比較 ma_cross.py 和 ma_cross_strategy.py 的 signal 計算差異」→ AI 指出 min_periods | AI 做 code review |
| 10 | Function-based 模式 | `def strategy(df, params)` → `return df[signal]`。DataFrame in/out | 共同模式 |
| 11 | signal 產生流程圖 | 計算指標 → 條件判斷 → signal column(1/-1/0) | 讀懂一個就懂全部 |
| 12 | 🎤 AI 視覺化策略邏輯 | 「把 ma_cross 的買賣點畫在 K 線圖上」→ AI 用 matplotlib 畫圖 | AI 取代 TradingView |
| 13 | 🎤 AI 找程式潛在問題 | 「檢查 breakout.py 有沒有 bug 或跟其他策略不一致的地方」→ AI 找出 ATR hardcode 問題 | 這個練習題很棒 |
| 14 | 快速遍歷四策略（AI加速） | 🎤「幫我用表格對比四個策略的計算方式、參數、訊號條件」 | AI 整理 |
| 15 | Bollinger — std + RSI 雙過濾 | SMA(20) ± 2×STD(20) + RSI(5) 雙重確認 | 統計學+情緒指標 |
| 16 | VWAP — 成交量加權平均 | Σ(close×volume)/Σ(volume)，rolling 20 | 需要 volume column |
| 17 | MA Cross — 趨勢跟隨經典 | 快線(9) vs 慢線(21)，ATR 過濾盤整 | 最古老但有效 |
| 18 | Breakout — Donchian Channel | N 天最高價突破，ATR 硬編碼問題 | ATR = `df['close']*0.01` |
| 19 | 🎤 AI 策略對戰分析 | 「對 2330 用四種策略各跑一次回測，比較績效，分析為什麼某策略表現最好」 | AI 執行+分析 |

### 1.3 用 AI 修改策略（30 min, ~12 slides）

| # | 標題 | 內容 | 講師筆記 |
|---|------|------|---------|
| 20 | 🎤 場景：改 ATR 門檻 | 「幫我把 ma_cross.py 的 atr_threshold 預設值從 0.005 改為 0.01」→ Sisyphus 修改 | AI 改 code |
| 21 | 🎤 場景：加 Volume Filter | 「幫我在 breakout.py 加一個成交量過濾：今日成交量要 > 過去 20 天平均成交量的 1.5 倍才觸發訊號」 | AI 設計+實作 |
| 22 | 🎤 場景：修 bug | 「幫我修復 breakout.py 中 ATR threshold 硬編碼的問題，改為使用參數 atr_threshold」 | AI 實作修正 |
| 23 | 🎤 場景：新增 RSI filter | 「幫我在 ma_cross.py 加入 RSI 過濾：金叉時 RSI > 50 才買」 | 複合策略 |
| 24 | 🎤 AI 做參數敏感性測試 | 「幫我對 ma_cross 做 grid search：fast_period 從 5 到 20 間隔 5，show 結果」 | AI 寫 loop + 跑 |
| 25 | Overfitting 檢查（AI 加速） | 🎤「幫我把找到的最佳參數拿去跑 2020-2022 和 2022-2024 兩段時間，看穩定性」 | — |
| 26 | 🎤 AI 做跨市場驗證 | 「把這個參數集拿去跑 0050、00878、2881，看是不是都有效」 | — |
| 27 | 🎤 AI 寫測試 | 「幫我對新增的 volume filter 寫 unit test」 | AI 補測試 |
| 28 | 🎤 AI 生成策略文件 | 「幫我更新策略說明.md，加入新 filter 的描述」 | AI 寫文件 |
| 29 | 策略引擎+風險管理 | 🎤「解釋 StrategyEngine 和 RiskManager 的程式碼架構，畫流程圖」 | AI 幫助理解 |
| 30 | 風險管理器邏輯 | can_trade() 判斷：每日交易次數、每日虧損、漲跌停 | 簡單但重要 |
| 31 | MarketFilter  | 🎤「解釋 market_filter.py 的 FinMind fallback 機制」 | — |

---

## 第 2 堂：AI 擴展多股系統與資料源（3hr）

### 2.1 🎤 AI 解讀多股系統（25 min, ~10 slides）

| # | 標題 | 內容 | 講師筆記 |
|---|------|------|---------|
| 1 | 🎤 AI 架構總覽 | 「解釋 live_trader_multi.py 的整體架構，畫流程圖」→ AI 分析 630 行程式碼 | — |
| 2 | 啟動流程解析 | load_portfolio() → 選 Broker → init 策略 → init 風控 → 主循環 | — |
| 3 | 🎤 AI Debug 載入流程 | 「幫我 trace PORTFOLIO 從 .env 讀取到策略實例化的完整流程」 | — |
| 4 | BROKER 選擇機制 | `BROKER=esun` → EsunProvider。`BROKER=kgi` → mock 或 real | if-elif-else |
| 5 | 🎤 AI 幫你擴充 Broker | 「幫我在 kgi_mock.py 加入一個新的行情模擬模式：回傳特定價格序列」 | AI 實作 |
| 6 | 資料源抽象層 | 五種 provider：Yahoo/FinMind/KGI Mock/KGI Real/E.Sun | duck typing 設計 |
| 7 | 🎤 AI 分析資料源差異 | 「比較五種資料源的 method signature 和回傳格式」 | — |
| 8 | 🎤 AI 改通知格式 | 「幫我把 Telegram 通知加上當日損益和持有庫存」 | AI 改程式碼 |
| 9 | 每月預算追蹤 | MONTHLY_BUDGET_* → logs/monthly_budget.json | 跨 session 持久化 |
| 10 | 🎤 AI 加新功能 | 「幫我在通知中加上 VWAP 偏離度數值」 | — |

### 2.2 🎤 AI 查資料 + 分析（25 min, ~10 slides）

| # | 標題 | 內容 | 講師筆記 |
|---|------|------|---------|
| 11 | 🎤 基本面分析 | 「分析 2454 聯發科最近四季的 EPS 趨勢和營收年增率」→ FinMind 自動拉資料 | AI 取代研究員 |
| 12 | 🎤 籌碼面分析 | 「最近一個月外資對 2330 的買賣超變化」→ AI 畫圖 | — |
| 13 | 🎤 選股篩選器 | 「幫我找出 PER < 20、月營收年增率 > 10%、法人買超的股票」 | 多條件查詢 |
| 14 | 🎤 同業比較 | 「比較台積電、聯發科、聯電最近一季的毛利率和營益率」 | — |
| 15 | 🎤 總體經濟 | 「查最近美元兌台幣匯率和美國十年期公債殖利率」 | — |
| 16 | 🎤 期貨法人動向 | 「查台指期外資淨多單變化」 | — |
| 17 | 🎤 策略結合基本面 | 「幫我把 ma_cross 和月營收年增率 > 0 的條件結合」→ 修改策略程式碼 | AI 做複合策略 |
| 18 | Intent-to-Dataset 對應 | 使用者意圖 → FinMind dataset 的對應表（價格/法人/基本面/期權） | 深入理解 FinMind |
| 19 | 🎤 AI 做 Dashboard | 「幫我做一個 HTML 儀表板，顯示目前持有股票的股價+法人動向+策略訊號」 | AI 從 FinMind 拉資料+畫圖 |
| 20 | Rate Limit 管理 | FinMind Free 600 req/hr。🎤「幫我計算我的策略一天需要多少 API 呼叫」 | — |

---

## 第 3 堂：AI 部署 + 監控 + 策略迭代（3hr）

### 3.1 🎤 AI 協助 Docker 化（20 min, ~8 slides）

| # | 標題 | 內容 | 講師筆記 |
|---|------|------|---------|
| 1 | 🎤 AI 解說 Dockerfile | 「解釋這個 Dockerfile 每一行的作用，以及最佳化建議」 | — |
| 2 | slim image + 多階段 build | python:3.10-slim vs 3.10、pip install cache 管理 | — |
| 3 | docker-compose.yml 結構 | volumes 讓 .env 即時生效、restart:always、log rotation | — |
| 4 | 🎤 AI 優化 Dockerfile | 「幫我優化 Dockerfile 減少 build 時間，加入健康檢查」 | — |
| 5 | 🎤 AI 寫 deploy script | 「幫我寫一個 deploy.sh，支援多環境（dev/staging/prod）」 | — |
| 6 | GCP e2-micro 部署 | 每月 ~NT$200，台灣機房。Instance Schedules 定時開關 | 極低成本 |
| 7 | 🎤 AI 設定排程 | 「幫我寫一個 cron job，每天早上 8:30 啟動 trader、下午 13:30 關閉」 | AI 寫 crontab |
| 8 | 🎤 AI 做監控告警 | 「幫我寫一個監控腳本，如果 container 掛掉或 API 斷線就發 Telegram 警告」 | — |

### 3.2 🎤 AI 深度績效分析（25 min, ~10 slides）

| # | 標題 | 內容 | 講師筆記 |
|---|------|------|---------|
| 9 | 🎤 AI 分析回測結果 | 「幫我分析這份回測報告，指出優缺點和改善方向」 | AI 當分析師 |
| 10 | 🎤 AI 深度回撤分析 | 「找到最大回撤期間，分析當時市場發生了什麼，以及策略為何賠錢」 | — |
| 11 | 🎤 AI 對比 baseline | 「跟 buy-and-hold 比較，這個策略的超額報酬是多少？」 | — |
| 12 | 回測指標深度 | 年化報酬率、Sharpe Ratio、Sortino Ratio、獲利因子、盈虧比 | 工程師喜歡數據 |
| 13 | 🎤 AI 算績效指標 | 「幫我算出這個回測的 Sharpe Ratio 和最大回撤」 | — |
| 14 | 🎤 AI Walk-forward 驗證 | 「幫我做 walk-forward 驗證：2020-2021 訓練、2022 驗證、2023-2024 測試」 | AI 實作 |
| 15 | 🎤 AI 做蒙地卡羅模擬 | 「幫我做蒙地卡羅模擬，評估這個策略的 robustness」 | — |
| 16 | 🎤 AI 參數可視化 | 「把 grid search 的結果畫成 heatmap，幫我找到最佳參數區域」 | — |
| 17 | 🎤 AI 比較回測與實盤 | 「幫我比較回測預期和實際模擬交易的績效差異，分析 gap 來源」 | — |
| 18 | 🎤 AI 自動化每日報告 | 「幫我寫一個腳本，每天收盤後自動跑績效分析+寄報告」 | — |

### 3.3 🎤 AI 驅動策略迭代（25 min, ~10 slides）

| # | 標題 | 內容 | 講師筆記 |
|---|------|------|---------|
| 19 | 策略開發的生命週期 | 想法 → Prometheus 規劃 → AI 實作 → 回測驗證 → Walk-forward → 上線 → 監控 | 完整流程 |
| 20 | 🎤 場景：新增一個策略 | 「我想做一個策略：開盤漲幅 > 2% 且成交量 > 前日 2 倍就買進」→ AI 規劃+實作 | 新策略 from scratch |
| 21 | 🎤 場景：策略組合優化 | 「幫我分析目前組合中各策略的相關性，建議怎麼調整比例」 | AI 做量化分析 |
| 22 | 🎤 場景：市場狀態分類 | 「幫我寫一個模組，判斷目前市場是盤整/趨勢/高波動/低波動」→ AI 實作 | 情境感知 |
| 23 | 🎤 場景：動態策略切換 | 「幫我寫一個邏輯：如果市場是盤整就用布林、趨勢就用均線」 | 策略切換器 |
| 24 | 🎤 場景：回測報告自動化 | 「幫我把回測結果輸出成跟 README 一樣格式的 MD 報告」 | — |
| 25 | 🎤 場景：AI 寫 CHANGELOG | 「幫我根據 git log 產出這週的變更記錄」 | — |
| 26 | 🎤 場景：程式碼品質 | 「幫我 review 最近修改的程式碼，指出潛在問題和改進方向」 | AI code review |
| 27 | Overfitting — 永遠的對手 | AI 讓開發變快，但也讓 overfitting 更容易。保持質疑 | 工程師的修養 |
| 28 | 結語 | AI 不會取代交易員，但會取代不用 AI 的交易員。**你的競爭力 = 交易知識 + 指揮 AI 的能力** | — |

---

> 🎤 = 學員可以直接對 OpenCode 說的中文指令。實做環節就是「用 AI 解決實際問題」