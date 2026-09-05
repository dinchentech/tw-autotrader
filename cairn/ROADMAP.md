# TW AutoTrader 路線圖

**目前焦點**：多策略自動交易系統維運與策略優化（布林/均線/VWAP/keep_wait + 法人動能選股），整合每季自動換股流程。

## 里程碑

- [x] 其他腳本 inline 快取版本化（backtest_inst_bottomfish / backtest_july / scripts/*.py）— 2026-08-11 完成，統一走 core/cache_io.py；plans/ 為獨立嵌套 repo 不處理
- [ ] 統一 cache/inst_momentum/price/ 格式：july/bottomfish 改以 core/inst_data.py 為規範來源（消除 ma 欄位不一致）
- [ ] 補齊 requirements.txt 遺漏依賴（python-dotenv/yfinance/tqdm）
- [ ] 確認 KGI 真實 API 端點（`data/kgi_real.py` 目前為 placeholder）
- [ ] 每季自動換股（stock_selector_grid auto_momentum）與實盤下單流程整合
- [ ] 護盤過濾（MAX_DIST_FROM_ACCUM=0.15）在實盤環境驗證

## 開放問題

1. 每季自動換股在避險期（如 2022 熊市 63d 防禦）資金如何停泊、何時回歸動能？
2. 法人動能策略（方案三）候選池與 TOP_N 在真實盤的滑價影響為何？
3. ⏳ **觀察 auto 訊號 & 排程 A 換股日後微調比例**（2026-09-05 記）：2026-09-05 依規則重整 `.env` —— 非輪替改為「正常」選股 auto 5 檔（2464/4967/2006/3515/2362，各 5%），汰換舊固定(3008/2360/6805/2884/2454/3189/6213)與未再選中的舊 auto；總 alloc **130.8% → 90.1%**（已不超額）。留意事項：持續觀察 5 檔 auto 訊號實盤表現；待排程 A（2/5/8/11月）換股日賣出 keep_wait 檔釋資後，斟酌全輪替/非輪替比例。選股工具已改為讀 `logs/holdings.json` 判已持倉、只汰換「未持倉且未選中」者、保留已持倉/keep_wait。
