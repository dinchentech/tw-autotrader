# 南亞科 2408 加碼持有 — .env 配置變更

## TL;DR

> **Quick Summary**: 將 TW AutoTrader 的 .env 配置從現有 9 檔調整為 10 檔：十銓降 alloc 空出額度，新增南亞科 2408 用均線交叉策略持有。
>
> **Deliverables**:
> - `.env` 中 PC_4967 alloc 從 16.67 降為 10
> - `.env` 新增 PC_2408 配置（ma_cross, alloc=15）
>
> **Estimated Effort**: Quick
> **Parallel Execution**: N/A（單一檔案、兩個區塊修改）
> **Critical Path**: 直接編輯 → 驗證格式

---

## Context

### 原始請求
用戶檢查 .env 後，確認已經用備用策略1（g1_strategy_1，價格區間）持有十銓 4967。現在要加碼持有南亞科 2408，詢問建議。

### 決策過程
- **策略選擇**：南亞科 342 億股本、毛利率 79.5%、營收年增 643%，不適合十銓的價格區間策略。選用 **ma_cross（均線交叉）**，fast=5/slow=20——比既有 2330 的 9/21 更靈敏，適合南亞科的高波動股性。
- **Alloc 調整**：現有 9 檔 alloc 加總 116.67%（超配）。十銓從 16.67% 降為 10%（空出 6.67%），南亞科拿 15%。調整後總 alloc = 125%（實務可行）。
- **十銓原有策略保留**：僅降 alloc，策略（g1_strategy_1, buy=250/sell=280）不變。

### 最終配置

| 股票 | 策略 | alloc | 資金 (基於 50 萬) |
|------|------|-------|-------------------|
| 4967 十銓 | g1_strategy_1 (價格區間) | ~~16.67%~~ → **10%** | NT$50,000 |
| **2408 南亞科** | **ma_cross (5/20)** | **15% (新增)** | **NT$75,000** |

---

## 工作目標

### 核心目標
在 `.env` 中新增南亞科 2408 的均線交叉策略配置，同時調降十銓 4967 的 alloc 以維持合理的總資金分配。

### 具體產出
- `PC_4967` 的 `alloc` 欄位從 16.67 改為 10
- 新增一行 `PC_2408` 配置

---

## 執行變更

### 變更 1：十銓 alloc 調降

**檔案**：`/home/frank/tw-autotrader/.env`，第 112-113 行

**現狀**：
```
# 4967 — 十銓 價格區間 ｜ alloc=16.67% → NT$100,000（250↓買/280↑賣）
PC_4967={"strategy":"g1_strategy_1","alloc":16.67,"buy_price":250,"sell_price":280,"position_amount":10000,"monthly_budget":0}
```

**改成**：
```
# 4967 — 十銓 價格區間 ｜ alloc=10% → NT$50,000（250↓買/280↑賣）
PC_4967={"strategy":"g1_strategy_1","alloc":10,"buy_price":250,"sell_price":280,"position_amount":10000,"monthly_budget":0}
```

### 變更 2：新增南亞科配置

**檔案**：`/home/frank/tw-autotrader/.env`，在第 113 行（PC_4967 改完後）下方新增一行

**新增**：
```
# 2408 — 南亞科 均線交叉 ｜ alloc=15% → NT$75,000
PC_2408={"strategy":"ma_cross","alloc":15,"fast_period":5,"slow_period":20,"atr_threshold":0.005,"position_amount":10000,"monthly_budget":0}
```

---

## 驗證檢查

變更完成後檢查：
1. `PC_4967` JSON 中 `alloc` 值為 `10`（非 `16.67`）
2. 新增的 `PC_2408` 行存在，JSON 格式與其他 PC_ 行一致
3. 總 alloc = 20+15+15+10+10+10+10+**10**+10+**15** = **125%**
4. 無多餘空格或語法錯誤導致 JSON parse 失敗

---

## 重啟容器

.env 變更後需重啟 Docker 容器才能生效：

```bash
cd /home/frank/tw-autotrader && sudo docker compose restart
```