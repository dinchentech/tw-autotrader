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
- **全輪替**：排程 A（2/5/8/11）keep_wait 3017/3653/2059（因 8/31 加碼為 26.7/16.7/21.7 = **65.1%，過渡超額**）；排程 B（3/6/9/12）以 ROTATE_CAPITAL_PCT=50 於選股日加入。`ROTATE_CAPITAL_PCT=50` 會在選股日覆寫以回到目標，故全輪替腿以輪替引擎自管。
- **非輪替（模型C 每月自動選股, 正常）**：auto 5 檔 **2464 盟立 / 4967 十銓 / 2006 東和鋼鐵 / 3515 華擎 / 2362 藍天**，各 5%（=25%）。
- **現況（2026-09-05 重整）**：全輪替 keep_wait 65.1% + 非輪替 auto 25% = **90.1%**（現金約 9.9%）。已依規則汰換舊固定(3008/2360/6805/2884/2454/3189/6213)與未再選中的舊 auto(1409/6197/2634/6214)；2464 因仍被選中而保留。
- ⚠️ 觀察：非輪替改為「正常」選股(權值/平衡)、全輪替維持(動能/中小飆股)，兩腿互補；auto 型態感知由 live 每日路由。

> ⏳ **待辦（session 開啟請留意）**：非輪替 auto 5 檔(各5%)已進 `.env`，總 alloc **90.1%**（已不超額）。**等排程 A 換股日賣出 keep_wait 檔釋資後**，視情況把全輪替/非輪替比例微調；並持續觀察 5 檔 auto 訊號實盤表現。詳見 `cairn/ROADMAP.md` 開放問題 3。

## 我該怎麼讀
1. 本檔（現況）+ `cairn/LOG.md` 最新條目。
2. 依任務 grep：策略 → `策略說明.md`；操作/參數/部署 → `使用手冊.md`；部署 → `cairn/deploy-pipeline.md`；資金 → `cairn/capital-ops.md`。
3. 大文件勿全文，用 grep 找。

## 可用 skill（DSH）
- **ponytail 家族（user 級，全域）**：ponytail(+audit/debt/gain/help/review)——**懶人資深工程師/YAGNI/最小化**。觸發詞：`ponytail`、`lazy`、`yagni`、`minimal`；亦可 `/ponytail-review`(只抓過度工程)、`/ponytail-audit`(全 repo)、`/ponytail-debt`(ponytail: 註解債單)、`/ponytail-gain`(省了多少)。
- 其他：`project-cairn`(知識沉澱)、`find-skills`(找/裝 skill)、`huashu-design`(HTML 原型/設計)、`vision`(看圖輔助)。
