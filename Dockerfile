FROM python:3.10-slim
WORKDIR /app
# 安裝基本編譯工具（若策略有用到 TA-Lib 等需要編譯的套件）
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "live_trader_multi.py"]
