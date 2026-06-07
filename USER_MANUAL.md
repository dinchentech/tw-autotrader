# TW AutoTrader 使用手冊

> **版本**：3.1  
> **最後更新**：2026 年 6 月  
> **適用對象**：台灣個人投資者  
> **核心功能**：✅ 四策略回測 ✅ 真實券商 API ✅ 風險控管 ✅ Telegram / LINE 通知  
> **參數調整**：✅ 免改程式碼 — CLI 命令列 / `.env` 環境變數

---

## 🌟 系統概覽

TW AutoTrader 是一套 **專業級台股自動交易系統**，整合：

- **四種經典策略**：VWAP 偏離、均線交叉、布林反轉、突破交易
- **真實券商支援**：凱基證券 API（可替換為其他券商）
- **專業風險控管**：單筆風險、每日虧損上限、交易次數限制
- **即時監控**：Telegram 通知 + 交易日誌
- **低成本部署**：GCP 定時排程（~60 元/月）、Docker、本機開發

---

## 📁 專案結構

```
tw-autotrader/
├── strategies/              # 四種策略實作（函式版 / FinMind class 版）
├── core/                    # 核心模組
│   ├── strategy_engine.py   # 策略執行引擎
│   └── risk_manager.py      # 風險控管
├── data/                    # 資料模組
│   ├── yahoo_loader.py      # Yahoo Finance 下載器
│   ├── kgi_mock.py          # 凱基 API 模擬器
│   └── kgi_real.py          # 真實凱基 API 連接
├── utils/                   # 工具模組
│   └── telegram.py          # Telegram 通知
├── config/
│   └── symbols.py           # 可交易標的設定
├── tests/                   # 自動化測試
├── backtest.py              # Yahoo Finance 回測（命令列調參）
├── backtest_finmind.py      # FinMind 回測
├── live_trader.py           # 實盤交易（函式版策略）
├── live_trader_finmind.py   # 實盤交易（FinMind class 策略）
├── live_trader_multi.py     # 多股多策略分流系統
├── requirements.txt         # 依賴套件
├── .env.example             # 環境設定範例（含策略參數）
├── USER_MANUAL.MD           # 本使用手冊
├── 策略說明.MD               # 四大策略原理解說
└── 回溯說明.MD              # 回溯（Backtest）操作指南
```

---

## 🔧 第一步：環境設定

### 1.1 系統需求
- **作業系統**：Windows / macOS / Linux
- **Python 版本**：3.8 或更高（推薦 3.10）
- **網路環境**：穩定網路連線

### 1.2 安裝依賴
```bash
# 克隆專案
git clone https://github.com/yourname/tw-autotrader-finmind.git
cd tw-autotrader-finmind

# 安裝依賴
pip install -r requirements.txt
pip install python-dotenv
```

### 1.3 設定環境變數
```bash
# 複製環境範例
cp .env.example .env

# 編輯 .env 檔案
nano .env
```

#### `.env` 檔案範例：
```env
# FinMind 設定（回測用）
FINMIND_API_TOKEN=your_finmind_api_token_here

# 凱基 API 設定
KGI_API_KEY=your_kgi_api_key_here
KGI_API_SECRET=your_kgi_api_secret_here
USE_REAL_API=false  # 開發時設為 false，實盤時設為 true

# Telegram 設定
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# LINE Notify 通知
LINE_NOTIFY_TOKEN=your_line_notify_token

# 風險控管參數
INITIAL_CAPITAL=1000000      # 初始資金（台幣）
MAX_RISK_PER_TRADE=0.01      # 單筆最大風險（1%）
MAX_DAILY_LOSS=0.05          # 每日最大虧損（5%）
MAX_DAILY_TRADES=3           # 每日最大交易次數

# ==========================================
# 策略參數（不設定則使用預設值）
# live_trader_finmind.py / live_trader_multi.py 自動讀取
# backtest.py 則用 --參數 命令列覆蓋
# ==========================================

# VWAP 偏離度反轉策略
VWAP_SIGMA_MULT=1.5          # VWAP 偏離倍數
VWAP_RSI_PERIOD=5            # RSI 計算週期

# 均線交叉策略
MA_CROSS_FAST_PERIOD=9       # 快線週期
MA_CROSS_SLOW_PERIOD=21      # 慢線週期
MA_CROSS_ATR_THRESHOLD=0.005 # ATR 波動度門檻（低於此值跳過盤整訊號）

# 布林通道反轉策略
BOLLINGER_WINDOW=20          # 布林通道計算週期
BOLLINGER_STD_DEV=2.0        # 標準差倍數
BOLLINGER_RSI_PERIOD=5       # RSI 計算週期

# 突破交易策略
BREAKOUT_LOOKBACK=20         # 突破回溯期間
BREAKOUT_ATR_PERIOD=14       # ATR 計算週期

# ==========================================
# 多股組合配置（live_trader_multi.py 專用）
# 格式：股票代號:策略名稱,股票代號:策略名稱,...
# 不設定則使用程式內建預設組合
# ==========================================
# PORTFOLIO=0050:bollinger,2330:ma_cross,2382:breakout,2881:vwap

# ==========================================
# 下單股數設定（live_trader_multi.py 專用）
# 金額制策略：bollinger / vwap / ma_cross 用 target_amount 計算股數
# 股數制策略：breakout 直接指定買/賣股數
# ==========================================
# BOLLINGER_POSITION_AMOUNT=2500
# VWAP_POSITION_AMOUNT=2500
# MA_CROSS_POSITION_AMOUNT=2200
# BREAKOUT_POSITION_BUY=50
# BREAKOUT_POSITION_SELL=100

# ==========================================
# 每月預算控管（0 = 不限制）
# ==========================================
# MONTHLY_BUDGET_BOLLINGER=10000
# MONTHLY_BUDGET_VWAP=3000
# MONTHLY_BUDGET_MA_CROSS=4000
# MONTHLY_BUDGET_BREAKOUT=3000

# ==========================================
# 大盤年線過濾（FinMind 為資料源，抓不到則跳過）
# ==========================================
MARKET_TREND_FILTER=true

# ==========================================
# 金字塔加碼（Bollinger 分批進場，需設 PYRAMID_ENABLED=true）
# ==========================================
# PYRAMID_ENABLED=false
# PYRAMID_TIER1_SHARES=200
# PYRAMID_TIER2_SHARES=400
# PYRAMID_TIER3_SHARES=600
# PYRAMID_TIER2_DROP=0.03
# PYRAMID_TIER3_DROP=0.05
```

> 💡 **取得 API Token 教學**：
> - **FinMind**：[https://finmindtrade.com/](https://finmindtrade.com/) → 免費註冊
> - **Telegram Bot**：Telegram 搜尋 `@BotFather` → `/newbot`
> - **凱基 API**：向凱基證券申請程式交易 API 權限

---

## 📊 第二步：回測驗證

### 2.1 執行 Yahoo Finance 回測（快速批次驗證）

```bash
# 使用預設策略（vwap）回測全部標的
python backtest.py

# 指定策略與開始日期
python backtest.py --strategy ma_cross --start 2022-01-01

# 調整策略參數（免改程式碼！）
python backtest.py --strategy ma_cross --fast_period 5 --slow_period 30
python backtest.py --strategy bollinger --std_dev 2.5 --rsi_period 7
python backtest.py --strategy breakout --lookback 40
python backtest.py --strategy vwap --sigma_mult 2.0
```

> 💡 完整參數列表請參閱 [`回溯說明.MD`](回溯說明.MD)。

### 2.2 執行 FinMind 回測（多策略比較）

```bash
# 需先註冊 FinMind API Token
python backtest_finmind.py --symbol 2330 --start 2023-01-01
```

### 2.3 回測輸出範例
```
📊 開始回測 TW AutoTrader
🎯 使用策略: ma_cross
⚙️  策略參數: {'fast_period': 5, 'slow_period': 30}
📅 回測期間: 2023-01-01 ~ 今日

  → 回測 2330 (2330.TW)...
    ✅ 交易次數: 24, 勝率: 62.5%, 總報酬: 18.32%
  → 回測 2454 (2454.TW)...

📈 回測總結
============================================================
2330   | 交易: 24 次 | 勝率: 62.5% | 報酬: 18.32%
2454   | 交易: 18 次 | 勝率: 55.6% | 報酬: 12.45%
...
------------------------------------------------------------
平均   | 交易: 42 次 | 勝率: 58.2% | 報酬: 14.88%

✅ 績效結果已匯出: results/backtest_results_ma_cross_20260606_143022.csv
```

---

## ⚠️ 第三步：策略暖身所需最少 K 線數

所有策略都是使用「滑動視窗（rolling window）」計算技術指標。在餵入的歷史資料還不夠多時，指標會是無效值（NaN）或噪聲極大，此時產生的交易訊號**不可靠**。

### 各策略暖身門檻

| 策略 | ⚡ 程式能產出第一個訊號 | 📊 指標真正穩定可靠 |
|------|----------------------|-------------------|
| **VWAP 偏離** | 6 根 K 線（RSI 限制） | 20 根（Std 收斂） |
| **均線交叉** | 2 根 K 線（shift 限制） | 22 根（MA21 完整一輪） |
| **布林反轉** | 2 根 K 線 | 20 根（通道穩定） |
| **突破交易** | 2 根 K 線（shift 限制） | 21 根（Donchian 通道滿） |

### 範例解說

以 **均線交叉（ma_cross, fast_period=9, slow_period=21）** 為例：

```
K 線  1 ~ 21：   MA21 只有部分資料，數值不具代表性
K 線     22：    MA21 首次涵蓋完整 21 根，交叉判斷才可靠
           ╰── 在此之前產生的黃金/死亡交叉都是假訊號
```

以 **VWAP 偏離（vwap, rsi_period=5, sigma_mult=1.5）** 為例：

```
K 線  1 ~ 5：    RSI 尚未產出有效值（全為 NaN）
K 線      6：    RSI 首次有效
K 線  1 ~ 19：   Std 使用 min_periods=1，數值逐漸收斂
K 線     20：    Std 完全收斂，偏離判斷才真正可靠
```

### 實戰建議

| 情境 | 建議餵入資料量 |
|------|--------------|
| **回測**（`backtest.py`） | 回測期間設為 **1 年以上**（約 250 根交易日 K 線），前 22 根視為 warm-up 即可 |
| **實盤剛啟動**（`live_trader_finmind.py`） | 程式會自動抓取 **30 天歷史資料**（約 22 根交易日 K 線），足夠所有策略暖身 |
| **多股實盤剛啟動**（`live_trader_multi.py`） | 同上，自動抓取 **30 天歷史資料** |
| **手動餵資料測試** | 至少餵 **22 根 K 線** 再開始觀察訊號 |

### 為什麼回測一定要設 `--start` 夠早？

```bash
# ❌ 錯誤：只給一個月資料，MA21 連一次交叉都算不準
python backtest.py --strategy ma_cross --start 2026-05-01

# ✅ 正確：至少給一年，前 22 根 warm-up 後還有 200+ 根可交易
python backtest.py --strategy ma_cross --start 2025-01-01
```

> 💡 **簡單記法：不管用哪個策略，餵少於 22 根 K 線就開始看訊號，跟擲硬幣沒兩樣。**

---

## 🚀 第四步：實盤交易

### 4.1 單股交易（`live_trader.py` / `live_trader_finmind.py`）

```bash
# 開發測試（模擬模式）
python live_trader_finmind.py --symbol 2330 --strategy vwap
python live_trader_finmind.py --symbol 0050 --strategy ma_cross

# 真實交易（生產模式）
# 先編輯 .env：USE_REAL_API=true
python live_trader_finmind.py --symbol 2330 --strategy vwap
```

### 4.2 多股多策略分流（`live_trader_multi.py`）

同時監控多檔股票，每檔搭配不同策略：

```bash
# 使用 .env 中的 PORTFOLIO 設定
python live_trader_multi.py
```

`.env` 設定範例：
```env
PORTFOLIO=0050:bollinger,2330:ma_cross,2382:breakout,2881:vwap
```

每檔股票會獨立判斷，不會互相干擾。

### 4.3 股票數量上限建議

由於 `live_trader_multi.py` 採用**順序迴圈架構**（一支股票處理完才處理下一支），股票數量過多會導致每輪循環時間拉長：

| 股票數 | 每輪循環時間 | 建議 |
|--------|------------|------|
| 1~4 支 | ~68 秒 | ✅ 最佳，當前設計目標 |
| 5~10 支 | ~80 秒 | ✅ 良好，仍在 1 分鐘內 |
| 10~15 支 | ~95 秒 | ⚠️ 可接受，留意循環漂移 |
| 15+ 支 | 超過 100 秒 | ❌ 不建議，訊號失去即時性 |

**建議上限：15 支股票**。如果你需要同時監控超過 15 支股票，建議：
- 方案一：將程式改為非同步並行（asyncio）架構，同時發送 API 請求
- 方案二：開兩台 GCP e2-micro VM，各負責一半股票
- 方案三：改用 Cloud Run Jobs + Cloud Scheduler，每分鐘觸發一次（無主機管理）

> 💡 超過 15 支時程式會顯示警告訊息，但不會強制停止。

---

### 4.4 調整策略參數（免改程式碼）

實盤策略參數透過 `.env` 環境變數設定：

```env
# 回測找到最佳參數後，直接寫入 .env
VWAP_SIGMA_MULT=2.0
MA_CROSS_FAST_PERIOD=5
MA_CROSS_SLOW_PERIOD=30
BOLLINGER_STD_DEV=2.5
BOLLINGER_RSI_PERIOD=7
BREAKOUT_LOOKBACK=40
```

三支程式的參數調整方式對照：

| 程式 | 調整方式 | 範例 |
|------|----------|------|
| `backtest.py` | CLI 命令列 `--參數` | `--fast_period 5 --slow_period 30` |
| `live_trader_finmind.py` | `.env` 環境變數 | `MA_CROSS_FAST_PERIOD=5` |
| `live_trader_multi.py` | `.env` 環境變數 | `MA_CROSS_FAST_PERIOD=5` |

---

## 🛡️ 第五步：風險控管

### 5.1 風險參數設定
在 `.env` 檔案中設定：

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `INITIAL_CAPITAL` | `1000000` | 初始資金（台幣） |
| `MAX_RISK_PER_TRADE` | `0.01` | 單筆交易最大風險（1%） |
| `MAX_DAILY_LOSS` | `0.05` | 每日最大可接受虧損（5%） |
| `MAX_DAILY_TRADES` | `3` | 每日最大交易次數 |

### 5.2 風險控管功能
- **單筆風險限制**：動態計算部位大小
- **每日虧損上限**：達上限後停止交易
- **交易次數限制**：避免過度交易
- **漲跌停過濾**：跳過流動性枯竭標的

### 5.3 部位計算邏輯
```
風險金額 = 初始資金 × MAX_RISK_PER_TRADE
止損距離 = 股價 × 2%（固定百分比）
股數 = 風險金額 / 止損距離
張數 = floor(股數 / 1000)  # 台股一張 = 1000 股
```

### 5.4 每月預算控管

`live_trader_multi.py` 支援**每月每策略預算上限**，避免單一策略超額下單：

```env
# 各策略每月預算（0 = 不限制）
MONTHLY_BUDGET_BOLLINGER=10000      # ETF 逆勢策略，預算最高
MONTHLY_BUDGET_VWAP=3000            # 金融存股策略
MONTHLY_BUDGET_MA_CROSS=4000        # 權值股順勢策略
MONTHLY_BUDGET_BREAKOUT=3000        # 飆股順勢策略
```

運作方式：
- **只有買進（BUY）會扣預算**，賣出（SELL）不計入
- 預算以「買進成本」（股數 × 成交價）計算，**不是**以每月總額預扣
- 月中達到預算上限後，該策略就不再買進，直到下個月 1 號重置
- 設定 `0` 或留空 = 不限制預算
- 預算追蹤資料儲存在 `logs/monthly_budget.json`

可搭配風險控管同時使用，兩層防護互不衝突。

### 5.5 大盤年線過濾

避免在空頭市場（大盤跌破年線）時逆勢買進：

- 啟動時從 **FinMind** 抓取加權指數（TX00）日線，計算 MA200
- 若指數 < MA200，跳過所有買進訊號
- 若 FinMind 抓取失敗（網路、API 問題），**安全跳過不過濾**，不影響正常交易
- 設定 `MARKET_TREND_FILTER=false` 可關閉

```env
MARKET_TREND_FILTER=true
```

### 5.6 金字塔加碼（Bollinger 分批進場）

Bollinger 逆勢策略觸發買進時，分批次進場降低成本，而非一次性買足：

| 梯次 | 條件 | 買入股數 |
|------|------|---------|
| Tier 1 | 首次觸發訊號 | 200 股 |
| Tier 2 | 價格再跌 3% | 400 股 |
| Tier 3 | 價格再跌 5% | 600 股 |

僅限 Bollinger 策略，可透過 `.env` 啟用：

```env
PYRAMID_ENABLED=true
PYRAMID_TIER1_SHARES=200
PYRAMID_TIER2_SHARES=400
PYRAMID_TIER2_DROP=0.03
```

> 預設為關閉（`PYRAMID_ENABLED=false`），需要手動開啟。

---

## 📱 第六步：Telegram 通知

### 6.1 設定步驟
1. **建立 Telegram Bot**：
   - Telegram 搜尋 `@BotFather`
   - 輸入 `/newbot` 建立新 Bot
   - 取得 `BOT_TOKEN`

2. **取得 Chat ID**：
   - 對你的 Bot 傳送訊息
   - 瀏覽 `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
   - 找到 `chat.id` 數值

3. **填入 `.env` 檔案**：
   ```env
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```

### 6.2 通知內容範例
```
🤖 TW AutoTrader
*BUY 2330*
💰 價格: 680.50
📊 數量: 2,000 股
🎯 策略: VWAP
⏰ 時間: 2025-04-05 10:30:22
```

---

## 🧪 第七步：自動化測試

### 7.1 執行測試
```bash
# 執行所有策略測試
python -m pytest tests/ -v

# 或直接執行
python tests/test_strategies.py
```

### 7.2 測試內容
- 策略訊號產生正確性
- 空資料處理
- 邊界條件測試

---

## ☁️ 第八步：雲端部署（GCP 定時排程，成本最低）

### 8.1 為什麼選 GCP 定時排程？

台股交易時間只有 **週一至五 09:00~13:30**（約 4.5 小時），把主機 24/7 開著很浪費。用 GCP 的排程服務只在交易時間開機，成本極低：

| 方案 | 運算方式 | 每月成本（估） | 適用本金 |
|------|---------|--------------|---------|
| **GCP 定時 VM**（e2-micro, spot） | 開盤前開機 → 收盤後關機 | **~60 元** | 1 萬 ~ 100 萬以上 |
| **Cloud Run Jobs**（無伺服器） | 每分鐘觸發一次，其餘靜止 | **~50 元** | 同上 |
| **Docker 24/7 VPS**（DO/NAS） | 24 小時全時運轉 | **~200 元** | 建議本金 50 萬以上 |

### 8.2 方式一：Docker + GCP Compute Engine（定時開關機）

#### 建立機器映像

在本地端建立 Dockerfile：

```dockerfile
FROM python:3.10-slim
RUN apt-get update && apt-get install -y libfreetype6-dev libpng-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "live_trader_finmind.py", "--symbol", "2330", "--strategy", "vwap"]
```

```bash
# 建立映像
docker build -t tw-autotrader .
```

#### 上傳到 GCP

```bash
# 上傳至 Google Container Registry
gcloud auth configure-docker
docker tag tw-autotrader gcr.io/[PROJECT_ID]/tw-autotrader
docker push gcr.io/[PROJECT_ID]/tw-autotrader
```

#### 建立 VM（開盤前開機 → 收盤後關機）

```bash
# 建立 e2-micro（最低成本）
gcloud compute instances create tw-autotrader \
  --zone=asia-east1-a \
  --machine-type=e2-micro \
  --preemptible \
  --container-image=gcr.io/[PROJECT_ID]/tw-autotrader \
  --container-env-file=.env
```

```bash
# 建立 Cloud Scheduler（開盤前 08:50 開機）
gcloud scheduler jobs create pubsub start-instance \
  --schedule="50 8 * * 1-5" \
  --topic=start-instance \
  --message-body='{"instance": "tw-autotrader"}'

# Cloud Scheduler（收盤後 13:35 關機）
gcloud scheduler jobs create pubsub stop-instance \
  --schedule="35 13 * * 1-5" \
  --topic=stop-instance \
  --message-body='{"instance": "tw-autotrader"}'
```

設定完成後，主機只在**週一至五 08:50~13:35** 運轉，每月運算時數約 **90 小時**，e2-micro 費用約 **60 元台幣**。

### 8.3 方式二：Cloud Run Jobs（無主機管理）

更輕量的做法：用 Cloud Scheduler + Cloud Run Jobs，每分鐘執行一次策略檢查。

```bash
# 建立 Cloud Run Job（無伺服器，按呼叫次數計費）
gcloud run jobs create tw-autotrader \
  --image=gcr.io/[PROJECT_ID]/tw-autotrader \
  --region=asia-east1 \
  --max-retries=0 \
  --task-timeout=30s

# Cloud Scheduler（每分鐘觸發，開盤時段才處理）
gcloud scheduler jobs create http trigger-trader \
  --schedule="* 9-13 * * 1-5" \
  --uri="https://asia-east1-run.googleapis.com/..." \
  --http-method=POST
```

Cloud Run 在沒有呼叫時不計費，**開盤時段約 270 次呼叫/日**，每月帳單約 **50 元台幣**。

### 8.4 監控日誌

```bash
# VM 模式
gcloud compute ssh tw-autotrader -- "docker logs tw-autotrader"

# Cloud Run 模式
gcloud run jobs executions list --region=asia-east1
gcloud logging read "resource.type=cloud_run_job" --limit=50
```

---

## 🛠️ 故障排除

### 常見問題與解決方案

| 問題 | 解決方案 |
|------|----------|
| **`Failed to get ticker '2330.TW'`** | 改用 FinMind 資料源，確保 `.env` 有 `FINMIND_API_TOKEN` |
| **凱基 API 連接失敗** | 確認 `KGI_API_KEY` 和 `KGI_API_SECRET` 正確，檢查網路連線 |
| **Telegram 未收到通知** | 驗證 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`，檢查 Bot 是否被封鎖 |
| **無交易訊號** | 延長回測期間，或調整策略參數（如降低 `sigma_mult`） |
| **風險控管攔截所有交易** | 檢查 `MAX_DAILY_LOSS` 是否過低，或手動清除 `logs/performance.csv` |

### 日誌檔案位置
- **交易日誌**：`logs/performance.csv`
- **系統錯誤**：終端機輸出或 Docker logs

---

## 📈 策略選擇建議

| 市場環境 | 推薦策略 | 參數調整建議 |
|----------|----------|--------------|
| **震盪市** | VWAP 偏離 | `sigma_mult=1.2`（更敏感） |
| **震盪市** | 布林反轉 | `std_dev=1.8`（更窄通道） |
| **趨勢市** | 均線交叉 | `fast=5, slow=20`（更快反應） |
| **趨勢啟動** | 突破交易 | `lookback=15`（更短回溯） |

---

## 🔒 安全注意事項

1. **API Key 保護**：
   - 切勿將 `.env` 檔案上傳到 GitHub
   - 在券商後台設定 IP 限制（如果支援）

2. **資金管理**：
   - 初始資金建議不超過總資產 10%
   - 先用模擬模式測試至少 1 週

3. **監控機制**：
   - 每日檢查交易日誌
   - 設定 Telegram 通知確保即時掌握

---

## 🚀 快速開始指令總表

| 功能 | 指令 |
|------|------|
| **安裝依賴** | `pip install -r requirements.txt` |
| **回測（Yahoo Finance，可調參）** | `python backtest.py --strategy ma_cross --fast_period 5 --slow_period 30` |
| **回測（FinMind 多策略比較）** | `python backtest_finmind.py --symbol 2330` |
| **單股實盤** | `python live_trader_finmind.py --symbol 2330 --strategy vwap` |
| **多股多策略實盤** | `python live_trader_multi.py` |
| **參數調整（回測）** | CLI 命令列 `--參數` |
| **參數調整（實盤）** | 編輯 `.env`，重啟程式 |
| **執行測試** | `python tests/test_strategies.py` |
| **本地 Docker 測試** | `docker build -t tw-autotrader . && docker run -d --env-file .env tw-autotrader` |
| **GCP 定時部署** | `gcloud run jobs create tw-autotrader --image=... && gcloud scheduler jobs create http ...` |

---

## ✅ 系統優勢總結

- **✅ 專業級風險控管**：保護本金安全
- **✅ 四策略完整實作**：涵蓋各種市場環境
- **✅ 真實券商整合**：凱基 API 直接下單
- **✅ 即時監控通知**：Telegram 即時警報
- **✅ 開發友好設計**：模擬器 + 真實 API 無縫切換
- **✅ 完整測試覆蓋**：確保系統穩定性

---

> 🎯 **最後建議**：  
> 1. 先用 **模擬模式** 運行 1 週  
> 2. 確認績效穩定後，再切換到 **真實交易**  
> 3. 初始資金建議 **不超過總資產 10%**  
> 4. 每日監控 **交易日誌** 和 **Telegram 通知**

**祝你交易順利，風險可控，獲利穩健！** 🛡️📈
