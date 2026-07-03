# TW AutoTrader V2.0 更新說明

## 🎉 新版本亮點

### 用戶自訂策略支持 (V2.0 核心功能)

現在您可以在不修改加密主程式 `live_trader_multi.py` 的情況下，自由定義和使用自己的交易策略。

---

## 📋 新增功能

### 1. 四組備用策略範本

| 代號 | 策略名稱 | 預設邏輯 |
|------|----------|----------|
| `g1_strategy_1` | 均線交叉策略 | 快線穿過慢線向上買進 |
| `g1_strategy_2` | RSI 超買超賣 | RSI<30 買進, RSI>70 賣出 |
| `g2_strategy_1` | 價格動能策略 | N 日漲跌幅超門檻買進 |
| `g2_strategy_2` | 量價配合策略 | 價格站穩均線+量放大買進 |

### 2. 回測支持

所有用戶自訂策略都可以透過 `backtest.py` 進行回測：

```bash
# 基本回測
python backtest.py --strategy g1_strategy_1 --symbol 2330 --start 2025-01-01

# 自訂參數回測
python backtest.py --strategy g1_strategy_1 --fast_period 10 --slow_period 20
```

### 3. 動態參數配置

透過 `.env` 檔案靈活配置每支股票的策略和參數：

```bash
# 使用預設參數
PC_2330={"strategy":"g1_strategy_1","alloc":20}

# 自訂參數
PC_2330={"strategy":"g1_strategy_1","alloc":20,"fast_period":10,"slow_period":20}
```

---

## 🚀 快速開始

### 步驟 1: 測試策略載入

```bash
python test_user_strategies.py
```

### 步驟 2: 在 `.env` 中設定

```bash
PC_2330={"strategy":"g1_strategy_1","alloc":20}
```

### 步驟 3: 啟動系統

```bash
python live_trader_multi.py
```

啟動時應該看到：
```
🚀 TW AutoTrader v2.0 (build 2026-07-03 16:35:00) 多股多策略分流系統啟動
✅ 已載入 4 個用戶自訂策略
```

---

## 📂 檔案變更

### 新增檔案

| 檔案 | 說明 |
|------|------|
| `user_strategies.py` | 用戶自訂策略定義檔案 |
| `USER_STRATEGIES_GUIDE.md` | 詳細使用說明 |
| `USER_STRATEGIES_README.md` | 給使用者的快速入門指南 |
| `test_user_strategies.py` | 策略測試工具 |
| `integration_test_user_strategies.py` | 完整整合測試 |
| `CHANGELOG_V2.0.md` | 本檔案 |

### 更新檔案

| 檔案 | 變更內容 |
|------|----------|
| `live_trader_multi.py` | ✅ 版本更新為 v2.0<br>✅ 添加用戶策略動態載入 |
| `core/config_loader.py` | ✅ 添加用戶策略參數鍵 |
| `core/strategy_engine.py` | ✅ 支持只返回訊號的用戶策略 |
| `backtest.py` | ✅ 支持用戶策略回測<br>✅ 添加用戶策略 argparse 參數 |
| `.env.example.txt` | ✅ 添加用戶策略使用範例 |

---

## 🔄 升級指南

### 從 V1.40 升級到 V2.0

1. **備份現有設定**
   ```bash
   cp .env .env.backup
   ```

2. **取得新檔案**
   確保您有以下檔案：
   - `user_strategies.py`（源碼）
   - `USER_STRATEGIES_GUIDE.md`（說明）
   - `USER_STRATEGIES_README.md`（快速入門）

3. **使用新版本主程式**
   - `live_trader_multi.py v2.0`（加密）

4. **（可選）更新 `.env`**
   在 `.env` 中使用新策略：
   ```bash
   PC_2330={"strategy":"g1_strategy_1","alloc":20}
   ```

---

## 🎯 如何自訂策略

### 步驟 1: 開啟 `user_strategies.py`

```bash
vim user_strategies.py
```

### 步驟 2: 修改或新增策略函式

每個策略必須：
1. 接受 `df: pd.DataFrame` 和 `**kwargs`
2. 回傳包含 `signal` 欄位的 DataFrame
3. `signal` 值為 `1` (BUY)、`-1` (SELL) 或 `0` (HOLD)

### 步驟 3: 在 `USER_STRATEGY_MAP` 中註冊

```python
USER_STRATEGY_MAP = {
    'my_strategy': my_strategy_function,
}
```

### 步驟 4: 在 `.env` 中使用

```bash
PC_2330={"strategy":"my_strategy","alloc":20}
```

---

## 📊 回測範例

### 內建策略回測

```bash
python backtest.py --strategy ma_cross --symbol 2330
```

### 用戶策略回測

```bash
python backtest.py --strategy g1_strategy_1 --symbol 2330 --fast_period 10
```

### 回測所有標的

```bash
python backtest.py --strategy g1_strategy_2
```

---

## ⚠️ 重要注意事項

1. **策略函式返回格式**
   - 用戶策略可以只返回 `pd.DataFrame({'signal': signals})`
   - 策略引擎會自動合併原始 OHLCV 資料

2. **參數傳遞**
   - 確保參數名稱與 `core/config_loader.py` 中的 `STRATEGY_PARAM_KEYS` 一致
   - 參數值會自動從 `.env` PC_ 設定或 CLI 參數中取得

3. **回測資料要求**
   - 所有用戶策略都需要 access `df['close']` 欄位
   - 使用成交量資料的策略需要 `df['volume']` 欄位

---

## 🆚 V1.40 vs V2.0

| 功能 | V1.40 | V2.0 |
|------|-------|------|
| 內建策略 | ✅ 5 種 | ✅ 5 種 |
| 用戶自訂策略 | ❌ 不支持 | ✅ 4 種範本 + 無限擴展 |
| 回測支持 | ✅ 內建策略 | ✅ 內建 + 用戶策略 |
| 動態參數配置 | ✅ PC_ 格式 | ✅ PC_ 格式 + 用戶策略參數 |
| 策略測試工具 | ❌ 無 | ✅ 有 |

---

## 🔐 加密部署

V2.0 支持以下部署方式：

**給使用者的檔案：**
- `live_trader_multi.py`（加密，v2.0）
- `user_strategies.py`（源碼，可修改）
- `USER_STRATEGIES_GUIDE.md`（源碼）
- `USER_STRATEGIES_README.md`（源碼）
- `.env.example.txt`（源碼）

**使用流程：**
1. 使用者修改 `user_strategies.py` 中的策略邏輯
2. 使用者在 `.env` 中配置策略
3. 啟動 `live_trader_multi.py`（加密版本會自動載入用戶策略）

---

## 🐛 已知問題

無重大已知問題。

---

## 📞 技術支援

如有問題，請聯絡：frank@dinchen.com.tw

---

## 📜 更新歷史

### V2.0 (2026-07-03)
- ✅ 新增用戶自訂策略功能
- ✅ 新增四組備用策略範本
- ✅ 支持用戶策略回測
- ✅ 更新策略引擎以支持簡化的策略返回格式
- ✅ 新增策略測試工具
- ✅ 更新所有相關文檔
- ✅ 文件名改為繁體中文（用戶自訂策略快速入門.md、用戶自訂策略使用說明.md）
- ✅ 在 README.md、使用手冊.md、策略說明.md 中添加備用策略功能說明及連結

### V1.40 (2026-07-01)
- 金字塔加碼優化
- 風險控管改進
- 通知系統更新

---

**TW AutoTrader V2.0** - 讓您的交易策略真正由您掌控！