# Project Cairn 日誌

本檔案以倒序記錄實質進續——最新條目在最上方、緊接本行之下。每條保持精簡——只要摘要與指標；結論沉澱到 `cairn/<topic>.md`。

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
