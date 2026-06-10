FROM python:3.10-slim
WORKDIR /app
# 安裝基本編譯工具
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 複製 E.Sun SDK 並安裝
COPY esun_sdk/ esun_sdk/
RUN pip install --no-cache-dir esun_sdk/esun_marketdata-*.whl esun_sdk/esun_trade-*.whl
# 複製其餘程式碼
COPY . .
CMD ["python", "live_trader_multi.py"]
