# 資金操作規範 — 手動買入 / 賣出 / 加減資金庫

> 當前真相（2026-08-30 建立，源自「Group 1 加碼 20 萬配置 3008/6805 breakout」的操作用例）。
> **凡涉及手動買入、賣出、加碼、提領資金庫的操作，務必先查閱使用手冊（策略說明.md / 使用手冊.md）再做，本件為查閱後的濃縮規則。**

## 一句話

資金池只有一個數字 `TOTAL_CAPITAL`（.env），所有個股上限 = `TOTAL_CAPITAL × alloc%`。加碼/提領要麼改 `.env` ＋ 在 `capital.txt` 註解記錄，要麼透過 `capital.txt` 有效條目讓系統「自動」處理——**但自動路徑有副作用（見陷阱 1），實務一律走「改 .env + 註解記錄」**。

## 加碼 / 提領資金庫的兩種路徑

| 路徑 | 做法 | 觸發行為 | 適用 |
|---|---|---|---|
| **A（推薦，全手動）** | ① `.env` 改 `TOTAL_CAPITAL` ② `capital.txt` 以 `#` 開頭註解記錄該筆 | 不觸發任何自動買入；僅影響 `get_stock_capital()` 計算 | 加碼有指定用途（如給特定標的）、不想系統自動攤到 keep_wait |
| **B（系統自動）** | `capital.txt` 寫有效條目 `金額, YYYY/MM/DD`（不加 #） | 下次啟動/每日檢查時：`TOTAL_CAPITAL += 金額`、TG 通知、**對所有 keep_wait 標的自動加碼** | 想讓系統按 keep_wait 配置自動分配新資金 |

## 範例（2026-08-30 實作）

加碼 20 萬 → 3008/6805 breakout 各 10 萬：

```env
# .env
TOTAL_CAPITAL=800000            # 可動用總資金（2026-08-30 加碼 20 萬；其中 10 萬×2 配置給 3008/6805 breakout）
PC_3008={"strategy":"breakout","alloc":12.5,"buy_shares":14,"sell_shares":14,"lookback":20,"atr_period":14,"atr_threshold":0.02}
PC_6805={"strategy":"breakout","alloc":12.5,"buy_shares":42,"sell_shares":42,"lookback":20,"atr_period":14,"atr_threshold":0.02}
```

```txt
# capital.txt（純記錄，因 # 開頭不觸發自動加碼）
##100000, 2023/06/01  # 外部加碼 10 萬（已計入 TOTAL_CAPITAL；註解故不觸發 keep_wait 加碼）
# 200000, 2026/08/30  # 外部加碼 20 萬 → 配置 3008/6805 breakout 各 10 萬（已計入 TOTAL_CAPITAL=800000）
```

## 手動新增標的（PC_<代號>）規則

1. **格式**：`PC_<代號>={"strategy":"<策略>","alloc":<%>,"<參數>":...}`，例：`PC_3008={"strategy":"breakout","alloc":12.5,"buy_shares":14,...}`
2. **alloc**：個股資金上限 = `TOTAL_CAPITAL × alloc%`。加碼後要重算——例如 TOTAL_CAPITAL 600000→800000 時，alloc 12.5 由 NT$75,000 變 NT$100,000
3. **strategies**：bollinger / vwap / ma_cross / breakout / keep_wait（見策略說明.md §9.2 參數表）
4. **位置**：放 `.env` 的「排程 A/B 區段之外」（非輪替區段）→ 季末全輪替選股腳本（update_env_section）只替換排程 A/B 區段的 PC_*，其餘不受影響（策略說明.md §8）
5. **撞股**：手動標的若被全輪替候選池（市值前 100）選中 → 買入端會觸發「跨策略重疊防護」跳過（策略說明.md §8），不需重複建倉
6. **breakout 特別注意**：v3.17 起下單數量**不再用固定 buy_shares/sell_shares**，改為依 `alloc` 自動計算（買入 = `TOTAL_CAPITAL × alloc% ÷ 股價`，賣出 = 全部持有）。`.env` 內的 `buy_shares`/`sell_shares` 欄位僅為 fallback（買入時股價抓取失敗才用）。`lookback`(20)、`atr_period`(14)、`atr_threshold`(0.02) 為常用預設；**v3.17 起 breakout 走日K模式**（Donchian=20 交易日，非分鐘K）——見 LOG 2026-08-30。

## 陷阱（contains）

1. **⚠️ capital.txt 有效條目會觸發 keep_wait 自動加碼**（live_trader_multi.py 加碼處理迴圈）：對**每個** keep_wait 標的（含全輪替的）買入 `TOTAL_CAPITAL × alloc% × initial_buy_pct`。範例：TOTAL_CAPITAL=800000、4 檔 keep_wait × alloc 12.5 × 1.0 → **每檔加碼 NT$100,000、合計 NT$400,000** — 遠超過注入金額，且會用現金池超買。**2026-08-30 因此棄用路徑 B**，改走「改 .env + 註解記錄」。
2. **VM processed_capital.json（logs/）會決定哪筆已被處理**：`capital.txt` 未註解的條目若尚未出現在 `logs/processed_capital.json`，下次啟動會再處理一次（重複加碼）。VM 上此檔為 `[]` 而本地為 `["2023-06-01"]`——**兩邊狀態不同，改動前先確認 VM 側**。
3. **breakout 訊號=「當日剛創新高」本身**：`breakout_strategy` 的買進條件是「收盤 > 前 N 日高（shift(1)）」——**突破發生的當日就是 BUY 訊號**，不是「創新高後等突破」。因此「適合 breakout」與「剛創新高」是同一件事：分析排名前二的 3008/6805 在 2026-08-28（收盤 7,065 > 6,915 / 2,345 > 2,225，ATR 5.3%/6.0% ≥ 2%）**當日即觸發 BUY**。反例：6213 聯茂收盤 582 < 前20日高 583，僅 1 點之差不觸發——接近高點≠已突破。
   - **操作時序注意**：若配置後數日股價已遠離突破點（突破已發生完），該次訊號已過，需等**下一次整理後的再突破**（如回檔縮量 → 又放量衝高）——這是時序問題，不是「不會有訊號」。
   - 2026-08-30 曾誤寫「剛創新高短期不會再觸發突破」——**因果顛倒**（突破=新高當下），本條為修正後版本。
4. **手改 VM .env 前先備份**：`cp .env .env.bak_$(date +%Y%m%d_%H%M%S)`；部署流程（deploy.sh）會覆蓋 VM 的 .env/config，見 `cairn/deploy-pipeline.md`。
5. **下單失敗的 TG 警示有縫隙（v3.18 修復）**：E.Sun 部分錯誤（如 `A00002: response parse Error`）是**回傳 `{"error": ...}` dict** 而非拋例外——v3.17 前 `if ('error' in order_result):` 分支沒呼叫 notify_order_failure，使用者完全不知情（2026-08-31 實盤 30+ 次失敗零通知）。v3.18 起該分支第一行補 TG 通知（所有策略通用）。**若看到 log 有「❌ E.Sun 下單失敗」但沒收到 TG → 檢查是否為舊版本**。
