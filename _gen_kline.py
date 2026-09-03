#!/usr/bin/env python3
"""依 finmind skill 流程：抓 2884 玉山金 近一年 K 線 → 產生 ECharts HTML。"""
import os, json, re
import requests, pandas as pd
from datetime import datetime, timedelta

# 讀 token（不印出來）——專案 .env 用 FINMIND_API_TOKEN
token = None
with open(".env", encoding="utf-8") as f:
    for line in f:
        m = re.match(r"\s*FINMIND_API_TOKEN\s*=\s*(.+)", line)
        if m:
            token = m.group(1).strip().strip('"').strip("'")
            break
if not token:
    raise SystemExit("找不到 FINMIND_API_TOKEN")

SYMBOL = "2884"
NAME = "玉山金"
END = datetime.now().date()
START = END - timedelta(days=395)

url = "https://api.finmindtrade.com/api/v4/data"
params = {"dataset": "TaiwanStockPrice", "data_id": SYMBOL,
          "start_date": START.isoformat(), "end_date": END.isoformat()}
headers = {"Authorization": f"Bearer {token}"}
resp = requests.get(url, params=params, headers=headers, timeout=30)
data = resp.json()

if data.get("status") != 200:
    raise SystemExit(f"FinMind 錯誤: {data.get('msg')}")

df = pd.DataFrame(data["data"])
df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
df = df.sort_values("date").reset_index(drop=True)
df = df[df["date"] >= START.isoformat()].reset_index(drop=True)

# FinMind TaiwanStockPrice 欄位：open / max(高) / min(低) / close / Trading_Volume
candles = [[float(r["open"]), float(r["close"]), float(r["min"]), float(r["max"])]
           for _, r in df.iterrows()]
dates = df["date"].tolist()
volumes = [float(v) if v == v else 0 for v in df["Trading_Volume"].tolist()]

def ma(col, n):
    return [None] * (n - 1) + [round(df[col].iloc[i - n:i].mean(), 2) for i in range(n, len(df) + 1)]

payload = {
    "symbol": SYMBOL, "name": NAME,
    "start": df["date"].iloc[0], "end": df["date"].iloc[-1],
    "rows": len(df),
    "dates": dates, "candles": candles, "volumes": volumes,
    "ma5": ma("close", 5), "ma10": ma("close", 10), "ma20": ma("close", 20),
}
print(f"✅ 抓到 {len(df)} 筆 | {df['date'].iloc[0]} ~ {df['date'].iloc[-1]} | 最後收盤 {df['close'].iloc[-1]}")

# 用唯一哨兵（__X__）做 .replace()，避開 { } 與 % %
head = """<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">
<title>__NAME__ (__SYMBOL__) 近一年 K 線</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>body{font-family:'Noto Sans CJK TC','Microsoft JhengHei',sans-serif;margin:16px;background:#fafafa}
h1{font-size:20px;margin:8px 0} .meta{color:#666;font-size:13px;margin-bottom:8px}
#chart{width:1000px;height:640px;margin:0 auto;border:1px solid #eee;background:#fff}</style>
</head><body>
<h1>__NAME__ (__SYMBOL__) 近一年 K 線</h1>
<div class="meta">資料來源 FinMind · TaiwanStockPrice · __START__ ~ __END__（__ROWS__ 筆）</div>
<div id="chart"></div>
<script>
const data = """
tail = """;
const up='#ef232a', down='#14b143';
const dates = data.dates, candles = data.candles.map(c => ({value:c, itemStyle:{color:c[1]>=c[0]?up:down, color0:c[1]>=c[0]?up:down, borderColor:c[1]>=c[0]?up:down, borderColor0:c[1]>=c[0]?up:down}}));
const vol = data.volumes.map((v,i)=>({value:v, itemStyle:{color:candles[i][1]>=candles[i][0]?up:down}}));
const ma = (arr) => arr.map(v => v==null?'-':v);
const chart = echarts.init(document.getElementById('chart'));
const option = {
  tooltip:{trigger:'axis', axisPointer:{type:'cross'}},
  legend:{data:['K線','MA5','MA10','MA20']},
  grid:[{left:60,right:20,top:30,height:'60%'},{left:60,right:20,top:'74%',height:'18%'}],
  xAxis:[{type:'category',data:dates,gridIndex:0,boundaryGap:true,axisLabel:{formatter: v=> v.slice(0,7) }},
         {type:'category',data:dates,gridIndex:1,axisLabel:{show:false}}],
  yAxis:[{scale:true,gridIndex:0,splitLine:{show:false}},
         {scale:true,gridIndex:1,axisLabel:{show:false},splitLine:{show:false}}],
  dataZoom:[{type:'inside',xAxisIndex:[0,1],start:70,end:100},{show:true,xAxisIndex:[0,1],type:'slider',top:'92%'}],
  series:[
    {name:'K線',type:'candlestick',data:candles,xAxisIndex:0,yAxisIndex:0},
    {name:'MA5',type:'line',data:ma(data.ma5),smooth:true,showSymbol:false,lineStyle:{width:1},xAxisIndex:0,yAxisIndex:0},
    {name:'MA10',type:'line',data:ma(data.ma10),smooth:true,showSymbol:false,lineStyle:{width:1},xAxisIndex:0,yAxisIndex:0},
    {name:'MA20',type:'line',data:ma(data.ma20),smooth:true,showSymbol:false,lineStyle:{width:1},xAxisIndex:0,yAxisIndex:0},
    {name:'成交量',type:'bar',data:vol,xAxisIndex:1,yAxisIndex:1}
  ]
};
chart.setOption(option);
</script></body></html>"""

head_html = (head
             .replace("__NAME__", NAME).replace("__SYMBOL__", SYMBOL)
             .replace("__START__", df["date"].iloc[0])
             .replace("__END__", df["date"].iloc[-1])
             .replace("__ROWS__", str(len(df))))
payload_json = json.dumps(payload, ensure_ascii=False)
html = head_html + payload_json + tail

outdir = "img"
os.makedirs(outdir, exist_ok=True)
outfile = os.path.join(outdir, f"{SYMBOL}_{NAME}_1y_kline.html")
with open(outfile, "w", encoding="utf-8") as f:
    f.write(html)
print(f"✅ 已產生 {outfile}（{os.path.getsize(outfile)} bytes）")
