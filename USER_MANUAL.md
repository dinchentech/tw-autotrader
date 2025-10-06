# TW AutoTrader 使用手冊

> **版本**：3.0  
> **最後更新**：2025 年 4 月  
> **適用對象**：台灣個人投資者  
> **核心功能**：✅ 四策略回測 ✅ 真實券商 API ✅ 風險控管 ✅ Telegram 通知

---

## 🌟 系統概覽

TW AutoTrader 是一套 **專業級台股自動交易系統**，整合：

- **四種經典策略**：VWAP 偏離、均線交叉、布林反轉、突破交易
- **真實券商支援**：凱基證券 API（可替換為其他券商）
- **專業風險控管**：單筆風險、每日虧損上限、交易次數限制
- **即時監控**：Telegram 通知 + 交易日誌
- **靈活部署**：本機開發 + Docker 生產部署

---

## 📁 專案結構

```
tw-autotrader-finmind/
├── strategies/              # 四種策略實作（FinMind 格式）
├── core/                    # 核心模組
│   └── risk_manager.py      # 風險控管
├── data/                    # 資料模組
│   ├── kgi_mock.py          # 凱基 API 模擬器
│   └── kgi_real.py          # 真實凱基 API 連接
├── utils/                   # 工具模組
│   └── telegram.py          # Telegram 通知
├── tests/                   # 自動化測試
├── backtest_finmind.py      # FinMind 回測
├── live_trader_finmind.py   # 實盤交易主程式
├── requirements.txt         # 依賴套件
├── .env.example             # 環境設定範例
└── USER_MANUAL.MD           # 本使用手冊
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

# 風險控管參數
INITIAL_CAPITAL=1000000      # 初始資金（台幣）
MAX_RISK_PER_TRADE=0.01      # 單筆最大風險（1%）
MAX_DAILY_LOSS=0.05          # 每日最大虧損（5%）
MAX_DAILY_TRADES=3           # 每日最大交易次數
```

> 💡 **取得 API Token 教學**：
> - **FinMind**：[https://finmindtrade.com/](https://finmindtrade.com/) → 免費註冊
> - **Telegram Bot**：Telegram 搜尋 `@BotFather` → `/newbot`
> - **凱基 API**：向凱基證券申請程式交易 API 權限

---

## 📊 第二步：回測驗證

### 2.1 執行回測
```bash
# 執行 VWAP 策略回測
python backtest_finmind.py

# 指定股票和期間
python backtest_finmind.py --symbol 2330 --start 2023-01-01
```

### 2.2 回測輸出範例
```
📊 開始 FinMind 回測: 2330

VWAP Deviation 策略績效:
  最終權益: 1085632.45
  交易次數: 24
  勝率: 62.50%
  平均報酬: 3.57%

MA Cross 策略績效:
  最終權益: 1042187.32
  交易次數: 18
  勝率: 55.56%
  平均報酬: 2.34%
```

### 2.3 回測參數說明
| 參數 | 預設值 | 說明 |
|------|--------|------|
| `--symbol` | `2330` | 股票代號 |
| `--start` | `2023-01-01` | 回測開始日期 |

---

## 🚀 第三步：實盤交易

### 3.1 開發測試（模擬模式）
```bash
# 使用模擬器測試 VWAP 策略
python live_trader_finmind.py --symbol 2330 --strategy vwap

# 測試其他策略
python live_trader_finmind.py --symbol 0050 --strategy ma_cross
```

### 3.2 真實交易（生產模式）
1. **編輯 `.env` 檔案**：
   ```env
   USE_REAL_API=true
   KGI_API_KEY=your_real_kgi_api_key
   KGI_API_SECRET=your_real_kgi_api_secret
   ```

2. **啟動真實交易**：
   ```bash
   python live_trader_finmind.py --symbol 2330 --strategy vwap
   ```

### 3.3 策略參數說明
| 策略 | 參數 | 預設值 | 說明 |
|------|------|--------|------|
| `vwap` | `--sigma_mult` | `1.5` | VWAP 偏離倍數 |
| | `--rsi_period` | `5` | RSI 週期 |
| `ma_cross` | `--fast_period` | `9` | 快速均線週期 |
| | `--slow_period` | `21` | 慢速均線週期 |
| `bollinger` | `--window` | `20` | 布林通道週期 |
| | `--std_dev` | `2.0` | 標準差倍數 |
| `breakout` | `--lookback` | `20` | 突破回溯期間 |

---

## 🛡️ 第四步：風險控管

### 4.1 風險參數設定
在 `.env` 檔案中設定：

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `INITIAL_CAPITAL` | `1000000` | 初始資金（台幣） |
| `MAX_RISK_PER_TRADE` | `0.01` | 單筆交易最大風險（1%） |
| `MAX_DAILY_LOSS` | `0.05` | 每日最大可接受虧損（5%） |
| `MAX_DAILY_TRADES` | `3` | 每日最大交易次數 |

### 4.2 風險控管功能
- **單筆風險限制**：動態計算部位大小
- **每日虧損上限**：達上限後停止交易
- **交易次數限制**：避免過度交易
- **漲跌停過濾**：跳過流動性枯竭標的

### 4.3 部位計算邏輯
```
風險金額 = 初始資金 × MAX_RISK_PER_TRADE
止損距離 = 股價 × 2%（固定百分比）
股數 = 風險金額 / 止損距離
張數 = floor(股數 / 1000)  # 台股一張 = 1000 股
```

---

## 📱 第五步：Telegram 通知

### 5.1 設定步驟
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

### 5.2 通知內容範例
```
🤖 TW AutoTrader
*BUY 2330*
💰 價格: 680.50
📊 數量: 2,000 股
🎯 策略: VWAP
⏰ 時間: 2025-04-05 10:30:22
```

---

## 🧪 第六步：自動化測試

### 6.1 執行測試
```bash
# 執行所有策略測試
python -m pytest tests/ -v

# 或直接執行
python tests/test_strategies.py
```

### 6.2 測試內容
- 策略訊號產生正確性
- 空資料處理
- 邊界條件測試

---

## 🐳 第七步：Docker 部署（可選）

### 7.1 建立 Dockerfile
```dockerfile
FROM python:3.10-slim
RUN apt-get update && apt-get install -y libfreetype6-dev libpng-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "live_trader_finmind.py", "--symbol", "2330", "--strategy", "vwap"]
```

### 7.2 一鍵部署
```bash
# 建立並啟動容器
docker build -t tw-autotrader .
docker run -d --env-file .env --name tw-autotrader tw-autotrader

# 監控日誌
docker logs -f tw-autotrader
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
| **回測 VWAP** | `python backtest_finmind.py --symbol 2330` |
| **模擬實盤** | `python live_trader_finmind.py --strategy vwap` |
| **真實交易** | `USE_REAL_API=true python live_trader_finmind.py --strategy vwap` |
| **執行測試** | `python tests/test_strategies.py` |
| **Docker 部署** | `docker run -d --env-file .env tw-autotrader` |

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
