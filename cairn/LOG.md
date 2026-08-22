# Project Cairn 日誌

本檔案以倒序記錄實質進展——最新條目在最上方、緊接本行之下。每條保持精簡——只要摘要與指標；結論沉澱到 `cairn/<topic>.md`。

## 2026-08-20 · IM_DEBUG 法人動能除錯模式（v3.12）

- 需求：法人動能未啟用（INST_MOM_CAPITAL=0）時，逐日檢查市場是否產生合格股票。
- 實作：`InstitutionalMomentumStrategy.debug_screen(now)` — 僅在盤後 13:31-13:45（每日或週五模式）執行 get_candidates（內部自動寫 logs/inst_momentum_screening.json，含 screen_date/qualified/near_misses），更新 state 但**不交易、不主動發 TG**；結果由既有 `send_sleep_notification` → `_build_inst_screening_msg` 於睡前報告帶出（✅入選 / ⚠️未達標前三）。live_trader_multi.py 兩處呼叫改為 `INST_MOM_CAPITAL>0 or IM_DEBUG=='1'` 分支。`IM_DEBUG` env 預設 1。
- 測試：test/test_inst_debug.py 6 個（時窗/同日去重/週末/週模式/capital=0 run 早退），全 94 tests OK。策略說明（主文+附錄）與 .env 同步；版本 3.11→3.12。

## 2026-08-20 · README/策略說明/使用手冊更新為含 MIN_DRAW_BACK 的 11 年數據

- 以與 README 基線相同的設定（N=100、15d 法人確認、含成本）重跑：基線 12,572,830/+2414.6%/34.1%/1.17/-39.2% 精確重現 ✓；**加 MIN_DRAW_BACK=20 → 終值 16,843,503、+3,268.7%、年化 37.7%、夏普 1.24、MDD -49.7%(@2025-04-09)、跳過換股 11 次**（A:2015-08/2016-02/2017-11/2018-05/11/2019-05/2022-11/2025-05、B:2020-03/2022-06/2025-03）。
- README 方案三主表/逐年表/現行設定一覽 → MDB=20 數字（+3,268.7%/37.7%/1.24/-49.7%），歷史掃描數字標註「無股災防護基線」；策略說明 11 年回測表新增 MDB=20 定案列（原 15d 基線降為中間列）、MIN_DRAW_BACK 小節標註 README 對齊版本；使用手冊 pool 註解與 MIN_DRAW_BACK 說明同步。cairn 已記。

## 2026-08-20 · 沉澱 PyArmor trial 單檔大小上限（56KB）

- 本機實測 PyArmor 8.5.12 trial：單檔源碼 ≤56KB 可加密、57KB 起被拒（`Can't obfuscate big script`）；**限制為單檔非總和**（40+30KB 兩檔合計 70KB ✅）→ 超限可拆模組繞過。
- 主程式源碼現 43KB（餘裕 ~13KB）；trial 無 BCC/RFT。已寫入 `cairn/deploy-pipeline.md`（含重測方法）。

## 2026-08-20 · 換股買入獨立路徑（ROTATION_BUY_DIRECT=1）— 貼近回測買入條件

- 問題：全輪替買入走 Group 1 風控通道（每日虧損/交易次數/漲跌停/大盤年線/預算/冷卻），大跌日換股會「賣了舊股卻買不進新股」→ 空手一季，與回測（無這些閘門）行為偏離。
- 實作：`core/rotation_hold.is_rotation_buy(cfg, is_rotation_day)` 判斷換股買入（排定買入日 + keep_wait + max_entry_price=-1）；live_trader_multi.py 買入迴圈以 `_rot_buy` 旗標跳過 5 個閘門（每檔次數/30分鐘冷卻/check_trade_allowed/每月預算/大盤年線），保留 check_stock_cap（alloc 語義）與 _rot_day_buys 去重；`ROTATION_BUY_DIRECT` env（預設 1）可關回原通道。`_is_rotation_day` 上移到每檔迴圈頂部（rotation 分支內重複計算移除）。
- 測試：test_rotation_hold +6（is_rotation_buy 判斷），全 88 tests OK。文件/使用手冊/.env 同步。

## 2026-08-18 · MIN_DRAW_BACK 實盤整合（定案 20、最多延長一季）

- 新增 `core/rotation_hold.py`：資產 = `TOTAL_CAPITAL + 已實現損益(performance.csv 買賣差額) + 持股市值`（不需成本基礎，避開分帳本重置干擾）；`should_hold` 狀態機（首次超標延後、仍超標強制換股、恢復即換股）；峰值/延長狀態持久化 `logs/equity_peak.json`/`logs/rotation_hold.json`；fail-open（股價抓取失敗或任何異常 → 照常換股）。
- live_trader_multi.py：換股日 13:31~13:35 觸發後先跑 `check_rotation_hold(MIN_DRAW_BACK, ...)`，超標則跳過選股、TG 通知、續抱（用旗標 `_rotation_held` 包住選股區塊，避免 continue 跳過 sleep 空轉）；`MIN_DRAW_BACK` env 每日 08:40 熱重載生效。
- 測試：`test/test_rotation_hold.py` 10 個（狀態機/資產計算/整合 fail-open），全 82 tests OK。`.env` 定案 `MIN_DRAW_BACK=20`；使用手冊/策略說明已更新（實盤整合狀態）。
- 部署：root + plans 同步（identical），deploy.sh 會自動加密上 VM。

## 2026-08-18 · MIN_DRAW_BACK 無限期延後模式對照測試

- `backtest_selector` 新增 `min_drawback_unlimited`（True=回撤未恢復就一直續抱；False=最多延長一季）；官方腳本 `MIN_DRAW_BACK_UNLIMITED=1` env；sweep 改跑 7 組合。
- 2015-2025 結果：**無限期全面劣於延長一季** — MDB=10 無限期跳過 50 次（B 排程 2015-12 起連續 34 季凍結，+408.6% 遠遜基線）；MDB=20 無限期 +2539.2% < 延長一季 +3228.3%（連續 6 季錯過 2019 反彈）；**MDB=30 兩模式等價**（4 次跳過後一季內必恢復，強制換股未觸發）。
- 結論：強制換股是必要安全閥；「無限期延後」在低門檻下可能策略凍結。MDD 同樣未改善（-45~-51% vs 基線 -42.3%）。已更新策略說明對照表。

## 2026-08-18 · 全輪替新增 MIN_DRAW_BACK 重大回撤保護 + 2015-2025 門檻測試

- 規格：換股日帳戶總回撤（自歷史峰值）> MIN_DRAW_BACK% → 該季不賣不買續抱；下一季仍超標 → 照常換股（最多延長一季）；0=停用。
- 實作：`backtest_selector` 新增 min_drawback（extended_once 狀態機；跳過季沿用 last_shares、不計買入成本）；`backtest_dual_quarterly`/`backtest_rotation_historical`（MIN_DRAW_BACK env）透傳；工具 `scripts/backtest_mindrawback_sweep.py`。
- 2015-2025 測試（月尾、誠實池100、法人21d、含成本）：**MDB=20 最佳 +3228.3%（年化37.5%、夏普1.23、跳過12次）**；MDB=30 +2993.3%（4次）；MDB=10 大傷 +1191.0%（25次過度干預）。
- ⚠️ 三者 MDD 皆比基線深（-48.2~-50.1% vs -42.3%，谷底移至 2025-04-09）：機制改善報酬（躲換股摩擦）、**不改善回撤**（跳過=不執行 63d 防禦切換、重新平衡延後一季）— 與「解決災情回撤」初衷相反，已誠實寫入策略說明。
- 陷阱：官方回測腳本 `INST_CONFIRM=1` env 才啟用法確認；shell 乾淨時為無法人基線（MDB=20 6,990,657 vs 有法人 16,641,369）→ 加 env 後精確吻合。實盤整合待辦（需權益峰值追蹤）。

## 2026-08-18 · 沉澱 deploy.sh 加密/備份流程至知識庫

- 建立 `cairn/deploy-pipeline.md`：完整紀錄 deploy.sh 13 步流程（源碼備份→plans 自動 commit/push→**pyarmor 加密（輸入=plans 備份）**→docker build→GCS→VM 重啟→**EXIT trap 還原 root**）。
- 關鍵陷阱：git HEAD 的 root `live_trader_multi.py` = 混淆版（3 行/179KB/變數改名），`plans/live_trader_multi.py` = 源碼（806 行）；deploy 被硬殺時 root 會留混淆版（檢查 `wc -l`，`cp plans/... root` 還原）；plans 若被備份成混淆版會二次加密。AGENTS.md 閱讀順序加入導覽指標。

## 2026-08-18 · 修復 _rot_day_buys UnboundLocalError（VM 全輪替買入全部失敗）

- 症狀：VM log 每分鐘重複 `❌ 3653/2395/3231/2357 錯誤: cannot access local variable '_rot_day_buys' where it is not associated with a value` — 4 檔全輪替持股的買入判斷全部拋錯。
- 根因：`_rot_day_buys = set()` 原寫在 `if (daily_symbol_trades_date != today_str):` 區塊內（每日初始化）。但 `main()` 啟動時 `load_daily_trades()` 若讀到「今天」的紀錄（當天重啟/熱更新），`daily_symbol_trades_date == today` → 該區塊被跳過 → 買入迴圈 `if symbol in _rot_day_buys`（L432）UnboundLocalError。**只要程式在當天有過一次紀錄後重啟就會觸發**（11:01 deploy 重啟即中）。
- 修復（最小改動）：`_rot_day_buys = set()` 移至迴圈層級無條件執行（每輪重新初始化；雙重買入防護由 `position_size = max(0, target_shares - existing)` 把關，語義安全）。
- 回歸測試：`test/test_rot_day_buys.py`（AST 靜態檢查：初始化不得只寫在 if 區塊內；先 RED 後 GREEN），全 72 tests OK。
- 陷阱：deploy.sh 的 pyarmor 流程會在 exit trap 把 root `live_trader_multi.py` 從 plans/ 還原；本次 10:49 的 deploy 中斷留下混淆檔在 root（「deploy 沒發生」的來源），11:01 的 deploy 有還原但**內容是未修復源碼** → 修正後須把 plans 修正版複製回 root 再重跑 deploy.sh。

## 2026-08-18 · ROTATE_TRADING_DAY_N=-1（月尾選股日）改為預設 + 11 年全期 N 掃描

- 承上筆掃描結論（月尾選股日 11 年 +1981.7% 遠勝 N=1 舊預設 +337.4%），實盤預設從 N=1 改為 **-1 = 每月最後交易日**。
- 實作：`TradingCalendar.get_nth_trading_day` 支援 n=-1（回傳該月最後交易日）；`should_rotate_today` 預設改 -1；`live_trader_multi.py`（+plans 副本）env 預設改 -1、啟動/Telegram 顯示「每月最後交易日」；`.env`/`.env.example.txt`/使用手冊/策略說明/scripts README 同步；測試 +2（月尾交易日、預設=月尾），全 69 tests OK。
- 全期重掃：`backtest_rotate_day_sweep.py` 支援 start/end 參數與 N=-1，2015-2025 全期 N=-1..12（誠實池 100、法人 21d）：**月尾 +1981.7%（年化 31.8%、夏普 1.12）最佳**；N=12 +826.7%（次佳）；N=1 +337.4%；N=4 +204.5% 最差。2022-2025：月尾 +234.2% vs N=1 +94.4%。選股相似度：月尾 vs N=1 僅 0.09、vs N=12 0.33。
- 結果存 `results/rotate_day_sweep_2015_2025.*`、`rotate_day_sweep_2022_2025.*`；N 影響分析已寫入 策略說明.md（選股日 N 的影響小節）。

## 2026-08-18 · 全輪替選股日 N=1..12 敏感性掃描（2022-2025）

- 動機：實盤 `ROTATE_TRADING_DAY_N=1`（每月第 1 交易日），但歷次回測皆用「月尾」選股日 → 想量化選股日對獲利/選股的影響。
- 實作：`scripts/backtest_rotate_day_sweep.py` — 以實際價格行事曆（0050 日曆）取每月第 N 交易日；誠實池前 100、每排程 4 檔、auto_momentum、MA 過濾、SW0.5、INST_CONFIRM=1（21d）、含成本、50 萬；輸出 `results/rotate_day_sweep_2022_2025.csv/.json/holdings.json`。
- 結果（2022-2025 總報酬）：**N=8 +247.8%（年化 36.6%、夏普 1.20）最佳** ｜ N=10 +242.9% ｜ N=6 +230.4% ｜ N=12 +230.2%（回撤最低 -31.3%） ｜ 月尾 +234.2%（夏普 1.22、回撤 -39.0%） ｜ **N=1（實盤預設）+94.4%（年化 18.1%）偏弱** ｜ N=3 +36.7% 最差。最佳/最差差 6.8 倍。
- 選股差異：相鄰 N 選股 Jaccard 0.6~0.72、距離越遠越低；**月尾 vs 任一 N 僅 0.07~0.31**（動能窗口+持有區間不同）。2022 熊年全部 N 皆負（-6.7%~-27.5%）。
- 關鍵結論：回測數字（月尾）≠ 實盤（N=1）行為；實盤要貼近回測應改 N=8~12 或月尾（N≈20）。單一 4 年窗口，選股日本身即高敏感參數，建議 walk-forward 再驗證。

## 2026-08-17 · 全輪替補上日夏普 / 最大回撤（2015-2025）

- 動機：全輪替 11 年回測只有終值/逐年，缺風險調整指標；對照 FinLab 複合動能（日夏普 1.18、MDD -40.1%）無法比較。
- 實作：`backtest_dual_quarterly` 回傳 records_a/b（向後相容）；`scripts/backtest_rotation_historical.py` 重建日頻權益曲線（每季持股×日收盤、買賣成本在換股日實現）→ 日夏普（rf=0，×√252）+ MDD + 0050 同源對照，輸出 `results/rotate_mode5_2015_2025_daily_equity.csv`。
- 結果（N=100 + 15d 法人確認）：**日夏普 1.17、MDD -39.2%**（@2025-04-09）；基線（無法人確認）0.98 / -48.7%；0050 0.95 / -33.8%。法人確認同時改善報酬與風險。
- 陷阱（兩次）：① `records[i].value` 是「下季末賣出後價值」非「本季初資本」——部署資本須取前筆 records 值（曾導致換股日 +164% 假跳變）；② 段內多檔同日期須 groupby 加總，不能用 drop_duplicates（曾掉到 1/4 價值、MDD -84.7% 假象）。兩次皆以終值 12,572,830 精確重現為驗收。
- 0050 原文件 +764% 終值與其逐年表複利（+457%）不符 → 同源重算 +451.9% 取代並註記。

## 2026-08-17 · TG 睡前/啟動持倉報告市價凍結修復

- 根因：`core/live_notifications._build_holdings_message` 以 performance.csv 最後一筆成交價當市價（未平倉部位=買進價）→ 參考市價恆等於成本、未實現損益 +0（與儀表板同根源）。
- 修復：`core/inst_data.py` 新增共用 `fetch_latest_closes()`（TWSE STOCK_DAY 本月+上月取最後收盤；失敗回退 CSV 價）；`_build_holdings_message` 優先使用真實收盤價；`scripts/generate_dashboard.fetch_current_prices` 改委派共用函式（消除重複）。
- **追加**：`send_closing_summary` 內聯了一份相同的舊邏輯（收盤報告仍顯示舊價）→ 重構委派 `_build_holdings_message`，刪除 ~50 行重複。
- 回歸測試 +3（test/test_live_notifications.py，68/68 全綠）；真實 API 驗證 4 檔全部取得市價（未實現 +44,660）。
- 影響範圍：睡前報告、啟動報告、收盤報告、儀表板共用同一抓價邏輯。

## 2026-08-16 · 實盤撞股改為與回測一致：跨排程權重合併 + 補足/超額 trim

- 動機：實盤撞股（兩排程選中同一支）時買入端 `existing>0` 跳過 → 該排程資金留空；回測為獨立帳戶各自滿倉 → 用戶要求實盤對齊回測。
- 設計：`core/config_loader.load_portfolio_config()` 讀 .env 檔計算 symbol 出現次數，alloc 乘次數（12.5×2=25）→ 撞股=合併權重；`plans/live_trader_multi.py` 買入端改「補足到目標股數」（rotation_pending.json 記錄買賣日、當日限一次 `_rot_day_buys`），換股日 09:00 新增超額 trim（持有>目標即賣差額、分帳本按比例扣減）。
- 關鍵取捨：最初做 .env 合併（merge_duplicate_alloc）會刪掉排程區段條目 → 排程退出時 symbol 從 config 消失（B 持股被誤清倉）→ 改由 loader 計數，區段成員關係完整保留。
- 回歸測試 +4（test_rotation_merge.py，65/65 全綠）；完整 3 個月生命週期模擬通過（撞股 +46 股加倍 → 退出 trim 回單排程權重）。
- 已更新策略說明「連續選股重複時的處理」章節（撞股行為、續抱不重複交易）。

## 2026-08-16 · 全輪替回測補計交易成本 + 連續選股重複處理定案

- 根因：`backtest_selector`（季度路徑，含 backtest_dual_quarterly/11 年全窗）買賣未扣手續費/證交稅；成本只在 TWO_BY_TWO 模式有 → README「已計入成本」宣稱與程式不符。
- 修復：`backtest_selector` 買入股數除以 `(1+COMMISSION_RATE)`、賣出/期末評價乘 `(1-COMMISSION_RATE-tax_rate(sym))`；回歸測試 +1（test_backtest_costs.py，61/61 全綠）。
- **實盤維持不排除已持有**（選股端自由重選；買入端 `existing>0` 不重複下單）→ 已在策略說明新增「連續選股重複時的處理」文件（同排程重選=先賣後買、跨排程撞股=資金留空、回測雙排程為獨立帳戶）。
- **新數字（2015-2025, N=100, 含成本）**：基線 +1,494.2%（年化 28.6%）/ 15d法人確認 **+2,414.6%（年化 34.1%）**（舊 +3,135%/37.2%）；雙窗 2018-2021 +429.4% vs +300.9%、2022-2026-07 +292.4% vs +275.2%；N 敏感性 N=100 仍見頂（28.6%）。2022-2025 +199.6%（年化 31.6%）。
- 已同步 README、策略說明、回測比較 MD 全部受影響數字 + 修正註記。

## 2026-08-16 · 績效儀表板現值凍結修復：市價改抓 TWSE 最新收盤

- 根因：`scripts/generate_dashboard.py` 的 `build_html()` 呼叫 `compute_positions()` 未傳即時市價 → 市價 = performance.csv 最後一筆成交價（未平倉部位即買進價）→ 未實現損益恆 +0、現值永不動（實際 2357 已 798→996）。
- 修復：新增 `fetch_current_prices()`（TWSE STOCK_DAY，抓本月+上月取最後交易日收盤；失敗回退 CSV 價不中斷產檔），`build_html()` 傳入 `current_prices=`；「持有天數」欄標題修正為「最後買進日」（原顯示日期）。
- 回歸測試 +3（test/test_dashboard.py，60/60 全綠）；實測 4 檔收盤價與 TWSE 一致（2357=996、3231=193.5、3653=4855、2395=683）。
- 部署提醒：VM 需更新 `scripts/generate_dashboard.py`（deploy.sh 或 git pull）後，下次盤後產檔即帶真實市價；GH Actions 每日 08:45 自動上線。

## 2026-08-13 · 法人訊號併入全輪替：15d 法人確認濾網定案（B 方案）

- 動機：法人動能策略本身跑不贏 0050（誠實池 22-26 +103.66% / 15-21 +49.37% vs 0050 +155.5%/+118.6%），但其邊際來源（法人籌碼）與全輪替（價格動能）正交 → 把法人訊號當全輪替的「確認濾網」。
- 實作：`scripts/stock_selector_grid.py` 新增 `load_twse_inst_merged()`（合併全市場法人快取 2098 交易日，2017-12-18 起；自動跳過 150 檔池子版）、`inst_net_buy()`、`pick_top_stocks(inst_conf, inst_days)` 過濾（近 N 日法人淨買超 > 0 才入選；無資料 pass-through 不誤殺）、回測鏈/實盤接線（INST_CONFIRM / INST_CONFIRM_DAYS env）+ live 補抓。
- **雙窗驗證（N=100, 誠實池）**：15d 2018-2021 **+478.0%**（基線 +337.7%）、2022-2026 **+333.5%**（基線 +314.5%）——兩窗皆改善。11 年全窗（2015-2025）**+3135%**（基線 +1951%，2015-2017 pass-through 逐季數字與基線完全一致）。
- 天數敏感性：10d/15d/21d 雙窗皆改善（高原效應非尖峰）；63d 大幅劣化（2018-2021 +93%）、30d 劣化——確認窗宜短（近月法人行為）。
- 機制確認：15d 下 34 季全部滿倉 4 檔、零空手季、12 季持股被替換——改善來自換股品質，非少持避險。
- 測試 +7（test_inst_confirm_rotation.py，56/56 綠）；.env/.env.example 已設 INST_CONFIRM=1 / INST_CONFIRM_DAYS=15。

## 2026-08-13 · 全輪替 500庫參數掃描定案 + 全文件/教材更新

- 500庫 × 2015-2025 × 參數掃描（top_n×MW×MAF×TW×SW×MP，54 組）：**最佳組合 N=100 + 每季4檔 + MW=2.0 + MAF=1 + SW=0.5 + MP=5 → 年化 31.6%**（總 +1,951%）。
- 雙窗驗證：2015-2021 年化 31.2%、2022-2026-07 年化 36.4%，皆優於舊設定（N=150）。
- 模式×N（2022-2025 誠實池）：純動能 N=100 年化 34.5% 最佳；純催化劑顯著較弱；N=100 見頂後遞減。
- 已調整：stock_selector_grid DEFAULT_PARAMS（use_ma_filter=True、stability_weight=0.5）、ROTATE_STOCK_NO 150→100（.env/.env.example）。
- 已更新：README（11年宣稱、模式×N表）、使用手冊、策略說明（11年回測段落+敏感性表+結論「池子不是越大越好」）、回測-全輪替比較.MD、W4/W6 教材（含重新配音）。


## 2026-08-13 · 全輪替 2015-2025 N 敏感性（500 庫）：N=100 見頂,方法論獲驗證

- 500 庫 × 2015-2025 × N={50,100,150,200,250,300}：年化 19.2% / 29.3% / 27.5% / 24.2% / 19.9% / 16.2%。
- **N=50 年化 +19.2% 與 MD 宣稱完全一致** → 重建方法論可信，差異非方法誤差；MD 大池數字（N=150 +43.6%）為「今天前 150 庫」強偏差版本。
- 誠實曲線 N=100 見頂後遞減；N=300 時 2021 年轉負（-6.5%，寬池稀釋集中贏家）。
- 全輪替相對 0050（21.7%）真實優勢約 6-8pp/年（N=100~150）。

## 2026-08-11 · 全輪替庫擴充至前500：數字持續下修,尚未收斂

- 歷史股本庫由前 300 擴充至前 500（21,967 筆、0 失敗），全輪替歷史池回測重跑：
  - 2015-2021 N=150：300庫 +638% → 500庫 **+519%**（-119pp）
  - 2022-2026-07 N=150：300庫 +284% → 500庫 **+208%**（-76pp）
  - 敏感性 N=300（500庫）：22-26 僅 **+101%**（300庫時為 +468%）
- 逐年（500庫）：15-21 年報 2015 -9.7%、2016 +70.3%、2017 +1.2%、2018 -4.7%、2019 +19.5%、2020 +73.2%、2021 +118.2%。
- 結論：**數字隨庫擴張持續下修、尚未收斂**——300 庫的殘餘偏差仍顯著，真實數字預期更低；全輪替相對 0050 的超額報酬仍存在（15-21 +519% vs +119%、22-26 +208% vs +156%）但遠小於文件宣稱（+1,180% / +381%），池大小敏感性高（N=300 崩至 +101%）。

## 2026-08-11 · 全輪替數據稽核：宣稱數字無法重現,歷史池重建約打五折

- 稽核發現：①原始回測程式不在 repo（stock_selector_grid 的池是今天排名、simulate_portfolio 是硬編碼清單）；②文件宣稱「無倖存者偏差」但庫=今天前150/300大,早年掉出榜者（台揚/茂矽/麗正）仍缺,殘餘偏差存在。
- 建立可重現路徑：stock_selector_grid 修 quarter_end_dates 窗口（原硬編碼 2022-2025）+ backtest_selector 支援逐季池過濾；新增 scripts/backtest_rotation_historical.py。
- **歷史池重建（N=150, 300庫）vs 文件宣稱**：2015-2021 **+638%** vs +1,180%；2022-2026-07 **+284%**（2022-2025 累計 +239% vs 宣稱 +381%）。重大年份 MD 明顯偏高（2021 +171% vs +116%、2023 +144% vs +74%）。
- 敏感性：N=100 +329%、N=300 +469%（22-26窗）——池越大越高,方向與 MD 敏感性表一致。
- 結論：全輪替相對 0050 的超額報酬**真實存在**（15-21 +638% vs +119%、22-26 +284% vs +156%）但規模約為宣稱的一半；宣稱數字疑建立在「今天前150庫」的強偏差版本上。

## 2026-08-11 · 出場重設計成功：MA20 停利雙窗大幅改善（等久一點）

- 使用者方向「等久一點,不要急著出場」→ 誠實池掃 TR∈{10,15,18,20,22,25,30}×SL∈{0.08~0.50}。
- **定案 MA20 停利 + -10% 停損**：22-26 +2.65%→**+103.66%**（PF 0.59→1.46）、15-21 +27.05%→**+49.37%**——雙窗同改善。
- TR=20 為尖銳最優（TR18 +46.78%、TR22 +15.58% 皆劣）；停損放寬（-15%~-50%）無系統性助益。
- **拉抬確認誠實池再驗證**：停用則 22-26 -25.27% / 15-21 -17.55%——方案 A 是核心邊際來源,倖存者修正未動搖。
- 已更新: core/backtest/live 預設 TRAILING_PERIOD=20、.env/.env.example、README/使用手冊/策略說明(誠實池數字)。

## 2026-08-11 · 牛熊適應三變體全數失敗（機制已刪除，教訓留庫）

- 依全輪替 auto_momentum 模式實作法人動能牛熊切換（0050 年線斜率），三變體雙窗驗證全敗：
  - v1 切魚過濾/買超(牛90/0.05、熊120/0.08)：22-26 +10.42% / 15-21 **-1.73%**
  - v2 切 LOOKBACK(牛10/熊15)：22-26 +0.45% / 15-21 +4.80%（雙窗皆劣於固定參數）
  - v2b 熊市暫停進場：22-26 -6.97% / 15-21 -19.82%
- 反直覺發現：熊市期進場其實**淨賺**——MA200 分類過粗,把太多「其實能賺」的日子標成熊市。
- 結論：**全輪替的牛熊切換模式無法移植到法人動能**；固定參數(誠實池 N150/FD120/BR0.08)仍是雙窗最佳折衷(22-26 +2.65%、15-21 +27.05%)。
- 依「失敗參數直接刪除」原則,機制已移除,回測可重現(+2.65%)。

## 2026-08-11 · 牛熊適應機制實作（借整窗最佳參數未達標，預設關閉）

- 實作法人動能版 auto_momentum：0050 年線(MA200)斜率切換進場參數（牛市魚90/買超5%、熊市魚120/買超8%），回測+實盤雙端接線，build_regime_state 純函式 +3 測試（52/52 綠）。
- 首輪雙窗：2022-2026-07 +2.65%→**+10.42%**（牛市日72%）、2015-2021 +27.05%→**-1.73%**（牛市日66%）——未達標。
- 根因：牛市參數(FD90/BR0.05)是「2022-2026 整窗最佳」，在 2015-2021 的牛市子期間本身虧損；**牛熊切換框架的參數需專屬調參（4 參數聯合 grid），不能借整窗最佳**。
- 預設關閉（INST_MOM_REGIME_SWITCH=0），待專屬調參後再啟用。

## 2026-08-11 · 誠實池參數 grid：無組合能雙窗皆正（策略邊際受市況支配）

- 在 2022-2026-07 誠實池（逐季池）重跑完整參數 grid（N×LB×FD×BR×拉抬確認×停利停損，54 組）。
- 最佳單窗：N=100/LB10/FD90/BR0.05/MB0.02/BS1 → +155.30%/回撤17.69%/勝率68.75%。
- **但所有候選在另一窗皆負**：N=100 系 2015-2021 全為負（-5%~-30%）；舊參數 N=150/FD120/BR0.08 是唯一 2015-2021 為正（+27.05%）但 2022-2026 僅 +2.65%。
- 結論：**法人動能無穩健參數配置**；2022-2026 偏好激進（FD90/BR0.05）、2015-2021 偏好保守（FD120/BR0.08）——參數調哪窗過擬合哪窗。固定池 +303.74% 為倖存者偏差幻覺。
- 詳見 cairn/survivorship-bias.md（固定池陷阱）與 cairn/inst-mom-markup-confirmation.md。

## 2026-08-11 · 倖存者偏差炸彈：逐季當時市值池揭露固定池回測大幅高估

- 法人動能回測導入「逐季當時市值候選池」（build_quarterly_pool：歷史股本 × 當季收盤價，歷史股本庫擴充至今天前 300 大），消除倖存者偏差。
- 修正 pool_for_month bug（取到最舊季點而非最近 → 曾造成 0 交易/錯誤池）。
- **誠實數字（逐季池）**：2022-2026-07 **+2.65%**（vs 固定池 +303.74%）、2015-2021 **+27.05%**（7 年，勝率 71.2%、回撤 13.8%）。
- 結論：**+303.74% 主要來自固定池內含「未來贏家」（今天才變大的股票），非策略真實優勢**；誠實邊際很薄。
- 殘餘限制：歷史庫=今天前 300 大（早年大公司掉出榜者仍缺，數字仍偏樂觀）；TWSE 法人資料 2017 前缺（2015-2016 無法回測）；方案 A 參數是在固定池數據上調的，誠實池下可能需重調。

## 2026-08-11 · 刪除失敗參數（B/C/量能確認）— 只留知識庫教訓

- 依使用者決策，直接刪除而非「勿啟用」標註：`EXIT_REVERSAL/EXIT_STALL_*`（方案 B）、`MARKET_FILTER_DAYS`+`fetch_taiex_history/taiex_ma_state`（方案 C）、`VOLUME_CONFIRM`（量能確認）。
- 還原：check_position_exit（純 MA10+硬停損）、check_momentum_entry（純拉抬確認）、live check_exit_signals（原 get_price_data）、market_filter.py（原 MA200）、backtest price_cache 補欄移除。
- 測試 -15（46/46 綠）；.env/.env.example/三文件同步清除。
- 驗證：2022-2026-07 重跑 **+303.74%/回撤 22.75% 完全重現**。
- 教訓保留於 cairn/inst-mom-markup-confirmation.md（B/C 完整數據與根因），勿重複測試。

## 2026-08-11 · 現行最佳設定定案 + 文件全面更新

- 現行最佳設定（.env = 程式預設值一致）：LOOKBACK=10/魚120/買超8%/MA10 + 拉抬確認(0.02/1)。
- 全窗回測 2022-01-01~2026-07-31：**+303.74%**、回撤 22.75%、勝率 62.93%、PF 1.83、232 筆；2023-2026 獨立窗 +205.55%、2022 熊市 holdout +26.57%（皆較方案 A 前大幅改善）。
- README / 使用手冊 2.4 / 策略說明第 6 章+附錄 J 全面更新：新數據、拉抬確認說明、5 個新參數（MIN_BREAKOUT/BUY_STREAK/VOLUME_CONFIRM/MARKET_FILTER_DAYS/EXIT_*，後三者標註「勿啟用」）。

## 2026-08-11 · 方案 C 完整 grid 定案：大盤濾網 9 期數全數失敗

- 18 次回測（MA30~250 × 兩窗）：**不存在任何期數能兩窗同時改善**。
- 虧損窗最佳 MA250 +24.69%（檔 28 天）但獲利窗 -55pp；獲利窗全數被誤傷（MA60 最佳仍 +110.82% vs +160.62%）。
- 定案：法人動能**不需要市場濾網**，此維度自 grid 除名；接線保留（INST_MOM_MARKET_FILTER_DAYS=0）作未來熊市斷路器備用。

## 2026-08-11 · 方案 C 大盤濾網實測失敗（負面結果沉澱 + TAIEX 抓取 bug 修正）

- 實作大盤 MA 濾網全鏈：inst_data.fetch_taiex_history（TWSE FMTQIK 版本化快取）+ taiex_ma_state + core market_ok 門 + 回測/實盤接線 + 6 測試（61/61 綠）。
- 過程中修正 fetch pagination bug：原只翻 20 頁導致 MA 熱身不足、NaN 誤擋 76% 交易日；改依窗口起點往前補 400 日曆天。
- 雙窗掃描（MA20/60/120/200）全敗：虧損窗大盤全程大多頭（200/200 日站上 MA120/200），濾網無用武之地；獲利窗被誤傷（MA60 最佳仍僅 +110.82% vs +160.62%）。
- 結論：**虧損是選股層問題（護盤股），方案 A 已修；市場濾網預設停用**，接線保留作未來熊市斷路器（詳見 inst-mom-markup-confirmation.md）。

## 2026-08-11 · 方案 B 出貨前兆實測失敗（負面結果沉澱）

- 實作買超反轉 + 高檔放量滯漲兩出場訊號（check_position_exit 並行於 MA10，預設全關）+ 8 測試（55/55 綠）+ 回測/實盤 price_info 補 inst_net5/vol_avg20/chg。
- 雙窗實測全敗：反轉訊號虧損窗 -0.40%（洗盤 104 筆）；滯漲訊號獲利窗 +29.35%（vs 基線 +160.62%），趨勢利潤被提早砍掉。
- 結論：法人單日賣超/放量滯漲為正常換手，非出貨前兆；MA10 已覆蓋趨勢轉弱。**預設停用，勿再試同設計**（詳見 inst-mom-markup-confirmation.md 出場端實測結論）。

## 2026-08-11 · 進場拉抬確認導入（護盤 vs 真拉抬區分）

- 動機：2025-08~2026-07 虧損期 8 筆硬停損多為跟進「護盤股」（法人防守成本線、不拉抬）。
- core/inst_strategy_core.py 新增三訊號：MIN_BREAKOUT（離開成本 ≥2%）+ BUY_STREAK（當日買超確認）+ VOLUME_CONFIRM（量能，雙窗實測負貢獻→停用）。
- 雙窗驗證（乾淨資料）：虧損窗 -11.84% → **+19.56%**（勝率 58.6→66.7%）、獲利窗 +142.71% → **+160.62%**（勝率 62.1→64.3%）——兩窗同時改善。
- 測試 +6 案例（test_inst_strategy_core.py，47/47 綠）；.env/.env.example 同步。
- 知識專題：cairn/inst-mom-markup-confirmation.md（含參數掃描教訓：單窗調校=過擬合）。

## 2026-08-11 · 零價髒點事件：假崩盤偵破 + clean_price_df 防護

- 2022-2025 回測最大回撤 62.97% 異常 → 追查發現非策略崩盤：2317（鴻海）2025-07-30 全零價格 row（FinMind 短暫異常被舊快取凍結），當日持倉估值歸零造成 -52% 假崩盤。
- 修復：`core/inst_data.py` 新增 `clean_price_df`（剔除 close<=0/OHLC 全零），_norm_price + july/bottomfish 載入/寫入前套用；測試 +3 案例（16/16 綠）。
- 刪除 2317 髒快取重抓（FinMind 已修正上游資料）→ 2022-2025 重測：**+114.96% → +142.71%，最大回撤 62.97% → 22.68%**（與 README 宣稱一致），交易次數 216 → 190（先前含髒點造成的假交易）。
- 陷阱 #5 寫入 backtest-data-pitfalls：權益暴崩先查持倉股零價髒點。

## 2026-08-11 · 知識沉澱教學文件 + W3 課程加 2 頁

- `opencode快速入門.md` 新增「跨工作階段知識沉澱」一章（機制三層 + Bug 修復三步曲 + 案例）。
- W3 課程（plans/ppt/）新增 2 頁：跨工作階段知識沉澱 / 知識沉澱三步驟；主檔、講稿版、配音版 pptx 同步更新（24 頁），內容.txt 與解說腳本.md（含時間表）同步。
- 課程講稿（notes）已寫入講稿版與配音版。

## 2026-08-11 · 快取共用規則定案（使用者指令）

- 確立硬規則：回測/實盤快取可共用的就共用、格式統一，禁止各策略自建一套；寫入 AGENTS.md「快取使用規則」。
- 建立快取共用地圖（cairn/backtest-data-pitfalls.md）：inst_momentum/price 與 {year}/ 為法人動能三腳本共用基準；selector_prices 因還原價語義不同保持獨立。
- 發現待統一：price/ 目錄內 july/bottomfish（含 ma 欄位）與 inst_data（不含）格式不一致 → 列入 ROADMAP。

## 2026-08-11 · 快取共用規則確認

- 確認全輪替與法人動能快取關係：`mcap_ranking.pkl` 兩邊共用（遷移式讀取）；**股價快取兩套禁止共用**（selector_prices 還原價 vs inst_momentum/price 原始價，合併=重演 2026-08 事件）。
- `backtest.py / simulate_portfolio.py / trading_calendar.py / find_catalyst_stocks.py` 等確認無 pickle 快取，全 repo 覆蓋無漏網（僅 plans/ 嵌套 repo 除外）。

## 2026-08-11 · inline 快取全版本化 + .omo 進 git

- 新增 `core/cache_io.py`（CACHE_SCHEMA_VERSION=2 + load_cache/dump_cache/load_cache_or_raw），`core/inst_data.py` 改用並保留 `_load_cache`/`_dump_cache` 別名（測試相容）。
- 版本化覆蓋：backtest_inst_bottomfish.py（5 處）、backtest_july.py（4 處）、scripts/stock_selector_grid.py（3 處）、build_historical_shares.py（3 處）、selector_keep/workflow/full（各 1 處）。
- 累積資料庫（mcap_ranking.pkl / historical_shares.pkl）走 `load_cache_or_raw` 遷移式讀取，舊格式不丟棄。
- `.omo/` 移除 gitignore 並進版控；`cache/` 整目錄加入 gitignore（避免 `git add .` 誤加可重建快取）。
- 未處理：`plans/` 為獨立嵌套 repo（有自己 .git），其內檔案不在主 repo 版控範圍。

## 2026-08-11 · 快取版本化 + 回歸測試 + 知識沉澱（防跨 session bug 復發）

- `core/inst_data.py`：導入 `CACHE_SCHEMA_VERSION=2` + `_dump_cache`/`_load_cache`（版本不符自動重建並警告、tmp+replace 原子寫入），覆蓋 fetch_twse_inst_bulk / get_price_data / get_institutional_data 三個快取；舊格式快取首次執行會自動重建。
- 新增 `test/test_inst_data_cache.py`（9 案例：版本不符拒絕/過期拒絕/歷史深度不足拒絕/命中/自動重建），`test.test_strategies` 不受影響。
- 新增 `cairn/backtest-data-pitfalls.md`：2026-08 數字無法重現事件（+85.22%→-13.05%）根因、防護與復發檢查清單。
- AGENTS.md：Quirks 加「數字劇變先查快取」、知識沉澱規則加「Bug 修復三步曲」硬規則。
- 已知未覆蓋：backtest_inst_bottomfish / backtest_july / scripts/*.py 的 inline 快取（見 ROADMAP）。

## 2026-08-01 · Project Cairn 初始化

- 建立 Project Cairn 結構（AGENTS.md 合併版、CLAUDE.md、`.cairn/config.yaml`、`cairn/LOG.md`、`cairn/ROADMAP.md`）。
- 歷史遷移模式：`start_fresh`。
- 詳情：見 `AGENTS.md` 與 `.cairn/config.yaml`。
