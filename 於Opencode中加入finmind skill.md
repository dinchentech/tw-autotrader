於Opencode中加入finmind skill

1.安裝finmind Skill(於wsl下執行):

frank@FRANK-I7:/mnt/c/Users/frank/Documents/github/tw-autotrader$ mkdir -p ~/.config/opencode/skills/finmind && curl -o ~/.config/opencode/skills/finmind/SKILL.md https://raw.githubusercontent.com/FinMind/FinMind/master/.claude/commands/finmind.md

  % Total    % Received % Xferd  Average Speed  Time    Time    Time   Current
                                 Dload  Upload  Total   Spent   Left   Speed
100   9646 100   9646   0      0  21044      0                              0

2.檢查安裝:
frank@FRANK-I7:/mnt/c/Users/frank/Documents/github/tw-autotrader$ head -n 3 ~/.config/opencode/skills/finmind/SKILL.md
You are a FinMind financial data assistant. Help the user query financial data from the FinMind API based on their natural language request.

3.輸入finmind token:
frank@FRANK-I7:/mnt/c/Users/frank/Documents/github/tw-autotrader$ echo 'export FINMIND_TOKEN="你的tokem"' >> ~/.bashrc
frank@FRANK-I7:/mnt/c/Users/frank/Documents/github/tw-autotrader$ source ~/.bashrc

4.進入opencode可以用 /finmind 使用(以下使用DeepSeek V4 flash 模型:

Frank: /finmind 台积电这个月股票如何?

=>finmind回覆
# TW AutoTrader 投資配置建議

> 每月 20,000 元 × 四策略 × 15 股以內  
> 資料日期：2026 年 6 月初

## 總覽

| 策略 | 月配金額 | 佔比 | 建議標的 |
|------|---------|------|---------|
| Bollinger（ETF 逆勢） | $10,000 | 50% | 0050 + 00878 |
| VWAP（金融逆勢） | $4,000 | 20% | 2881 + 2886 |
| Breakout（AI 順勢） | $4,000 | 20% | 2382（調整股數後） |
| MA Cross（半導體順勢） | $2,000 | 10% | 0050 或暫不配置 |

---

## 一、Bollinger（ETF 逆勢）— $10,000/月

適合 ETF，跌深反覆接刀，均值回歸。

| 標的 | 代號 | 目前股價 | 每月金額 | 每筆股數 |
|------|------|---------|---------|---------|
| 元大台灣50 | 0050 | ~104 | $5,000 | ~24 股 |
| 國泰永續高股息 | 00878 | ~32 | $5,000 | ~78 股 |

**設定：**
```env
BOLLINGER_POSITION_AMOUNT=2500
MONTHLY_BUDGET_BOLLINGER=10000
```

---

## 二、VWAP（金融逆勢）— $4,000/月

金融股價格低於法人成本時存股。

| 標的 | 代號 | 目前股價 | 每月金額 | 每筆股數 |
|------|------|---------|---------|---------|
| 富邦金 | 2881 | ~118 | $2,000 | ~21 股 |
| 兆豐金 | 2886 | ~42 | $2,000 | ~59 股 |

**設定：**
```env
VWAP_POSITION_AMOUNT=2500
MONTHLY_BUDGET_VWAP=4000
```

---

## 三、Breakout（AI 順勢）— $4,000/月

⚠️ **務必調整參數！** 廣達目前股價 ~390 元，預設 `BREAKOUT_POSITION_BUY=50` 一次就要花 $19,500。

| 標的 | 代號 | 目前股價 | 每月金額 | 每筆股數 |
|------|------|---------|---------|---------|
| 廣達 | 2382 | ~390 | $4,000 | **5 股** |

**設定：**
```env
BREAKOUT_POSITION_BUY=5        # 每次買 5 股（~1,950 元）
BREAKOUT_POSITION_SELL=10
MONTHLY_BUDGET_BREAKOUT=4000
```

---

## 四、MA Cross（半導體順勢）— $2,000/月

台積電 (2,365) 和聯發科 (4,300) 股價過高，`MA_CROSS_POSITION_AMOUNT=2200` 買不到 1 股。

**建議：**
- 調高 `MA_CROSS_POSITION_AMOUNT=2600` 才能買 1 股台積電
- 或將此預算合併到 Bollinger 做 ETF
- 或改買價格較低的權值股（如鴻海 2317）

---

## 完整 `.env` 設定

```env
# 投資組合
PORTFOLIO=0050:bollinger,00878:bollinger,2881:vwap,2886:vwap,2382:breakout

# 每月預算
MONTHLY_BUDGET_BOLLINGER=10000
MONTHLY_BUDGET_VWAP=4000
MONTHLY_BUDGET_MA_CROSS=2000
MONTHLY_BUDGET_BREAKOUT=4000

# 下單股數
BOLLINGER_POSITION_AMOUNT=2500
VWAP_POSITION_AMOUNT=2500
MA_CROSS_POSITION_AMOUNT=2600
BREAKOUT_POSITION_BUY=5
BREAKOUT_POSITION_SELL=10

# 大盤過濾
MARKET_TREND_FILTER=true
```

---

## 各策略目前股價參考（2026/06）

| 代號 | 名稱 | 收盤價 | 月漲跌 | 適合策略 |
|------|------|--------|-------|---------|
| 0050 | 元大台灣50 | 104 | +6.99% | Bollinger |
| 00878 | 國泰永續高股息 | 32 | +15.97% | Bollinger |
| 2330 | 台積電 | 2,365 | +2.83% | MA Cross（需調高額度） |
| 2382 | 廣達 | 390 | +13.68% | Breakout（需調降股數） |
| 2881 | 富邦金 | 118 | +24.87% | VWAP |
| 2886 | 兆豐金 | 42 | +4.88% | VWAP |

> ⚠️ 免責聲明：以上為個人研究筆記，不構成投資建議。自動交易有風險，請自行評估。


Frank: /findmind 依照tw_autotrader_multi.py中的四种投资方式,一个月2万台币,投资15股以内,你建议如何投资?

=>finmind回覆
# TW AutoTrader 每月 2 萬元投資配置建議

> 資料更新：2026 年 6 月初  
> 免責聲明：以下為個人研究筆記，不構成投資建議。自動交易有風險，請自行評估。

---

## 核心原則

1. **四策略分工**：每種策略對應不同市場環境，互補降低風險
2. **零股交易**：2 萬元/月全部以零股執行，分散進場時點
3. **順勢/逆勢平衡**：Bollinger + VWAP（逆勢）與 MA Cross + Breakout（順勢）各半
4. **大盤過濾**：指數跌破年線時暫停買進，避免逆勢接刀

---

## 策略 vs 資金配置

| 策略 | 類型 | 月金額 | 佔比 | 適合市場 |
|------|------|-------|------|---------|
| **Bollinger** | 逆勢（均值回歸） | $10,000 | 50% | 震盪盤、恐慌大跌 |
| **VWAP** | 逆勢（法人成本） | $4,000 | 20% | 金融股低於法人成本 |
| **Breakout** | 順勢（追動能） | $4,000 | 20% | 多頭突破、趨勢啟動 |
| **MA Cross** | 順勢（趨勢跟隨） | $2,000 | 10% | 大波段行情確認 |
| **合計** | | **$20,000** | **100%** | |

---

## 選股建議與每筆股數計算

### Bollinger（$10,000/月）— 推薦：0050 + 00878

ETF 波動穩定、不會倒閉，最適合逆勢接刀。

| 標的 | 股價 | 每月金額 | 每筆股數 | 月交易次數 |
|------|------|---------|---------|-----------|
| **0050** 元大台灣50 | ~104 | $5,000 | 24 股 | ~2 次 |
| **00878** 國泰永續高股息 | ~32 | $5,000 | 78 股 | ~2 次 |

- 0050 涵蓋台灣前 50 大權值股
- 00878 專注 ESG + 高股息，股價低利於零股
- 也可二擇一，將 $10,000 全部集中一檔降低手續費比例

### VWAP（$4,000/月）— 推薦：2881 + 2886

金融股波動低、與法人成本 VWAP 黏著度高，逆勢抄底勝率高。

| 標的 | 股價 | 本益比 | 月營收 | 每月金額 | 每筆股數 |
|------|------|-------|-------|---------|---------|
| **2881** 富邦金 | ~118 | 16.2 | 533 億 | $2,000 | 17 股 |
| **2886** 兆豐金 | ~42 | 17.1 | 90 億 | $2,000 | 48 股 |

- 金融股本益比 15~17 倍，屬於合理偏低
- 月營收穩定，適合長期存股
- 兩者風格不同：富邦金（獲利成長型）vs 兆豐金（穩健官股）

### Breakout（$4,000/月）— 推薦：2382（⚠️ 需調參數）

| 標的 | 股價 | 本益比 | 月營收 | 說明 |
|------|------|-------|-------|------|
| **2382** 廣達 | ~390 | 19.6 | 3,399 億 | 月營收年增強勁，PER 合理 |

**⚠️ 重要：BREAKOUT 預設參數必須調整！**

預設 `BREAKOUT_POSITION_BUY=50` → 50 股 × 390 元 = **$19,500/次**，等於整月預算。

```env
# 強烈建議改為：
BREAKOUT_POSITION_BUY=5        # 每次買 5 股（~1,950 元）
BREAKOUT_POSITION_SELL=10
```

**替代方案**：如果覺得廣達波動太大，可改為 Breakout 搭配：

| 替代標的 | 代號 | 股價 | 優點 |
|---------|------|------|------|
| 鴻海 | 2317 | 查詢中 | 權值股波動較小 |
| 台達電 | 2308 | 查詢中 | 電源龍頭，趨勢明確 |

### MA Cross（$2,000/月）— 建議：暫配置或買 0050

MA Cross 適合大波段趨勢，但目前台積電（2,365）過高：

| 標的 | 股價 | POSITION_AMOUNT | 可買股數 | 結論 |
|------|------|----------------|---------|------|
| 2330 台積電 | 2,365 | 預設 2,200 | **0 股** | ❌ 買不起 |
| 2330 台積電 | 2,365 | 調為 2,600 | **1 股** | ⚠️ 每月只買 1 股，意義不大 |

**建議二選一**：
- **方案 A**：$2,000 併入 Bollinger，改為 $12,000 做 ETF
- **方案 B**：$2,000 買 **0050**（每次 ~19 股），用 MA Cross 抓大盤權值股的波段

---

## 三種投資組合方案

### 保守型（60% 逆勢 / 40% 順勢）

| 策略 | 資金 | 標的 |
|------|------|------|
| Bollinger | $12,000 | 0050 + 00878 |
| VWAP | $4,000 | 2881 + 2886 |
| Breakout | $4,000 | 2382（5 股/次） |
| MA Cross | $0 | 暫不配置 |

### 均衡型（50% 逆勢 / 50% 順勢）— ✅ 建議

| 策略 | 資金 | 標的 |
|------|------|------|
| Bollinger | $10,000 | 0050 + 00878 |
| VWAP | $4,000 | 2881 + 2886 |
| Breakout | $4,000 | 2382（5 股/次） |
| MA Cross | $2,000 | 0050（19 股/次抓波段） |

### 積極型（40% 逆勢 / 60% 順勢）

| 策略 | 資金 | 標的 |
|------|------|------|
| Bollinger | $8,000 | 0050 |
| VWAP | $4,000 | 2881 |
| Breakout | $5,000 | 2382（7 股/次） |
| MA Cross | $3,000 | 2330（1 股/次，調高額度至 3,000） |

---

## 完整 `.env` 設定（均衡型）

```env
# 投資組合
PORTFOLIO=0050:bollinger,00878:bollinger,2881:vwap,2886:vwap,2382:breakout,0050:ma_cross

# 每月預算（總計 20,000）
MONTHLY_BUDGET_BOLLINGER=10000
MONTHLY_BUDGET_VWAP=4000
MONTHLY_BUDGET_BREAKOUT=4000
MONTHLY_BUDGET_MA_CROSS=2000

# 下單股數
BOLLINGER_POSITION_AMOUNT=2500
VWAP_POSITION_AMOUNT=2500
MA_CROSS_POSITION_AMOUNT=2600
BREAKOUT_POSITION_BUY=5
BREAKOUT_POSITION_SELL=10

# 大盤過濾 + 金字塔加碼
MARKET_TREND_FILTER=true
PYRAMID_ENABLED=true
PYRAMID_TIER1_SHARES=200
PYRAMID_TIER2_SHARES=400
PYRAMID_TIER3_SHARES=600
PYRAMID_TIER2_DROP=0.03
PYRAMID_TIER3_DROP=0.05
```

---

## 目前市場狀況參考（2026 年 6 月）

| 代號 | 名稱 | 股價 | 本益比 | 月營收 | 適合策略 |
|------|------|------|-------|-------|---------|
| 0050 | 元大台灣50 | 104 | — | — | Bollinger ✅ |
| 00878 | 國泰永續高股息 | 32 | — | — | Bollinger ✅ |
| 2330 | 台積電 | 2,365 | 31.8x | 4,107 億 | MA Cross（需調高額度） |
| 2382 | 廣達 | 390 | 19.6x | 3,399 億 | Breakout ✅（需調降股數） |
| 2454 | 聯發科 | 4,300 | 68.5x | 467 億 | ❌ 太貴 |
| 2881 | 富邦金 | 118 | 16.2x | 533 億 | VWAP ✅ |
| 2886 | 兆豐金 | 42 | 17.1x | 90 億 | VWAP ✅ |
| 3661 | 世芯-KY | 4,285 | 62.8x | 21 億 | ❌ 太貴 |

---

## 營收趨勢觀察

**台積電（2330）** 月營收持續在 3,100~4,100 億之間，基本面穩健。

```
1月  3,350億
2月  4,012億
3月  3,176億
4月  4,151億
5月  4,107億  ← 維持高檔
```

**廣達（2382）** AI 伺服器需求帶動營收跳升：

```
1月  2,724億
2月  2,308億
3月  2,155億
4月  3,628億  ← 跳升
5月  3,399億  ← 維持高檔
```

---

## 風險提示

1. **順勢策略（Breakout / MA Cross）在盤整期會被雙巴**：搭配大盤年線過濾 + 金字塔加碼可降低影響
2. **逆勢策略（Bollinger / VWAP）在崩盤時太早接刀**：分批進場永遠比一次性下單安全
3. **零股手續費**：多數券商單筆低消 1 元，建議每筆下單金額維持在 2,000 元以上
4. **每月 2 萬元不宜分散太多標的**：建議 3~5 檔就好，每檔每月至少能交易 1~2 次
5. **本益比僅供參考**：台積電 31x 看似偏高，但考慮 AI 長期需求，溢價有其合理性

---

## 總結

| 策略 | 資金 | 標的 | 每筆股數 | 每月約交易 |
|------|------|------|---------|----------|
| Bollinger | $10,000 | 0050 + 00878 | 24 + 78 股 | 2~4 次 |
| VWAP | $4,000 | 2881 + 2886 | 17 + 48 股 | 1~2 次 |
| Breakout | $4,000 | 2382（5 股/次） | 5 股 | 1~2 次 |
| MA Cross | $2,000 | 0050 | 19 股 | 1 次 |
| **合計** | **$20,000** | **5 檔標的** | | **5~9 次/月** |

> ⚠️ 免責聲明：以上為個人研究筆記，不構成投資建議。所有自動交易策略皆有虧損風險，請在模擬模式充分測試後再投入真實資金。

Frank: 
依照你建议的请产生一个.env檔存成.env_finmind.txt

產生的.env_finmind.txt:
# ==========================================
# TW AutoTrader 環境設定檔
# 每月 2 萬元 / 均衡型配置 / 2026-06
# ==========================================

# FinMind 設定
FINMIND_API_TOKEN=your_finmind_api_token_here

# 凱基 API 設定
KGI_API_KEY=your_kgi_api_key_here
KGI_API_SECRET=your_kgi_api_secret_here
USE_REAL_API=false

# Telegram 通知
TELEGRAM_BOT_TOKEN=您的Telegram機器人Token
TELEGRAM_CHAT_ID=您的Telegram聊天群組ID

# LINE Notify
LINE_NOTIFY_TOKEN=您的LineNotify權杖密碼

# 風險控管
INITIAL_CAPITAL=240000           # 初始資金 24 萬（每月存 2 萬，假設已存 1 年）
MAX_RISK_PER_TRADE=0.01          # 單筆最大風險 1%
MAX_DAILY_LOSS=0.05              # 每日最大虧損 5%
MAX_DAILY_TRADES=5               # 每日最大交易次數

# ==========================================
# 策略參數
# ==========================================

# 布林通道反轉策略
BOLLINGER_WINDOW=20
BOLLINGER_STD_DEV=2.0
BOLLINGER_RSI_PERIOD=5

# VWAP 偏離度反轉策略
VWAP_SIGMA_MULT=1.5
VWAP_RSI_PERIOD=5

# 均線交叉策略
MA_CROSS_FAST_PERIOD=9
MA_CROSS_SLOW_PERIOD=21
MA_CROSS_ATR_THRESHOLD=0.005

# 突破交易策略
BREAKOUT_LOOKBACK=20
BREAKOUT_ATR_PERIOD=14

# ==========================================
# 多股組合配置（均衡型）
# Bollinger 50% + VWAP 20% + Breakout 20% + MA Cross 10%
# ==========================================
PORTFOLIO=0050:bollinger,00878:bollinger,2881:vwap,2886:vwap,2382:breakout,0050:ma_cross

# ==========================================
# 每月預算控管（總計 20,000 元）
# 0 = 不限制
# ==========================================
MONTHLY_BUDGET_BOLLINGER=10000
MONTHLY_BUDGET_VWAP=4000
MONTHLY_BUDGET_BREAKOUT=4000
MONTHLY_BUDGET_MA_CROSS=2000

# ==========================================
# 下單股數設定
# 金額制（bollinger / vwap / ma_cross）
# 股數制（breakout）
# ==========================================
BOLLINGER_POSITION_AMOUNT=2500
VWAP_POSITION_AMOUNT=2500
MA_CROSS_POSITION_AMOUNT=2600
BREAKOUT_POSITION_BUY=5
BREAKOUT_POSITION_SELL=10

# ==========================================
# 大盤年線過濾（FinMind 資料源）
# ==========================================
MARKET_TREND_FILTER=true

# ==========================================
# 金字塔加碼（Bollinger 分批進場）
# ==========================================
PYRAMID_ENABLED=true
PYRAMID_TIER1_SHARES=200
PYRAMID_TIER2_SHARES=400
PYRAMID_TIER3_SHARES=600
PYRAMID_TIER2_DROP=0.03
PYRAMID_TIER3_DROP=0.05

