# 將程式上傳 VM

## 事前準備

在開始之前，請確認你已完成以下步驟：

| 項目 | 說明 |
|------|------|
| ✅ 安裝 Docker | 本機 WSL 需安裝 Docker |
| ✅ GCP 帳號 | 已申請且通過信用卡驗證 |
| ✅ gcloud 登入 | `gcloud auth list` 可看到帳號 |
| ✅ VM 已建立 | `tw-autotrader` VM 在 `asia-east1-b` |
| ✅ VM 已安裝 Docker | Ubuntu 上已安裝 `docker.io` |
| ✅ 程式碼在本機 | `~/tw-autotrader/` 目錄 |
| ✅ `.env` 已設定 | 已填入券商 API Key、TG Token 等 |

---

## 完整部署流程

### 目錄結構確認

你的 WSL 本機目錄結構應該長這樣：

```
/home/frank/tw-autotrader/
├── live_trader_multi.py    ← 主程式
├── strategies/             ← 策略模組
├── core/                   ← 核心功能（風控、券商連線）
├── Dockerfile              ← Docker 建構設定
├── docker-compose.yml      ← Docker 容器設定
├── deploy.sh               ← 一鍵部署腳本
├── requirements.txt        ← Python 套件列表
└── .env                    ← 你的機密設定（不含在 git 中）
```

### 一鍵部署

在 WSL 終端機執行：

```bash
cd ~/tw-autotrader
sudo ./deploy.sh
```

### deploy.sh 做了什麼？

```
🏗️  建構 Docker image          → 將本機程式打包成 Docker 映像檔
📦 壓縮並傳送至 GCP VM         → 透過 SSH 傳送壓縮的映像檔到 VM
📄 同步設定檔                  → 將 .env 和 docker-compose.yml 傳到 VM
🔄 重啟容器                    → 用新映像檔啟動交易程式
🧹 清理舊 image                → 刪除 VM 上舊的 Docker 映像檔
```

### 查看 Log

部署完成後，檢視執行狀態：

```bash
gcloud compute ssh tw-autotrader --zone=asia-east1-b \
  --command='sudo docker logs tw_autotrader_bot --tail 20'
```

正常啟動會看到：
```
🏦 【玉山證券】使用玉山 API 進行行情 + 交易
🚀 啟動 TW AutoTrader 多股多策略分流系統
✅ Telegram 通知已發送
✅ 0050 初始化成功 -> [BOLLINGER]
✅ 2330 初始化成功 -> [MA_CROSS]
...
```

---

## 分步驟部署（除錯用）

如果一鍵部署失敗，可以逐一執行：

### 步驟 1：建構 Docker 映像檔

```bash
cd ~/tw-autotrader
sudo docker build -t tw-autotrader .
```

### 步驟 2：傳送映像檔到 VM

```bash
sudo docker save tw-autotrader | gzip -1 | \
  gcloud compute ssh tw-autotrader --zone=asia-east1-b \
  --ssh-flag="-C" --command="gunzip | sudo docker load"
```

### 步驟 3：同步設定檔

```bash
gcloud compute scp .env tw-autotrader:~/tw-autotrader/.env --zone=asia-east1-b
gcloud compute scp docker-compose.yml tw-autotrader:~/tw-autotrader/docker-compose.yml --zone=asia-east1-b
```

### 步驟 4：重啟容器

```bash
gcloud compute ssh tw-autotrader --zone=asia-east1-b \
  --command="cd ~/tw-autotrader && sudo docker compose up -d --force-recreate"
```

---

## 日常操作

### 更新程式後重新部署

```bash
cd ~/tw-autotrader
sudo ./deploy.sh
```

### 只更新 .env 設定（不重新建構映像檔）

```bash
gcloud compute scp .env tw-autotrader:~/tw-autotrader/.env --zone=asia-east1-b
gcloud compute ssh tw-autotrader --zone=asia-east1-b \
  --command="cd ~/tw-autotrader && sudo docker compose up -d --force-recreate"
```

### 查看即時 Log

```bash
gcloud compute ssh tw-autotrader --zone=asia-east1-b \
  --command='sudo docker logs tw_autotrader_bot --tail 30 -f'
# 加上 -f 可以持續追蹤
```

### 停止容器

```bash
gcloud compute ssh tw-autotrader --zone=asia-east1-b \
  --command='sudo docker stop tw_autotrader_bot'
```

---

## 疑難排解

### 「Permission denied」或 gcloud 驗證問題

```bash
# 重新登入 gcloud
gcloud auth login
```

### Docker 建構失敗

```bash
# 清除 Docker 快取後重試
sudo docker build --no-cache -t tw-autotrader .
```

### VM 硬碟空間不足

```bash
# 連線 VM 後清理
gcloud compute ssh tw-autotrader --zone=asia-east1-b
sudo docker system prune -a -f
sudo journalctl --vacuum-time=3d
```

### 容器一直重啟

```bash
# 查看詳細錯誤
gcloud compute ssh tw-autotrader --zone=asia-east1-b \
  --command='sudo docker logs tw_autotrader_bot'
```

常見原因：
- `.env` 格式錯誤（缺少必要的變數）
- Python 套件安裝失敗（檢查 pip install 日誌）
- 網路問題導致無法連線券商 API
