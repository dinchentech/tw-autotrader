# 部署管線（deploy.sh）— pyarmor 加密 + plans 備份流程

> 當前真相（2026-08-18 建立，源於 `_rot_day_buys` 除錯期間對「root 為何是混淆版 / deploy 沒發生」的誤判）。
> 涉及部署、加密、版本發布的任務，先讀本篇。

## 一句話

`deploy.sh` = 把**源碼** `live_trader_multi.py` 用 pyarmor 加密成混淆版 → 塞進 Docker image → 上傳 GCS → VM 拉取重啟。過程先把源碼備份到 `plans/`（git 子模組，自動 commit/push），**結束時一定把 root 還原成源碼**。

## 角色對照（最容易搞混的部分）

| 檔案 | 是什麼 | 判別方式 |
|---|---|---|
| `live_trader_multi.py`（root，git 內） | **混淆/加密版**（README 明言「GIT站上已加密僅可執行」） | 3 行、~179KB、變數名被改名（grep 不到源碼變數） |
| `plans/live_trader_multi.py`（子模組） | **源碼**（可讀、可改） | 806 行；`grep -c _rot_day_buys plans/live_trader_multi.py` > 0 |
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

## PyArmor 免費版（trial）限制（contains）

> 2026-08-20 本機實測（PyArmor **8.5.12 trial**，deploy.sh 會自動把過期的 9.x 降級到 8.x）。

1. **單檔源碼上限 ≈ 56KB**：55/56KB ✅ 可加密；57KB 起 ❌ 拒絕（`Can't obfuscate big script`）。官方文件只說「不能加密大型腳本」未給數字，以實測為準。
2. **限制是「單檔」不是總和**：40KB+30KB 兩檔合計 70KB 一起 `pyarmor gen` ✅ 成功 → 主程式超過 ~56KB 時，**拆成多個 .py 模組 import 即可繞過**，不影響加密效果。
3. **主程式現況**：源碼 43KB（2026-08-20，820 行）→ 限制內、餘裕約 13KB；加密產物 177KB 不受此限（只看源碼）。
4. **trial 版其他限制**：BCC（綁定 C 裝置）/RFT（綁定函式）模式不可用；`License No.: pyarmor-vax-000000` 即 trial。要解除需 `pyarmor register` 買正式 license。
5. **重測方法**（版本升級後）：`python3 -c "pathlib.Path('t.py').write_text('x = 1\n' * (N*1024//8))"` + `pyarmor gen -O out t.py`，二分找邊界。

## 2026-08-18 實例（本篇誕生原因）

- 10:49 的 deploy 在步驟 6 後中斷 → root 停留在混淆版 → 誤判「deploy 沒發生」。
- 11:01 重跑（部分完成）→ root 還原成**未修復**的源碼（`_rot_day_buys` bug 仍在）→ VM 出現 UnboundLocalError。
- 教訓：碰到 root=混淆版先還原；改完源碼記得 cp 回 root 再 deploy，否則 build 的是舊內容。
