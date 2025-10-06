from core.strategy_engine import StrategyEngine
from data.yahoo_loader import load_historical_data

print("✅ 匯入成功！")

# 測試載入資料
df = load_historical_data("2330.TW", start="2024-01-01")
print(f"✅ 載入 {len(df)} 筆資料")