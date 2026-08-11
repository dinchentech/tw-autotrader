# 全輪替自動排程 — Work Plan

## TL;DR

> **Quick Summary**: Automate full-rotation stock selection and trading by adding an in-process scheduler to `live_trader_multi.py` that detects the 1st trading day of each rotate-month, runs `stock_selector_grid.py` to generate new `.env` entries after market close, then hot-reloads the config on the next trading day. The existing cleanup mechanism (09:00-09:05) auto-sells old stocks, and new rotation stocks get bought on Day 2.
>
> **Deliverables**:
> - `core/trading_calendar.py` — Taiwan trading day detection with holiday support
> - `core/rotate_scheduler.py` — Rotation scheduling & .env generation
> - `config/taiwan_holidays.json` — Holiday/補班日 database
> - Modified `live_trader_multi.py` — Hot-reload + post-market scheduler trigger
> - Modified `stock_selector_grid.py` — `--output-env` flag for PC_* generation
> - Modified `docker-compose.yml` — `.env` volume mount
> - Unit tests for calendar + scheduler
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 3 waves
> **Critical Path**: Task 1 → Task 4 → Task 7 → Task 8

---

## Context

### Original Request
將全輪替加入 `live_trader_multi.py` 的自動化流程：
- 每月第一個交易日自動呼叫選股程式（依 ROTATE_MODE），自動產生 `.env` 檔
- 第二個交易日主程式依新 `.env` 自動買賣全輪替股票

### Interview Summary
**Key Discussions**:
- Day 1 執行時間：盤後（13:30 收盤後）自動執行 selector + 產生新 `.env`
- Day 2 配置更新：08:40 熱重載 `.env`（不重啟程式，保留 in-memory state）
- 排程器：程式內建日期檢查（main loop 中判斷交易日）
- 台灣休市：精確版（週末 + 休市日 + 補班日）
- 測試策略：加入 unit test

**Research Findings**:
- `live_trader_multi.py` 已有 09:00-09:05 清倉機制（line 253-271）：賣出不在 PORTFOLIO_CONFIG 的舊持股 → 可以直接利用
- 全輪替模式（`max_entry_price=-1`）已在 line 312-333 實作：一次性買入、無後續操作
- `stock_selector_grid.py --recommend` 只輸出 console，不產生 `.env` 檔案 → 需新增 `--output-env`
- Docker 目前 `.env` 未 mount 為 volume → 需修改 docker-compose.yml
- `load_dotenv(override=True)` 在 module level 執行，`PORTFOLIO_CONFIG` 只建立一次 → 需加入熱重載

---

## Work Objectives

### Core Objective
在 `live_trader_multi.py` 加入全輪替自動排程：偵測每月第一個交易日 → 盤後自動選股並更新 `.env` → 次日 08:40 熱重載配置 → 自動執行清倉+新建倉。

### Concrete Deliverables
- `core/trading_calendar.py` — 台灣股市交易日曆模組
- `config/taiwan_holidays.json` — 休市日 + 補班日資料檔
- `core/rotate_scheduler.py` — 輪替排程邏輯 + `.env` 產出
- `live_trader_multi.py` — 加入熱重載 + 盤後選股觸發
- `scripts/stock_selector_grid.py` — 新增 `--output-env` 輸出模式
- `docker-compose.yml` — `.env` volume mount
- `test/test_rotate_scheduler.py` — 單元測試

### Definition of Done
- [ ] `python -m unittest test.test_rotate_scheduler` → PASS
- [ ] 模擬 1 日盤後 → `.env` 自動更新 4 檔 PC_* 條目
- [ ] 模擬 2 日 08:40 → PORTFOLIO_CONFIG 自動重建
- [ ] 模擬 2 日 09:00-09:05 → 不在新配置的舊持股被清倉
- [ ] Telegram 通知確認收到「全輪替選股完成」訊息

### Must Have
- 台灣股市交易日曆（週末 + 休市 + 補班日）
- ROTATE_MODE 0~5 全模式支援
- 雙排程（MODE 4/5）各自獨立的 `.env` 區段
- 舊 `.env` 自動備份到 `backups/.env.YYYYMMDD_HHMMSS`
- Telegram 通知：選股完成、`.env` 已更新

### Must NOT Have (Guardrails)
- ❌ 不修改非 keep_wait 策略的邏輯
- ❌ 不影響 Group 2 法人動能策略
- ❌ 不引入外部排程依賴（cron/systemd）
- ❌ 不用 `exec()` / `eval()` 處理 `.env` 內容
- ❌ 不在交易時段（09:00-13:30）執行選股或修改 `.env`
- ❌ 不覆蓋手動設定的非輪替 PC_* 條目

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES（`test/test_strategies.py` 使用 unittest）
- **Automated tests**: Tests-after（先實作，再加測試）
- **Framework**: unittest（與現有測試保持一致）
- **Test file**: `test/test_rotate_scheduler.py`

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.omo/evidence/task-{N}-{scenario-slug}.{ext}`.

- **CLI/Script**: Use Bash — run Python scripts, assert output, check exit code
- **API/Backend**: Use Bash（curl）— verify Telegram notification
- **File verification**: Use Bash — check `.env` contents, backup existence

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — ALL INDEPENDENT):
├── Task 1: core/trading_calendar.py + holidays JSON [quick]
├── Task 2: docker-compose.yml .env volume mount [quick]
└── Task 3: test/test_rotate_scheduler.py — calendar tests [quick]

Wave 2 (Core Logic — depends on Wave 1):
├── Task 4: core/rotate_scheduler.py [deep]
├── Task 5: stock_selector_grid.py --output-env flag [deep]
└── Task 6: test/test_rotate_scheduler.py — scheduler tests [quick]

Wave 3 (Integration — depends on Wave 2):
├── Task 7: live_trader_multi.py — hot-reload @ 08:40 [deep]
└── Task 8: live_trader_multi.py — post-market selector trigger @ 13:30 [deep]

Wave FINAL (Verification):
├── Task F1: Plan Compliance Audit (oracle)
├── Task F2: Code Quality Review (unspecified-high)
├── Task F3: Real Manual QA (unspecified-high)
└── Task F4: Scope Fidelity Check (deep)
```

### Dependency Matrix
- **1, 2, 3**: None — Wave 1, all independent
- **4**: 1 — depends on trading_calendar
- **5**: None — independent (but in Wave 2 for grouping)
- **6**: 4 — depends on rotate_scheduler
- **7**: 4 — depends on rotate_scheduler for should_rotate_today
- **8**: 4, 5, 7 — depends on scheduler, selector output, and hot-reload

### Agent Dispatch Summary
- **Wave 1**: 3× `quick`
- **Wave 2**: 2× `deep`, 1× `quick`
- **Wave 3**: 2× `deep`
- **FINAL**: 4 agents in parallel

---

## TODOs

- [ ] 1. `core/trading_calendar.py` — 台灣股市交易日曆模組 + `config/taiwan_holidays.json`

  **What to do**:
  - 建立 `core/trading_calendar.py`，實作 `TradingCalendar` class：
    - `is_trading_day(date: date) -> bool`：判斷是否為交易日（非週末、非休市日、是補班日則為交易日）
    - `get_nth_trading_day(year: int, month: int, n: int) -> date | None`：取得該月第 N 個交易日
    - `get_first_trading_day(year: int, month: int) -> date`：取得該月第一個交易日（封裝 get_nth_trading_day(year, month, 1)）
  - 建立 `config/taiwan_holidays.json`，結構：
    ```json
    {
      "holidays": ["2026-01-01", "2026-01-28", ...],
      "makeup_workdays": ["2026-02-14", ...]
    }
    ```
  - 預先填入 2026 年已知休市日（參考 TWSE 公告）：元旦(1/1)、春節(1/28-2/2)、和平紀念日(2/28)、兒童節/清明(4/3-4/5)、勞動節(5/1)、端午(5/31)、中秋(10/4)、國慶(10/10)
  - 補班日先留空（2026 尚無公布），結構已預留
  - Load JSON 時用 `lru_cache` 快取，避免重複讀檔

  **Must NOT do**:
  - 不要用 pip 安裝第三方日曆套件（用自家 JSON 維護即可）
  - 不要在 `is_trading_day` 中做 I/O（用 cache）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 單一檔案，邏輯單純（週末檢查 + JSON lookup），約 80 行
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1（with Tasks 2, 3）
  - **Blocks**: Task 4, 7, 8
  - **Blocked By**: None

  **References**:
  - `core/live_utils.py:11-43` — 現有 `get_next_market_open()` 函式，參考其時區處理方式（`pytz.timezone("Asia/Taipei")`）
  - 現有專案 style：無 type hints、用 datetime.date、用 `pathlib.Path`

  **Acceptance Criteria**:
  - [ ] `core/trading_calendar.py` 檔案存在且可 import
  - [ ] `is_trading_day(date(2026, 1, 1))` → `False`（元旦休市）
  - [ ] `is_trading_day(date(2026, 8, 3))` → `True`（一般週一交易日）
  - [ ] `is_trading_day(date(2026, 8, 1))` → `False`（週六）
  - [ ] `get_first_trading_day(2026, 8)` → `2026-08-03`（8/1 週六，8/2 週日，8/3 週一）
  - [ ] `get_nth_trading_day(2026, 8, 2)` → `2026-08-04`

  **QA Scenarios**:
  ```
  Scenario: 一般交易日（週一）正確判斷
    Tool: Bash
    Preconditions: taiwan_holidays.json 存在
    Steps:
      1. python -c "from datetime import date; from core.trading_calendar import TradingCalendar; tc = TradingCalendar(); print(tc.is_trading_day(date(2026, 8, 3)))"
      2. 檢查 stdout 輸出
    Expected Result: 輸出 "True"
    Failure Indicators: 輸出 "False" 或 ImportError
    Evidence: .omo/evidence/task-1-weekday-true.txt

  Scenario: 休市日（元旦）正確判斷
    Tool: Bash
    Preconditions: taiwan_holidays.json 包含 "2026-01-01"
    Steps:
      1. python -c "from datetime import date; from core.trading_calendar import TradingCalendar; tc = TradingCalendar(); print(tc.is_trading_day(date(2026, 1, 1)))"
    Expected Result: 輸出 "False"
    Evidence: .omo/evidence/task-1-holiday-false.txt
  ```

  **Commit**: YES（groups with Wave 1）
  - Message: `feat(rotate): add Taiwan trading calendar with holiday support`
  - Files: `core/trading_calendar.py`, `config/taiwan_holidays.json`

- [ ] 2. `docker-compose.yml` — `.env` volume mount

  **What to do**:
  - 在 `docker-compose.yml` 的 `volumes:` 區塊加入：
    ```yaml
    - ./.env:/app/.env:ro
    - ./backups:/app/backups
    ```
  - `.env` 設為 `:rw`（預設），讓 container 內可以寫入更新（但 host 端的 `.env` 也會被更新）
  - 實際使用 `:rw` 而非 `:ro`，因為 selector 需要在容器內更新 `.env`
  - `backups/` 目錄也 mount，確保 `.env` 備份持久化

  **Must NOT do**:
  - 不要改其他 volume mount（`logs/` 保持原樣）
  - 不要改 `env_file:` 設定

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 單行 YAML 修改
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1（with Tasks 1, 3）
  - **Blocks**: Task 8（selector 寫入 .env 需要在 container 內持久化）
  - **Blocked By**: None

  **References**:
  - `docker-compose.yml:1-16` — 現有 mount 格式，保持一致風格

  **Acceptance Criteria**:
  - [ ] `docker-compose.yml` 包含 `./.env:/app/.env:rw` 和 `./backups:/app/backups`
  - [ ] `docker compose config` 無語法錯誤
  - [ ] Container 內 `ls /app/.env` 能看到 host 的 `.env` 內容

  **QA Scenarios**:
  ```
  Scenario: docker compose config 驗證
    Tool: Bash
    Preconditions: docker-compose.yml 已修改
    Steps:
      1. docker compose config 2>&1 | head -20
    Expected Result: 無錯誤輸出，能正確解析 yaml
    Evidence: .omo/evidence/task-2-compose-config.txt

  Scenario: volumes 包含 .env mount
    Tool: Bash
    Steps:
      1. grep -A2 "volumes:" docker-compose.yml | grep ".env"
    Expected Result: 找到 `./.env:/app/.env`
    Evidence: .omo/evidence/task-2-volume-mount.txt
  ```

  **Commit**: YES（groups with Wave 1）
  - Message: `chore(docker): mount .env and backups as volumes`
  - Files: `docker-compose.yml`

- [ ] 3. `test/test_rotate_scheduler.py` — 交易日曆單元測試

  **What to do**:
  - 建立 `test/test_rotate_scheduler.py`，使用 unittest 框架
  - Test class: `TestTradingCalendar`
  - 測試案例：
    - `test_weekday_is_trading_day`：週一~週五都是交易日（非假日時）
    - `test_weekend_not_trading`：週六、週日不是交易日
    - `test_known_holiday_not_trading`：用 holiday JSON 中的已知日期驗證
    - `test_get_first_trading_day_august_2026`：8月第一個交易日是 8/3（8/1 週六、8/2 週日）
    - `test_get_nth_trading_day`：取得第 N 個交易日正確
    - `test_cache_works`：重複呼叫 is_trading_day 不重複讀檔
  - `setUp` 中載入 TradingCalendar

  **Must NOT do**:
  - 不要依賴外部 API 或網路請求
  - 不要 hardcode 會隨時間變化的日期（用固定年份 2026）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 標準 unittest，6 個測試案例，約 60 行
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1（with Tasks 1, 2）
  - **Blocks**: None（最後驗證時一起跑）
  - **Blocked By**: Task 1

  **References**:
  - `test/test_strategies.py` — 現有測試的 import 風格、assert 用法
  - `core/trading_calendar.py`（Task 1 產出）— 要被測試的模組

  **Acceptance Criteria**:
  - [ ] `python -m unittest test.test_rotate_scheduler.TestTradingCalendar` → 6 tests, 0 failures

  **QA Scenarios**:
  ```
  Scenario: 完整測試套件通過
    Tool: Bash
    Preconditions: Task 1 完成，trading_calendar.py 和 holidays.json 存在
    Steps:
      1. python -m unittest test.test_rotate_scheduler.TestTradingCalendar -v
    Expected Result: 所有 6 個測試顯示 "ok"，總結 "OK"
    Failure Indicators: 任何 FAILED 或 ERROR
    Evidence: .omo/evidence/task-3-test-output.txt
  ```

  **Commit**: YES（groups with Wave 1）
  - Message: `test(rotate): add trading calendar unit tests`
  - Files: `test/test_rotate_scheduler.py`

- [ ] 4. `core/rotate_scheduler.py` — 輪替排程邏輯 + `.env` 產出

  **What to do**:
  - 建立 `core/rotate_scheduler.py`，實作以下函式：
    - `get_rotate_months(rotate_mode: int) -> dict`：依 ROTATE_MODE 回傳該排程月份對照表
      - mode 0: `{}`（不啟用）
      - mode 1: `{"A": (1,4,7,10)}`
      - mode 2: `{"A": (2,5,8,11)}`
      - mode 3: `{"A": (3,6,9,12)}`
      - mode 4: `{"A": (1,4,7,10), "B": (2,5,8,11)}`（雙排程各半資金）
      - mode 5: `{"A": (2,5,8,11), "B": (3,6,9,12)}`（雙排程各半資金）
    - `should_rotate_today(today: date, rotate_mode: int, calendar: TradingCalendar) -> str | None`：
      判斷今天是否為 rotate-month 的第一個交易日。回傳 `None`（不需輪替）或排程標籤 `"A"` / `"B"`
    - `run_rotation_selection(rotate_mode: int, schedule_label: str, env_path: str, backup_dir: str) -> list[dict]`：
      1. 呼叫 `stock_selector_grid.py --recommend --output-env`（subprocess）
      2. 讀取 selector 輸出的 PC_* 條目
      3. 更新 `.env` 檔案（僅替換該排程區段，保留其他 PC_*）
      4. 備份舊 `.env` 到 `backups/.env.YYYYMMDD_HHMMSS`
      5. 回傳選出的股票清單
    - `update_env_section(env_path: str, schedule_label: str, pc_entries: list[str]) -> None`：
      僅更新 `.env` 中對應排程的區段（`# ── 排程 A` 或 `# ── 排程 B`），
      不影響排程標記以外的 PC_* 條目或其他設定
    - `backup_env(env_path: str, backup_dir: str) -> str`：備份 `.env`，回傳備份路徑
  - 匯出常數供 `live_trader_multi.py` 使用：
    ```python
    ROTATE_ALLOC = 12.5  # 雙排程每檔 alloc=12.5（4 檔 × 12.5 = 50%）
    ROTATE_STRATEGY = "keep_wait"
    ROTATE_MAX_ENTRY = -1
    ROTATE_BUY_PCT = 1.0
    ```

  **Must NOT do**:
  - 不要修改 `PORTFOLIO_CONFIG` 或任何 live_trader 的全域變數（只處理檔案）
  - 不要在 `update_env_section` 中覆蓋排程區段以外的 PC_* 條目
  - 不要假設 `.env` 檔案的編碼（用 UTF-8）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 多個互依函式、檔案 I/O、subprocess 呼叫、區段 parse/replace 邏輯，約 150-200 行
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2（with Tasks 5, 6）
  - **Blocks**: Task 7, 8
  - **Blocked By**: Task 1（trading_calendar）

  **References**:
  - `core/config_loader.py:31-49` — `load_portfolio_config()` 如何解析 PC_*，確保產出格式相容
  - `.env:78-92` — 現有排程 A 區段格式、PC_* JSON 格式範例
  - `scripts/stock_selector_grid.py:1244-1255` — ROTATE_QMAP 定義和 dual_mode 邏輯
  - `live_trader_multi.py:312-333` — 全輪替模式的參數格式確認（`max_entry_price=-1`, `alloc`, `initial_buy_pct`）

  **Acceptance Criteria**:
  - [ ] `get_rotate_months(0)` → `{}`
  - [ ] `get_rotate_months(5)` → `{"A": (2,5,8,11), "B": (3,6,9,12)}`
  - [ ] `should_rotate_today(date(2026, 8, 3), 5, calendar)` → `"A"`（8/3 是 8 月第一個交易日，mode 5 排程 A 包含 8 月）
  - [ ] `should_rotate_today(date(2026, 8, 4), 5, calendar)` → `None`（第二個交易日不觸發）
  - [ ] `backup_env(".env", "backups")` → 產出 `backups/.env.20260803_*`，內容與原 `.env` 一致
  - [ ] `update_env_section` 只修改排程 A 區段，排程 B 和其他 PC_* 保持不變

  **QA Scenarios**:
  ```
  Scenario: ROTATE_MODE=5 + 8月第一個交易日 → should_rotate_today 回傳 "A"
    Tool: Bash
    Preconditions: Task 1 完成
    Steps:
      1. python -c "
  from datetime import date
  from core.trading_calendar import TradingCalendar
  from core.rotate_scheduler import should_rotate_today
  tc = TradingCalendar()
  result = should_rotate_today(date(2026, 8, 3), 5, tc)
  print(f'Result: {result}')
  "
    Expected Result: 輸出 "Result: A"
    Evidence: .omo/evidence/task-4-should-rotate-a.txt

  Scenario: backup_env 正確備份 .env
    Tool: Bash
    Preconditions: .env 存在
    Steps:
      1. mkdir -p /tmp/test_backups
      2. python -c "
  from core.rotate_scheduler import backup_env
  path = backup_env('.env', '/tmp/test_backups')
  print(f'Backup: {path}')
  "
      3. diff .env /tmp/test_backups/.env.*  # 確認內容一致
    Expected Result: diff 無輸出（內容一致），backup 檔案存在
    Evidence: .omo/evidence/task-4-backup-env.txt
  ```

  **Commit**: YES（groups with Wave 2）
  - Message: `feat(rotate): add rotation scheduler with .env generation logic`
  - Files: `core/rotate_scheduler.py`

- [ ] 5. `scripts/stock_selector_grid.py` — 新增 `--output-env` 輸出模式

  **What to do**:
  - 在 `stock_selector_grid.py` 的 argparse 加入：
    - `--output-env`：flag，啟用 `.env` 格式輸出（取代 console 美觀輸出）
    - `--schedule-label`：str，排程標籤（"A" 或 "B"），用於產生正確的 `.env` 註解區段
  - 當 `--output-env` 啟用時，`recommend_next_quarter()` 不 print 表格，改為：
    1. 計算每檔 alloc = `100.0 / top_n`（雙排程時，各排程的 top_n 是總數的一半）
    2. 輸出格式（stdout，一行一個）：
       ```
       PC_2357={"strategy":"keep_wait","alloc":12.5,"max_entry_price":-1,"initial_buy_pct":1.0}
       ```
    3. 在 stdout 第一行輸出 `#SCHEDULE=A` 或 `#SCHEDULE=B` 供 scheduler 解析
  - 保持 `--recommend` 原有 console 美觀輸出不變（`--output-env` 是疊加 flag）
  - `recommend_next_quarter()` 需重構為可回傳選股結果（目前只 print），新增 `return_selected=True` 參數時回傳 list[dict]

  **Must NOT do**:
  - 不要改變 `--recommend` 預設行為（無 `--output-env` 時保持原樣）
  - 不要在輸出中包含註解行以外的非 PC_* 內容
  - 不要 hardcode alloc 值（應由呼叫方傳入或根據 top_n 計算）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要理解現有 1338 行的 selector 程式結構，重構 `recommend_next_quarter()`，新增雙排程邏輯
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2（with Tasks 4, 6）
  - **Blocks**: Task 8
  - **Blocked By**: None（理論上與 Task 4 獨立，但都在 Wave 2 中）

  **References**:
  - `scripts/stock_selector_grid.py:1295-1334` — `recommend_next_quarter()` 和 `--recommend` 實作
  - `scripts/stock_selector_grid.py:1244-1255` — ROTATE_QMAP 和 dual_mode 邏輯
  - `.env:84-92` — PC_* 格式範例（`alloc:12.5`, `max_entry_price:-1`, `initial_buy_pct:1.0`）
  - `scripts/stock_selector_grid.py:1324-1331` — selected 變數的結構（symbol, close, momentum 等）

  **Acceptance Criteria**:
  - [ ] `python scripts/stock_selector_grid.py --recommend --output-env --schedule-label A` → stdout 第一行 `#SCHEDULE=A`，後接 N 行 PC_* JSON
  - [ ] 每行 PC_* 為合法 JSON（`json.loads` 可解析）
  - [ ] alloc 總和為 50.0（雙排程各半）或 100.0（單排程）
  - [ ] 無 `--output-env` 時，`--recommend` 輸出不變（原有表格格式）

  **QA Scenarios**:
  ```
  Scenario: --output-env 正確輸出 PC_* 格式
    Tool: Bash
    Preconditions: 候選池資料已快取
    Steps:
      1. python scripts/stock_selector_grid.py --recommend --output-env --schedule-label A --top-n 4 2>&1 | head -6
      2. 檢查第一行是否為 "#SCHEDULE=A"
      3. 檢查後續行是否為 "PC_XXXX={...}" 格式
      4. python -c "import json; json.loads('...')" 驗證每行 JSON 合法
    Expected Result: 正確輸出 5 行（1 header + 4 stocks），每行 JSON 合法
    Failure Indicators: 非 JSON 輸出、alloc 總和不對、格式與現有 PC_* 不一致
    Evidence: .omo/evidence/task-5-output-env.txt
  ```

  **Commit**: YES（groups with Wave 2）
  - Message: `feat(selector): add --output-env flag for .env PC_* generation`
  - Files: `scripts/stock_selector_grid.py`

- [ ] 6. `test/test_rotate_scheduler.py` — 排程邏輯單元測試（擴充）

  **What to do**:
  - 在 `test/test_rotate_scheduler.py` 加入新的 test class：`TestRotateScheduler`
  - 測試案例：
    - `test_get_rotate_months_mode_0` → `{}`
    - `test_get_rotate_months_mode_1` → `{"A": (1,4,7,10)}`
    - `test_get_rotate_months_mode_5` → `{"A": (2,5,8,11), "B": (3,6,9,12)}`
    - `test_should_rotate_mode5_august_first_trading_day` → `"A"`
    - `test_should_rotate_mode5_september_first_trading_day` → `"B"`
    - `test_should_rotate_not_first_trading_day` → `None`
    - `test_should_rotate_wrong_month` → `None`
    - `test_update_env_section_preserves_other_pc`：只改排程 A，排程 B 和手動 PC_* 保持不變
    - `test_backup_env_creates_file`：備份檔案存在且內容一致
  - `setUp` 中建立 temporary `.env` 和 `backups/` 目錄（用 `tempfile`）

  **Must NOT do**:
  - 不要在測試中真的呼叫 `stock_selector_grid.py`（用 mock 或 skip）
  - 不要修改真實的 `.env` 檔案（用 tempfile）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 9 個測試案例，使用 tempfile，約 100 行
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2（with Tasks 4, 5）
  - **Blocks**: None
  - **Blocked By**: Task 4

  **References**:
  - `core/rotate_scheduler.py`（Task 4 產出）— 要被測試的模組
  - `test/test_strategies.py` — 現有測試風格
  - `.env:78-92` — `.env` 區段格式參考

  **Acceptance Criteria**:
  - [ ] `python -m unittest test.test_rotate_scheduler.TestRotateScheduler` → 9 tests, 0 failures

  **QA Scenarios**:
  ```
  Scenario: 完整排程測試通過
    Tool: Bash
    Preconditions: Task 4 完成
    Steps:
      1. python -m unittest test.test_rotate_scheduler.TestRotateScheduler -v
    Expected Result: 9 tests, OK
    Evidence: .omo/evidence/task-6-scheduler-tests.txt
  ```

  **Commit**: YES（groups with Wave 2）
  - Message: `test(rotate): add scheduler logic unit tests`
  - Files: `test/test_rotate_scheduler.py`

- [ ] 7. `live_trader_multi.py` — 加入每日 08:40 熱重載機制

  **What to do**:
  - 在 `live_trader_multi.py` 中加入以下邏輯：
  - **新增 import**（module level）：
    ```python
    from core.rotate_scheduler import should_rotate_today, ROTATE_ALLOC
    from core.trading_calendar import TradingCalendar
    ```
  - **新增全域變數**：
    ```python
    _rotate_calendar = TradingCalendar()
    _last_reload_date = None  # 追蹤今天是否已 reload
    ```
  - **在 main loop 中新增熱重載區塊**（放在 `cci()` 之後、`today_str` 之前，約 line 242 附近）：
    ```python
    # ── 每日 08:40 熱重載 .env（全輪替配置更新）──
    if is_weekday and h == 8 and m >= 40 and _last_reload_date != today_str:
        try:
            import os as _os
            from dotenv import load_dotenv as _reload
            _reload(override=True)
            new_config = load_portfolio_config()
            # 合併新配置：保留仍在 config 中的 symbol 的 history
            removed = set(PORTFOLIO_CONFIG.keys()) - set(new_config.keys())
            PORTFOLIO_CONFIG.clear()
            PORTFOLIO_CONFIG.update(new_config)
            for sym in removed:
                portfolio_history.pop(sym, None)
                pyramid_tracker.pop(sym, None)
            _last_reload_date = today_str
            print(f'🔄 08:40 熱重載 .env 完成，目前監控 {len(PORTFOLIO_CONFIG)} 檔')
        except Exception as e:
            print(f'⚠️ 熱重載 .env 失敗: {e}')
    ```
  - **關鍵考量**：
    - `_last_reload_date` 確保每天只 reload 一次
    - `PORTFOLIO_CONFIG.clear()` + `update()`（而非重新賦值）保持 module-level reference 不變
    - 被移除的 symbol 從 `portfolio_history` 和 `pyramid_tracker` 中清除（09:00 cleanup 會賣出舊持股）
    - 新增的 symbol 會在 main loop 的初始化邏輯中自動加入（但目前初始化只在 `main()` 開頭做一次）→ **需要額外處理**：
      - 對新加入的 symbol，仿照 `main()` 中的初始化邏輯（line 155-169），載入價格歷史到 `portfolio_history`

  - **補充：新 symbol 初始化**：
    ```python
    # 在熱重載後，對新 symbol 初始化資料
    for sym in new_config:
        if sym not in portfolio_history:
            df_init = broker.get_minute_bars(sym, minutes=60) if USE_REAL_API else broker.get_historical_data(sym, days=30)
            if not df_init.empty:
                portfolio_history[sym] = df_init
                print(f'✅ {sym} 熱重載初始化成功')
    ```

  **Must NOT do**:
  - 不要改變 `main()` 開頭的初始化順序
  - 不要在非交易時段（週末）reload
  - 不要移除仍在 PORTFOLIO_CONFIG 中的 symbol 的 history
  - 不要改變 `PORTFOLIO_CONFIG` 的 module-level binding（用 `.clear()` + `.update()` 而非 `= new_config`）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需精確理解 main loop 的狀態管理（portfolio_history, pyramid_tracker, holdings），修改核心執行流程，約 40 行新增
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3（with Task 8）
  - **Blocks**: None（最後一層）
  - **Blocked By**: Task 4（rotate_scheduler）, Task 1（trading_calendar）

  **References**:
  - `live_trader_multi.py:50-169` — `main()` 中的初始化流程，特別是 symbol 初始化（line 155-169）
  - `live_trader_multi.py:238-251` — main loop 的開始位置（`while True`, `today_str`, `is_weekday` 定義）
  - `live_trader_multi.py:9-13` — `load_dotenv(override=True)` 和 `PORTFOLIO_CONFIG = load_portfolio_config()` 的 module-level 呼叫
  - `core/config_loader.py:31-49` — `load_portfolio_config()` 實作

  **Acceptance Criteria**:
  - [ ] 交易日 08:40~08:44 之間，出現 `🔄 08:40 熱重載 .env 完成` 日誌
  - [ ] 同一天不會重複 reload（`_last_reload_date` 保護）
  - [ ] `.env` 中新增的 PC_* symbol 自動加入 `portfolio_history`
  - [ ] `.env` 中移除的 PC_* symbol 從 `portfolio_history` 和 `pyramid_tracker` 清除
  - [ ] 現有的非輪替 monitoring 不受影響

  **QA Scenarios**:
  ```
  Scenario: 熱重載後新增 symbol 被初始化
    Tool: Bash
    Preconditions: 修改 .env 加入一個新 PC_9999 symbol
    Steps:
      1. 在 08:40 時間窗內執行 python live_trader_multi.py（或模擬時間）
      2. grep "熱重載" 日誌
      3. grep "9999" 日誌 → 確認出現初始化成功訊息
    Expected Result: 日誌顯示新 symbol 已初始化，PORTFOLIO_CONFIG 包含新 symbol
    Evidence: .omo/evidence/task-7-hot-reload.txt

  Scenario: 重複 reload 被防止
    Tool: Bash
    Steps:
      1. 模擬程式在 08:41 reload 後繼續執行到 08:42
      2. 確認不出現第二次 "熱重載 .env 完成"
    Expected Result: 只有一條 reload 日誌
    Evidence: .omo/evidence/task-7-no-double-reload.txt
  ```

  **Commit**: YES（groups with Wave 3）
  - Message: `feat(rotate): add daily 08:40 hot-reload of .env configuration`
  - Files: `live_trader_multi.py`

- [ ] 8. `live_trader_multi.py` — 加入盤後全輪替選股觸發

  **What to do**:
  - 在 main loop 中加入盤後選股觸發邏輯（放在 `if is_weekday and h == 13 and m >= 31:` 區塊之後，約 line 599）：
  - **新增邏輯**：
    ```python
    # ── 盤後全輪替選股觸發（13:31~13:35，每月第一個交易日）──
    ROTATE_MODE_VAL = int(os.getenv('ROTATE_MODE', '0'))
    if ROTATE_MODE_VAL > 0 and is_weekday and h == 13 and 31 <= m <= 35:
        _rotate_key = '_rotate_done_date'
        if globals().get(_rotate_key) != today_str:
            schedule = should_rotate_today(now.date(), ROTATE_MODE_VAL, _rotate_calendar)
            if schedule:
                try:
                    import subprocess as _sp
                    print(f'🔄 全輪替觸發：{schedule}排程，執行選股程式...')
                    result = _sp.run(
                        ['python', 'scripts/stock_selector_grid.py', '--recommend', '--output-env',
                         '--schedule-label', schedule, '--top-n', '4'],
                        capture_output=True, text=True, timeout=120
                    )
                    if result.returncode == 0:
                        pc_lines = [l for l in result.stdout.strip().split('\n') if l.startswith('PC_')]
                        if pc_lines:
                            from core.rotate_scheduler import update_env_section, backup_env
                            backup_env('.env', 'backups')
                            update_env_section('.env', schedule, pc_lines)
                            stocks_str = ', '.join(l.split('=')[0].replace('PC_', '') for l in pc_lines)
                            send_telegram_message(f'🔄 *全輪替 {schedule}排程 選股完成*\n📋 {" ".join(pc_lines[:2])}...\n📁 舊 .env 已備份至 backups/')
                            print(f'✅ 全輪替 {schedule}排程: .env 已更新 {len(pc_lines)} 檔')
                        else:
                            print(f'⚠️ 全輪替: selector 無輸出')
                    else:
                        print(f'❌ 全輪替: selector 執行失敗\n{result.stderr[:500]}')
                except Exception as e:
                    print(f'❌ 全輪替選股異常: {e}')
            globals()[_rotate_key] = today_str
    ```
  - **關鍵設計**：
    - 只在 13:31~13:35 這個 5 分鐘窗口觸發，避免重複執行（用 `_rotate_done_date` 保護）
    - `should_rotate_today()` 使用 `now.date()` 判斷（不是 `today_str`），因為 `today_str` 可能在跨日時尚未更新
    - subprocess 呼叫 `stock_selector_grid.py`，timeout 120 秒（足夠載入快取資料）
    - 成功後立即備份 + 更新 `.env` + Telegram 通知
    - **只在 `ROTATE_MODE > 0` 時才檢查**，避免不必要的 overhead

  **Must NOT do**:
  - 不要在交易時段（09:00-13:30）修改 `.env`
  - 不要在 selector 失敗時覆蓋 `.env`（先檢查 returncode）
  - 不要阻塞 main loop（subprocess 有 timeout）
  - 不要忘記 `globals()[_rotate_key]` 的防止重複機制

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 修改核心 main loop，涉及 subprocess、檔案 I/O、Telegram 通知整合，約 30 行新增
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3（with Task 7）
  - **Blocks**: None
  - **Blocked By**: Task 4（rotate_scheduler）, Task 5（selector --output-env）, Task 7（hot-reload）

  **References**:
  - `live_trader_multi.py:599-614` — 現有盤後處理區塊（daily report, closing summary）
  - `live_trader_multi.py:252-271` — cleanup 機制（`globals()[_cd_key] != today_str` pattern）
  - `live_trader_multi.py:69-70` — `send_telegram_message()` 呼叫範例
  - `scripts/stock_selector_grid.py:1305-1334` — `--recommend` 雙排程輸出格式
  - `core/rotate_scheduler.py`（Task 4 產出）— `should_rotate_today`, `update_env_section`, `backup_env`

  **Acceptance Criteria**:
  - [ ] ROTATE_MODE=5，8 月第一個交易日 13:31 → 觸發選股，執行 `stock_selector_grid.py --recommend --output-env --schedule-label A`
  - [ ] 選股成功後，`.env` 的排程 A 區段被更新為新股票
  - [ ] 舊 `.env` 備份至 `backups/.env.20260803_133100`
  - [ ] Telegram 收到「全輪替 A排程 選股完成」訊息
  - [ ] 非 rotate-month 不觸發
  - [ ] ROTATE_MODE=0 不觸發
  - [ ] 同一天不會重複觸發（`_rotate_done_date` 保護）

  **QA Scenarios**:
  ```
  Scenario: ROTATE_MODE=5 + 8月第一個交易日 13:31 → 自動選股
    Tool: Bash（模擬時間）
    Preconditions: Task 1, 4, 5, 7 完成，taiwan_holidays.json 存在
    Steps:
      1. 設定 ROTATE_MODE=5
      2. python -c "
  from datetime import date
  from core.trading_calendar import TradingCalendar
  from core.rotate_scheduler import should_rotate_today
  tc = TradingCalendar()
  result = should_rotate_today(date(2026, 8, 3), 5, tc)
  print(f'Trigger: {result}')
  "
      3. 確認輸出為 "Trigger: A"
    Expected Result: should_rotate_today 正確回傳 "A"
    Evidence: .omo/evidence/task-8-trigger-check.txt

  Scenario: 非 rotate-month 不觸發
    Tool: Bash
    Steps:
      1. python -c "
  from datetime import date
  from core.trading_calendar import TradingCalendar
  from core.rotate_scheduler import should_rotate_today
  tc = TradingCalendar()
  result = should_rotate_today(date(2026, 7, 1), 5, tc)
  print(f'Trigger: {result}')
  "
    Expected Result: 輸出 "Trigger: None"（7 月不在 ROTATE_MODE=5 的排程中）
    Evidence: .omo/evidence/task-8-no-trigger.txt
  ```

  **Commit**: YES（groups with Wave 3）
  - Message: `feat(rotate): add post-market rotation stock selection trigger`
  - Files: `live_trader_multi.py`

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in `.omo/evidence/`. Compare deliverables against plan.
  Key checks: trading_calendar.py exists + works, rotate_scheduler.py exists + works, docker-compose has .env mount, live_trader_multi.py has hot-reload + trigger code, test file has 15 passing tests, .env backup mechanism works.
  Output: `Must Have [N/9] | Must NOT Have [N/5] | Tasks [8/8] | Evidence [N] | VERDICT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `python -m unittest test.test_rotate_scheduler -v`. Review all new/changed files for: `as any`/`@ts-ignore`, empty catches, `console.log` equivalent, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names. Verify new code follows existing style (no type hints, spaces indentation).
  Output: `Tests [N pass/N fail] | Lint issues [N] | Style [MATCH/ISSUES] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration:
  1. Calendar + Scheduler: `should_rotate_today(date(2026,8,3), 5, calendar)` returns "A"
  2. Selector output: `--recommend --output-env --schedule-label A` produces correct PC_* lines
  3. .env update: `update_env_section` preserves non-rotation PC_* entries
  4. End-to-end: mock date → trigger fires → .env updated → backup created → hot-reload picks up new config
  5. Edge cases: ROTATE_MODE=0 (no trigger), weekend dates, holiday dates, dual-mode both schedules
  Save to `.omo/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination: Task 8 touching Task 5's files unnecessarily. Flag unaccounted changes (any file modified outside the plan's file list).
  Output: `Tasks [N/8 compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **All tasks**: Single commit after final verification passes
  - Message: `feat(rotate): add automated full rotation scheduler`
  - Pre-commit: `python -m unittest test.test_rotate_scheduler`

---

## Success Criteria

### Verification Commands
```bash
python -m unittest test.test_rotate_scheduler  # Expected: all tests pass
python live_trader_multi.py                     # Expected: no import errors, scheduler initializes
python scripts/stock_selector_grid.py --recommend --output-env --dry-run  # Expected: PC_* output
```

### Final Checklist
- [ ] 交易日曆正確判斷休市日與補班日
- [ ] ROTATE_MODE 0~5 全模式正確產出對應月份的股票
- [ ] 雙排程模式（4/5）產出獨立區段（排程 A / 排程 B）
- [ ] `.env` 舊檔備份至 `backups/`
- [ ] Telegram 通知選股完成
- [ ] 熱重載在 08:40 正確更新 PORTFOLIO_CONFIG
- [ ] 現有非輪替 PC_* 條目不被覆蓋
