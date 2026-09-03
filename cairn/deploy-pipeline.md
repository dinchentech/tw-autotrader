# 部署管線（deploy.sh）— pyarmor 加密 + plans 備份流程

> 當前真相（2026-08-18 建立，源於 `_rot_day_buys` 除錯期間對「root 為何是混淆版 / deploy 沒發生」的誤判）。
> 涉及部署、加密、版本發布的任務，先讀本篇。

## ⚠️ 鐵則：所有 deploy 一律由「人工」執行（2026-08-31 起）

**任何 agent（AI）不得代跑 deploy 命令**（`./deploy.sh` / `./deploy_source.sh` / `docker compose` 於 VM 上重啟等）。
AI 的職責止於：改 `plans/` 源碼 → 跑測試 → 更新 cairn → 告知「準備就緒，請人工執行 deploy」。
原因：deploy 涉及 VM 重啟、交易系統中斷、git push，屬高風險操作；2026-08-31 使用者明確指示。

## 一句話

**目前預設用 `deploy_source.sh`（C 方案，2026-08-30 起）**：把**源碼** `live_trader_multi.py` 直接 `docker build`（**不加密**）→ 上傳 GCS → VM 拉取重啟；過程先把源碼備份到 `plans/`（git 子模組，自動 commit/push）。
- `deploy.sh` = pyarmor **加密版**（現無正式 license、8.x trial 單檔上限已過 → 改走 C 方案），加密輸入是 `plans/`，結束後把 root 還原成源碼。
- `deploy_crypted.sh` = 給**只有加密檔 `.encrypted`、無源碼（未買主程式源碼）**的使用者；無 plans 備份、scp 直傳 VM。
- **使用路徑**：現況（無 license）以 `deploy_source.sh` 為主；**購入 pyarmor license 後改以 `deploy.sh` 加密版為主**；一般使用者（沒買源碼）用 `deploy_crypted.sh`。
- 三個腳本的完整對照見下方「三個 deploy 腳本對照」。

## C 方案（2026-08-30 起）：deploy_source.sh — 源碼直部署（無加密）

> pyarmor 8.x trial 授權 2026-08-30 全數過期（`out of license`），6.x/7.x 語法與 deploy.sh 不相容 → 使用者選 C 方案。
> `deploy_source.sh` = deploy.sh 移除全部 pyarmor 步驟，直接 `docker build`（Dockerfile `COPY . .` 打包源碼）→ GCS → VM 重啟。
> 舊混淆版仍保留於 VM `~/plans/live_trader_multi.py.obfuscated_bak`；VM 根目錄不放未加密源碼（放 ~/plans）。
> 未來若購入 pyarmor 授權，可回歸 `deploy.sh`（加密版）。

## 三個 deploy 腳本對照（常用，先看這張表）

| 腳本 | 資料來源 | 加密 | plans 備份 | 上傳途徑 | 結束時 root | 什麼時候用 |
|---|---|---|---|---|---|---|
| `deploy.sh` | root **源碼** | Pyarmor（需正式 license；8.x trial 單檔上限 ~45.5KB） | **有**（commit+push） | **GCS bucket** | **還原為源碼**（EXIT trap 保證） | 需**加密**部署；**購入 license 後為主路徑** |
| `deploy_source.sh` | root **源碼** | 無（源碼直出） | **有**（commit+push） | **GCS bucket** | 維持源碼 | **目前預設（無 license，2026-08-30 起）** |
| `deploy_crypted.sh` | 已加密 `.encrypted` | 現成 | **無** | **scp 直傳 VM** | **移除**複製的根檔 | **無源碼（未買主程式源碼）的一般使用者** |

**共同點**（三者都做）：gcloud 認證檢查 → VM 必須 RUNNING（非交易時段可能關機）→ `scp .env + docker-compose.yml` 到 VM → VM 上 `docker compose down/up --force-recreate`（**交易中斷**）→ `docker system prune` → 清理 VM 回測快取（`historical_shares.pkl`/`2015`/`2020`/`2021`/`inst_momentum_2022`/過舊 `twse_inst_*.pkl`）。

**主要差異**：
- **加密輸入是 `plans/`（源碼備份），不是 root**：deploy.sh / deploy_source.sh 都先 `cp live_trader_multi.py → plans/` 再 commit+push。deploy.sh 再 `pyarmor gen plans/...`（防二次加密）。deploy_crypted.sh 無 plans 流程。
- **上傳途徑**：deploy.sh / deploy_source.sh 把 image tar.gz 傳 **GCS bucket**（VM 再 gsutil 拉）；deploy_crypted.sh 直接 **scp tar.gz 到 VM**（不走 GCS）。
- **deploy.sh / deploy_source.sh 結束後 root 必為源碼**；看到 root=3行/179KB 混淆版 = 上次 deploy 在加密後被**硬殺**（EXIT trap 沒跑到）。deploy_crypted.sh 用 `set -e`（任一失敗即停）且結束時移除複製的 `live_trader_multi.py`（只留 `.encrypted` 與可能產生的 `.bak`）。

**口徑提醒**：三者部署的 `.env` 與本 repo 相同（`ESUN_ENVIRONMENT=simulation` 模擬資金）——見 `environment-scope.md`；真錢是另一分支、用 real key。

## 角色對照（最容易搞混的部分）

| 檔案 | 是什麼 | 判別方式 |
|---|---|---|
| `live_trader_multi.py`（root，git 內） | **混淆/加密版**（README 明言「GIT站上已加密僅可執行」） | 3 行、~179KB、變數名被改名（grep 不到源碼變數） |
| `plans/live_trader_multi.py`（**私有 submodule**） | **主程式源碼**（可讀、可改、**私有不公開**） | git@github.com:dinchentech/plans.git（SSH **private**）；`grep -c _rot_day_buys` > 0；~981 行/56KB |

> **`plans/` = 主程式源碼的私有存放處**：是 git submodule，指向 `git@github.com:dinchentech/plans.git`（**私有、不公開**，非公開 repo）。deploy.sh / deploy_source.sh 部署時把 root 源碼備份到 `plans/` 並 commit+push 到此私有 repo。**機密來源（源碼）以 plans 為準；root 只是混淆/部署用版本。**
| `TMP/live_trader_multi.py.encrypted` | 每次 deploy 的加密檔備份（回滾用） | 與 git 內版本不同來源 |
| `pyarmor_runtime_000000/` | pyarmor 解密密碼函式庫（必須與加密檔同目錄） | — |

## deploy.sh 完整流程（13 步）

1. gcloud 認證檢查（`auth print-identity-token`）＋ VM 必須 RUNNING（非交易時段 VM 自動關機）
2. pyarmor 版本處理（9.x 試用版過期 → 自動降級 8.x）
3. **`cp live_trader_multi.py → plans/`**（源碼備份）
4. plans 子模組單獨 `git add/commit/push`（訊息 `Auto-backup live_trader_multi.py during deploy`；無變更則跳過）
5. **`pyarmor gen -O pyarmor_dist plans/live_trader_multi.py`** ← 加密的輸入是 **plans/ 備份**，不是 root
6. `cp pyarmor_dist/live_trader_multi.py → root`（此刻起 root 是混淆版）＋ runtime 裝到根目錄
7. `docker build -t tw-autotrader .`（image 內含混淆版）
8. 加密檔備份 `TMP/live_trader_multi.py.encrypted`＋runtime；`docker save | gzip > TMP/tw-autotrader.tar.gz`
9. `gsutil cp` 上傳 `gs://tw-autotrader-deploy/`
10. scp `.env` + `docker-compose.yml` 到 VM
11. VM：從 GCS 下載 → `docker load` → `docker compose down/up -d --force-recreate`
12. VM：`docker system prune -a -f` 清舊 image
13. **結尾 `trap - EXIT; restore_original_script`** → `cp plans/live_trader_multi.py → root`＋清 pyarmor_dist/runtime

## 陷阱（contains）

1. **deploy 結束後 root 一定是源碼**。若看到 root 是 3 行/179KB → 上次 deploy 在步驟 6~13 之間被**硬殺**（kill -9/斷電/終端關閉，EXIT trap 沒機會執行）→ 還原：`cp plans/live_trader_multi.py live_trader_multi.py`。
2. **加密輸入是 plans/**：若 plans 曾被錯誤備份成混淆版，會「二次加密」→ 產物行為異常（錯誤訊息/變數名消失）。備份前先確認 plans 是源碼（grep 源碼變數）。
3. **修 bug 的正確流程**：改 `plans/live_trader_multi.py`（或 root 若正好是源碼）→ 測（`test/test_rot_day_buys.py` 等）→ **`cp plans/live_trader_multi.py live_trader_multi.py`** → 跑 `./deploy.sh`。deploy 會自動再備份一次到 plans（內容相同，無害）。
4. **判斷 VM 是否跑新版**：看啟動 log 的版號與設定字串（例：`選股日: 每月最後交易日` = ROTATE_TRADING_DAY_N=-1 新設定；`每月第 1 個交易日` = 舊版）。
5. **deploy 失敗不會破壞源碼**：gcloud 認證過期 / VM 關機 / docker build 失敗都是 `exit 1`，EXIT trap 仍會還原 root——只有硬殺才會留混淆版。
6. **deploy_crypted.sh 是另一條路**：給「沒有源碼、只有 .encrypted 檔」的使用者（上傳加密檔＋runtime），不涉及 plans 備份。
7. **選股邏輯曾被 continue 擋死（v3.19 修復）**：主迴圈 13:31+ 盤後區塊（`h==13 and m>=31`）內每分鐘 `continue`，曾導致寫在區塊後的選股邏輯（13:31~13:35）**永遠不可達——全輪替自動選股自導入以來從未執行**（2026-08-31 發現，backups/ 空 + rotation_pending.json 從不存在為鐵證）。改動主迴圈時務必確認「同層級 continue 後的程式碼是否可達」；回歸測試 `test/test_rotation_selectable.py` 防再犯。

## 回測 vs 實盤快取（VM 只需實盤用）（contains）

> 2026-08-20：VM cache 110MB → 51MB 清理後；deploy.sh 每次部署自動執行下方清理。

1. **實盤必須保留**：`cache/selector_prices/`（選股用，VM 上為 250d lookback 版）、`cache/inst_momentum/` 的 **rolling 法人檔**（`2022/twse_inst_2022-01-01_2026-08-10.pkl` 類，檔名 end ≥ 60 天前）、`price/`、`inst/`、`mcap_ranking.pkl`。
2. **回測專用（VM 不需要）**：`historical_shares.pkl`（歷史股本池）、`2015/2020/2021/` 舊法人目錄（2017-2021 era）、舊年度 twse_inst 檔（end < 60 天前）、`inst_momentum_2022/`（舊版殘留目錄，無程式引用）。
3. **清理規則**（deploy.sh 內建）：刪 `historical_shares.pkl` + `2015/2020/2021/` + `inst_momentum_2022/`；`find cache/inst_momentum -name 'twse_inst_*.pkl'` 檔名 end 日期 < 60 天前 → 刪。rolling 檔（end=今天附近）必定保留。
4. **安全性**：實盤法人確認只查最近 21 交易日 → 只留 rolling 檔完全足夠；`.dockerignore` 已排除 cache/ → image 不會夾帶回測快取；舊檔刪除不影響 `load_twse_inst_merged`（缺檔自動略過）。

## PyArmor 免費版（trial）限制（contains）

> 2026-08-20 本機實測（PyArmor **8.5.12 trial**，deploy.sh 會自動把過期的 9.x 降級到 8.x）。

1. **單檔源碼上限 ≈ 56KB**（dummy 檔實測）；但**真實執行碼的有效臨界更低（~45.5KB，2026-08-23 實測）**——限制看的是「可執行內容」（混淆後大小），註解/空白不計。live_trader_multi.py 曾 46.9KB 觸發 out of license，瘦身至 45.5KB 後恢復（margin 僅 ~1KB）。**維護原則：新增功能時把邏輯搬進 core/ 模組（不加密、不占額度），或購買正式 license**；deploy 前可先跑 `pyarmor gen -O /tmp/t plans/live_trader_multi.py` 預檢。
2. **限制是「單檔」不是總和**：40KB+30KB 兩檔合計 70KB 一起 `pyarmor gen` ✅ 成功 → 主程式超過 ~56KB 時，**拆成多個 .py 模組 import 即可繞過**，不影響加密效果。
3. **主程式現況**：源碼 43KB（2026-08-20，820 行）→ 限制內、餘裕約 13KB；加密產物 177KB 不受此限（只看源碼）。
4. **trial 版其他限制**：BCC（綁定 C 裝置）/RFT（綁定函式）模式不可用；`License No.: pyarmor-vax-000000` 即 trial。要解除需 `pyarmor register` 買正式 license。
5. **重測方法**（版本升級後）：`python3 -c "pathlib.Path('t.py').write_text('x = 1\n' * (N*1024//8))"` + `pyarmor gen -O out t.py`，二分找邊界。

## 2026-08-18 實例（本篇誕生原因）

- 10:49 的 deploy 在步驟 6 後中斷 → root 停留在混淆版 → 誤判「deploy 沒發生」。
- 11:01 重跑（部分完成）→ root 還原成**未修復**的源碼（`_rot_day_buys` bug 仍在）→ VM 出現 UnboundLocalError。
- 教訓：碰到 root=混淆版先還原；改完源碼記得 cp 回 root 再 deploy，否則 build 的是舊內容。
