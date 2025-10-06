import finmind
from finmind.data import Data
import os

# 設定 API Token（先用假的測試套件是否安裝成功）
os.environ['FINMIND_API_TOKEN'] = 'test_token'

try:
    data_loader = Data()
    print("✅ FinMind 套件安裝成功！")
    print(f"版本: {data_loader.__version__}")
except Exception as e:
    print(f"❌ 錯誤: {e}")