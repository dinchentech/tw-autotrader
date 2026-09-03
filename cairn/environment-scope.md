---
type: project_topic
status: active
summary: "環境邊界與術語——「實盤」=用玉山 API 的實際執行路徑；本目錄用玉山模擬 API key → 模擬資金（無真金）；真錢（玉山 real key）日後另開分支。"
tags: [環境, 部署, 資金, 沙箱, 模擬, 實盤, 真錢, 分支]
contains: [decision, experience]
created: "2026-09-03"
updated: "2026-09-03"
related:
  - cairn/deploy-pipeline.md
  - cairn/capital-ops.md
authoring_mode: ai_generated
---
# 環境邊界與術語：實盤執行路徑 × 模擬資金

## 一句話

**本 repo 跑的是「實盤」路徑——用玉山 API 實際執行——但用的是玉山「模擬」API key（`.env` `ESUN_ENVIRONMENT=simulation`，沙箱），所以資金是模擬、下單不觸及真錢。** 真錢（玉山 real API key）日後另開分支執行。

## 兩個軸：執行模式 × 資金性質（本話題的核心）

「**實盤**」與「**錢**」是兩個獨立的軸，別混在一起：

| 軸 | 取值 | 說明 |
|---|---|---|
| **執行模式** | 回測 | `backtest*.py` / `simulate_portfolio.py`，用歷史資料模擬。 |
| （縱軸） | **實盤** | `live_trader_multi.py`，呼叫**玉山 API 得到實際執行結果**。「實盤」= 玉山 API 的實際執行路徑。 |
| **資金性質** | 模擬資金 | 玉山**模擬** API key／沙箱。下單不下真錢。 |
| （橫軸） | **真金** | 玉山 **real** API key。真錢下單，**日後另開分支**執行。 |

> 「實盤」在專案裡的意思是「**用玉山 API 實際執行**」（跟「回測」相對），**不代表就是真錢**。要不要錢，看用的是模擬 key 還是 real key。

## 環境邊界（Decision）

- 本 repo = **實盤執行路徑 × 模擬資金** 的驗證環境。
- 軟體以「實盤」模式運行（`live_trader_multi.py` 完整管線：風控、通知、選股、下單都會走玉山 API），但因 `.env` 用模擬 key，**下單結果是模擬的、不觸及真錢**。
- **真錢另開分支**：真正用真金的下單離開本目錄、另起分支，且那是玉山 **real** key。
- 因此本目錄的所有讀數——績效、損益、回撤、監控、資金配置——都是**模擬資金**結果，不能當成真錢績效或投資決策依據。

## 術語澄清（容易誤判）

- `simulate_portfolio.py` = 回測（歷史資料）。
- `live_trader_multi.py` = 實盤（玉山 API 實際執行）；**此 repo 以此模式跑，但配模擬 key**。
- 看到 cairn 文件／LOG／README 中寫「實盤」，指的是**玉山 API 實際執行路徑**；要判斷有無真錢，改看 `.env` 的 `ESUN_ENVIRONMENT`（simulation=模擬資金、real=真金）。
- `deploy.sh`/`deploy_source.sh` 部署到 VM 的也是同一套 `.env`（simulation key），所以此 repo 的部署流程是**管線驗證**，不是真錢上線。

## 影響（Experience）

1. **歸因別混**：本 repo 對「回測 vs 實盤」的一切比較與誠實差異，都是在「實盤路徑 × 模擬資金」下成立；真錢的滑價、成交、資金風險不在此 repo 兌現。
2. **資本操作**：`cairn/capital-ops.md` 的資金決策（如 Group 2 法人動能 30 萬試跑）在此 repo 皆以模擬資金計；真錢資金架構待 real key 分支落地才成立。
3. **數據健康**：模擬環境下 broker 的成交／資金回報由沙箱給，若要驗證真錢的行為（滑價、部分成交、資金不足），別信任此 repo 的模擬數字。
