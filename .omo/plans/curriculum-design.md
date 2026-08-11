# TW AutoTrader 三階課程設計大綱

## TL;DR

> **Summary**: 針對三種學員（純小白、有程式背景、無程式投資人）設計三套課程，每堂 3 小時（90' 講課 + 90' 實做），共用同一份 tw-autotrader 專案但切入點和深度不同。
> **Deliverables**: 課程 A（4 堂 × 3hr = 12hr）、課程 B（3 堂 × 3hr = 9hr）、課程 C（6 堂 × 3hr × 2 日 = 18hr）完整大綱
> **Effort**: Medium
> **Parallel**: NO
> **Critical Path**: 課程 A → 課程 B → 課程 C（共用核心教材結構）

---

## 前提（所有課程通用）

### 學員環境
學員收到已設定好的 **WSL 備份檔**，解壓縮後包含：
- Ubuntu WSL + Python 3.10+ + pip、venv
- PyCharm Community/Professional
- OpenCode + FinMind skill + 相關 agents
- 完整 tw-autotrader 目錄（含所有原始碼）
- 玉山 E.Sun SDK（已安裝）
- 預設 .env 範本
- Docker + docker-compose

**學員只需做**：申請 FinMind API Token → 填入 .env → 啟動 OpenCode → 開始上課

### 課程結構共用設計

| 環節 | 時間 | 說明 |
|------|------|------|
| 講課 | 90 min | 概念解說 + 程式/操作演示 |
| 實做 | 90 min | 學員動手 + 助教巡迴（建議 1:8 助教學員比） |
| 休息 | 10 min（內嵌） | 在 90' 中間插入 |

### 每堂課產出
每堂結束學員應有具體可運行的成果（跑成功的回測、修改過的 .env、看懂的一張圖表）— 不只有「學到觀念」。

---

## 課程 A：小白從零開始（4 堂 × 3hr = 12hr）

> **對象**：完全沒有程式經驗，但會用電腦開瀏覽器、打字。
> **核心理念**：先建立「操作肌肉記憶」，再補理論。不教 Python 語法，只教「怎麼執行這些指令會發生什麼事」。

### 課前準備（學員自行完成，約 30 分鐘）
- ✅ 解壓縮 WSL 備份檔
- ✅ 申請 FinMind API Token（[finmind-api.tw](https://finmind-api.tw)）
- ✅ 打開 WSL terminal，確認 `python --version` 有輸出
- ✅ 將 FinMind Token 填入 `tw-autotrader/.env` 中的 `FINMIND_API_TOKEN`
- ✅ 執行 `pip install -r requirements.txt && pip install python-dotenv yfinance tqdm`
- ✅ 執行 `python backtest_finmind.py` 確認可以跑（預設就會跑台積電 2330）

---

### 第 1 堂：認識你的交易機器人（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| 1.1 什麼是自動交易？ | 20' | 手動 vs 自動交易的差別、這套系統能做什麼（回測/模擬/實盤）、學完這 4 堂你能做到的事 |
| 1.2 你的工具箱導覽 | 25' | WSL 是什麼（圖示說明）、專案目錄結構（只講 6 個資料夾的用途）、.env 檔案的角色、terminal 基本操作（`ls`, `cd`, `python xxx.py`） |
| 1.3 第一次回測 | 25' | 什麼是「回測」？展示跑 `python backtest.py --strategy ma_cross` 的過程、看懂輸出結果（獲利/交易次數/勝率） |
| 1.4 四種賺錢方法簡介 | 20' | 一句話 + 一張圖介紹四大策略 — 布林反轉（跌深反彈）、VWAP（偏離回正）、均線交叉（趨勢跟隨）、突破（追強勢） |

**實做（90'）** — 目標：每個人都成功跑出第一份回測報告

| 步驟 | 預計 | 動作 |
|------|------|------|
| 環境確認 | 10' | 打開 terminal，`cd tw-autotrader`，`ls` 看到資料夾，確認 `.env` 有 Token |
| 第一個指令 | 10' | `python backtest.py --strategy ma_cross` — 看著數字跑出來 |
| 試其他策略 | 15' | 換 `--strategy vwap`、`--strategy bollinger`、`--strategy breakout` |
| 加參數 | 15' | `python backtest.py --strategy ma_cross --fast_period 5 --slow_period 60` — 看到結果不同 |
| FinMind 回測 | 15' | `python backtest_finmind.py` — 對照差異 |
| 自己試參數 | 25' | 自由探索：改數字、換股票代碼（--symbol 2330→0050），看結果怎麼變 |

**本堂產出** ✅ 成功跑完 4 種策略回測，至少修改過 1 次參數看到結果變化

---

### 第 2 堂：看懂四大策略 — 不做程式設計師，做策略設計師（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| 2.1 布林通道反轉（Bollinger） | 20' | 一句話：跌深反彈。用 bollinger-animation.html 展示。三個數字：Window=20, Std=2, RSI=5。什麼時候買/賣？ |
| 2.2 VWAP 偏離反轉 | 15' | 一句話：偏離均價太遠會回來。VWAP 是「真正的平均成本」(成交量加權)。Sigma 倍數控制敏感度 |
| 2.3 均線交叉（MA Cross） | 15' | 一句話：短期均線穿過長期均線 = 趨勢開始。快線週期 vs 慢線週期。ATR 過濾（波動太小不交易） |
| 2.4 唐奇安突破（Breakout） | 15' | 一句話：創近期新高就追上車。Lookback 天數。海龜交易法則簡化版 |
| 2.5 Keep & Wait + 法人動能 | 10' | Keep_Wait（越跌越買的 DCA 低接）、法人抬轎（跟著投信+外資買） |
| 2.6 策略比較矩陣 | 15' | 哪種策略適合哪種市場？（盤整/趨勢/大跌/大漲）。搭配表：看策略說明.md |

**實做（90'）** — 目標：能為每種策略調整參數並觀察效果變化

| 步驟 | 預計 | 動作 |
|------|------|------|
| 布林調參 | 20' | 跑 Bollinger：改 `--bollinger_window 10 vs 30`、`--bollinger_std_dev 1.5 vs 2.5` — 看訊號密度變化 |
| VWAP 調參 | 15' | 跑 VWAP：改 `--vwap_sigma_mult 1.0 vs 2.0` — 看交易次數變化 |
| 均線調參 | 15' | 跑 MA Cross：`--fast_period 5 --slow_period 60` vs `--fast_period 20 --slow_period 50` |
| 突破調參 | 10' | 跑 Breakout：`--breakout_lookback 10 vs 40` |
| 對戰分析 | 20' | 同一支股票（如 2330），四種策略各跑一次，比較 total_return — 哪個賺最多？ |
| 自由探索 | 10' | 學員選自己有興趣的股票/策略組合 |

**本堂產出** ✅ 完成「四策略參數比較表」（自填：哪個參數讓交易變多/變少、哪個賺最多）

---

### 第 3 堂：投資組合配置 — 多股多策略實戰（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| 3.1 為什麼要分散？ | 15' | 單策略缺點、雞蛋不放同一個籃子、2024-2025 真實績效展示（README 中的方案一/二） |
| 3.2 PORTFOLIO 設定 | 20' | 格式解說 `0050:bollinger,2330:ma_cross,...`。演示 live_trader_multi.py 如何載入 |
| 3.3 資金配置計算 | 20' | TOTAL_CAPITAL、各策略 ALLOC_% 的關係。展示 `ALLOC_BOLLINGER=40` 如何算出可用資金 |
| 3.4 風險控管 | 20' | MAX_DAILY_TRADES、MAX_DAILY_LOSS、大盤年線過濾（MARKET_TREND_FILTER）、金字塔加碼 |
| 3.5 通知系統 | 15' | Telegram Bot 設定、LINE Notify、如何知道機器人在幹嘛 |

**實做（90'）** — 目標：設計自己的投資組合並模擬跑起來

| 步驟 | 預計 | 動作 |
|------|------|------|
| 設計組合 | 20' | 決定 4-6 檔股票、分配策略。先用 `simulate_portfolio.py` 試算 |
| 編輯 .env | 10' | 修改 PORTFOLIO 和 ALLOC_* 對應自己的組合 |
| 跑多股模擬 | 20' | `python live_trader_multi.py`（模擬模式 — BROKER=kgi, USE_REAL_API=false） |
| 看交易日誌 | 15' | 打開 `logs/performance.csv`，看懂每筆交易的記錄。用 Excel/VS Code 打開 |
| 調整再跑 | 15' | 根據第一次結果調整 ALLOC_% 或策略配對，重新模擬 |
| Telegram 設定 | 10' | 申請 Bot Token、設定 chat_id、測試通知發送 |

**本堂產出** ✅ 完成自己的投資組合設定檔、成功跑過多股模擬、看懂 performance.csv

---

### 第 4 堂：上線部署與實戰監控（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| 4.1 模擬 → 實盤的關鍵一步 | 15' | USE_REAL_API=true 的意義。先紙上模擬 1 個月再上線 |
| 4.2 券商串接 | 20' | 玉山 vs 凱基的選擇。玉山憑證（.p12）設定、BROKER=esun vs kgi |
| 4.3 回測完整工作流 | 25' | 真實工作流：選股→策略配對→回測→調整→組合模擬→驗證→部署。如何解讀回溯_2024_2025.MD 等級的報告 |
| 4.4 Docker 部署 | 15' | 什麼是 Docker？docker-compose.yml 結構。在 VM 上跑 vs 在自己電腦跑 |
| 4.5 日常維護 | 15' | 每天看什麼（Telegram 通知/performance.csv）、每週做什麼、何時調整策略參數 |

**實做（90'）** — 目標：完成從回測到部署的完整流程

| 步驟 | 預計 | 動作 |
|------|------|------|
| 完整回測報告 | 20' | 對自己的投資組合產出 md 格式回測報告、解讀總報酬/勝率/最大回撤/Sharpe |
| Docker build | 15' | `docker build -t tw-autotrader .` — 看到 build 成功 |
| Docker run | 10' | `docker compose up -d` — 看到 container 跑起來、看 logs |
| 調整再重啟 | 10' | 修改 .env → `docker compose restart` — 體會不需 rebuild |
| 開放式 QA | 35' | 學員自由提問、助教協助解決實際問題、回顧四堂課學到的全部流程 |

**本堂產出** ✅ 自己的 Docker container 在背景跑、會完整的回測→部署流程、有 Telegram 通知

---

## 課程 B：有程式背景加速班（3 堂 × 3hr = 9hr）

> **對象**：會 Python、用過 terminal/pip/git，但沒做過金融交易系統。
> **核心理念**：跳過環境安裝和基本操作，直接深入策略邏輯、程式結構、參數校調、客製化修改。

### 課前準備（學員自行完成）
- ✅ 解壓縮 WSL 備份，確認可執行 `python backtest.py --strategy vwap`
- ✅ 申請 FinMind Token 並填入 .env
- ✅ 快速瀏覽 `使用手冊.md` 第一章

---

### 第 1 堂：策略核心 — 從程式碼理解交易邏輯（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| 1.1 專案架構鳥瞰 | 15' | AGENTS.md 的架構圖 + 入口點對照。Function-based vs Class-based 策略的雙軌設計（重點！） |
| 1.2 讀懂一份策略程式碼 | 30' | 以 `strategies/ma_cross.py` 為例逐行解說：signal 計算邏輯、DataFrame in/out 模式、min_periods=1 的陷阱 |
| 1.3 四策略演算法深度 | 30' | Bollinger（std 統計 + RSI 情緒雙過濾）、VWAP（volume-weighted 計算）、Breakout（Donchian Channel） |
| 1.4 策略引擎與風險管理 | 15' | `core/strategy_engine.py` 包裝模式、`core/risk_manager.py` 怎麼攔截交易 |

**實做（90'）** — 目標：能讀懂並修改策略參數

| 步驟 | 預計 | 動作 |
|------|------|------|
| 追蹤策略執行 | 20' | 在 `backtest.py` 加 `print` 或設中斷點，觀察 signal 怎麼產生的 |
| 改 ATR 門檻 | 15' | 修改 `ma_cross.py` 的 ATR threshold 邏輯（目前有一致性問題），觀察對回測的影響 |
| 加新 filter | 25' | 在任一策略中加一個簡單的 volume filter（成交量太低跳過），重新回測 |
| 比較雙版本 | 15' | 同一策略 function-base vs class-based 的 signal 差異（min_periods 造成的 mismatch） |
| 參數敏感性測試 | 15' | 寫一個簡單 loop 跑多組參數組合，找出 best performer |

**本堂產出** ✅ 至少改過一個策略的程式碼並看到回測結果變化、理解雙版本差異

---

### 第 2 堂：多股系統與資料流（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| 2.1 多股系統設計 | 25' | `live_trader_multi.py` 的 event loop 結構、每分鐘 tick 流程、portfolio 載入邏輯 |
| 2.2 資料源抽象層 | 25' | data/ 目錄設計：Yahoo/FinMind/KGI mock/KGI real/E.Sun 五種 provider、BROKER 選擇機制、mock vs real 切換 |
| 2.3 資金管理模型 | 20' | 百分比配置計算、每月預算（monthly_budget.json）、金字塔加碼演算法 |
| 2.4 市場趨勢過濾 | 20' | `core/market_filter.py` — TAIEX > MA200 才買、FinMind fallback 機制 |

**實做（90'）** — 目標：能在多股系統中加入自己的邏輯

| 步驟 | 預計 | 動作 |
|------|------|------|
| 擴充投資組合 | 15' | 在 .env 中加入新股票+策略組合、debug 載入流程 |
| 加 broker mock | 25' | 在 `kgi_mock.py` 中加入一個新的 mock handler（如回傳特定價格模式） |
| 改通知格式 | 20' | 修改 `utils/telegram.py` 中的訊息格式，加入更多交易資訊 |
| 設 monthly budget | 15' | 實作並觀察 MONTHLY_BUDGET_* 如何限制交易次數 |
| 測 market filter | 15' | 開關 MARKET_TREND_FILTER，比較 filter on/off 的交易差異 |

**本堂產出** ✅ 擴充過 broker mock、改過通知格式、理解資金控管實際運作

---

### 第 3 堂：部署、監控與生產化（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| 3.1 Docker 化部署 | 20' | Dockerfile 分析（slim image、volume mount、log rotation）、docker-compose.yml 結構 |
| 3.2 GCP 生產環境 | 20' | e2-micro 成本、Instance Schedules 定時開關機、pipe deploy 流程（docker save + gzip + ssh） |
| 3.3 策略績效評估 | 25' | 回測指標深度解讀：總報酬率 vs 年化、最大回撤（Max Drawdown）、Sharpe Ratio、獲利因子、勝率+盈虧比 |
| 3.4 參數校調方法論 | 25' | Overfitting 風險、Walk-forward 驗證概念、什麼時候該調參什麼時候該認錯 |

**實做（90'）** — 目標：完成生產級部署、能自行評估策略績效

| 步驟 | 預計 | 動作 |
|------|------|------|
| 完整效能報告 | 20' | 對多組參數組合產出比較報表（用 simulate_portfolio.py 或自寫腳本） |
| Deep-dive 回撤分析 | 15' | 找到最大回撤期間、分析當時市場發生了什麼 |
| Docker 完整部署 | 15' | build + compose up + 驗證 logs + 修改 .env + restart |
| 寫一個小 helper | 20' | 自選題：寫一個 daily report 腳本 / 價格 alert / 策略切換排程器 |
| 系統健檢 | 20' | 所有同學互相 review portfolio 設定、給建議、分享發現 |

**本堂產出** ✅ 可生產的 Docker 部署 + 自己的策略效能分析報告 + 至少一個 helper 腳本

---

## 課程 C：2 日投資人快攻班（6 堂 × 3hr = 18hr，分 2 天）

> **對象**：有投資經驗但不會寫程式，想用工具強化交易決策。
> **核心理念**：完全不碰程式碼，專注操作流程。提供模板和腳本，學員只要改 .env 和跑指令。

### 課前準備
- ✅ 解壓縮 WSL 備份（提供 step-by-step 影片）
- ✅ 申請 FinMind API Token
- ✅ 確認 terminal 可執行 `python backtest.py --strategy vwap`

---

### 第一天（3 堂 × 3hr = 9hr）

#### 第 1 堂：3 小時上手 — 第一次回測（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| C1.1 系統導覽 | 20' | 你的電腦現在有什麼？WSL/terminal/Python/tw-autotrader 的關係。只用 3 個指令就能開始 |
| C1.2 什麼是回測？ | 20' | 用數據驗證策略、不是憑感覺。展示 README 的 2024-2025 績效 — 方案一 +NT$46k、方案二 +NT$141k |
| C1.3 三大關鍵數字 | 20' | 總報酬率（賺多少）、勝率（幾次賺幾次賠）、最大回撤（最大帳面虧損） |
| C1.4 四種策略一句通 | 30' | 用動畫 HTML 展示四大策略的買賣點。附策略比較表 |

**實做（90'）**

| 步驟 | 預計 | 動作 |
|------|------|------|
| 第一個回測 | 10' | `python backtest.py --strategy bollinger` — 看數字跑 |
| 全部跑一次 | 20' | 四種策略各跑一次、記錄總報酬 |
| 換股票跑 | 20' | 改 `--symbol` 成自己有興趣的股票（2330/0050/00878/2881/2382） |
| 調一個參數 | 20' | 老師指定：布林 std_dev 1.5 vs 2.5，看哪個賺 |
| 自由探索 | 20' | 玩自己的股票+策略組合 |

**本堂產出** ✅ 自己的第一張策略績效比較表（誰賺最多）

---

#### 第 2 堂：參數怎麼調？（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| C2.1 每個參數代表什麼 | 25' | 布林：Window(週期長短) Std(敏感度) RSI(鈍化門檻)、VWAP: Sigma、均線: Fast/Slow、突破: Lookback |
| C2.2 調參黃金法則 | 25' | 一次只改一個參數（對照實驗）、先理解再調、預設值就是 good start |
| C2.3 過度最佳化的陷阱 | 20' | 什麼是 overfitting？為什麼回測很賺但實盤賠錢？保持簡單 |
| C2.4 策略適合哪種股票 | 20' | 大型權值 vs 中小型、波動大 vs 波動小 — 策略配對表 |

**實做（90'）**

| 步驟 | 預計 | 動作 |
|------|------|------|
| 參數 grid search | 25' | 用老師準備好的腳本（scripts/param_search.sh），一次跑 6 組參數，看結果表格 |
| 找出最佳組合 | 15' | 對自己的標的找出 best performer |
| 換標的驗證 | 20' | 把最佳參數拿去跑另一支股票 — 還是一樣賺嗎？體會 overfitting |
| 策略配對練習 | 15' | 給 5 支股票、選適合的策略並說明原因 |
| 小組討論 | 15' | 分享各自發現：哪個策略配哪支股票效果最好 |

**本堂產出** ✅ 自己的參數校調紀錄表 + 理解 overfitting 的親身體驗

---

#### 第 3 堂：建自己的投資組合（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| C3.1 為什麼要配置 | 15' | 複習 2024-2025 績效：單一策略 vs 組合的差異 |
| C3.2 PORTFOLIO 設定 | 20' | 一行設定搞定：`0050:bollinger,2330:ma_cross,...` |
| C3.3 資金比例決策 | 25' | 你有 50 萬怎麼分？ALLOC_* 的意義。老師示範三種配置方案 |
| C3.4 風控設定 | 30' | 每天最多買幾次？單日最大虧損？大盤不好要不要買？（MARKET_TREND_FILTER）金字塔加碼的威力 |

**實做（90'）**

| 步驟 | 預計 | 動作 |
|------|------|------|
| 設計配置 | 20' | 先手寫自己的配置方案（用提供的表格模板） |
| 編輯 .env | 15' | 把配置寫入 .env |
| 跑多股模擬 | 20' | `python simulate_portfolio.py` — 看組合績效 |
| 調整再跑 | 20' | 根據結果改配置比例，再模擬一次 |
| 存檔分享 | 15' | 把自己的設定存成 `.env.myportfolio`，和同學交換心得 |

**本堂產出** ✅ 自己的投資組合 .env 設定檔 + 模擬績效報表

---

### 第二天（3 堂 × 3hr = 9hr）

#### 第 4 堂：從模擬到上線（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| C4.1 模擬 vs 實盤 | 15' | 模擬怎麼運作（BROKER=kgi, USE_REAL_API=false）、差在哪？ |
| C4.2 券商選擇與設定 | 25' | 玉山（憑證+keyring） vs 凱基（API Key/Secret）。申請流程。模擬環境先測 |
| C4.3 通知設定 | 25' | Telegram Bot 從申請到設定完成（step-by-step）、LINE Notify 申請 |
| C4.4 每日檢核表 | 25' | 每天早上看什麼（Telegram 通知）、每週看什麼（performance.csv）、遇到問題怎麼辦 |

**實做（90'）**

| 步驟 | 預計 | 動作 |
|------|------|------|
| 啟動模擬交易 | 20' | `python live_trader_multi.py` — 觀察它怎麼跑 |
| 看交易日誌 | 15' | `cat logs/performance.csv`，用 Excel 打開看格式 |
| Telegram 設定 | 20' | 申請 Bot、填入 .env、發送測試訊息 |
| 換 BROKER=esun | 20' | 模擬玉山資料源（不需實體憑證也能測試資料流） |
| 設排程 | 15' | scripts/ 中的排程範本，讓系統每天定時啟動 |

**本堂產出** ✅ 模擬交易在背景跑、Telegram 有通知、知道如何切換券商

---

#### 第 5 堂：Docker 部署與 24/7 運作（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| C5.1 Docker 是什麼（非技術比喻） | 20' | 貨櫃概念：打包你的交易機器人，到處都能跑 |
| C5.2 一鍵部署流程 | 20' | `docker build` → `docker compose up -d` — 只需 3 個指令 |
| C5.3 部署到雲端 | 25' | GCP 免費方案、e2-micro 每月 $5-7 鎂、Instance Schedules 開關機 |
| C5.4 上線後的日常 | 25' | Log rotation 不會塞爆硬碟、如何重啟、修改 .env 不用重 build |

**實做（90'）**

| 步驟 | 預計 | 動作 |
|------|------|------|
| Docker build | 15' | `docker build -t tw-autotrader .` |
| Docker run | 10' | `docker compose up -d`、`docker compose logs` |
| 改 .env + restart | 10' | 修改某個參數 → `docker compose restart` — 不用 rebuild |
| 看 log 和 CSV | 15' | `docker compose exec app cat logs/performance.csv` |
| 雲端部署模擬 | 25' | 用 deploy.sh（在本地模擬 pipe 到 local VM） |
| 災難復原練習 | 15' | container 掛了怎麼辦？`docker compose down && docker compose up -d` |

**本堂產出** ✅ Docker container 穩定運作、會 deploy.sh 流程、知道災難復原

---

#### 第 6 堂：總結 — 你的交易系統上線了（3hr）

**講課（90'）**

| 主題 | 分鐘 | 內容 |
|------|------|------|
| C6.1 完整工作流回顧 | 20' | 從選股 → 策略配對 → 回測 → 調參 → 組合配置 → 驗證 → 部署 |
| C6.2 如何持續優化 | 20' | 每月回顧績效、何時該調整、什麼時候該認賠換策略 |
| C6.3 常見問題 FAQ | 25' | 回測賺但實盤賠？策略失效怎麼辦？API 斷線？憑證過期？market filter 連續擋買？ |
| C6.4 進階資源 | 25' | 使用手冊.md（完整參考）、策略說明.md（原理深化）、回溯說明.MD（進階回測）、原始碼閱讀指引（給想更進一步的人） |

**實做（90'）** — 最終驗收

| 步驟 | 預計 | 動作 |
|------|------|------|
| 最終驗收 | 20' | 從頭到尾走一遍：選股 → 設定 .env → 跑回測 → 調參 → 跑模擬 → Docker run |
| 問題排解挑戰 | 25' | 老師故意弄壞 .env/設定，學員找出問題並修復（API token 錯、BROKER 設錯、PORTFOLIO 格式錯） |
| 個人化設定 | 20' | 每位學員產出自己完整的投資組合（股票+策略+資金比例+風控） |
| QA 與結業 | 25' | 自由問答 + 學員分享 + 課後資源說明 + 社群/LINE 群加入 |

**本堂產出** ✅ 完整上線的個人化交易系統 + 故障排除能力 + 結業證書（建議）

---

## 三課程比較總表

| 面向 | 課程 A（小白） | 課程 B（程式背景） | 課程 C（2 日投資人） |
|------|---------------|-------------------|-------------------|
| 總時數 | 12hr（4 堂） | 9hr（3 堂） | 18hr（6 堂/2 日） |
| 需寫程式 | ❌ 不用（只跑指令） | ✅ 會改策略程式碼 | ❌ 完全不用 |
| 需 Python 基礎 | ❌ 不用 | ✅ 需有經驗 | ❌ 不用 |
| 需交易知識 | ❌ 不用（會教） | ❌ 不用（會教） | ✅ 有投資經驗佳 |
| 環境安裝 | 課前 30min 搞定（WSL 備份） | 課前 15min 確認 | 課前 30min 搞定 |
| 核心教學法 | 操作肌肉記憶→理論 | 程式碼深度→實務應用 | 操作流程→投資決策 |
| 最終產出 | 會跑回測+模擬+Docker | 會改策略+加功能+部署 | 完整個人化系統上線 |
| 適合人數 | 8-15 人（需助教 1:8） | 10-20 人（可少助教） | 6-12 人（需 1:6 助教） |

---

## 教材需求清單（課前準備）

### 必備（所有課程共用）
- [ ] 更新版 WSL 備份檔（含最新 tw-autotrader + OpenCode + FinMind skill + 玉山 SDK）
- [ ] 課前準備影片（解壓縮 WSL、申請 API Token、確認環境可用）— 3-5 分鐘
- [ ] 學員課前檢查清單 PDF
- [ ] .env 填寫輔助表（中文欄位說明）

### 課程 A 專屬
- [ ] 第 1 堂：Terminal 常用指令 cheat sheet（中英對照、10 個以內）
- [ ] 第 2 堂：四策略參數比較表模板（填空用）
- [ ] 第 3 堂：投資組合配置工作表格
- [ ] 第 4 堂：完整流程 check list（從回測到部署 step by step）

### 課程 B 專屬
- [ ] Code walkthrough 指引（ma_cross.py 逐行註解版）
- [ ] 參數敏感性測試腳本範本
- [ ] 策略修改練習題庫（5 題，從易到難）

### 課程 C 專屬
- [ ] 第 1 堂：四策略動畫 HTML（已有 bollinger/ma_cross/vwap/breakout 動畫）
- [ ] 第 2 堂：`scripts/param_search.sh` 批次調參腳本 + 結果比較表模板
- [ ] 第 3 堂：投資組合配置空白表格（pdf/Excel）
- [ ] 第 6 堂：故障情境卡（5-6 題，附解答）

### 通用教材
- [ ] 投影片（三套課程共用核心內容，依需求增刪）
- [ ] 實做環節的「助教指引」（每堂課的常見問題與解答）
- [ ] 結業後的 LINE/Telegram 社群連結
- [ ] 課後自學路徑指引（使用手冊.md 的章節對照）

---

## 實做環節助教指引要點

| 常見問題 | 解答方向 |
|----------|---------|
| `ModuleNotFoundError` | pip install 沒做 / WSL 環境跑錯 |
| 回測結果很差（負報酬） | 正常！不是策略壞了。討論為什麼這個策略在這支股票不 work |
| 不知道該調哪個參數 | 先回到預設值，一次只改一個 |
| `.env` 改了沒生效 | 確認沒有 typo、重開 terminal、重跑指令（不需要重開機） |
| Docker build 很慢 | 第一次正常。之後有 cache 會變快 |
| 回測和實盤結果不一樣 | 市場變化 + 滑價 + 延遲。不是系統壞了 |
| Telegram 沒收到通知 | 檢查 TELEGRAM_BOT_TOKEN 和 CHAT_ID、Bot 有沒有先發 `/start` |

---

## 課後學員能力驗收標準

完成課程後學員應能：

| # | 能力 | A | B | C |
|---|------|---|---|---|
| 1 | 在 terminal 執行回測指令 | ✅ | ✅ | ✅ |
| 2 | 修改 .env 改變策略參數 | ✅ | ✅ | ✅ |
| 3 | 看懂回測報表（總報酬/勝率/回撤） | ✅ | ✅ | ✅ |
| 4 | 設定多股投資組合 (PORTFOLIO) | ✅ | ✅ | ✅ |
| 5 | 執行多股模擬交易 | ✅ | ✅ | ✅ |
| 6 | 設定 Telegram 通知 | ✅ | ✅ | ✅ |
| 7 | 用 Docker 部署系統 | ✅ | ✅ | ✅ |
| 8 | 調整策略參數並對比結果 | ✅ | ✅ | ✅ |
| 9 | 理解 overfitting 概念 | ✅ | — | ✅ |
| 10 | 修改策略程式碼 | — | ✅ | — |
| 11 | 擴充 broker mock | — | ✅ | — |
| 12 | 寫輔助腳本 | — | ✅ | — |
| 13 | 故障排除（env/broker/docker） | 基礎 | 進階 | 基礎 |
| 14 | 理解 Walk-forward 驗證 | — | ✅ | — |

---

## Commit Strategy

N/A — 此為課程設計文件，非程式碼變更。

## Success Criteria

- [ ] 三套課程大綱完整，每堂課有明確的主題分配（分鐘級）和實做步驟
- [ ] 每堂課結束都有具體產出（不只是「學會了」，而是跑出了一個結果）
- [ ] 課程 A/B/C 的難度和深度差異合理，沒有 overlapping 或跳階
- [ ] 所有實做環節只需要學員換 API Key，不需要安裝環境
- [ ] 教材需求清單明確，可據此準備投影片和腳本
- [ ] 助教指引涵蓋 80% 以上常見問題