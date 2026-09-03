---
type: project_topic
status: active
summary: "開啟 session 的步 0 索引——環境邊界/目前焦點/配股現況，指向正式 cairn 知識。"
tags: [索引, 現況, 引導]
contains: [reference]
created: "2026-09-03"
updated: "2026-09-03"
related:
  - cairn/LOG.md
  - cairn/ROADMAP.md
  - cairn/environment-scope.md
  - cairn/deploy-pipeline.md
  - cairn/capital-ops.md
authoring_mode: ai_generated
---
# 當前狀態（Session 引導索引）

> 每個 session 的第一步先讀本檔取得方向；細節依任務 grep 對應章節。**正式知識以 `cairn/<topic>.md` 為準**，本檔只做快速索引。

## 環境邊界（先看）
- **本目錄 = 模擬資金**：走「實盤」路徑（玉山 API 實際執行），但 `.env` 用玉山**模擬** key → 無真錢。
- **真錢 = 玉山 real key，日後另開分支**；本目錄只當沙箱/驗證場。詳見 `cairn/environment-scope.md`。
- **執行位置**：平時在本機（DESKTOP-EUEMD3C WSL）直接跑 `live_trader_multi.py` 驗證；GCP VM 要吃到同一份 `.env`，M 需走 `deploy_source.sh`（人工執行）或只上傳 `.env` + 重啟 container。

## 目前焦點
- Group 1 全輪替（ROTATE_MODE=5、TOP_N=3、CAPITAL_PCT=50）維運 + 固定策略（bollinger/vwap/ma_cross/breakout）+ 每季自動換股。

## 近期決策（最新在 `cairn/LOG.md` 上方）
- 法人動能（Group 2）關閉（INST_MOM_CAPITAL=0），專注 Group 1。
- 2454 轉 vwap（原 bollinger）；全輪替 `ROTATE_CAPITAL_PCT=50`（每檔 8.3%、各排程 25%）——修「總配置超額」。
- 實盤訊號改日K（修 bollinger/vwap/ma_cross 分鐘污染）；方案 B 補買更新分帳本。

## 配股現況（TOTAL_CAPITAL=1,200,000）
- **全輪替**：排程 A（2/5/8/11）3017/3653/2059（因 8/31 加碼為 26.7/16.7/21.7 = **65.1%，過渡超額**）；排程 B（3/6/9/12）9 月底以 ROTATE_CAPITAL_PCT=50 加入（3 檔 × 8.33% = 25%）。
- **固定（40.7%）**：2360 致茂(5%) / 3008 大立光(5%, 8股) / 6805 富世達(7%, 30股) / 2454 聯發科(6.7%) / 3189 景碩(5%) / 6213 聯茂(5%) / **2884 玉山金(7%, 新增金融/防禦腿)**。
- **目標（下個選股日修正後）**：固定 40.7% + 輪替 50% = **90.7%** → 現金約 NT$111,600(9.3%)。
- **現況（過渡）**：固定 40.7% + 排程 A 65.1% ≈ **105.8%（略超 1.2M）**——因排程 A 仍超額；`ROTATE_CAPITAL_PCT=50` 會在下個選股日（9 月底排程 B、11 月底排程 A）把排程 A 覆寫回 25%，屆時回到 90.7%。
- ⚠️ 觀察：主要仍集中電子硬體（3008/6805 高價已降部位、新增 2884 金融腿略降集中度）；台股高檔、資金輪動至金融避險。

## 我該怎麼讀
1. 本檔（現況）+ `cairn/LOG.md` 最新條目。
2. 依任務 grep：策略 → `策略說明.md`；操作/參數/部署 → `使用手冊.md`；部署 → `cairn/deploy-pipeline.md`；資金 → `cairn/capital-ops.md`。
3. 大文件勿全文，用 grep 找。
