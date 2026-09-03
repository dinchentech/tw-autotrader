---
type: project_topic
status: active
summary: "版本庫結構：明文(源碼)主程式放 plans/（私有 submodule）——root 為可部署版、機密/快取被 gitignore。"
tags: [git, repo, 子模組, plans, 源碼, 部署, 機密, 快取]
contains: [reference]
created: "2026-09-03"
updated: "2026-09-03"
related:
  - cairn/deploy-pipeline.md
  - cairn/environment-scope.md
  - cairn/backtest-data-pitfalls.md
authoring_mode: ai_generated
---
# 版本庫結構與 plans 子模組

## 一句話
- repo：`git@github.com:dinchentech/tw-autotrader.git`，分支 `main`。
- **明文（源碼）主程式放在 `plans/`（私有 submodule）**；root 的 `live_trader_multi.py` 是**可部署版**（目前源碼，若跑過 `deploy.sh` 則為混淆版）。
- 機密（`.env`、證書、E.Sun 設定）與實盤快取**永不進 git**；回測長歷史快取有條件上 git。

## 子模組（submodule）
- 僅 **`plans`** 一個：`git@github.com:dinchentech/plans.git`（**私有、不公開**）。
- `plans/live_trader_multi.py` = **主程式明文源碼**（可讀、可改、~981 行/56KB）。deploy.sh / deploy_source.sh 部署時把 root 源碼備份到 plans 並 commit+push 到此私有 repo（見 `deploy-pipeline.md`）。

## 一層/二層/三層 split（最易搞混）
| 位置 | 是什麼 | 說明 |
|---|---|---|
| `plans/live_trader_multi.py` | **明文源碼**（私有） | 真正可讀可改的源碼；機密等級最高 |
| root `live_trader_multi.py` | **可部署版** | 目前為源碼；跑過 deploy.sh 會變混淆版（3 行/179KB=grep 不到源碼變數） |
| `TMP/`、`pyarmor_runtime_000000/` | 部署產物 | deploy 的備份/解密密碼，gitignore |

> 判別：root=混淆版 = 上次 deploy 被硬殺未還原 → `cp plans/live_trader_multi.py live_trader_multi.py`。

## 永不進 git（機密，`.gitignore`）
- `.env`（含 telegram/finmind/E.Sun 密碼）。
- `backups/**/.env*`、`*.p12`、`*.pem`、`*.key`、`*.ini`、`*.whl`、`capital.txt`（deploy 備份）。
- `esun_sdk/*.p12`、`*.whl`、`config.simulation.ini*`（E.Sun SDK 憑證/設定）。
- 這些只隨 deploy `scp` 到 VM，永不 commit。

## gitignore 其他（建置/快取）
- `build/`、`venv/`、`node_modules/`、`TMP/`、`vm_logs/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`、`.pdm-build/`、`docs/_build/`。
- `cache/*` 預設忽略，但**保留上 git**：`cache/inst_momentum/bt_price/`、`inst_history/`、`20*/twse_inst_*.pkl`、`selector_prices/`（回測長歷史快取 0 秒載入）；**排除**：`cache/inst_momentum/price/`（實盤短歷史，見 `backtest-data-pitfalls.md`）。
- ⚠️ gotcha：`node_modules/` 已在 .gitignore（line 214），但**先前被誤 commit**，現為「已追蹤」狀態（git status 會顯示 node_modules 變更/刪除）——舊歷史造成，勿再新增。

## 其他
- `.omo/` 在 git（Boulder/plan 追蹤資料，2026-08-11 起跨機器同步）。
- 環境邊界（模擬/真錢）、快取語義（原始價 vs 還原價）分別見 `environment-scope.md`、`backtest-data-pitfalls.md`。
