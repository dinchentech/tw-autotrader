# TW AutoTrader — 台股自動交易系統

📖 [完整使用手冊](使用手冊.md) · 📊 [策略說明](策略說明.md) · 🔙 [回溯說明](回溯說明.MD)



## 🎯 這是什麼？

TW AutoTrader 是一套**專業級台股自動交易系統**，整合四種經典技術分析策略，支援**玉山證券 API** 真實下單，部署在 GCP 台灣機房（每月成本 ~NT$50）。

## 🏆 2024-2025 回溯績效

### 方案一：每月 NT$20,000 DCA（4 檔標的）

| 標的 | 策略 | 報酬率 |
|------|------|--------|
| 0050 | 布林通道反轉 | +10.6% |
| 2330 | 均線交叉 | +36.8% |
| 2382 | 唐奇安突破 | +4.0% |
| 2881 | VWAP 偏離反轉 | +11.9% |
| **組合** | | **+20.0%（年化 +10.0%）** |

結果：**NT$480,000 → NT$575,804（+NT$95,804）** 📈

### 方案二：NT$500,000 一筆資金（8 檔標的）

| 策略 | 資金 | 配置標的 | 組合報酬 |
|------|------|---------|---------|
| 布林通道反轉 | NT$200,000 | 0050, 006208, 00878 | +37.6% |
| 均線交叉 | NT$125,000 | 2330, 2454 | +61.5% |
| VWAP 偏離反轉 | NT$100,000 | 2881, 2886 | +10.1% |
| 唐奇安突破 | NT$75,000 | 2382 | +15.8% |
| **總計** | **NT$500,000** | **8 檔** | **+36.4%（年化 +17.6%）** |

結果：**NT$500,000 → NT$681,791（+NT$181,791）** 📈


> ⚠️ **過去績效不代表未來獲利**，完整回測報告見 [`回溯_50万_2024_2025.MD`](回溯_50万_2024_2025.MD)

---

## 📊 實盤績效

👉 **[即時績效儀表板](https://dinchentech.github.io/tw-autotrader/)**

> 此為**模擬交易**，非真實資金。設定如下：
>
> | 項目 | 內容 |
> |------|------|
> | 起始資金 | NT$500,000（單筆投入） |
> | 選股 | 0050・006208・00878・2330・2454・2881・2886・2382（共 8 檔） |
> | 策略配置 | 布林通道反轉 40%・均線交叉 25%・VWAP 偏離反轉 20%・唐奇安突破 15% |
> | 資金分配 | 布林 NT$200,000・均線 NT$125,000・VWAP NT$100,000・突破 NT$75,000 |
> | 資料源 | FinMind（盤後更新） |
> | 執行環境 | GCP e2-micro (asia-east1-b) · Docker |
> | 更新頻率 | 每日 14:00（臺北） |

---

## 🚀 快速開始

### 本地開發

```bash
# 安裝依賴
pip install -r requirements.txt

# 複製環境設定
cp .env.example .env
# 編輯 .env 填入你的 API Token

# 回測驗證
python backtest.py --strategy vwap
python backtest_esun.py --symbol 2330 --strategy vwap

# 實盤模擬
python live_trader_multi.py
```

### 部署到 GCP VM

```bash
# 1. 本機 build Docker image（約 1-2 分鐘）
docker build -t tw-autotrader .

# 2. Pipe 進 GCP VM（快，不用在雲端重裝套件）
docker save tw-autotrader | gzip -1 | gcloud compute ssh tw-autotrader \
  --zone=asia-east1-b --ssh-flag="-C" \
  --command="gunzip | sudo docker load"

# 3. 啟動
gcloud compute ssh tw-autotrader --zone=asia-east1-b \
  --command="cd ~/tw-autotrader && sudo docker compose up -d"
```

---

## 🏗 專案架構

```
tw-autotrader/
├── strategies/           # 四種策略實作（函式版 + FinMind class 版）
├── core/                 # 策略引擎 + 風險控管
├── data/                 # 資料源（Yahoo / 玉山 / KGI）
├── backtest.py           # Yahoo Finance 回測
├── backtest_esun.py      # 玉山 SDK 回測
├── simulate_portfolio.py # 投資組合模擬引擎
├── live_trader_multi.py  # 多股多策略實盤（主力程式）
├── 使用手冊.md            # 完整使用教學
├── 策略說明.md            # 四大策略原理解說
└── 回溯說明.MD           # 回測操作指南
```

---

## 🔧 技術棧

- **語言**：Python 3.10
- **券商 API**：玉山證券 E.Sun SDK（行情 + 交易）
- **部署**：Docker · GCP e2-micro · Instance Schedules
- **通知**：Telegram Bot · LINE Notify
- **資料源**：Yahoo Finance · FinMind · 玉山行情 API

---

## 版權聲明

本專案（TW AutoTrader）僅供個人學習、研究與學術交流免費使用。

未經原作者（dinchentech）書面明確授權，嚴格禁止：
1. 將本系統之全部或部分原始碼進行商業販售、出租或轉讓。
2. 將本系統包裝為付費軟體、付費雲端服務或訂閱制產品。
3. 利用本專案進行任何直接或間接獲取商業利益之行為。

若有商業合作需求，請洽詢：frank@dinchen.com.tw

## 📧 聯絡

有問題或想學習搭建自動交易系統？請發郵件至 **frank@dinchen.com.tw**，標題請寫：`TW-AUTOTRADER`

