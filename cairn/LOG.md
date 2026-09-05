本檔案以倒序記錄實質進展——最新條目在最上方、緊接本行之下。每條保持精簡——只要摘要與指標；結論沉澱到 `cairn/<topic>.md`。

## 2026-09-05 · git push 在本機需繞過 system ssh 設定（權限擋 ssh）

- **問題**：直接 `git push` 報 `Bad owner or permissions on /etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf`（該檔權限異常，ssh 讀取時拒絕），同先前 cairn 記錄的「VM ssh 直連」環境問題（系統 `/etc/ssh/ssh_config.d/` 唯讀）。
- **解法**：用 `GIT_SSH_COMMAND` 繞過全域 ssh config，走原生 ssh＋指定金鑰：
  ```
  GIT_SSH_COMMAND="ssh -F /dev/null -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519" git push origin main
  ```
- **適用**：github（ssh）、`plans` submodule 的 push 皆同。已成功推 2 筆：`5141725`（V4.00 每月換股/auto/混合分析）與 `dab4c71`（MAX_PROFIT/GCP 認證規則/部署摘要/plans 指標 2e79508）。
- **提交前已做**：僅暫存目標檔（勿 `git add -A`，工作樹有大量 runtime 產物/先前 session 未提交變更）；確認 `.env`、`esun_sdk/*.p12` 已 gitignore、暫存內容無密鑰/憑證；`plans` submodule 先確認「指標 commit 已推上 remote」（`Everything up-to-date`）再記錄指標，避免 clone 指向不存在 commit。

## 2026-09-05 · auto 策略 TG 通知標示「今日路由→底層策略」

- 依使用者要求，`live_trader_multi.py` 在交易通知處，當 `sn=='auto'` 時以 `route_strategy(acd)` 判斷當日型態，把**底層路由策略帶進 TG/LINE 通知**（如 `策略: AUTO(路由→ma_cross)`）。僅用當日 K 線、無前瞻；`import route_strategy` 已接、`py_compile` 過、跨檔一致性檢查全通過。`策略說明.md` 4.5 補說明，`consistency_check.py` 可重跑驗證。

## 2026-09-05 · 建議「全輪替＋模型C」並存，混合比例回測（2015-2025）

- 依使用者決定：建議使用者**同時用全輪替(偏中小飆股動能)＋模型C(每月自動選股,偏權值/價值/防守)**，自行動態調整比例。新增 `scripts/blend_rotation_vs_modelC.py`（混用兩腿每日權益曲線算組合報酬/年化/MDD/夏普）。
- **各自 2015-2025（50萬）**：全輪替 年化 **44.9%**/MDD -52.2%/夏普 1.31｜模型C正常 年化 21.2%/MDD -60.5%/夏普 0.88｜模型C高穩定 年化 8.9%/MDD -27.2%｜模型C高獲利 年化 8.5%｜0050 年化 16.4%。
- **混合（w=全輪替）**：如 全輪替×正常 50/50 → 年化 37.6%/MDD -49.8%/夏普 1.25；×高穩定 20/80 → 年化 26.9%/**MDD -43.8%**/夏普 1.24。
- **結論**：全輪替回報最高但 MDD 深；混合可**把 MDD 壓到比任一腿單獨都低**（分散）但改善有限（兩腿大回撤重疊）；夏普混合大多 1.2~1.3（優於 0050 0.94）。調整建議：w 0.7~0.8 偏攻、0.4~0.5 均衡、0.2 偏防守。詳見 `全輪替與模型C混合分析_2015-2025.md`。
- 文件：`全輪替與模型C混合分析_2015-2025.md` 補「模型C 正常/高穩定/高獲利逐年(2015-2025)」附錄；`策略說明.md` 新增「4.6 建置建議：全輪替 × 模型C 混合」決策指引。

## 2026-09-05 · 每月換股回測 2015-2025：A(掉出前N就賣) vs C(只依賣訊號出場)

- 把 `scripts/backtest_plan2_monthly_3group.py` 期間延到 **2015-2025（50萬、誠實池前100、每月5檔、auto策略、法人確認、股災防護一輪@30%）**，並新增 `SWAP_MODE`（`full`=A 每月掉出前N就賣；`addonly`=C 只依訊號出場、每月只新增不硬賣仍持的）。
- **結果（總報酬）**：| A：高獲利 +262.5% / 正常 +319.1% / 高穩定 -9.5% ｜ C：高獲利 +143.1% / **正常 +703.8%** / 高穩定 +152.9% ｜ 0050 +431.4%（年化16.4%）｜ 方案三 +5,485%（年化44.2%）。
- **C（正常操作模型）結論**：「正常」+704%、年化 20.9%，**首度勝過 0050**；「高穩定」轉正（+152.9%、MDD -27%）；但「高獲利」反而變差（追強需每月換到新強勢股）。MDD 偏深（正常 -60.5%）；夏普正常 0.87 / 高穩定 0.77 / 0050 0.94。
- **重點**：**A 的「每月掉出前N就賣」是不自然、偏強迫的模型**（會剪掉仍在漲的股票、壓抑獲利）；**一般使用者實際操作 = C（只依訊號出場）**，故真實績效應以 C 為準。方向：續抱(只依訊號)適合 正常/高穩定；每月換倉(追強)適合 高獲利。詳見 `回測_方案二_每月換股_三組.md` 第五節。

## 2026-09-05 · V4.00 每月換股 auto 初入實盤 `.env`（等排程 A 賣出再調整）

- 依使用者決定，把「每月換股(高獲利) 5 檔」以 `strategy=auto` 追加進 `.env`（保留下現有全輪替 keep_wait 3017/3653/2059 ＋ 固定股）：**PC_2464/1409/6197/2634/6214**，各 `alloc=5.0`（原 15%→5%），`max_entry_price` 依當日價。
- **現況**：15 檔 PC_ 全可解析（`auto` 已認得）；**總 alloc 130.8%**（原 ~105.8% + 5×5%=25%）→ **仍超 100% 約 30.8%**。使用者計畫**等排程 A（ROTATE_MODE=5）換股日賣出 keep_wait 檔釋出資金後再調整**。
- 未動全域設定（BROKER/TOTAL_CAPITAL/ROTATE_*）；備份 `backups/.env.bak.20260905_215652`。後續：排程 A 賣出後回歸重整總 alloc（目標回 ~100%）、並觀察 auto 訊號實際表現。

## 2026-09-05 · 每月換股選股工具 + 型態感知策略路由器（自動感知）

- 新增 `scripts/monthly_rebalance_picker.py`：每月換股固定程式。用法 `python scripts/monthly_rebalance_picker.py --risk high_profit|normal`（僅兩選項）。誠實池前100、法人確認、選股僅用截至當下資料（無前瞻）；輸出 目前持股 vs 新選股 → 賣出/維持/買入，每檔給「原固定策略」與「auto 型態感知」建議，並輸出可貼進 `.env` 的 `PC_<代號>` 設定列。
- 新增 `strategies/auto_sensing.py`：`route_strategy(df, as_of)`（型態感知路由：價>MA20 且 MA20>MA60 且 20日動能>0 → 順勢 breakout/ma_cross，否則回歸 bollinger/vwap；每天開盤前/收盤後呼叫一次）+ `auto_sensing_strategy(df)`（drop-in 策略函式，逐日路由取當日訊號）。
- 整合：`core/config_loader.py` `STRATEGY_PARAM_KEYS` 加 `"auto":[]`；`live_trader_multi.py` `STRATEGY_FUNCS` 加 `'auto': auto_sensing_strategy`（`py_compile` 通過、單一定義）。`live_trader` 即可用 `PC_<sym>={"strategy":"auto",...}` 讓該股每日依型態自動分派策略。
- 回測對照（續抱+法人確認+股災防護一輪@30%）：`STRAT_MODE=form`（四種開放、依型態）高獲利 +105.6%、正常 +99.3%、高穩定 -10.5%；`group`（策略綁組別）+71.3%/+56.7%/-7.9%。結論：自適應對追強/正常有效、對慢速防守股反而害（被路由到 ma_cross）。詳見 `回測_方案二_每月換股_三組.md`。
- 文件已更新：`使用手冊.md`「選股工具工作流程」加 `monthly_rebalance_picker.py`（參數/用法/記錄比對）；`策略說明.md` 加「4.5 型態感知策略（Auto-Sensing）」章節。`.env.example.txt` 加 `auto` 策略說明與範例。
- **版本升 V4.00**：`core/version.py` APP_VERSION 3.30→4.00；修正 `core/live_trader_helpers.py` 的本地 `APP_VERSION="2.03"` 覆寫（改為 import 共用來源，單一來源）；`使用手冊.md` 版本標註與 V4.00 新功能列。

## 2026-09-05 · 方案二改「每月換股＋三組獨立選股」回測（2022-2025, 500k）

- 新腳本 `scripts/backtest_plan2_monthly_3group.py`：每月換股、誠實池前100、每月5檔等權、只用 bollinger/ma_cross/vwap/breakout 四策略、計入交易成本；三組=三套**獨立**選股規則（非同一次內分三類）。無事後之明：選股日=上個月底（及其前全部資料可用、禁用其後），訊號僅用當日及之前。
- **操作方式（依使用者修正）**：月初重選並買入；持股依策略訊號進出（賣出訊號才出場，**不做月底強制平倉**）；**只換掉被剔除的、續抱仍在選的**（減少換倉）；月內賣出空出資金回 bucket，被剔除後併回現金池於下月重選時分配。
- **可選方案三濾網**：`INST_CONFIRM=1`（近15日法人淨買超>0才入選）、`MIN_DRAW_BACK=30`（`MDB_UNLIMITED=0`=最多延一輪；`=1`=無限延長）。
- **策略指派模式**：`STRAT_MODE=group`（策略綁組別：高獲利=ma_cross/breakout、正常=四種、高穩定=bollinger/vwap）或 `STRAT_MODE=form`（C：四種開放、每月依個股型態自動選順勢/回歸）。
- **結果（續抱+法人確認+股災防護一輪@30%）**：
  - `group`：高獲利 **+71.3%(MDD-38.7%)**｜正常 **+56.7%(MDD-31.3%)**｜高穩定 **-7.9%(MDD-16.8%)**。0050 **+99.9%**。
  - `form`(C)：高獲利 **+105.6%(MDD-36.5%)**｜正常 **+99.3%(MDD-39.4%,逼近0050)**｜高穩定 **-10.5%(MDD-22.2%)**。
- **結論**：C 自適應策略強化「高獲利/正常」、但傷「高穩定」（慢速防守股被路由到 ma_cross 而非回歸）；股災防護「無限@30%」高獲利 +117.7% 最佳、「無限@15%」反而 -29.5%（2022 就鎖死）。三組方向相反，同一套路由+濾網無法全體適用，仍遜方案二/三。詳見 `回測_方案二_每月換股_三組.md`、`每月選股明細_三組.md`。

## 2026-09-05 · 查詢 VM 實盤 3653 買入紀錄（logs/performance.csv）

- 依使用者要求連 VM 查「實盤 3653（健策）買入時間與價格」。**VM 連線方式**：gcloud 授權後用可寫 config（`CLOUDSDK_CONFIG` → 複製 `~/.config/gcloud`）；但 `/etc/ssh/ssh_config.d/` 唯讀權限擋住 `gcloud compute ssh`，改用**原生 ssh 直連**：`ssh -i ~/.ssh/google_compute_engine -F /dev/null -o GCPStrictHostKeyChecking=no frank@35.194.221.238`（VM 外部 IP 35.194.221.238、zone asia-east1-b、user frank、金鑰 google_compute_engine）。
- **3653 實盤買入（VM `/home/frank/tw-autotrader/logs/performance.csv`）**：2026-08-06 17股@4,255｜2026-09-01 15股@6,075 + 1股@5,975 + 1股@5,875＝共 **34 股、總成本 175,310、均價 5,156**。與 GitHub Pages 實盤儀表板（3653 34股/均價5,156/最後買進日2026-09-01/未實現+8.9%）一致。
- 3653 屬全輪替（Group1 排程 A，`.env` PC_3653 keep_wait alloc 16.7%）；首買 8/06、9/01 加碼，均價由 4,255（8/06 snap）拉高至 5,156。儀表板「3653 buys:4」= 此 4 筆。

## 2026-09-04 · 權值年入場調節（BREADTH_GATE）已 revert 移除

- 依使用者決定「權值年入場調節不啟用」，**完整 revert BREADTH_GATE 相關**（保留 MAX_PROFIT 與 max_profit_by_year）：
  - `scripts/stock_selector_grid.py`：`backtest_selector`/`backtest_dual_quarterly` 移除 `breadth_gate`/`breadth_shrink_to`/`breadth_series` 參數與選股段集中邏輯。
  - `scripts/backtest_rotation_historical.py`：移除 `_momentum_at`/`_build_breadth_series` helper 與 `BREADTH_GATE`/`BREADTH_SHRINK_TO`/`BREADTH_DAYS` env。
  - `.env.example.txt`：移除 `BREADTH_GATE` 說明行。
- 驗證：語法 OK、`python -m unittest test.test_strategies` 4/4 過、全期回測重現 README（final NT$27,925,347、年化 44.16%、2024 -0.82%、2025 +96.87%）。
- **現行狀態**：引擎只剩 `MAX_PROFIT`（預設0/停用）與 `max_profit_by_year`（實驗參數）；`.env` 無 BREADTH_GATE。下方「權值年入場調節」條目為實驗結論保存，不再有對應可跑參數。

## 2026-09-04 · 權值年入場調節（廣度差集中 top1）：正式引擎回測結論

- 續前「找 2024 可事前區分特徵」。實測兩個方向，正式引擎（`BREADTH_GATE`/`breadth_series` 新增，預設停用；`backtest_selector`/`backtest_dual_quarterly` 加 `breadth_gate`/`breadth_shrink_to`/`breadth_series`，向後相容；`MP=0` 仍重現 README 27,925,347、unittest 過）：
  - **方向1「動能池納入權值股」→ 無效**。權值股（台積電/鴻海/聯發科等）本來就在當時前100候選池內，且常進綜合排名前列（2024-03 鴻海排第1 被選中；B-06 台積電第7、B-06大立光第3）。2024 輸給 0050 **不是池子漏了大牛股**，而是「近季動能追到段尾」的動能本質。看 2024 池內動能排名也證實：權值股常在高檔（動能+0.5）才被選入、下一季回檔被套。
  - **方向2「權值年廣度差集中 top1」→ 全期略優，但主力是 2025 單檔賭對、2024 未系統改善**。定義廣度差 = 換股日 0050 近21日動能 − 全市場(池)中位數動能（季初即可算、非前瞻）。**2024 最極端權值/廣度年**：0050 當年 +49.3%、全市場中位數僅 +5.6%、差距 **+43.7pp**（次高 2020/2019 僅 15pp）；季初廣度差 2024-02/05 達 +4.2pp、2024-03/06 +7.6pp/+6.3pp，但**僅上半年，8 月即轉負**。
  - **回測（pool100/top3/MDB30/inst15）**：GATE=0（現行）年化 44.2%｜**GATE=2% → 年化 45.8%、2024 +1.29%、2025 +101.5%、final 31.6M**｜3%→42.6%｜4%→40.4%｜5%→40.3%。**2% 較佳但疑點重**：2024 權值年集中（A-02 1503 +23.6%、A-05 2615 +5.3%）**未能系統救回**（B-06 2449 -3.6%、**B-12 3661 -16.9%** 反而單一檔撞 2025 修正更慘）；2025 的 +101% 主力來自 **B-09 集中 2344（+141%）、B-06 3665（+23%）——「單檔賭對大牛股」**，非權值年集中邏輯本身。且集中 top1 使 MDB 停輪替跳過次數暴增（A 排程 8 次 vs 現行 4 次）。
  - **教訓**：① 權值年可事前觀測（0050動能 vs 市場廣度差，2024 極端分離），但它是**上半年短暫現象**，難全年精準捕捉。②「權值年集中到單一檔」全期略贏主要來自**事後賭對單一大牛股**，仍有過度擬合/高波動(MDB頻觸發)風險。③ **不建議實盤啟用 BREADTH_GATE**（Keep 0）；真正對症權值年仍靠 0050 混合（但使用者已排除此方向）。結論沉澱。

## 2026-09-04 · 權值年偵測實驗：2024=15% 其他=0 無淨價值（證實「停利救單年傷他年」）

- 動機：2024 全輪替 -0.8%（0050 +48.8%），想找 2024 可事前區分的特徵、切 MAX_PROFIT=15% 救回。先量化 2015-2025 各年市場特徵（`0050當年漲幅 − 全市場(候選池)中位數漲幅`）：**2024 = +43.7pp 是 11 年最極端權值年/廣度差**（0050 +49.3% vs 全市場中位數僅 +5.6%），次高的是 2020/2019（15pp）；2025 亦 +37.9pp。全輪替買中小型動能股正好踩在「權值年廣度差」上 → 輸。
- 實作 `max_profit_by_year`（dict{年:比例}）：`backtest_selector`/`backtest_dual_quarterly` 加參數，當季買入日年份命中即覆寫閾值；向後相容（不傳=沿用 max_profit）。`MP=0` 仍重現 README 27,925,347、unittest 4/4 過。
- **回測結論**（pool100/top3/MDB30/inst15）｜「2024=15% 其他=0」：終值 **26,123,133**（vs 現行 27,925,347，**反而 -6.5%**），2024 由 -0.82%→**+10.61%** ✅，但 **2025 由 +96.9%→+72.5%**——提早停利改變 2024 底部資金，連帶 2025 少賺 ~23pp。**拿 2025 的 +23pp 去換 2024 的 +11pp = 淨虧**。
- 連帶傷害（隱藏成本）：「2024+2025=15% 其餘0」終值更掉到 15,689,005（+3,038%）——權值年後常接動能年，停利把落袋現金帶進隔年動能年反被砍。**「權值年才停利」不是零成本修補，會把復利鏈切斷**。
- 教訓：**單一牛市年（2024）優化 = 過度擬合**；即便用可事前觀測的「權值/廣度」特徵，切換某年停利仍以他年為代價。真正對症權值年：**全輪替+0050 各半**（吃到 0050 的權值年、全輪替的動能年），非停利。`max_profit_by_year` 保留為實驗參數（預設不啟用）。

## 2026-09-04 · 新增 MAX_PROFIT 提前獲利出場參數（回測實測：啟用會毀掉動能）

- 依使用者要求加 `MAX_PROFIT`（提前停利，0=停用）：持股達 `buy_px*(1+MAX_PROFIT%)` 即當日賣出、不等季末。改 `scripts/stock_selector_grid.py`（`backtest_selector`/`backtest_dual_quarterly` 加 `max_profit`，舊呼叫皆帶預設值向後相容）+ `scripts/backtest_rotation_historical.py` 讀 `MAX_PROFIT` env + `.env.example.txt` 說明（建議保持 0）。
- 引擎早賣正確處理：早賣股從 `current_holdings`/`last_shares` 移除避免重複評價；**修了最後季評價 bug**——`is_last` 分支原本從 0 重算，早賣清空持倉時會把終值誤判歸零（曾見 2025-12-31 -100%），改用 `capital`（上一非末季已存最後交易日價值）；`MAX_PROFIT=0` 重現 README 27,925,347 / 2024 -0.82%，無回歸；`python -m unittest test.test_strategies` 4/4 過。
- **回測結論（2015-2025 全期，pool100/top3/MDB30/inst15 定案參數）**：`MAX_PROFIT=0` 年化 **44.2%**（+5,485%）｜10% **8.8%**｜15% **12.2%**｜25% **16.0%**｜40% **17.4%**——**啟用即重挫**。原因：全輪替骨子裡是動能策略，「讓贏家跑完波段」才賺錢；+15% 就停利 = 砍在起漲點，讓 2016(+72%→+17%)/2020(+116%→+68%)/2021(+170%→+31%)/2023(+80%→+36%)/2025(+97%→+6%) 全被砍掉。2024 單年確實由 -0.82% 轉正（+10.6%），但以長期為代價——**用單一牛市年優化 = 過度擬合，不建議**。
- 評估：`MAX_PROFIT` 為新增可選參數（預設 0/停用，不改變現行）。真正對症「權值年」靠「全輪替+0050 各半」混合配置，非停利。

## 2026-09-04 · 重新驗證方案三 2015 年獲益（=READM -5.1%）

- 依使用者要求用 README 方案三定案參數重跑（pool100/top3/MW2.0/SW0.5/MAF1/MP5/INST_CONFIRM=1 15d/MIN_DRAW_BACK=30）：**2015-2025 全期跑 → yearly["2015"]=-0.0511（-5.11%）**，與 README 表格 -5.1% 一致；0050 該年 -0.0615（-6.2%），皆吻合。回測前 `verify_cache.py` 6/6 通過。
- **陷阱**：單獨跑 `backtest_rotation_historical.py 2015-01-01 2015-12-31` → **-4.35%**，不等於 README。原因：`backtest_selector` 把「回測範圍最後一季」當只評價不買賣（is_last 分支），單年跑時 2015-11/12 被截斷不換股（報酬 +0.0、持倉停在前值、B 排程未轉新持股）；全期跑 2015 是序列中段會正常交易至 2016，才是正確全年數字。
- **結論**：要取 README 對應的 2015 年值，必須跑**全期窗口**看 `yearly[2015]`；不建議直接跑 2015 單年窗口（會漏最末季真實報酬）。指標：全期 final NT$27,925,347、+54.85、年化 44.16%、Sharpe 1.31、MDD -52.19%、skipped 4 次——皆與 READM 定案一致。

## 2026-09-03 · 新增 DSH入門.md（plan + goal + LOG 工作流）

- 依使用者要求，`DSH入門.md` 以 tw-autotrader 為例，說明 DSH 的「規劃→追蹤→續跑」怎麼跑：**Plan 模式**（`exit_plan_mode`，一次性任務先核准再執行）、**Goal**（`create_goal`/`update_goal`，長期目標跨回合＋`resume` 重新武裝）、**LOG**（`cairn/LOG.md` 時間序進度沉澱，≤20行/摘要+指標/指向專題）。
- 含綜合工作流範例（評估並調整配股）與務實提醒（plan 用短任務、goal 用 session 內、持久記憶靠檔案、deploy 人工）。

## 2026-09-03 · ponytail 家族裝為 user 級 DSH skill（全域）

- `npx skills add MengYuil/dsh-ponytail` 失敗（repo 結構不符 Skills CLI，No valid skills found）→ 改複製**本機 ponytail** 到 `~/.agents/skills/`：`cp -r ~/ponytail/skills/ponytail* ~/.agents/skills/`。
- 結果：ponytail(+audit/debt/gain/help/review) 共 6 個成為 **user 級 DSH skill**，本機**任何目錄**皆載入（catalog 已見）。
- 用途：懶人資深工程師/YAGNI/最小化寫碼；觸發 `ponytail`/`lazy`/`yagni`，或 `/ponytail-review`(過度工程)、`/ponytail-audit`(全 repo)、`/ponytail-debt`(ponytail: 註解債單)、`/ponytail-gain`(省多少)。
- 來源：原 `DietrichGebert/ponytail`(MIT)；本機 `/home/frank/ponytail/` 為私有工作目錄。已記於 `cairn/CURRENT.md`「可用 skill」。

## 2026-09-03 · WSL恢復.md：opencode → DSH 轉換

- 依使用者指示，把 `WSL恢復.md` 的 AI agent 設定由 opencode 改成 DSH（DeepSeek Harness）：
  - API Key 備份：`~/.local/share/opencode/auth.json` → `~/.dsh/.credentials.yaml`（`refs.DEEPSEEK_API_KEY`）。
  - 買家需準備表、還原後檢查/設定 provider 全部改為 DSH；**經使用者確認：重設 API Key 一律建議「於 DSH 設定(Settings)→憑證 重新輸入」，不採手動建 `.credentials.yaml`**。
- 提醒：DSH 憑證檔若 mode 有 group/other 讀 bit，DSH **拒絕啟動**（須 `chmod 600`）；刪檔不會自動重建帶內容的檔，須重設（見本 session 對 credentials-local 的確認）。

## 2026-09-03 · finmind 存取常駐化 + K線 HTML 實作

- 新增 `cairn/finmind-access.md`（FinMind 資料存取專題）：API 端點、dataset 對照、token=`.env` FINMIND_API_TOKEN（注意 skill 原文是 $FINMIND_TOKEN）、錯誤處理、中文繪圖字型、查詢範例。
- **陷阱（lesson）**：`TaiwanStockPrice` 欄位用 `max`(高)/`min`(低)/`Trading_Volume`(量)，非 high/low/volume（2026-09-03 實測死在這一欄）。
- `AGENTS.md` 導覽加「台股/FinMind 資料查詢 → 先讀 finmind-access.md」（自動注入，跨 session 免提醒）。
- 實作示例：`_gen_kline.py` 抓 2884 玉山金 近一年(265筆/2025-08-04~09-03/收盤43.2) K線 → `img/2884_玉山金_1y_kline.html`（ECharts 蠟燭+MA5/10/20+成交量）。

## 2026-09-03 · 沉澱：版本庫結構 + plans 子模組（明文源碼位置）

- 新增 `cairn/repo-layout.md`：repo（dinchentech/tw-autotrader, main）、唯一 submodule=`plans`（dinchentech/plans，**私有不公開**）、**明文主程式源碼在 `plans/live_trader_multi.py`**、root=可部署版（源碼或混淆）、三層 split（plans/root/TMP）、機密 gitignore（.env/backups/esun_sdk *.p12/*.whl/*.ini/*.pem/*.key/capital.txt）、快取條件上 git（bt_price/inst_history/20*/twse_inst_*/selector_prices/ 上；price/ 排除 → backtest-data-pitfalls）、node_modules 誤追蹤 gotcha。
- `AGENTS.md` 加導覽「版本庫/源碼位置/結構 → 先讀 repo-layout.md」。

## 2026-09-03 · CURRENT.md 再校正：本機跑 + 過渡超額現況（配股驗證）

- 啟動 log（v3.29，本機 DESKTOP WSL）驗證 `.env` 配股正確生效：2884 玉山金(7%=8.4萬, ma_cross 新)、3008(5%, 8股)、6805(7%, 30股)，其餘上限金額全數相符；10 檔初始化成功、Group2 關閉。
- 更新 `cairn/CURRENT.md`：環境邊界補「本機 vs GCP VM」；配股現況改為「目標（90.7%/現金9.3%）vs 現況（固定40.7%+排程A 65.1% ≈ 105.8% 過渡超額）」。
- 觀察：過渡期排程 A（3017/3653/2059 = 26.7/16.7/21.7%）仍超額，`ROTATE_CAPITAL_PCT=50` 將於 9 月底排程 B、11 月底排程 A 覆寫回 25%。

## 2026-09-03 · plans/ 定位確認：主程式源碼的私有存放處

- 使用者確認：`plans/` = **主程式源碼存放處、私有不公開**。核查：`plans/` 是 git submodule → `git@github.com:dinchentech/plans.git`（SSH private）；`plans/live_trader_multi.py` 為源碼（~981 行/56KB，與 root 源碼同 size）。
- 更新 `cairn/deploy-pipeline.md` 角色對照表：plans 行註明「私有 submodule、主程式源碼、不公開」+ 補一句 plans 定位（deploy 備份 + push 到此私有 repo）。
- 判別：**root = 混淆版/部署用版本；plans = 源碼（私有不公開）**；機密源碼以 plans 為準（見環境/部署）。root live_trader_multi.py 目前為源碼（981 行）＝上次 deploy 有正常還原。

## 2026-09-03 · deploy 使用路徑定案（現況/未來/使用者三分法）

- 使用者明示 deploy 長期使用路徑 → 更新 `cairn/deploy-pipeline.md`（一句話+對照表「何時用」欄）：
  - **現況**：無加密 license → 用 `deploy_source.sh`（C 方案、不加密）。
  - **未來（購入 pyarmor license）**：改以 `deploy.sh` 加密版為主。
  - **一般使用者**：未買主程式源碼 → 用 `deploy_crypted.sh`（只有加密檔）。校正檔名為 `deploy_crypted.sh`（非 `deploy_scrypted.sh`）。

## 2026-09-03 · 沉澱：三個 deploy 腳本對照（常用）

- 讀懂 `deploy.sh` / `deploy_source.sh` / `deploy_crypted.sh` 三腳本，沉澱到 `cairn/deploy-pipeline.md`：
  - 新增「三個 deploy 腳本對照」表 + 共同點/主要差異（加密輸入=plans、上傳途徑 GCS vs scp、結束時 root 狀態、deploy_crypted 用 set -e）。
  - 更新「一句話」：**目前預設 = deploy_source.sh（C 方案、不加密）**；deploy.sh=加密版（無license、8.x trial 過期）；deploy_crypted.sh=只有加密檔無源碼者。
- 反覆出現的判別：root=混淆版(3行/179KB) = 上次 deploy 被硬殺、EXIT trap 沒還原 → `cp plans/live_trader_multi.py live_trader_multi.py`。

## 2026-09-03 · 配股調整（第三節建議 #1/#3/#4/#5，使用者核准）

- **新增 2884 玉山金（金融/防禦腿）**：ma_cross（金融股波動低、用趨勢策略）、alloc 7%=NT$84,000。動機：資金輪動至金融避險、降beta+搭輪動。
- **3008/6805 降高價部位**：3008 alloc 12.5%→5%、buy_shares 14→8；6805 alloc 12.5%→7%、buy_shares 42→30（各自 < alloc 上限）。控高檔高價股回撤風險。
- **留現金緩衝**：固定腿 40.7%(488,400) + 全輪替 50%(600,000) = 90.7% → 現金約 NT$111,600(9.3%)。
- **註解對齊**：#5 修正 .env 全輪替「4檔×12.5」vs 實際 3 檔 26.7/16.7/21.7、2360 過時基準(1000000→1200000)。
- #2（選股日資金估算 v3.25）：`estimate_rotation_capital` 已存在（core/live_notifications.py + live_trader/plans 接線），runtime 觀察 9 月底排程 B 的 TG 資金估算。

## 2026-09-03 · 部署安全硬規則（deploy 一律手動、勿自動代跑）

- 補 AGENTS.md「部署安全規則（硬規則）」+ 歸納到 cairn（deploy-pipeline.md 已有鐵則）：**任何 agent 不得代跑 ./deploy.sh / deploy_source.sh / docker compose 於 VM 重啟**；職責止於改 plans 源碼→跑測試→更新 cairn→告知「請人工執行 deploy」（2026-08-31 使用者明示）。

## 2026-09-03 · 對話語言定案：回覆一律繁體中文

- 補一筆規則到 AGENTS.md「文件協作規則」：**對話回覆一律使用繁體中文**（除非使用者指定其他語言）；並明訂 `cairn/.cairn/config.yaml` 的 `language: zh` = 繁體中文，與專案文件（cairn/、使用手冊、策略說明）一致。
- 動機：之前「回繁體中文」只是跟隨慣例（使用者語氣 + 專案文件皆繁體），未寫成規則；本筆讓不同 session／agent 都明確遵守，非靠猜。

## 2026-09-03 · session 引導：新增 CURRENT.md + AGENTS.md STEP 0

- 新增 `cairn/CURRENT.md`（session 引導索引）：環境邊界（本目錄=模擬資金、真錢=real key 另開分支）、目前焦點、近期決策、配股現況（TOTAL_CAPITAL=120萬、輪替50%/固定46.7%集中AI硬體）、「我該怎麼讀」。
- AGENTS.md 閱讀順序前加 **STEP 0 硬規則**：任一 session 第一步先讀 `cairn/CURRENT.md`；不存在則改讀 LOG 最新 + ROADMAP。
- 目的：讓每個 session 自動先讀輕量現況索引取得方向，大文件（使用手冊/策略說明）仍依任務 grep（勿全文載入）。

## 2026-09-03 · 環境邊界術語精修：「實盤」=玉山 API 實際執行，資金另看 key

- 修正（原地修 `cairn/environment-scope.md`，非覆寫舊結論）：把「實盤」定義再精確——**兩個軸**：① 執行模式（回測 vs **實盤**=用玉山 API 的實際執行結果）；② 資金性質（玉山**模擬** key=模擬資金、real key=真金=另開分支）。
- 前版本誤把「實盤」講成「非指真錢」（語意混淆）；正確：**「實盤」指用玉山 API 實際執行，不代表就是真錢**；要不要錢看 `.env` 的 `ESUN_ENVIRONMENT`（simulation／real）。
- 結論不變：本目錄（`ESUN_ENVIRONMENT=simulation`）跑實盤路徑 × 模擬資金，無真金；真錢日後另起分支用玉山 real key。

## 2026-09-03 · 環境邊界定案：本目錄只跑模擬、真錢另開分支

- 定義：本 repo（root，`/home/frank/tw-autotrader`）**永遠只跑 E.Sun 模擬**（`ESUN_ENVIRONMENT=simulation`，模擬 API 沙箱、無真金）。軟體走「實盤流程」（`live_trader_multi.py` 完整管線：風控/通知/選股/下單），但 broker 後端是模擬 → 下單不觸及真錢。
- 決策（使用者）：真錢日後**另開分支**執行；本目錄只當沙箱/驗證場。
- 影響：① 本目錄所有讀數（績效/損益/回撤/監控）都是**模擬**結果，勿當真錢績效或投資依據；② cairn/LOG 中「實盤」=「實盤後端流程」之意，非指真錢；③ deploy 到 VM 與資本操作皆為模擬資金，真錢架構待分支落地才成立。
- 詳見：`cairn/environment-scope.md`（新增 topic，`related`: deploy-pipeline / capital-ops）。

## 2026-09-03 · 法人動能關閉（啟用數小時後即關）

- 啟用 30 萬試跑後即發現：帳戶現金僅 ~24 萬（Group1 持股 ~96 萬），Group2 虛擬資金池無實體支撐；且 TOTAL_CAPITAL 是 Group1 基準，加碼會放大 Group1 補買吃光資金（無法用加碼解決）。
- 決策：INST_MOM_CAPITAL 回 0 關閉，**專心觀察 Group 1**（全輪替 + 固定策略）。TG「法人動能篩選」通知仍會發（IM_DEBUG=1）但僅供參考不下單。

## 2026-09-03 · 法人動能 Group 2 啟用（30 萬試跑）

- 使用者要求開啟法人動能（原計畫 50 萬）→ 資金分析：帳戶現金 ~24 萬（Group1 持股 ~96 萬 + 誤賣回籠 19 萬），Group2 50 萬虛擬資金無實體支撐會下單失敗 → 採方案 2：INST_MOM_CAPITAL=300000（每檔 10 萬 × 3 檔）。
- 背景：5880/5876 入選 TG 通知（score 37.37%/21.61% = 法人淨買超佔成交量比）；5880 現價 26.7 離法人累積成本 25.14 僅 +6.2%（≤15% 安全線內）；金融股板塊行情（升息預期 NIM + 地緣避險 + 法說股利利多），第一金/華南/兆豐創歷史新高、合庫相對落後。
- 注意：Group2 虛擬帳本與 Group1 同帳戶真錢，無可用資金檢查 → 若同時進場可能資金不足；法人動能長期績效仍不如全輪替，僅小額對照觀察。
- 資金決策：曾試 TOTAL_CAPITAL 120→150 萬給 Group2 實體支撐 → 發現衝突：TOTAL_CAPITAL 是 Group1 配置基準（target=CAPITAL×alloc），放大會讓全部標的自動補買吃光新資金 → **回退 120 萬**。Group 2 用帳戶既有現金（~24 萬，實際只能建 2 檔）。

## 2026-09-03 · 2454 策略轉 VWAP

- VWAP 適合度掃描（近 2 年日K、買訊後 20 日，本地快取）：2454 聯發科最佳 — 買訊 60 次、20 日平均 +18.1%/中位 +8.9%、勝率 65%、波動率 51% 適中。6805 勝率 72% 次之（但 breakout 中、波動 64% 偏高）。
- 決定：PC_2454 bollinger → vwap（sigma_mult 1.5 / rsi 5/30/70，alloc 6.7%=80,400 維持）。2454 空倉（9/3 分鐘污染誤賣後）轉換零成本。
- 高價股特性：法人定價效率高 → 偏離 VWAP 回歸力強，適合均值回歸。

## 2026-09-03 · 方案 B 補買未更新分帳本修正（v3.29）

- Bug：方案 B 買入補足只做 log_trade + save_holdings，未更新 stock_alloc → 9/3 賣出時 avg_cost 算不出（「預估損益 +0」被 PROFIT_MARGIN 擋）、check_stock_cap 資金上限失效（可能超買）。
- 修正：新增 `core/live_utils.add_stock_allocation(stock_alloc, symbol, cost, shares)` 純函式，方案 B 補買成交後呼叫並 save_stock_allocation。
- 測試 +3（新檔建立/既有累加/空 dict 安全），全 184 tests OK。版本 3.28→3.29。plans/live_trader_multi.py 同步（core/ 在 root git 明文）。

## 2026-09-03 · 實盤訊號改日K：bollinger/vwap/ma_cross 分鐘污染修正（v3.28）

- Bug：9/2 買入 2454/6213/3189（bollinger），9/3 隔天全賣且虧損（2454: 4410→4350、6213: 549→531、3189: 848→813）。根因：主迴圈對 bollinger/vwap/ma_cross concat 1-min bars → acd = 日K+分鐘混合 → rolling(20) 變成「20 分鐘」而非「20 日」→ 訊號隔天反轉（9/2 分鐘級跌破下軌假買訊 → 9/3 分鐘級漲破上軌假賣訊）。
- 驗證：FinMind 日K 算 bollinger 三檔皆無賣訊（6213 RSI 24、3189 RSI 42），證明日K訊號正常、分鐘才是亂源；docker timestamps 顯示 SELL 在 10:10-10:19（非開盤）。
- 修正（v3.28）：除 keep_wait（signal=0、主程式管理買賣、用即時價）外，**所有策略統一改日K模式** — 初始化 get_historical_data(260)、盤中合成當日K（更新 high/low/close=現價），比照 breakout 既有作法。涵蓋 bollinger/vwap/ma_cross/user_strategies（未來啟用 g1/g2 不再踩坑）。熱重載同步。
- 另發現：方案 B 買入未更新 stock_alloc（只 log_trade）→ 成本/損益計算失真（9/3「預估損益 +0」即因此）；待修。
- SIGNAL_DEBUG env 診斷 log 保留（驗證用，之後移除）。測試 181 全綠。版本 3.27→3.28。

## 2026-09-02 · 方案 B 補足修正：空倉不建倉、等策略訊號（v3.27）

- Bug：方案 B 補足邏輯 `_need = _target - held` 在 held=0 時 `_need = _target > 0` → 空倉標的也被直接建倉（9/2 實盤 2454 空倉被補買 18 股）。方案 B 本意是「補足已持有但程式錯誤/未買足的倉位」，空倉應等策略訊號。
- 修正：新增 `core/live_utils.calc_topup_need(held, target, buy_offset, market_open)` — held<=0 或 target<=0 或盤外或已足額 → 0（不補）；僅「有持股且 < 目標×(1-offset)」→ 補差額。live_trader_multi.py 補足區塊改用此函式。
- 測試 +5（空倉不補/有持股補足/足額不補/盤外不補/目標0安全），全 181 tests OK。版本 3.26→3.27。plans 同步。

## 2026-09-01 · README 實盤測試加註：未實現損益依首次買入價差

- 使用者質疑儀表板 3653「9/1 剛買就 +14.13%」— 查 VM performance.csv：3653 於 8/6 以 4,255 首購 17 股、9/1 補足至 34 股（平均成本 5,156）→ 報酬率反映 8/6 以來累計漲幅，非當日買入即獲利。
- README 實盤測試段加 📌 附註：未實現損益/報酬率依「首次買入平均成本」與市價價差計算，非最近買進價差；看高報酬率時先對照最後買進日判斷。

## 2026-09-01 · 使用手冊/策略說明：全輪替持有期間勿重複建倉提醒

- 提醒使用者：全輪替已持有、尚未輪替掉的股票，不要用其他策略（bollinger/vwap/ma_cross/keep_wait）重複持有同一支 — 撞股時程式會通知+跳過（策略額度白佔、資金配置不符），且與回測乾淨分離模型不一致；等換股日賣出後其他策略才可接手。全輪替自身撞股由程式自動處理。
- 位置：策略說明 §跨策略選股重疊的處理 後、使用手冊 §全輪替自動化 一句話說明後。

## 2026-09-01 · 使用手冊：實盤無獲利自動滾入警示（§5.8）

- 確認落差：回測（simulate_portfolio / 全輪替回測）有獲利自動滾入本金（records[i-1].value 當下季本金，複利）；實盤 live_trader_multi.py 的 TOTAL_CAPITAL 固定讀 .env，獲利不會自動增加 → 買入額度永遠按原 TOTAL_CAPITAL。
- 實盤僅有的加碼管道：capital.txt（每日檢查、TG 通知、依 alloc 加碼 keep_wait 70%）；ekwr() 獲利滾入加碼只對「非全輪替 keep_wait」觸發（現有 keep_wait 全為全輪替 → 走清倉路徑不觸發）。
- 使用手冊 §5.8 加 🔴 實盤警示（建議每季換股日後把盈餘記入 capital.txt）+ §1.5 補對照連結。回測數字（+5,485% 等）含複利，實盤不手動加碼則為固定本金、績效低於回測。

## 2026-09-01 · ROTATE_CAPITAL_PCT 資金佔比參數（v3.26）

- 問題：ROTATE_MODE=5 雙排程下每排程固定 50% → 全輪替吃光 100% 資金，固定策略（breakout/bollinger/ma_cross）排後買不到（6805/2454/2360 長期未進場，總配置 111.8% 超額）。
- 新增 `ROTATE_CAPITAL_PCT`（預設 50）：全輪替總資金佔 TOTAL_CAPITAL 比例。alloc = PCT ÷ 排程數(雙=2/單=1) ÷ top_n → 預設下每檔 8.33%、各排程 25%。
- 相容性：PCT=100 完全等於舊行為（雙排程 50/top_n、單排程 100/top_n）；`core/rotate_scheduler.calc_rotation_alloc()` 為純函式（5 測試）。選股程式兩處輸出（1188/1590）改用它。
- 現況影響：下次選股日（9 月底排程 B）起新 alloc 生效；現有排程 A 手動 26.7/16.7/21.7 待 11 月底覆寫。9 月底排程 B 需求從 60 萬降到 30 萬 → 解決資金不足。
- 測試 +5，全 176 tests OK。使用手冊/策略說明/.env 同步。版本 3.25→3.26。

## 2026-09-01 · 選股日 TG 通知資金預估（v3.25）

- 需求：全輪替選股日選好股後，TG 通知使用者「新配置所需資金」及「目前資金是否足夠」。
- 實作：`core/live_notifications.estimate_rotation_capital(pc_lines, total_capital, stock_alloc)` 回傳 need（新選檔 alloc×TOTAL_CAPITAL 總和）/ available（TOTAL_CAPITAL−已投入）/ released（非新選清單內持股成本=次日清倉回籠）/ sufficient / shortfall；live_trader_multi.py 選股完成通知改為多行（✅資金足夠 或 ⚠️資金不足+短少金額）。
- ⚠️ 順序陷阱：資金估算必須在 v3.5 重置分帳本之前（否則 stock_alloc 全 0 → available 虛高、released 錯 0）；已用註解標示。
- 測試 +5（足夠/回籠補足/不足含短少/續抱不計回籠/空清單），全 171 tests OK。版本 3.24→3.25。

## 2026-09-01 · 全輪替選入標的移除其他策略監控條目（v3.24）

- 需求：其他策略「僅監控未持有」（有 PC_ 條目但 holdings=0）的股票被全輪替選入時 → 自動移除該監控條目 + TG 通知使用者；「已持有」維持現況（買入端 should_skip_rotation_overlap 通知+跳過，不重複建倉）。
- 實作：`core/rotate_scheduler.remove_monitored_only_entries(env_path, selected_symbols, holdings)` — 移除「非全輪替管理」（strategy != keep_wait 或 max_entry_price != -1）且 holdings=0 的 PC_ 條目，回傳 [(sym, 原條目)]；live_trader_multi.py 選股完成後呼叫並逐檔 TG 通知被移除的策略名。
- 判定基準：全輪替管理條目特徵 = keep_wait + max_entry_price=-1 → 不會被誤刪（撞股由 config_loader alloc 加倍處理）；非 keep_wait 策略（breakout/ma_cross/bollinger 等）即使放在排程區段內也會被正確移除。
- 測試 +3（僅監控移除/已持有保留/無條目不變），全 166 tests OK。版本 3.23→3.24。

## 2026-09-01 · bollinger/vwap/ma_cross 買入與回測對齊 + BUY_AMOUNT_OFFSET 補足機制

- 問題：實盤用 position_amount（預設 2500 元 → 只買 2-4 股），回測 simulate_portfolio 用 bucket 全額買入且滿倉不買 → 實盤行為 ≠ 回測績效。
- 修正：bollinger/vwap/ma_cross 買入量改為 alloc×TOTAL_CAPITAL（一次買足）；滿倉判定 held ≥ target×(1-BUY_AMOUNT_OFFSET=0.02)；賣出全賣；金字塔移除（keep_wait 專用，回測無）。position_amount 廢除。
- 新增 BUY_AMOUNT_OFFSET（預設 0.02）：**方案 B 主動補足** — 每日盤中（09:00-13:30）檢查持倉 < 目標×(1-offset) 即自動補買到目標（不看策略訊號，因回測假設全額成交）；逾 3 交易日仍未滿 → TG 通知（每日一次去重，core/live_utils.check_buy_fill_shortfall）。補買僅盤中執行避免盤後下單失敗。
- 測試 +5（足額/不足/3日內/去重/安全），全 163 tests OK。.env/.env.example/使用手冊/策略說明同步。


## 2026-09-01 · bollinger 買太少根因：position_amount 未設定（預設 2,500 元）

- 現象：6213 買 4 股（2,200 元）、3189 買 2 股（1,748 元），與 alloc 5%（6 萬）差太多。
- 根因：bollinger/vwap/ma_cross 的買入金額走 `position_amount`（預設 2,500），**不看 alloc**；PC_2454/3189/6213 未設 → 每次只買 2,500 元。
- 修復：三檔加 `position_amount`（2454=80400、3189=60000、6213=60000，對應 alloc×TOTAL_CAPITAL）。.env.example 加警告註解。
- 教訓：bollinger 買入金額由 position_amount 決定（非 alloc），新增 bollinger 標的必須同時設定。


## 2026-09-01 · 全輪替換股不計入每日交易次數 + 風險攔截通知去重（v3.21）

- 3008 breakout 被攔截根因：全輪替 4 賣 4 買吃掉 MAX_DAILY_TRADES=5 額度 → 一般策略無額度。
- 修復：`risk_manager.log_trade` 加 `exclude_from_daily` 參數（CSV 記 `exclude_daily` 欄位），`_load_today_trades` 排除；主程式 4 處接線（全輪替換股 `_rot_buy`/清倉/trim/資本注入不計額度）。MAX_DAILY_TRADES 5→10。
- 通知去重：風險控管攔截 TG 改每日每檔一次（`_risk_notified` dict，仿 `_order_fail_notified` 模式）— 不再每分鐘洗版。
- 版本統一 3.20→3.21（root 與 plans 首行曾漂移不一致，已對齊）。158 tests OK。需 deploy。

## 2026-08-31 · 加碼 20 萬投入布林通道（Group 1 比例制）

- 需求：TOTAL 100萬→120萬，20萬佈局布林通道（上一個布林前100回測的穩健檔）。
- 新增：PC_2454 聯發科（alloc 6.7=8萬）、PC_3189 景碩（5=6萬）、PC_6213 聯茂（5=6萬）；策略 bollinger 全參數（20/2.0/5/30/70，即 strategies/bollinger.py 實盤版）。
- 決策：維持比例制（A案）— 舊標的上限等比放大 20% 屬設計特性，由訊號+check_stock_cap+現金三重約束；總 alloc 111.8% 僅為理論上限。
- 布林三檔目前皆無買訊號（需跌破下軌+RSI<30），系統等訊號進場。
- ⚠️ 未部署：本地 .env 已改，VM 待人工 ./deploy_source.sh 同步（鐵則：AI 不代跑）。


## 2026-08-31 · 市值前100布林通道回測分析（外部資料層驗證 + 新陷阱）

- 任務：近3年（2023-09-01~2026-08-31）市值前100大公司、每檔10萬、布林通道策略、獲利最高前5。
- 市值定義：FinMind `CapitalStock`（單位＝**元**，非千元；市值＝cap×close/10）×最新收盤價，與群益權值100大（8/31）**88檔中83檔比值=1.000**交叉驗證；5檔異常（2327/6669/6415/6531/6919 股本欄位資料差）以官方值覆寫。
- ⚠️ 新陷阱：**金融股（2881等）資產負債表股本欄位是 `OrdinaryShare` 不是 `CapitalStock`**（抓 CapitalStock 會整批缺失，金控季報延遲時更要退到上一季）；兩份權威名單（群益/mcap_ranking）並集取前100最穩（邊界股如 2633 高鐵 1463億 只在一份名單）。
- 回測：FinMind 原始價、零股、次日開盤執行、手續費0.1425%+賣出證交稅0.3%；4,630筆訊號全數通過條件驗證。
- 結果（top5）：布林反轉+RSI(實盤版)：川湖+328.7%、聯茂+294.0%、緯創+213.0%、新代+187.2%、富世達+173.0%（100檔勝率81%）；經典布林(20,2)：川湖+111.0%、健策+106.3%、聯發科+93.1%、緯創+83.4%、台光電+82.4%。
- 產物：/tmp/opencode/bt_top100_universe.csv、bt_results_final.csv、bt_chart_{classic,revrsi}.png（未進 repo，回測產物）。


## 2026-08-31 · v3.20 換股日盤前現金提醒（送審，待人工 deploy）

- 需求：換股日（rotation_pending.buy_date==當日）啟動時，TG 提醒使用者預估現金需求＝Σ(max(0, 目標股數−現有持股))×現價，非全額目標。
- 實作：`core/live_notifications.send_rotation_cash_reminder()`（公式與買入端一致：target=TOTAL×alloc%、target_shares=max(1,int(target/px))）+ 主程式啟動持倉報告後呼叫（plans/root 同步）；`APP_VERSION=3.20`。
- 邊界：現價抓不到→顯示「現價未知」估算模式；非換股日/檔案缺失→靜默；超額→提示 trim；僅 keep_wait+mep=-1 輪替股計入（breakout/ma_cross 不計）；MDB=30 觸發時換股可能暫緩（訊息註記）。
- 測試：`test/test_cash_reminder.py` 7 案例；全套 **158/158 綠**（含 py_compile）。
- 待辦：使用者人工 `./deploy_source.sh`（鐵則：AI 不代跑 deploy）；部署後驗證啟動 log 出現「換股日資金提醒」與 TG 訊息。

## 2026-08-31 · 手動選股補救寫入使用手冊（10.3.1 + 自動化章節交叉引用）

- 使用手冊.md 新增「10.3.1 手動選股補救（選股日沒執行選股的救援）」：`scripts/manual_rotation_pick.py` 用法（dry-run / --sync-vm / --schedule / --force）、local→VM 流程圖、注意事項（部署順序：先 deploy 再選股；VM 買賣由 rotation_pending 驅動不依賴新版主程式）。
- 全輪替自動化章節補交叉引用：「若選股日沒收到選股完成 TG → 用 10.3.1 補救」。
- 今日實作已驗證：v3.19 部署成功 → local 選股（3017/3653/2059）→ .env + rotation_pending（buy_date=09/01）同步 VM → 明日開盤自動換股。

本檔案以倒序記錄實質進展——最新條目在最上方、緊接本行之下。每條保持精簡——只要摘要與指標；結論沉澱到 `cairn/<topic>.md`。

## 2026-09-01 · bollinger/vwap/ma_cross 買入與回測對齊 + BUY_AMOUNT_OFFSET 補足機制

- 問題：實盤用 position_amount（預設 2500 元 → 只買 2-4 股），回測 simulate_portfolio 用 bucket 全額買入且滿倉不買 → 實盤行為 ≠ 回測績效。
- 修正：bollinger/vwap/ma_cross 買入量改為 alloc×TOTAL_CAPITAL（一次買足）；滿倉判定 held ≥ target×(1-BUY_AMOUNT_OFFSET=0.02)；賣出全賣；金字塔移除（keep_wait 專用，回測無）。position_amount 廢除。
- 新增 BUY_AMOUNT_OFFSET（預設 0.02）：**方案 B 主動補足** — 每日盤中（09:00-13:30）檢查持倉 < 目標×(1-offset) 即自動補買到目標（不看策略訊號，因回測假設全額成交）；逾 3 交易日仍未滿 → TG 通知（每日一次去重，core/live_utils.check_buy_fill_shortfall）。補買僅盤中執行避免盤後下單失敗。
- 測試 +5（足額/不足/3日內/去重/安全），全 163 tests OK。.env/.env.example/使用手冊/策略說明同步。


## 2026-09-01 · bollinger 買太少根因：position_amount 未設定（預設 2,500 元）

- 現象：6213 買 4 股（2,200 元）、3189 買 2 股（1,748 元），與 alloc 5%（6 萬）差太多。
- 根因：bollinger/vwap/ma_cross 的買入金額走 `position_amount`（預設 2,500），**不看 alloc**；PC_2454/3189/6213 未設 → 每次只買 2,500 元。
- 修復：三檔加 `position_amount`（2454=80400、3189=60000、6213=60000，對應 alloc×TOTAL_CAPITAL）。.env.example 加警告註解。
- 教訓：bollinger 買入金額由 position_amount 決定（非 alloc），新增 bollinger 標的必須同時設定。


## 2026-08-31 · manual_rotation_pick.py 改為 local 執行設計（+ --sync-vm）

- 使用者要求：補救選股在 local 執行、改 local .env，明日 VM 主程式負責買賣（不必部署到 VM）。
- 更新 `scripts/manual_rotation_pick.py`：新增 `--sync-vm`（scp .env + logs/rotation_pending.json 到 VM，`--vm`/`--zone` 可指定）；未加 --sync-vm 時印出手動複製清單。
- 驗證：local `get_next_market_open` 正確（2026-08-31 → buy_date 2026-09-01）；主程式買賣由 `rotation_pending.json.buy_date` 驅動（`is_rotation_buy`），**與 v3.18 選股 bug 無關** → VM 主程式不需升級也能執行明日換股。
- MIN_DRAW_BACK 檢查：local 無 broker → fail-open 照常換股（與主程式一致）。
- scripts/README.md 補文件；151 tests 維持通過。

本檔案以倒序記錄實質進展——最新條目在最上方、緊接本行之下。每條保持精簡——只要摘要與指標；結論沉澱到 `cairn/<topic>.md`。

## 2026-09-01 · bollinger/vwap/ma_cross 買入與回測對齊 + BUY_AMOUNT_OFFSET 補足機制

- 問題：實盤用 position_amount（預設 2500 元 → 只買 2-4 股），回測 simulate_portfolio 用 bucket 全額買入且滿倉不買 → 實盤行為 ≠ 回測績效。
- 修正：bollinger/vwap/ma_cross 買入量改為 alloc×TOTAL_CAPITAL（一次買足）；滿倉判定 held ≥ target×(1-BUY_AMOUNT_OFFSET=0.02)；賣出全賣；金字塔移除（keep_wait 專用，回測無）。position_amount 廢除。
- 新增 BUY_AMOUNT_OFFSET（預設 0.02）：**方案 B 主動補足** — 每日盤中（09:00-13:30）檢查持倉 < 目標×(1-offset) 即自動補買到目標（不看策略訊號，因回測假設全額成交）；逾 3 交易日仍未滿 → TG 通知（每日一次去重，core/live_utils.check_buy_fill_shortfall）。補買僅盤中執行避免盤後下單失敗。
- 測試 +5（足額/不足/3日內/去重/安全），全 163 tests OK。.env/.env.example/使用手冊/策略說明同步。


## 2026-09-01 · bollinger 買太少根因：position_amount 未設定（預設 2,500 元）

- 現象：6213 買 4 股（2,200 元）、3189 買 2 股（1,748 元），與 alloc 5%（6 萬）差太多。
- 根因：bollinger/vwap/ma_cross 的買入金額走 `position_amount`（預設 2,500），**不看 alloc**；PC_2454/3189/6213 未設 → 每次只買 2,500 元。
- 修復：三檔加 `position_amount`（2454=80400、3189=60000、6213=60000，對應 alloc×TOTAL_CAPITAL）。.env.example 加警告註解。
- 教訓：bollinger 買入金額由 position_amount 決定（非 alloc），新增 bollinger 標的必須同時設定。


## 2026-08-31 · 手動補救選股程式 scripts/manual_rotation_pick.py

- 因 v3.18 bug（13:31 continue 擋死選股）錯過 08/31 排程 A 選股日，建立手動補救程式：`python scripts/manual_rotation_pick.py --dry-run`（預覽）/ 正式執行。
- 行為與主程式 13:31~13:35 一致：should_rotate_today 判斷（08/31 → 排程 A）→ MIN_DRAW_BACK 檢查（fail-open）→ selector → backup_env + update_env_section → rotation_pending.json 排買賣日 → 重置分帳本/預算。
- **順帶發現 selector 重複輸出 bug**：`--recommend --output-env` 在雙排程模式印兩次 PC_（1185 行單排程路徑 + 1592 行雙排程路徑）→ `run_rotation_selection` 加保序去重（6→3 條）；主程式 v3.19 內聯路徑若直接用 run_rotation_selection 也受益。
- dry-run 選出（08/31 排程 A top3）：**3017 奇鋐 / 3653 健策 / 2059 川湖**（alloc 16.7 全輪替）。
- 151 tests 通過（含新去重邏輯）。

# Project Cairn 日誌

本檔案以倒序記錄實質進展——最新條目在最上方、緊接本行之下。每條保持精簡——只要摘要與指標；結論沉澱到 `cairn/<topic>.md`。

## 2026-09-01 · bollinger/vwap/ma_cross 買入與回測對齊 + BUY_AMOUNT_OFFSET 補足機制

- 問題：實盤用 position_amount（預設 2500 元 → 只買 2-4 股），回測 simulate_portfolio 用 bucket 全額買入且滿倉不買 → 實盤行為 ≠ 回測績效。
- 修正：bollinger/vwap/ma_cross 買入量改為 alloc×TOTAL_CAPITAL（一次買足）；滿倉判定 held ≥ target×(1-BUY_AMOUNT_OFFSET=0.02)；賣出全賣；金字塔移除（keep_wait 專用，回測無）。position_amount 廢除。
- 新增 BUY_AMOUNT_OFFSET（預設 0.02）：**方案 B 主動補足** — 每日盤中（09:00-13:30）檢查持倉 < 目標×(1-offset) 即自動補買到目標（不看策略訊號，因回測假設全額成交）；逾 3 交易日仍未滿 → TG 通知（每日一次去重，core/live_utils.check_buy_fill_shortfall）。補買僅盤中執行避免盤後下單失敗。
- 測試 +5（足額/不足/3日內/去重/安全），全 163 tests OK。.env/.env.example/使用手冊/策略說明同步。


## 2026-09-01 · bollinger 買太少根因：position_amount 未設定（預設 2,500 元）

- 現象：6213 買 4 股（2,200 元）、3189 買 2 股（1,748 元），與 alloc 5%（6 萬）差太多。
- 根因：bollinger/vwap/ma_cross 的買入金額走 `position_amount`（預設 2,500），**不看 alloc**；PC_2454/3189/6213 未設 → 每次只買 2,500 元。
- 修復：三檔加 `position_amount`（2454=80400、3189=60000、6213=60000，對應 alloc×TOTAL_CAPITAL）。.env.example 加警告註解。
- 教訓：bollinger 買入金額由 position_amount 決定（非 alloc），新增 bollinger 標的必須同時設定。


## 2026-08-31 · 修復重大 bug：全輪替自動選股從未執行過（v3.19）

- 使用者問「今天有選股了?」→ 查 VM：08/31（8月最後交易日=選股日）13:31-13:35 log 只有 INST_MOM DEBUG，無選股輸出；`backups/` 空、`rotation_pending.json` 從未存在 → **ROTATE_MODE=5 的自動選股自導入以來從未運作**（8/03 持倉是手動配置的）。
- **根因（控制流 bug）**：主迴圈 `if (is_weekday and (h == 13) and (m >= 31)):` 區塊內每分鐘 `run_inst_momentum → time.sleep(60) → continue`；選股邏輯（`31<=m<=35`）寫在**同層級、該區塊之後** → 13:31~13:35 被 continue 擋死，永遠不可達。v3.16 起即有此結構。
- 修復：選股區塊移入 13:31+ 區塊**內部**（run_inst_momentum 之前），`31<=m<=35` 保留。版本 3.18→3.19。
- 回歸測試：`test/test_rotation_selectable.py`（AST 驗證 13:31+ 區塊內含 should_rotate_today），全套 151 tests 通過。
- **後續影響**：因從未自動選股，8/31 的 11 月排程選股錯過——下次選股日 11/30（排程 A 2/5/8/11）將是修復後首次實盤驗證；部署 v3.19 後可考慮手動跑 `stock_selector_grid.py --recommend --output-env --schedule-label A --top-n 3` 補選。

## 2026-08-31 · 規則：所有 deploy 由人工執行（AI 不代跑）

- 使用者指示：所有 deploy（deploy.sh / deploy_source.sh / VM 重啟）一律由使用者本人執行，AI 不代跑。
- 已寫入 `cairn/deploy-pipeline.md` 開頭「鐵則」；AI 職責止於改源碼 → 測試 → cairn → 告知就緒。
- 背景：v3.18（下單失敗 TG 警示修復）準備完成後，deploy_source.sh 由使用者中止改為人工執行。

## 2026-08-31 · 修復：下單失敗（error dict）未發 TG 警示（v3.18）

- 實盤（08/31 09:00-10:36）3008 breakout 買入連敗 30+ 次（E.Sun `A00002: response parse Error`），使用者完全沒收到 TG 警示。
- **根因**：E.Sun place_order 的 A00002 是**回傳 `{"error": ...}` dict**（非拋例外）。主迴圈 `if ('error' in order_result):` 分支只有 keep_wait rollback + continue，**未呼叫 notify_order_failure**——TG 警示只覆蓋「委託未成交 `_filled<=0`」與「except Exception」兩路徑，error-dict 路徑是縫隙。
- 修復：`plans/live_trader_multi.py` error 分支第一行補 `notify_order_failure(...)`（所有策略通用，含買/賣動作標示）。版本 3.17→3.18。
- 回歸測試：新增 `test/test_order_fail_notify_branch.py`（AST 驗證 error 分支必須呼叫 notify_order_failure），先紅後綠；全套 150 tests 通過。
- 使用者觀察 ②：休眠 TG 報告其實有發（名為「睡前持倉報告」、14:00 觸發 `send_sleep_notification`），非 bug，只是名稱易混淆。
- 後續：VM 10:41 重啟後 3008 買入成功（13 股 @ 7455）；部署 v3.18 待執行。

## 2026-08-30 · Group 1 加碼 20 萬 → 3008/6805 breakout 各 10 萬；沉澱資金操作規範

- 使用者指令：加碼 20 萬、3008 大立光 / 6805 富世達用 breakout 各投 10 萬（並要求「以後手動買賣/加減資金先參考使用手冊」→ 沉澱 cairn）。
- 查閱順序：策略說明.md（PC_ 格式、全輪替非輪替區段共存 §8、breakout 參數）→ 確認後改 `.env`：`TOTAL_CAPITAL=600000→800000`、新增 `PC_3008`/`PC_6805`（breakout、alloc 12.5、buy/sell_shares 14/42）。capital.txt 僅註解記錄（# 開頭）。
- **陷阱①（關鍵）**：capital.txt 有效條目會對**每個 keep_wait 標的自動加碼**（`800000×12.5%×1.0 = 10 萬/檔`，4 檔=40 萬 > 注資 20 萬）→ 全輪替 4 檔皆 keep_wait，改走「.env 直改 + capital.txt 註解」安全路徑。
- **陷阱②**：VM `logs/processed_capital.json` = `[]`（本地含 2023-06-01）→ 兩邊狀態不一致，未來動 capital.txt 前先查 VM。
- 驗證：`load_portfolio_config()` 解析 PC_3008/6805 正確（TOTAL_CAPITAL=800000、breakout 參數入列、4 檔 keep_wait 不變）；breakout_strategy 函式 dry-run OK；VM .env/capital.txt 已同步（先備份 .bak_）。
- 新增專題 `cairn/capital-ops.md`（資金操作規範：改 .env+註解記錄、PC_ 格式、breakout 固定股數特性、上述陷阱）。
- 後續注意（2026-08-30 修正）：**breakout 訊號=當日剛創新高本身就觸發**（收盤 > 前20日高 shift(1)），非「創高後等突破」。3008/6805 在 2026-08-28 當日即符合 BUY（7,065>6,915 / 2,345>2,225，ATR≥2%）。先前的「剛創新高短期可能無訊號」為因果顛倒之誤——操作時序提醒應為「若配置時已遠離突破點，該次訊號已過，需等下次再突破」。

## 2026-08-30 · 文件回測資料全量重跑（top3/15d/MDB30 定案參數）

- 使用者要求用新參數重跑 README/策略說明中的回測資料（先前 +199.6%/N 敏感性/法人確認驗證等皆為 top4 時代）。
- 14+2 組合重跑（結果 `results/rotation_newparams_doc_rerun_2026-08-30.json`）：
  - **2022-2025**：+244.1%（NT$1,720,553；2022 +1.7% / 2023 +80.3% / 2024 -0.8% / 2025 +96.9%）
  - **N 敏感性（2015-2025 全堆疊）**：50→12.2% ｜ **100→44.2%** ｜ 150→28.2% ｜ 200→21.2% ｜ 300→17.2%
  - **法人確認驗證（top3、無 MDB）**：2018-2021 +370.1%→+593.2%（+223pp）；2022-2026 窗 **-5.5pp 微幅負貢獻**（top4 時代 +17.2pp）⚠️；11 年全窗 +2,232.1%→+3,520.2%（+1,288pp）
  - 窗口比較：2015-2021 +1,351.4% ｜ 2022-2026 +302.4%（全堆疊）
- 更新：README（方案二比較表/三方案/116 N 註記/157 註記）、策略說明（回測實證表/N 敏感性表/法人確認驗證表/11 年比較表基線列/全輪替 vs 法人動能比較）。排程影響表與選股日表為明確標註的歷史掃描，保留。
- 教訓：**法人確認濾網在 top3 下的單窗（2022-2026）效果轉負**，價值在長窗與 MDB 疊加後才顯著——文件更新時以全堆疊與全窗為準。

## 2026-08-30 · 全輪替參數 Grid Sweep（2015-2025 目前完整法人快取）：top_n=3 顯著勝出 → 實盤定案

- 動機：先前掃描（rotate_day 8/18、mindrawback 8/19、N 敏感性）皆在 2026-08-29 法人稽核前資料（2015-2017 pass-through）上跑；用目前快取重掃確認現有參數。
- 工具：`scripts/backtest_rotation_grid_sweep.py`（26 組合，單維掃描繞生產基準 N100/top4/inst15d/MDB20/預設權重；結果 `results/rotation_grid_sweep_2015_2025.csv/.json`）。基準組合精確重現稽核值（14,899,849 / +2,880% / 36.2% / 1.21 / -49.5%）。
- **確認最佳（維持現有）**：N=100（50→12.9%…300→13.9% 皆遠遜）、MA 過濾（開關差 +8~9pp）、MW=2.0、SW 0.5≈0.0、inst 15d（top3 下 15d 44.0% > 21d 38.3%）。
- **新發現 ① top_n=3 大勝（先前從未掃過）**：top3/15d/MDB20 → **NT$27.6M / +5,427% / 年化 44.0% / 夏普 1.30** vs top4 36.2%/1.21（代價 MDD -53.5% vs -49.5%）。逐年分布健康非單年驅動。top2 36.3%、top5 32.1%、top6 28.5% — top3 峰值。
- **新發現 ② MDB=30 微幅優於 20**：top3 下 44.2%/1.31（跳過 4 次、MDD -52.2%）vs 44.0%/1.30（11 次、-53.5%）；top4 下亦 36.9% vs 36.2%。
- **實盤定案（使用者核准，程式鏈驗證過）**：`.env` 更新 `ROTATE_TOP_N=3` + `MIN_DRAW_BACK=30`。驗證：`ROTATE_TOP_N`/`MIN_DRAW_BACK` 皆 env 驅動（rotate_scheduler/rotation_hold/plans 源碼 `--top-n os.getenv`）、`config_loader` 列舉式讀 PC_（撞股合併語義不變）、alloc=round(50/3,1)=16.7（捨入容差與既有 top6/8 相同）、無寫死 4 檔、149 tests OK。定案組合 = 11 年 **NT$27,925,347 / +5,485.1% / 年化 44.2% / 夏普 1.31 / MDD -52.2%**（跳過 4 次：A 2018-05/11、B 2020-03、2025-03）。README/策略說明已同步。注意：11 年 in-sample 優化本質 + top3 集中度（3 檔/排程、雙排程 6 檔）風險。

## 2026-08-29 · 隔夜滑價實測（2021-2025，152 次換股）：淨成本年化僅 0.36%

- 使用者質疑「時間滑價雙向」→ 實測：比較每次換股「選股日收盤」vs「次日開盤」。
- 買入平均 +0.526%（正 57.9%）、賣出平均 +0.437%（正 62.5%）— 動能股隔夜傾向高開（動能延續），但**買賣同日 → 部分抵消，淨滑價僅 +0.089%/季 → 年化 0.36%**。
- **推翻「7-8 折」保守估計**：實盤預期接近回測值（年化 ~49-50%，100 萬 → 360-375 萬）；剩餘風險在參數失效/系統性事件（漲停買不到等），非日常執行成本。
- 策略說明「回測 vs 實盤誠實差異」更新為實測數據（含 1000 萬內流動性 <0.1%）。

## 2026-08-29 · 全輪替流動性量化：1000 萬以內衝擊 <0.1%，折扣來自時間滑價

- 使用者問：1000 萬以內是否同樣 7-8 折？→ 量化分析（三個代表季點 2021/2023/2025 市值前 100 大日成交額：P25 1.9-3.7 億、中位數 3.7-8.3 億）。
- **1000 萬投資 = 每檔 250 萬 = 最差流動性股日成交額之 0.67-1.30% → 市場衝擊僅 ~0.05-0.1%（可忽略）**；500 萬以下更小。
- **折扣真正來源 = 時間滑價**（回測用選股日收盤價 vs 實盤次日 09:00 開盤下單 → 隔夜跳空），與金額無關 → 1000 萬以內實盤預期仍年化 30-40%。
- 資金 >3000-5000 萬（每檔 >750-1250 萬、佔日成交額 >3-5%）才需拆分下單。
- 策略說明「回測 vs 實盤誠實差異」小節更新為含流動性量化表。

## 2026-08-29 · 全輪替 2021-2025 驗證：100 萬 → 375 萬（回測），實盤預期 250-300 萬

- 使用者問：2021 投入 100 萬（獲利滾入）2025 底本利和？回測精確值 **NT$3,754,808（+650.96%、年化 49.71%、夏普 1.42）**；0050 同期僅 +120.1%。
- 手算逐年相乘（710 萬）高估 — 全輪替是雙排程（A/B 各半）獨立複利取平均，非單帳戶。
- **誠實評估**：回測用收盤價成交、假設全量成交、獲利全額再投入；實盤換股滑價（每季 4 賣 4 買 × ~1%）→ 年化降至 ~30-40%（100 萬 → 250-300 萬）— 仍遠超主動基金平均，但非無風險 50%。
- **無未來函數驗證**：逐函式稽核（trailing_ret/ma_position/volatility/catalyst/inst_net_buy/auto_momentum）皆以 `idx = get_loc(end_date)` 錨定選股日、只取 ≤ 選股日資料；搭配誠實池（歷史股本 × 當季股價）→ 無倖存者偏差 + 無前瞻雙重防護。
- 策略說明新增「回測 vs 實盤誠實差異」與「選股無未來函數驗證」兩小節。

## 2026-08-29 · 法人動能 vs 全輪替：動用成本公平比較（推翻「資金 90% 閒置」舊說）

- 使用者質疑：比較應以「持倉成本」（實際動用資金）為基準，非市值。
- 重建法人動能每日持倉成本（FIFO 攤銷，含零持倉日全樣本）：**全期平均動用 NT$471,362/年（佔本金 94%）、空手僅 46/2682 天（2%）** — 新參數（LB20/BR0.05）下交易頻繁、幾乎滿倉，**推翻舊參數時代「90% 時間資金閒置」的描述**。
- 動用成本報酬率：法人動能 588,500/471,362 ≈ **125%** vs 全輪替 ≈ **576%**（平均動用 ~250 萬、獲利 1,439.9 萬）→ **同為滿倉，全輪替每元動用成本獲利 4.6 倍**。差異在資金配置效率（全輪替每季汰弱留強、法人動能長期持有低吃標的）。
- 更新策略說明（主文+附錄 4 處）：「90% 時間資金閒置」→ 動用成本報酬率比較。結論不變：全輪替遠優於法人動能。

## 2026-08-29 · 全輪替 2015-2025 完整法人資料稽核：+3,268.7% → +2,879.97%

- 用新快取（TWSE 法人欄位動態定位、2015 起完整）重跑官方指令（N=100、15d 法人確認、MDB=20、含成本）。
- **新結果：NT$14,899,849 / +2,879.97% / 年化 36.16% / 夏普 1.21 / MDD -49.55% / 跳過換股 9 次**。
- 差異來源：舊資料法人僅 2017-12-18 後 → 2015-2017 pass-through（無法人確認）；新資料 2015-01-05 起完整 → **2015-2017 法人確認真正生效**（2016 +61.5% vs 原 +84.1%）。2018+ 逐年與 README 完全一致 → 結果更真實。
- 更新 README（主表/掃描定案/現行設定）、策略說明（4 處）、使用手冊（2 處）為稽核後值。結論不變：全輪替（+2,880%）仍遠勝 0050（+431%）與法人動能（+117.7%）。

## 2026-08-29 · 法人動能正確資料 grid 掃描：新最佳參數 LB20/BR0.05

- 背景：舊參數（LB10/FD120/BR0.08/TR20）在還原價污染假資料上調出 → 正確原始價下 2022-2026 為 -41.51%（最差組）。使用者要求用正確資料重掃。
- 工具：`scripts/inst_mom_grid_sweep.py`（16 組合 × LB{10,20}×FD{90,120}×BR{0.05,0.08}×TR{10,20}，2022-2026 窗口，結果 `results/inst_mom_grid_2022_2026.csv`）。
- **最佳：LB20/FD120/BR0.05/TR20 → +185.37%（勝率 65.2%）**；次佳 LB20/FD90/BR0.05/TR20 +139.77%。舊參數 LB10/BR0.08 為**最差** -41.51%。
- 雙窗口驗證（LB20/BR0.05）：2015-2021 +2.37%（勝率 65.4%）、2015-2025 +117.70%（勝率 65.3%、回撤 34%）— 三窗口勝率穩定 65% 左右，非過擬合。
- 更新：`.env`（INST_MOM_LOOKBACK=20、INST_MOM_BUY_RATIO=0.05）、策略說明、README。結論：法人動能仍不敵 0050/全輪替，但新參數從「大虧」變「打平/小賺」。
- 教訓：**參數調優必須在正確資料上做** — 假資料（還原價污染）調出的「最佳參數」在真實資料下可能恰好是最差。

## 2026-08-28 · TWSE 反爬 428 容錯 + 法人動能真實數字（勝率 100% 假象揭穿）

- 使用者質疑 2015-2021 勝率 100% → 查證為假象：TWSE 法人快取僅 44 天（2020-09~12），2015-2019 零法人 → 只交易 2020-10 後 8 個月 5 筆（全獲利）→ 勝率 100%。
- 根因：`fetch_twse_inst_bulk` 逐日抓 1712 天 → **TWSE 大量連續請求觸發反爬（428 Precondition Required / HTML 驗證頁）** → 靜默失敗（回 {}）→ 殘缺快取被載入 → 假數字。另：舊殘缺快取（8/14 建的 2015-2025 檔，僅 2017-12 後）不會自動重建。
- 修復：① `fetch_twse_day` 偵測 428/非 JSON → 拋 `TwseBlockedError`（不再靜默 {}）；② `fetch_twse_inst_bulk` 單日重試 3 次 + >30% 天被封鎖 → raise；③ 回測 `fetch_twse_inst_data` 殘缺快取（<80%）→ 刪除重建；④ 回測 1b 主流程 TWSE 覆蓋 <80% → 自動 FinMind inst_history 補段。
- **法人動能真實數字（完整資料）**：2015-2021 **-11.66%**（勝率 71%、回撤 32.2%、202 筆交易）；2015-2025 **-49.91%**（勝率 59.9%、回撤 58.1%、336 筆）。之前的 +21.98% / +52.54% 皆為殘缺快取假數字。
- 合併快取：`twse_inst_2015-01-01_2021-12-31.pkl`（1667 天）、`twse_inst_2015-01-01_2025-12-31.pkl`（2637 天）= TWSE（2015 + 2017-12 後）+ FinMind inst_history（2016-01~2017-12）。測試 +4（428/HTML/bulk raise/正常 JSON），全 149 tests OK。
- 教訓：**回測數字「好得太不真實」（如勝率 100%）→ 先查資料覆蓋完整性**；TWSE 大量請求會反爬，必須偵測封鎖而非靜默失敗。

## 2026-08-28 · 重大翻案：TWSE T86 完整涵蓋 2015-2025 — 欄位格式 bug 誤導了三天

- 症狀：2015-2021 法人動能回測一度 -4.15%（假數字，快取殘缺），2015 單年卻有 44 筆交易 — 矛盾。
- 根因：`fetch_twse_day` 硬編碼 2017+ 的 19 欄索引（投信 [8]/[9]、自營避險 [15]/[16]），但 **2015-2016 是 16 欄格式**（投信 [5]/[6]、避險 [12]/[13]）→ 解析 2015 時 `row[16]` IndexError → 回 `{}` → **誤判「TWSE 無 2015 法人資料」**（8/25 起錯誤結論）→ 繞道 FinMind 補抓 → 撞 600/hr 配額 → 大量等待。
- 修復：`fetch_twse_day` 改以 API 回傳 `fields` 標題動態定位欄位（外資/投信/自營自行/自營避險），2015-2025 全部正常（實測 20150105 → 863 檔、20260825 → 1335 檔）。回測階段 1b 移除 FinMind 補段，全走 TWSE bulk（無配額）。
- **真實數字（完整資料）**：2015 單年 -18.22%（勝率 47.4%）、**2015-2021 +21.98%**（勝率 100%）、**2015-2025 +52.54%**（勝率 61.2%、回撤 40.4%）。README 舊 +49.37% 仍含還原價污染，新數字為 TWSE/FinMind 原始價。
- 快取修正：`fetch_price_history_bulk`/`fetch_inst_history_bulk` 命中改「請求範圍 ⊆ 快取範圍」（原精確等於 → 不同窗口互相覆寫，單年跑覆寫全窗口快取導致殘缺）；bt_price 已 500/500 完整（上 git）。145 tests OK。
- 教訓：外部 API「回 EMPTY」先懷疑解析器欄位格式（不同年代欄位數不同），別急著斷言資料不存在 — 已沉澱 `cairn/backtest-data-pitfalls.md`（快取共用地圖 + 回測前快取檢查順序）。

## 2026-08-26 · 全輪替重啟後誤判「其他策略持有」→ 每分鐘重複跳過通知（v3.16）

- 症狀：容器重啟後，全輪替 4 檔（2395/3653/2357/3231，皆自己的持倉）被「跨策略防重疊」誤判為其他策略持有 → 09:00-09:05 每分鐘重複發「選出 X 但 N 股由其他策略持有 → 跳過」。
- 根因：`pyramid_tracker` 重啟後為空（`{}`，未持久化）→ `should_skip_rotation_overlap` 見 holdings 有股但 tracker 無 buy_count → 誤判。
- 修復：① 全輪替分支重啟後從 holdings 恢復 tracker（buy_count=1/total_shares=existing，仿 keep_wait 既有邏輯）→ 非換股日直接 continue、換股日正常補足；② `should_skip_rotation_overlap` 增 `is_rotation_managed` 參數（全輪替管理的股票永不跳，雙保險）；呼叫端傳 True。
- 測試 +1（tracker 空但 is_rotation_managed → 不跳），全 144 tests OK；版本 3.15→3.16。需重 deploy（VM 現仍每分鐘刷通知）。

## 2026-08-26 · 法人動能回測資料稽核：README 數字為還原價 bug 產物

- 重跑雙窗 vs README：2022-2026-07 **+107.31%**（原 +103.66%，接近 ✓）；2015-2021 **-4.15%**（原 +49.37%，❌ 無法重現）。
- 根因一：TWSE T86 API 僅提供 2017-12-18 後法人資料 → 2015-2017 法人全空 → 魚過濾失效。FinMind 有完整歷史 → 新增 `fetch_inst_history_bulk` 補 2015-2017 池內股票（FinMind 免費 600/hr，遇 402 自動等待重試）。
- 根因二（更根本）：回測與實盤共用 `cache/inst_momentum/price/`，實盤短歷史（yfinance 2021-06 起）覆寫回測長歷史 → 2015-2020 無價格。且 `min_start` 的 span_ok 例外（覆蓋≥365天視為上市晚）誤放行殘缺快取。
- 根因三（README 數字虛胖的真正來源）：舊 price/ 快取混入 **yfinance 還原價**（auto_adjust=True 修正前）→ 歷史買入價被系統性調低 → 虛增報酬。2015-2021 累積 7 年除息影響巨大（1101 買入 27.55 vs 真實 37.55）；2022 窗僅 4-5 年影響小（+103.66%≈+107.31%）。
- 修復：`fetch_price_history_bulk`（FinMind 原始價）+ 回測價格快取獨立 `bt_price/`（與實盤 price/ 分離）；`_norm_price` 先 rename 再 clean（FinMind max/min → high/low KeyError）；回測階段 1b = TWSE bulk（2017-12 後）+ FinMind 補 2015-2017 池內。
- 快取上 git（2026-08-25 起）：`bt_price/` + `inst_history/` 放行 .gitignore（回測長歷史快取 0 秒載入、不耗配額）；實盤 price/、inst/ 與 VM 仍排除（.dockerignore）。
- README/策略說明/使用手冊 法人動能數字更新為稽核後值（+107.31% / -4.15%）+ 註記還原價 bug。測試 +4（inst/price history bulk、402 重試、快取命中），全 143 tests OK。

## 2026-08-25 · 跨策略選股重疊防護（v3.15）

- 規定：法人動能/全輪替選出的股票若已被持有 → TG 通知 + 跳過（不重複建倉）；**全輪替自身撞股（排程 A/B，pyramid_tracker 有 buy_count）維持補足不變**。
- 實作：`core/live_utils.skip_if_overlap_held()`（法人動能買入前檢查全域 holdings）+ `should_skip_rotation_overlap()`（全輪替買入前：僅非自身倉位才跳）。接線：`strategies/institutional_momentum.py` 買入迴圈、`live_trader_multi.py` 全輪替 max_entry_price=-1 路徑（root 明文 + plans 同步）。
- 測試 +11（test_overlap_skip.py：已持有/未持有/零股/None/tracker 判斷），全 136 tests OK。版本 3.14→3.15。策略說明新增「跨策略選股重疊的處理」。
- 安全提醒（本次提交）：**root 的 live_trader_multi.py 工作樹是明文、git 是加密版 — commit 時勿 add root 明文檔**，明文只走 plans 子模組。

## 2026-08-25 · 篩選報告「未達標前三」排除已入選股票（v3.14）

- 瑕疵：2633 同時出現在「✅ 入選」與「⚠️ 未達標前三」（near_misses 取自 all_evaluated 前三名，未排除 qualified）— 報告易誤讀。
- 修復：`_save_screening_summary` 過濾 qualified_ids；qualified 為空時備援前三不受影響（2454/3533/3030 情境保留）。
- 測試 +2，全 125 tests OK；版本 3.13→3.14（core/version.py + 兩處 live_trader_multi.py 首行）。需重 deploy。

## 2026-08-25 · TWSE 法人備援不寫個股快取 → 降級警示每天重發

- 現象：FinMind 配額 402（Requests reach the upper limit）→ 15 檔（市值後段）走 TWSE 備援，但 `get_institutional_data` 的 TWSE 分支只回傳不落盤 → 每天搜尋重試 + 降級警示每天重發。
- 修復：TWSE 備援成功時也 `_dump_cache`（與 finmind 分支一致，meta source=twse）→ 隔日命中快取、不再重試。測試 +1（TWSE 備援寫快取），全 123 tests OK。需重 deploy。
- 補充：FinMind 免費配額單日爆量（多跑幾次全池搜尋即耗盡）；快取命中後不耗配額，日常單次搜尋不受影響。

## 2026-08-25 · 實盤全池篩選靜默失敗（第二層根因）：check_date 型態未統一

- 現象：deploy c991375 後法人/價格資料正常（148/148 有法人、最新 08-25），但 near_misses 前三 score 全 0.0 — momentum check 沒真正執行。
- 根因：`check_momentum_entry` 內 `df["date"] <= check_date` — 回測/測試傳 `pd.Timestamp`（正常），**實盤傳 `date.today()`（datetime.date）** → pandas 2.2+ 對 datetime64 <= date 拋 `TypeError: Invalid comparison` → `get_candidates` 每檔 `except: continue` 吞掉 → 只剩備援排名（fish/price_return，score 0.0）。回測數字不受影響（傳 Timestamp），故 121 舊測試全綠未抓到。
- 引爆時點：VM 最近 rebuild 裝到 pandas 2.2.1（Dockerfile 未鎖版本）→ 8/24/25 實盤開始 0/0（與 TWSE 單月 bug 疊加）。
- 修復：`check_momentum_entry` 開頭 `check_date = pd.Timestamp(check_date)` 統一型態，所有呼叫端（回測/實盤）安全。測試 +1（datetime.date 傳入不拋錯），全 122 tests OK。需重 deploy。

## 2026-08-25 · 法人動能實盤全池 0/0 事故根因：TWSE 價格抓取只回單月

- 現象：法人資料正常（60 rows/股）但價格資料只有 4 筆（4/27-4/30）→ `_build_core_dataframe` 全池丟棄 → qualified/near_misses 皆 0 → 睡前報告「法人/價格資料可能異常」（連 c95717f 價格備援也列不出）。
- 根因 1：`_fetch_price_twse` 用 `strftime("%Y%m01")` 只請求 start 所在月份 — TWSE STOCK_DAY 一次只回一個月，120 天請求只拿到 4 筆殘缺資料。
- 根因 2：殘缺 4 筆被當成功寫入快取（source=twse）→ 5 天內每次搜尋都命中殘缺快取 → 持續 0/0。
- 修復：`_fetch_price_twse` 改逐月迴圈抓取合併；`get_price_data` 加新鮮度防護 — fetch 結果最新日期距 ref_date > max_stale_days 視為失敗（不採用、不寫快取）。測試 +2（跨月合併、殘缺拒絕不寫快取），全 121 tests OK。需重 deploy。
- 背景：FinMind 價格 API 18:00-19:28 間暫時失敗 fallback 到 TWSE 引爆；回測不受影響（ref_date 歷史日期新鮮度檢查照舊）。

## 2026-08-23 · 下單成交確認機制（resolve_fill）— 修正「委託成功≠成交」誤判

- 問題：place_order 回傳即視為買到 — 漲停排隊未成交、E.Sun timeout 回傳 {"error":...} 都被誤判已持有；清倉部分成交會誤刪全部持股。
- 實作：`core/live_utils.resolve_fill(broker, symbol, action, order_ret, requested)` — error dict→0、mock filled→requested、其餘走 `broker.check_fill()`（None=無法得知維持原行為）；三家 broker 加 check_fill（E.Sun 用 `get_transactions_by_date` 解析、格式不明回 None 防誤判；KGI real 未實作回 None；mock 全成交）。live 接線三處：買入(real 分支)/清倉賣出/超額 trim — 未成交→TG 警示+不計持股+每分鐘重試；部分成交→依實際股數計（清倉餘額續留隔日重試）。
- 測試 +9（resolve_fill 各分支 + E.Sun 解析/格式不明安全），全 110 tests OK。策略說明新增「成交確認機制」說明。

## 2026-08-23 · 下單失敗 TG 警示（每檔每日一次）

- 缺口：買入/清倉/trim 失敗只有 console log，無 TG 通知。
- 實作：`core/live_utils.notify_order_failure(symbol, error, notified, today_str, notify_fn, action, retry_hint)` — 每檔每日一次去重（避免每分鐘重試洗版），依買/賣動作給對應重試提示；接線三處 except（買入、清倉賣出、超額 trim）。測試 test_order_fail_notify 7 個，全 101 tests OK。
- 策略說明新增「下單失敗的處理與 TG 警示」表（情境/機率/系統行為/使用者建議）。
- 順帶修正：main() 內 daily_symbol_trades 初始化區 3 空格縮排與主體 2 空格不一致（歷史遺留，compile 隱性通過後才暴露）→ 統一 2 空格。

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

## 2026-08-23 · deploy 失敗：pyarmor trial「out of license」— 真實執行碼臨界 ~45.5KB

- 症狀：deploy.sh 加密階段 ERROR out of license（先前同檔 43-45KB 皆可）。
- 診斷：trial 限制**不是原始位元組**（48KB 註解填充可過），而是「可執行內容」（混淆後大小）— 實測臨界：vD(43,862B) 過、+1KB 執行碼 44,065B 爆；現版 46,943B 爆、瘦身後 45,473B 過（margin ~1KB）。
- 修復：live_trader_multi.py 瘦身 ~1.5KB 執行碼 — ① 兩處重複 inst-momentum 呼叫區塊 → core/live_utils.run_inst_momentum()；② 清倉/trim 賣出+成交確認 → sell_with_fill_check()；③ 5 處內聯 import → top-level。全 110 tests OK。
- ⚠️ 教訓：trial 對「真實執行碼」的額度極窄（~45.5KB 臨界），檔案只會隨功能增長 → **長期必須購買 PyArmor license** 或持續搬移邏輯到 core/ 模組（不加密、不占額度）。

## 2026-08-23 · 下單成交確認機制（resolve_fill）— 修正「委託成功≠成交」誤判

## 2026-08-24 · 修復 deploy 後 VM 崩潰（瘦身引入兩缺漏）

- 症狀：v3.13 啟動後 `NameError: name 'os' is not defined`（core/live_utils.run_inst_momentum）＋`name 'is_rotation_buy' is not defined`（買入迴圈）→ Docker 重啟迴圈。
- 根因：① core/live_utils.py 原無 `import os`（先前 helper 皆未用 os）；② 瘦身腳本的「移除內聯 import」步驟誤刪了我剛加的 top-level `from core.rotation_hold import is_rotation_buy, check_rotation_hold`。兩者皆執行期才爆，py_compile 與既有測試抓不到。
- 修復：補 `import os` + 補回 top-level import；新增回歸測試（run_inst_momentum 兩分支 + **importlib 載入 live_trader_multi 驗證 helper 皆已綁定** + live_utils 有 os），全 114 tests OK。
- 教訓：搬移 import/呼叫後必須用「實際載入模組」的回歸測試，不能只靠 py_compile。

## 2026-08-23 · deploy 失敗：pyarmor trial「out of license」— 真實執行碼臨界 ~45.5KB

## 2026-08-24 · 法人動能收盤報告「無符合標的」也要列前三名（備援排名）

- 症狀：IM_DEBUG 收盤/睡前報告只顯示「❌ 今日無符合標的」，前三名沒列出。
- 根因：VM 首次 debug 搜尋時**法人資料抓取全失敗**（json health: stocks_with_inst=0、inst_source={}；FinMind token 有設，疑限流）→ fish/momentum 全無 → all_evaluated 空 → near_misses 空 → 報告 ❌。
- 修復：`inst_strategy_core.rank_by_price_return(all_data, days=5, top_n)` — 法人資料全失敗時退回「近 5 日漲幅」前三，保證有價格資料時 near_misses 必有值；`_build_inst_screening_msg` 全空時提示資料可能異常。測試 +3（排序/短歷史/空資料），全 117 tests OK。
- 註：合格判定仍需法人資料 — 若 FinMind 限流持續，需等配額或改用 TWSE 備援。

## 2026-08-24 · 修復 deploy 後 VM 崩潰（瘦身引入兩缺漏）

## 2026-08-24 · deploy 失敗：pyarmor UTF-8 嗅探窗解碼錯誤（首 80 bytes 內 3-byte 字元跨界）

- 症狀：`ERROR 'utf-8' codec can't decode byte 0xef in position 78: unexpected end of data`（位置隨檔案偏移變動：78 / 77-78 / 55-56）。
- 根因：pyarmor 8.5.12 對檔首約 80 bytes 的嗅探窗做 UTF-8 解碼；若 3-byte CJK 字元剛好跨越窗口邊界 → 解碼失敗。使用者新增的長免責聲明（全 CJK 首行 225B）與近期改動讓某字元落在邊界。
- 修復（決定性）：**首行改為 ≥80 bytes 純 ASCII 註解**（版本/網址行）→ 嗅探窗內全是 ASCII、永不跨字元，CJK 全部推到窗後。`pyarmor gen -O /tmp/t plans/live_trader_multi.py` 通過。
- 教訓：live_trader_multi.py 檔首不要放長 CJK 行；維護時若 pyarmor 報 utf-8 decode 錯誤，檢查檔首 80 bytes 是否含跨越邊界的多字元序列（插入/移除 ASCII 可驗證）。

## 2026-08-24 · 法人動能收盤報告「無符合標的」也要列前三名（備援排名）

## 2026-08-24 · 0050 對照組改為「公平扣費版」— 管理費 + 買賣成本

- 問題：benchmark_curve 用還原價淨值直接算，未扣 0050 管理費（~0.32%/年）與買入/賣出各一次交易成本 → 0050 被高估、比較不公平。
- 修正：benchmark_curve 逐交易日扣 0.32%/年管理費 + 買入手續費 0.1425% + 賣出手續費 0.1425%/證交稅 0.1%（ETF 稅率）。
- 新數字：11 年 0050 +451.9% → **+431.4%**（年化 16.4%、夏普 0.94、MDD -34.0%）；動畫窗口（2021-08~2026-08）+257.7% → **+250.8%**（全輪替 +258.9% → 差距從 +1.2pp 變 +8.1pp）；2022-2025 +103% → +101.8%。
- 已同步：README（主表/逐年表/現行設定）、策略說明（11 年表/候選池表/結論數字）、動畫 b50 資料與總結。測試全過。

## 2026-08-25 · 法人動能「無可列舉候選」根因：法人資料缺失時整檔被丟棄

- 症狀：08-24/08-25 收盤報告「❌ 今日無符合標的（且無可列舉候選）」，連備援前三都列不出。
- 根因：`_build_core_dataframe` 在 `_get_institutional_data` 回空時直接 `return pd.DataFrame()` → all_data 全空 → 備援 rank_by_price_return（需 all_data）無從排名。VM 法人資料靜默失敗（inst_source: {}，無錯誤訊息；FinMind/TWSE 皆空），價格正常（twse 150）。
- 修復：法人缺失時**保留價格資料**、inst_buy/sell 填 0（動能/魚分會因法人全 0 判定不通過，不會誤入選）→ 備援排名有料 → 前三名必列。
- 測試 +2（法人空保留價格、正常合併不變），全 119 tests OK。待 deploy。

## 2026-08-24 · 0050 對照組改為「公平扣費版」— 管理費 + 買賣成本
