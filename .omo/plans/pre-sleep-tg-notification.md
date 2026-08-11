# Pre-Sleep TG Holdings Notification

## TL;DR

> **Quick Summary**: Add a Telegram notification that reports current holdings + next open time before `live_trader_multi.py` enters its long overnight sleep period.
>
> **Deliverables**:
> - New function `send_sleep_notification()` in `core/live_notifications.py`
> - Modified sleep block in `live_trader_multi.py` to call it
>
> **Estimated Effort**: Quick
> **Parallel Execution**: NO — 1 sequential task
> **Critical Path**: Task 1

---

## Context

### Original Request
*改成休眠前TG先報持倉* — Send current holdings to Telegram before the program goes to sleep for the night.

### Interview Summary
**Key Discussions**:
- Current problem: `send_closing_summary` is sent at 13:45, then `daily_report_sent_date` guard blocks re-sending before long sleep
- User wants a distinct pre-sleep notification with holdings + "sleeping until next open"

**Research Findings**:
- `core/live_notifications.py:send_closing_summary()` reads `logs/holdings.json` and builds a full holdings report with per-stock P&L (cost, qty, market value, unrealized gain)
- `notify_all(msg)` sends to both Telegram and LINE
- Sleep block at `live_trader_multi.py:518-531` runs when `sleep_seconds >= 3600`, loops every hour

---

## Work Objectives

### Core Objective
Add a pre-sleep holdings notification to Telegram that fires once per day when the program enters long hibernate mode.

### Concrete Deliverables
- `core/live_notifications.py`: new `send_sleep_notification(pd, app_version, next_open)` function
- `live_trader_multi.py`: modified sleep block with `sleep_notified_date` tracking + call to new function

### Must Have
- Send TG message with holdings snapshot before overnight sleep
- Include "next open time" in the message
- Fire ONCE per day (no hourly spam)
- Works with both Telegram and LINE (via `notify_all`)

### Must NOT Have (Guardrails)
- Do NOT change 13:45 `send_closing_summary` behavior
- Do NOT add new dependencies
- Do NOT refactor existing notification functions
- Do NOT change the dashboard generation logic

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (`python -m unittest test.test_strategies`)
- **Automated tests**: None (notification function — no meaningful unit test)
- **Agent-Executed QA**: YES — deploy to VM, check TG message arrives

### QA Policy
Evidence saved to `.omo/evidence/task-1-*.{ext}`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave FINAL (single task):
└── Task 1: Add pre-sleep TG notification function + wire into main loop [quick]
```

### Dependency Matrix
- **1**: - - F1-F4
- **F1-F4**: 1 - user ok

---

## TODOs

- [ ] 1. Add `send_sleep_notification()` + wire into sleep block

  **What to do**:
  - In `core/live_notifications.py`, add function `send_sleep_notification(pd, app_version, next_open)`:
    - Read `logs/holdings.json` — if absent or empty, send generic "💤 休眠中" message
    - Build message with format:
      ```
      💤 *睡前持倉報告 ({date})* V{ver}
      ────────────────────
      {per-stock: symbol, shares, cost avg, market value, unrealized P&L}
      ────────────────────
      總成本: NT$...
      總市值: NT$...
      未實現損益: +NT$...
      💤 休眠到 {next_open.strftime('%m/%d %H:%M')}
      ```
    - Send via `notify_all(msg)`
  - In `live_trader_multi.py`:
    - Add `sleep_notified_date = None` at init section (near `daily_report_sent_date = None`)
    - Modify the sleep block (around line 520-531):
      ```python
      if (sleep_seconds >= 3600):
          if (daily_report_sent_date != now.date()):
              # existing: closing report + dashboard
              ...
          # NEW: pre-sleep notification (once per day)
          if (sleep_notified_date != now.date()):
              send_sleep_notification(pd, datetime, next_open)
              sleep_notified_date = now.date()
          print(f"💤 非交易時段，下次開盤 ...")
      ```
    - Pass `datetime` (the `datetime` module, already imported) to the new function

  **Must NOT do**:
  - Do NOT change `send_closing_summary` or `send_daily_report`
  - Do NOT change the 13:45 report schedule
  - Do NOT touch Docker/docker-compose

  **Recommended Agent Profile**:
  > Single quick task, familiar with the codebase
  - **Category**: `quick`
    - Reason: Simple function addition + 2-line wiring change
  - **Skills**: none needed
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: NO (single task)
  - **Blocks**: F1-F4
  - **Blocked By**: None

  **References**:
  - `core/live_notifications.py:72-132` — `send_closing_summary()` — pattern for reading holdings.json, building per-stock P&L message
  - `core/live_notifications.py:19-20` — `notify_all(msg)` — use this to send
  - `live_trader_multi.py:501-504` — existing 13:45 report call pattern
  - `live_trader_multi.py:518-531` — sleep block to modify
  - `logs/holdings.json` — the file read to get current positions

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY — task is INCOMPLETE without these):**

  ```
  Scenario: Pre-sleep notification appears on Telegram after market close
    Tool: Bash (SSH into VM + tail logs)
    Preconditions: Container running, past 13:30 Taipei time (or set system clock forward)
    Steps:
      1. gcloud compute ssh tw-autotrader --zone=asia-east1-b --command='sudo docker logs tw_autotrader_bot --tail 30'
      2. Check log for "💤 睡前持倉報告" output
      3. Check Telegram app for notification with same header
    Expected Result: TG message "💤 睡前持倉報告" appears with holdings data + "休眠到" with next open time
    Failure Indicators: Message not received, wrong format, no holdings data
    Evidence: .omo/evidence/task-1-sleep-notification.log

  Scenario: No duplicate notifications on hourly loop
    Tool: Bash (check logs)
    Preconditions: Container running, past 13:30 Taipei time, already sent sleep notification
    Steps:
      1. Wait 1+ hour or check log for repeated sleep notifications
      2. grep for "睡前持倉報告" in docker logs
    Expected Result: Only 1 occurrence of "睡前持倉報告" per day
    Failure Indicators: Multiple copies found
    Evidence: .omo/evidence/task-1-no-duplicate.log

  Scenario: Graceful handling when no holdings
    Tool: Bash (inject empty holdings file + restart)
    Preconditions: Access to VM
    Steps:
      1. gcloud compute ssh tw-autotrader --zone=asia-east1-b --command='echo "{}" > ~/tw-autotrader/logs/holdings.json'
      2. sudo docker restart tw_autotrader_bot
      3. Force sleep condition, check TG
    Expected Result: Generic "💤 休眠中" message without holdings
    Failure Indicators: Crash, exception in logs
    Evidence: .omo/evidence/task-1-empty-holdings.log
  ```

  **Evidence to Capture**:
  - [ ] `.omo/evidence/task-1-sleep-notification.log` — proof TG message was sent
  - [ ] `.omo/evidence/task-1-no-duplicate.log` — proof only once per day

  **Commit**: YES
  - Message: `feat: add pre-sleep Telegram holdings notification`
  - Files: `core/live_notifications.py live_trader_multi.py`
  - Pre-commit: `python -m unittest test.test_strategies`

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read plan end-to-end. Verify: `send_sleep_notification()` function exists in `core/live_notifications.py`. `send_sleep_notification` is called in the sleep block of `live_trader_multi.py`. `sleep_notified_date` tracking prevents duplicates.
  Output: `Must Have [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `python -m unittest test.test_strategies`. Check new function for: no bare exceptions, no hardcoded paths, correct f-string usage, no console.log in production code paths.
  Output: `Tests [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  After deploy to VM, wait for market close OR simulate. Check Telegram app for the 💤 notification. Verify holdings data matches actual positions. Check that no duplicate is sent on subsequent hourly loops.
  Output: `TG Notification [PASS/FAIL] | Duplicates [NONE/FOUND] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  Verify only the two files listed were changed. No changes to `send_closing_summary`, `send_daily_report`, docker-compose, or dashboard generation.
  Output: `Files [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **1**: `feat: add pre-sleep Telegram holdings notification` - `core/live_notifications.py live_trader_multi.py` - python -m unittest test.test_strategies

---

## Success Criteria

### Verification Commands
```bash
# Check function exists
grep -n "def send_sleep_notification" core/live_notifications.py
grep -n "sleep_notified_date" live_trader_multi.py

# Run tests
python -m unittest test.test_strategies
```

### Final Checklist
- [ ] `send_sleep_notification()` added to `core/live_notifications.py`
- [ ] Sleep block calls `send_sleep_notification` with `sleep_notified_date` guard
- [ ] All tests pass
- [ ] No changes to unrelated files
- [ ] No duplicate notifications per day
