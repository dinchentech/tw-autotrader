# 取得券商 API Key 與設定 .env

## (1) 取得玉山證券 API Key 及憑證

### 申請流程

1. **開立證券戶**（若尚未開戶）：
   - 至玉山證券臨櫃或線上開戶
   - 申請「API 下單」權限

2. **申請 API 憑證**：
   - 登入玉山證券網路下單系統
   - 找到「API 憑證申請」功能
   - 下載憑證檔（通常為 `.pfx` 或 `.p12` 格式）
   - 設定憑證密碼

3. **取得 API 資訊**：
   - 玉山證券會提供：
     - `ESUN_ACCOUNT`：證券帳號
     - `ESUN_ACCOUNT_PASSWORD`：下單密碼
     - `ESUN_CERT_PASSWORD`：憑證密碼
     - API 端點 URL（通常為 `esunapi-uat.fhtls.com` 測試 / `esunapi.fhtls.com` 正式）

4. **憑證安裝**：
   將憑證檔案放到專案目錄中：
   ```bash
   # 將憑證放入專案目錄
   cp /mnt/c/Users/frank/Downloads/cert.pfx /home/frank/tw-autotrader/
   ```

---

## (2) .env 的設置

### 什麼是 .env？

`.env` 是儲存**機密設定**的檔案（API Key、密碼、資金配置），**永遠不要 commit 到 git**。

### .env 範本

```ini
# ==========================================
# TW AutoTrader 環境設定檔
# ==========================================

# FinMind 設定（免費註冊：https://finmind.github.io）
FINMIND_API_TOKEN=your_finmind_api_token_here

# 券商選擇（kgi / esun）
BROKER=esun

# 玉山 API 設定（BROKER=esun 時使用）
ESUN_ACCOUNT_PASSWORD=你的下單密碼
ESUN_CERT_PASSWORD=你的憑證密碼

# Telegram 通知
TELEGRAM_BOT_TOKEN=你的機器人Token
TELEGRAM_CHAT_ID=你的聊天ID

# ==========================================
# 資金配置（可與 AI 討論調整）
# ==========================================
TOTAL_CAPITAL=500000            # 可動用總資金
INITIAL_CAPITAL=500000          # 風險計算用初始資金
ALLOC_BOLLINGER=40              # 布林通道反轉 40%
ALLOC_VWAP=20                   # VWAP 偏離反轉 20%
ALLOC_MA_CROSS=25               # 均線交叉 25%
ALLOC_BREAKOUT=15               # 唐奇安突破 15%

# ==========================================
# 多股組合配置
# ==========================================
PORTFOLIO=0050:bollinger,006208:bollinger,00878:bollinger,2330:ma_cross,2454:ma_cross,2881:vwap,2886:vwap,2382:breakout

# ==========================================
# 風險控管
# ==========================================
MAX_RISK_PER_TRADE=0.02         # 單筆最大風險 2%
MAX_DAILY_LOSS=0.03             # 每日最大虧損 3%
MAX_DAILY_TRADES=5              # 每日最大交易次數
MARKET_TREND_FILTER=true        # 大盤年線過濾

# ==========================================
# 下單股數設定
# ==========================================
BOLLINGER_POSITION_AMOUNT=15000
VWAP_POSITION_AMOUNT=10000
MA_CROSS_POSITION_AMOUNT=10000
BREAKOUT_POSITION_BUY=1000
BREAKOUT_POSITION_SELL=1000

# ==========================================
# 策略參數
# ==========================================
BOLLINGER_WINDOW=20
BOLLINGER_STD_DEV=2.0
BOLLINGER_RSI_PERIOD=5
VWAP_SIGMA_MULT=1.5
VWAP_RSI_PERIOD=5
MA_CROSS_FAST_PERIOD=9
MA_CROSS_SLOW_PERIOD=21
BREAKOUT_LOOKBACK=20
BREAKOUT_ATR_PERIOD=14
```

### 與 AI 討論投資配置

你可以問 AI 的問題範例：

**資金配置**
> 「我有 50 萬資金，4 種策略各分配多少比較合理？」
> 「布林通道策略放 40% 會不會太多？」

**風險設定**
> 「每日最大虧損 3% 算保守還激進？」
> 「單筆最大風險 2% 適合小資金嗎？」

**策略參數**
> 「均線快慢週期設 9/21 適合台灣股票嗎？」
> 「布林通道標準差 2.0 要改嗎？」

**保守 vs 激進範例**

| 項目 | 保守型 | 平衡型（預設） | 激進型 |
|------|--------|---------------|--------|
| `MAX_DAILY_LOSS` | 1-2% | 3% | 5-8% |
| `MAX_DAILY_TRADES` | 2-3 | 5 | 8-10 |
| `MAX_RISK_PER_TRADE` | 1% | 2% | 3-5% |
| `MARKET_TREND_FILTER` | true | true | false |

---

## (3) 安裝 Telegram 並取得 ID 與 Key

### 步驟

1. **下載 Telegram**
   - https://telegram.org 或手機 App Store

2. **建立 Bot 取得 Token**
   - 在 Telegram 搜尋 `@BotFather`
   - 傳送 `/newbot`
   - 依提示設定 Bot 名稱（例如 `MyTradeBot`）
   - 完成後會拿到一組 Token，像：
     ```
     1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
     ```

3. **取得 Chat ID**
   - 方法一：搜尋 `@userinfobot`，傳送 `/start` 即可看到 ID
   - 方法二：傳送一則訊息給你的 Bot，然後開啟瀏覽器：
     ```
     https://api.telegram.org/bot<你的Token>/getUpdates
     ```
     找到 `"chat":{"id":123456789}` 即為 Chat ID

4. **填入 .env**
   ```ini
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_CHAT_ID=123456789
   ```

### 驗證
部署後可在 Telegram 收到「✅ TW AutoTrader 已啟動」訊息。
