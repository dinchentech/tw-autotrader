# TW AutoTrader 路線圖

**目前焦點**：多策略自動交易系統維運與策略優化（布林/均線/VWAP/keep_wait + 法人動能選股），整合每季自動換股流程。

## 里程碑

- [x] 其他腳本 inline 快取版本化（backtest_inst_bottomfish / backtest_july / scripts/*.py）— 2026-08-11 完成，統一走 core/cache_io.py；plans/ 為獨立嵌套 repo 不處理
- [ ] 補齊 requirements.txt 遺漏依賴（python-dotenv/yfinance/tqdm）
- [ ] 確認 KGI 真實 API 端點（`data/kgi_real.py` 目前為 placeholder）
- [ ] 每季自動換股（stock_selector_grid auto_momentum）與實盤下單流程整合
- [ ] 護盤過濾（MAX_DIST_FROM_ACCUM=0.15）在實盤環境驗證

## 開放問題

1. 每季自動換股在避險期（如 2022 熊市 63d 防禦）資金如何停泊、何時回歸動能？
2. 法人動能策略（方案三）候選池與 TOP_N 在真實盤的滑價影響為何？
