"""
_bt_100wan.py — 100萬資金最佳化配置回測 (2022~2025)
Group 1: 核心權值池 (500K) → 0050/2330/2454 HYBRID
Group 2: 法人抬轎動能池 (500K) → 動能選股
資料源：FinMind + TWSE 公開 API
"""
import os, sys, math, pickle
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
import requests
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

START_DATE = "2022-01-01"; END_DATE = "2025-12-31"
COMMISSION_RATE = 0.001425; STOCK_TAX_RATE = 0.003; ETF_TAX_RATE = 0.001
ETF_SYMBOLS = {"0050"}
def tax_rate(sym): return ETF_TAX_RATE if sym in ETF_SYMBOLS else STOCK_TAX_RATE

G1_STOCKS = [("0050","bollinger",167000),("2330","ma_cross",167000),("2454","keep_wait",166000)]
G1_CAPITAL = 500000

G2_CAPITAL = 500000; G2_TOP_N_STOCKS = 150; G2_TOP_N = 5
G2_BASE_SIZE = 60000; G2_PYRAMID_ADD = 0.03; G2_ADD_SIZE = 40000; G2_MAX_POSITION = 100000
G2_STOP_LOSS = 0.07; G2_TRAILING_PCT = 0.10; G2_TAKE_PROFIT = 0.25
G2_FISH_DAYS = 60; G2_FISH_MIN_SCORE = 4.0; G2_MIN_VOLUME = 2000; G2_BUY_RATIO = 0.03
G2_LOOKBACK = 20; G2_SELL_COST = 0.004425

def finmind_login():
    from FinMind.data import DataLoader
    token = os.getenv("FINMIND_API_TOKEN","")
    dl = DataLoader(token=token)
    if token: dl.login_by_token(api_token=token)
    return dl

G1_CACHE = Path("cache/bt_100wan/g1"); G1_CACHE.mkdir(parents=True, exist_ok=True)
G2_CACHE = Path("cache/inst_momentum/price")

def load_price(sid, dl, cache_dir, offset=60):
    cf = cache_dir / f"{sid}.pkl"
    if cf.exists():
        df = pickle.loads(cf.read_bytes())
        if not df.empty and df["date"].max() >= pd.Timestamp(END_DATE) - timedelta(days=7):
            return df
    start = (datetime.strptime(START_DATE,"%Y-%m-%d")-timedelta(days=offset)).strftime("%Y-%m-%d")
    try:
        raw = dl.taiwan_stock_daily(stock_id=sid, start_date=start, end_date=END_DATE)
        if raw.empty: return pd.DataFrame()
        df = pd.DataFrame({"date":pd.to_datetime(raw["date"]),"open":raw["open"].astype(float),
            "high":raw["max"].astype(float),"low":raw["min"].astype(float),
            "close":raw["close"].astype(float),"volume":raw["Trading_Volume"].astype(float)
        }).sort_values("date").reset_index(drop=True)
        df["ma10"]=df["close"].rolling(10).mean(); df["ma20"]=df["close"].rolling(20).mean()
        cf.write_bytes(pickle.dumps(df)); return df
    except: return pd.DataFrame()

TWSE_CACHE = Path("cache/inst_momentum")
def fetch_twse_inst(trading_dates):
    ck = f"twse_inst_{START_DATE}_{END_DATE}.pkl"; cf = TWSE_CACHE / ck
    if cf.exists(): print("   載入 TWSE 快取..."); return pickle.loads(cf.read_bytes())
    dates = sorted(d for d in trading_dates); inst_data = {}
    for i, d in enumerate(dates):
        ds = d.strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/fund/T86?response=json&date={ds}&selectType=ALLBUT0999"
        try:
            resp = requests.get(url, timeout=15); data = resp.json()
        except: continue
        if data.get("stat") != "OK": continue
        dd = {}
        for row in data.get("data",[]):
            sid = str(row[0]).strip()
            if not sid.isdigit() or len(sid)!=4: continue
            try:
                fb=int(row[2].replace(",","")); fs=int(row[3].replace(",",""))
                tb=int(row[8].replace(",","")); ts=int(row[9].replace(",",""))
            except: continue
            dd[sid] = (fb+tb, fs+ts)
        inst_data[d.isoformat()] = dd
        if (i+1)%100==0: print(f"   TWSE: {i+1}/{len(dates)}")
    cf.write_bytes(pickle.dumps(inst_data))
    print(f"✅ TWSE: {len(inst_data)} 天"); return inst_data

def merge_inst(all_data, twse):
    for sid, df in all_data.items():
        if df.empty: continue
        b,s=[],[]
        for d in df["date"]:
            ds = d.strftime("%Y-%m-%d") if hasattr(d,"strftime") else str(d)[:10]
            dd=twse.get(ds,{}).get(sid,(0,0)); b.append(dd[0]); s.append(dd[1])
        df["inst_buy"]=b; df["inst_sell"]=s
    return all_data

# ─── G1 ───────────────────────────────
from strategies.bollinger import bollinger_reverse_strategy
from strategies.ma_cross import ma_cross_strategy
SF = {"bollinger":bollinger_reverse_strategy,"ma_cross":ma_cross_strategy}
KW = {"initial_buy_pct":0.7,"add_drop_pct":5,"add_shares":6,"max_additions":2,"tp_pct":15,"tp_sell_ratio":50,"cooldown_days":30}

class Pos:
    def __init__(self,sym,strat,alloc):
        self.sym=sym;self.strat=strat;self.alloc=alloc
        self.shares=0.;self.cost_basis=0.;self.cash_held=alloc;self.trades=[]
        self.kbc=0;self.kac=0.;self.kts=0;self.kcd=None
    def v(self,p): return self.shares*p
    def buy(self,dt,px,amt):
        if amt<=0 or px<=0: return 0
        c=round(amt*COMMISSION_RATE); a=amt-c
        if a<=0: return 0
        sb=a/px; co=round(sb*px,2); ac=round(co*COMMISSION_RATE); t=co+ac
        self.shares+=sb; self.cost_basis+=t
        self.trades.append({"date":dt,"type":"buy","price":px,"shares":round(sb,4),"amount":round(co,2),"commission":ac,"tax":0})
        return t
    def sell(self,dt,px,reason=""):
        if self.shares<=0 or px<=0: return 0,0
        p=self.shares*px; c=round(p*COMMISSION_RATE); t=round(p*tax_rate(self.sym)); n=p-c-t; pnl=n-self.cost_basis
        self.trades.append({"date":dt,"type":"sell","price":px,"shares":round(self.shares,4),"amount":round(p,2),"commission":c,"tax":round(t,2),"reason":reason})
        self.shares=0.;self.cost_basis=0.;return round(n,2),round(pnl,2)
    def sell_p(self,dt,px,ratio,reason=""):
        ss=self.shares*ratio
        if ss<=0: return 0,0
        p=ss*px; c=round(p*COMMISSION_RATE); t=round(p*tax_rate(self.sym)); n=p-c-t; cp=self.cost_basis*ratio; pnl=n-cp
        self.shares-=ss; self.cost_basis-=cp
        self.trades.append({"date":dt,"type":"sell_partial","price":px,"shares":round(ss,4),"amount":round(p,2),"commission":c,"tax":round(t,2),"reason":reason})
        return round(n,2),round(pnl,2)

def sim_g1(d):
    print("\n"+50*"="+"\n📦 G1 核心權值池 (500K)\n"+50*"=")
    for s,st,a in G1_STOCKS: print(f"  {s:6} → {st:12s} {a:>7,}")
    ps={}
    for sym,strat,alloc in G1_STOCKS:
        df=d.get(sym)
        if df is None or df.empty: continue
        df=df[df["date"]>=START_DATE].copy()
        if strat=="keep_wait": df["signal"]=0
        elif strat in SF:
            p={}
            if strat=="bollinger": p={"window":20,"std_dev":2.0,"rsi_period":5}
            elif strat=="ma_cross": p={"fast_period":9,"slow_period":21,"atr_threshold":0.005}
            df=SF[strat](df.set_index("date"),**p).reset_index()
        else: df["signal"]=0
        d[sym]=df; ps[sym]=Pos(sym,strat,alloc)
    ad = sorted(set(dd for df in d.values() if not df.empty for dd in df["date"]))
    mr=[]
    for dt in ad:
        for sym,strat,_ in G1_STOCKS:
            df=d.get(sym)
            if df is None or df.empty: continue
            r=df[df["date"]==dt]
            if r.empty: continue
            rr=r.iloc[0]; px=float(rr["close"])
            if pd.isna(px) or px<=0: continue
            p=ps[sym]
            if strat!="keep_wait":
                sig=int(rr.get("signal",0))
                if sig==1 and p.shares==0 and p.cash_held>10:
                    spent=p.buy(dt,px,p.cash_held); p.cash_held-=spent
                elif sig==-1 and p.shares>0:
                    net,_=p.sell(dt,px); p.cash_held+=net
            else:
                if p.kcd and dt<p.kcd: continue
                if p.kbc==0:
                    ba=p.cash_held*KW["initial_buy_pct"]; spent=p.buy(dt,px,ba)
                    if spent>0: p.cash_held-=spent; p.kac=px; p.kts=spent/px; p.kbc=1
                else:
                    dp_=(p.kac-px)/p.kac*100 if p.kac>0 else 0
                    pp_=(px-p.kac)/p.kac*100 if p.kac>0 else 0
                    if pp_>=KW["tp_pct"] and p.kts>0:
                        net,_=p.sell_p(dt,px,KW["tp_sell_ratio"]/100)
                        p.cash_held+=net; p.kac=0; p.kbc=0; p.kts=0; p.kcd=dt+timedelta(days=KW["cooldown_days"])
                    elif dp_>=KW["add_drop_pct"] and p.kbc<KW["max_additions"]:
                        amt=KW["add_shares"]*px; spent=p.buy(dt,px,amt)
                        if spent>0: p.cash_held-=spent; p.kts+=spent/px; p.kac=(p.kac*(p.kts-spent/px)+px*spent/px)/p.kts; p.kbc+=1
        mds=[dd for dd in ad if dd.year==dt.year and dd.month==dt.month]
        if dt==mds[-1]:
            tv=sum(p.cash_held for p in ps.values())
            for sym,_,_ in G1_STOCKS:
                p=ps[sym]; df=d.get(sym)
                if df is not None:
                    rr=df[df["date"]==dt]
                    if not rr.empty: tv+=p.v(float(rr.iloc[0]["close"]))
            mr.append({"date":dt,"value":round(tv,2)})
    fc=0
    for sym,_,_ in G1_STOCKS:
        p=ps[sym]; fc+=p.cash_held
        if p.shares>0:
            df=d.get(sym)
            if df is not None and not df.empty:
                lr=df.iloc[-1]; net,_=p.sell(lr["date"],float(lr["close"]),"期末"); fc+=net
    pnl=fc-G1_CAPITAL; ret=pnl/G1_CAPITAL
    print(f"  ✅ G1 最終: {fc:,.0f}  損益: {ret:+.2%}")
    return {"final_value":fc,"total_return":ret,"total_pnl":pnl,"positions":ps,"monthly_records":mr,"capital":G1_CAPITAL,"config":G1_STOCKS}

# ─── G2 ───────────────────────────────
def get_sids():
    mf=TWSE_CACHE/"mcap_ranking.pkl"
    if mf.exists():
        r=pickle.loads(mf.read_bytes()); r=[s for s in r if s.isdigit() and len(s)==4]
        return r[:G2_TOP_N_STOCKS]
    c=sorted(f.stem for f in G2_CACHE.glob("*.pkl") if f.stem.isdigit() and len(f.stem)==4)
    return c[:G2_TOP_N_STOCKS]

def fish_score(ca,oa,ha,la,va,ib,is_,idx):
    ci=ca[idx]; vi=va[idx]
    rl=la[max(0,idx-29):idx+1].min(); pl=(ci-rl)/ci if ci>0 else 1
    ps=0
    if pl<0.02: ps+=1
    if idx>=19 and ci<ca[idx-19:idx+1].mean(): ps+=1
    if idx>=59 and ci<ca[idx-59:idx+1].mean(): ps+=1
    if idx>=5:
        st=sum(1 for j in range(idx-4,idx) if ca[j]<ca[j-1])
        if st>=3 and ci>=la[max(0,idx-2):idx+1].min(): ps+=0.5
    ps=min(ps,3)
    av5=va[max(0,idx-4):idx+1].mean(); av20=va[max(0,idx-19):idx+1].mean(); vr=vi/av5 if av5>0 else 1
    vs=0
    if vr>1.3: vs+=1
    if vr>2: vs+=1
    if vr>1.3:
        pc=(ci-oa[idx])/oa[idx] if oa[idx]>0 else 0
        if -0.02<=pc<=0.02: vs+=1
        elif pc>0.03: vs-=0.5
    if av5>av20*1.2: vs+=0.5
    vs=max(0,min(vs,3))
    body=abs(ci-oa[idx]); ls=min(oa[idx],ci)-la[idx]; us=ha[idx]-max(oa[idx],ci); tr=ha[idx]-la[idx]
    pts=0
    if tr>0:
        lr=ls/tr
        if lr>0.5 and body<tr*0.4: pts+=1
        if lr>0.6 and us<tr*0.2: pts+=1
        if body/tr<0.1 and ls>0 and us>0: pts+=1
    pts=min(pts,2)
    net=ib[idx]-is_[idx]; ins=(1 if net>0 else 0)+(1 if net>1000 else 0); ins=min(ins,2)
    return ps+vs+pts+ins

def pre_fish(ad):
    fs={}; t=len(ad)
    for i,(sid,df) in enumerate(ad.items()):
        if df.empty or len(df)<30: continue
        ca=df["close"].values; oa=df["open"].values; ha=df["high"].values
        la=df["low"].values; va=df["volume"].values; ib=df["inst_buy"].values; is_=df["inst_sell"].values
        dates=df["date"].values; scs={}
        for ix in range(29,len(df)):
            sc=fish_score(ca,oa,ha,la,va,ib,is_,ix)
            d=dates[ix]; ds=d.strftime("%Y-%m-%d") if hasattr(d,"strftime") else str(d)[:10]
            scs[ds]=sc
        fs[sid]=scs
        if (i+1)%100==0: print(f"   🐟 {i+1}/{t}")
    return fs

def scr_fish(fs,sd,fd,fm):
    sd_str=sd.strftime("%Y-%m-%d") if hasattr(sd,"strftime") else str(sd)[:10]
    lb=(pd.Timestamp(sd_str)-timedelta(days=fd)).strftime("%Y-%m-%d")
    q=set()
    for sid,scs in fs.items():
        mx=max((s for d,s in scs.items() if lb<=d<sd_str),default=0)
        if mx>=fm: q.add(sid)
    return q

def chk_mom(ad,sid,cd):
    df=ad.get(sid)
    if df is None or df.empty or len(df)<G2_LOOKBACK+5: return False,0
    m=df["date"]<=cd
    if not m.any(): return False,0
    r=df[m].tail(G2_LOOKBACK+5)
    if len(r)<G2_LOOKBACK+1: return False,0
    l=r.iloc[-1]; lc=l["close"]
    if lc<=0 or math.isnan(lc): return False,0
    if r.tail(5)["volume"].mean()/1000<G2_MIN_VOLUME: return False,0
    if lc<r.tail(G2_LOOKBACK)["close"].max(): return False,0
    ma20=l.get("ma20")
    if ma20 is None or math.isnan(ma20) or lc<=ma20: return False,0
    i5=r.tail(5); tnb=i5["inst_buy"].sum()-i5["inst_sell"].sum(); tv5=i5["volume"].sum()
    if tnb<=0 or tv5<=0: return False,0
    if tnb/tv5<G2_BUY_RATIO: return False,0
    return True,round(tnb/tv5,4)

def sim_g2(ad,fs=None):
    print("\n"+50*"="+"\n📦 G2 法人動能池 (500K)\n"+50*"=")
    print(f"   {G2_TOP_N_STOCKS}檔池/持有{G2_TOP_N} 停損{G2_STOP_LOSS:.0%} 回落{G2_TRAILING_PCT:.0%} 停利{G2_TAKE_PROFIT:.0%}")
    print(f"   首單{format(G2_BASE_SIZE,',')}→+{G2_PYRAMID_ADD:.0%}+{format(G2_ADD_SIZE,',')}→上限{format(G2_MAX_POSITION,',')}")
    cash=float(G2_CAPITAL); pos={}; tl=[]; eq=[]
    ad_=sorted(set(d.date() if hasattr(d,"date") else d for df in ad.values() if not df.empty for d in df["date"]))
    ad_=[d for d in ad_ if d>=datetime.strptime(START_DATE,"%Y-%m-%d").date()]
    pc={}
    for d in ad_: pc[d]={}
    for sid,df in ad.items():
        if df.empty: continue
        for _,r in df.iterrows():
            d=r["date"].date() if hasattr(r["date"],"date") else r["date"]
            if d in pc: pc[d][sid]={"close":r["close"],"open":r["open"],"ma10":r.get("ma10"),"ma20":r.get("ma20")}
    nd={}
    for i,d in enumerate(ad_):
        for j in range(i+1,len(ad_)):
            if ad_[j]>d: nd[d]=ad_[j]; break
    sd=ad_; fq={}
    if fs:
        for i,s in enumerate(sd):
            q=scr_fish(fs,s,G2_FISH_DAYS,G2_FISH_MIN_SCORE)
            if q: fq[s]=q
            if (i+1)%300==0: print(f"   篩選: {i+1}/{len(sd)}")
    me={}; lb={}
    def ban(s,d): return s in lb and d<=lb[s]
    td=len(ad_)
    for di,d in enumerate(ad_):
        dp=pc.get(d,{}); cf=fq.get(d,set()) if fs else set()
        for sid in list(pos.keys()):
            pi=dp.get(sid,{}); cp=pi.get("close",0)
            if cp<=0: continue
            p=pos[sid]; bp=p["buy_price"]
            loss=(cp-bp)/bp; gain=(cp-bp)/bp
            if loss<=-G2_STOP_LOSS:
                sh=p["shares"]; pr=sh*cp*(1-G2_SELL_COST); cb=sh*bp; pnl=pr-cb
                cash+=pr; tl.append({"date":d.isoformat(),"action":"SELL","stock":sid,"shares":sh,"price":round(cp,2),"pnl":round(pnl,0),"reason":f"停損 {loss:.1%}"})
                if pnl<0: lb[sid]=d+timedelta(days=30)
                del pos[sid]; continue
            if gain>=G2_TAKE_PROFIT:
                sh=p["shares"]; pr=sh*cp*(1-G2_SELL_COST); cb=sh*bp; pnl=pr-cb
                cash+=pr; tl.append({"date":d.isoformat(),"action":"SELL","stock":sid,"shares":sh,"price":round(cp,2),"pnl":round(pnl,0),"reason":f"停利 {gain:.1%}"})
                del pos[sid]; continue
            pk=p.get("peak_price",bp)
            if cp>pk: p["peak_price"]=cp
            if gain>0:
                dd=(pk-cp)/pk
                if dd>=G2_TRAILING_PCT:
                    sh=p["shares"]; pr=sh*cp*(1-G2_SELL_COST); cb=sh*bp; pnl=pr-cb
                    cash+=pr; tl.append({"date":d.isoformat(),"action":"SELL","stock":sid,"shares":sh,"price":round(cp,2),"pnl":round(pnl,0),"reason":f"回落停利 {dd:.1%}"})
                    del pos[sid]; continue
        if cf:
            for sid in sorted(cf):
                if sid in pos or ban(sid,d): continue
                if len(pos)>=G2_TOP_N: break
                ok,sc=chk_mom(ad,sid,pd.Timestamp(d))
                if ok:
                    ed=nd.get(d)
                    if ed: me.setdefault(ed,[]).append((sid,sc))
        if d in me:
            for sid,sc in sorted(me[d],key=lambda x:-x[1]):
                if sid in pos or ban(sid,d): continue
                if len(pos)>=G2_TOP_N: break
                pi=dp.get(sid,{}); bp=pi.get("open",pi.get("close",0))
                if bp<=0: continue
                ba=min(G2_BASE_SIZE,cash)
                if ba<10000: continue
                sh=int(ba/bp/1000)*1000
                if sh<=0: continue
                co=sh*bp*(1+COMMISSION_RATE)
                if cash<co:
                    sh=int(cash/(bp*(1+COMMISSION_RATE))/1000)*1000
                    if sh<=0: continue; co=sh*bp*(1+COMMISSION_RATE)
                cash-=co
                pos[sid]={"shares":sh,"buy_price":bp,"buy_date":d,"peak_price":bp,"pyramid_level":1}
                tl.append({"date":d.isoformat(),"action":"BUY","stock":sid,"shares":sh,"price":round(bp,2),"pnl":0,"reason":f"入場 sc={sc}"})
            del me[d]
        for sid in list(pos.keys()):
            p=pos[sid]; pi=dp.get(sid,{}); cp=pi.get("close",0)
            if cp<=0: continue
            gain=(cp-p["buy_price"])/p["buy_price"]; cv=p["shares"]*cp
            if gain>=G2_PYRAMID_ADD and cv<G2_MAX_POSITION and cash>=G2_ADD_SIZE:
                as_=int(G2_ADD_SIZE/p["buy_price"]/1000)*1000
                if as_>0:
                    ac=as_*p["buy_price"]*(1+COMMISSION_RATE)
                    if cash>=ac: cash-=ac; p["shares"]+=as_; p["pyramid_level"]+=1; tl.append({"date":d.isoformat(),"action":"ADD","stock":sid,"shares":as_,"price":round(p["buy_price"],2),"pnl":0,"reason":f"金字塔 L{p['pyramid_level']}"})
        pv=sum(p["shares"]*dp.get(sid,{}).get("close",p["buy_price"]) for sid,p in pos.items())
        te=cash+pv; eq.append({"date":d.isoformat(),"cash":round(cash,0),"position_value":round(pv,0),"total_equity":round(te,0)})
        if (di+1)%300==0: print(f"   模擬: {di+1}/{td} 持倉{len(pos)} 權益{te:,.0f}")
    for sid in list(pos.keys()):
        p=pos.pop(sid); ld=ad_[-1]; pi=pc.get(ld,{}).get(sid,{})
        sp=pi.get("close",p["buy_price"]); sh=p["shares"]
        pr=sh*sp*(1-G2_SELL_COST); cb=sh*p["buy_price"]; pnl=pr-cb; cash+=pr
        tl.append({"date":ld.isoformat(),"action":"SELL","stock":sid,"shares":sh,"price":round(sp,2),"pnl":round(pnl,0),"reason":"期末"})
    fv=cash; pnl_=fv-G2_CAPITAL; ret=pnl_/G2_CAPITAL
    sls=[t for t in tl if t["action"]=="SELL"]; wn=[t for t in sls if t.get("pnl",0)>0]; ls=[t for t in sls if t.get("pnl",0)<0]
    pk=G2_CAPITAL; mdd=0; mddp=0
    for e in eq:
        if e["total_equity"]>pk: pk=e["total_equity"]
        dd=pk-e["total_equity"]; ddp=dd/pk if pk>0 else 0
        if ddp>mddp: mdd=dd; mddp=ddp
    print(f"  ✅ G2 最終: {fv:,.0f}  損益: {ret:+.2%}  MaxDD: {mddp:.2%}")
    return {"final_value":fv,"total_return":ret,"total_pnl":pnl_,"capital":G2_CAPITAL,"trade_log":tl,"equity_curve":eq,"max_drawdown":mdd,"max_drawdown_pct":mddp,"wins":len(wn),"losses":len(ls),"total_sells":len(sls)}

# ─── 報告 ──────────────────────────────
def n(v): return f"NT${v:,.0f}"
def p(v): return f"+{v:.1%}" if v>=0 else f"{v:.1%}"

def report(g1,g2):
    tv=g1["final_value"]+g2["final_value"]; tc=G1_CAPITAL+G2_CAPITAL; tpnl=tv-tc; tr=tpnl/tc
    y=(date(2025,12,31)-date(2022,1,1)).days/365.25; c=(tv/tc)**(1/y)-1
    l=[]
    l.append("# 100 萬資金最佳化配置 — 2022~2025 回測報告\n")
    l.append(f"> 📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}  FinMind+TWSE\n")
    l.append("## 📋 配置\n")
    l.append("### G1 核心權值池 (500K) HYBRID\n")
    l.append("| 標的 | 策略 | 配置 |\n|------|------|------|\n")
    for s,st,a in G1_STOCKS: l.append(f"| {s} | {st} | {n(a)} |\n")
    l.append(f"\n### G2 法人動能池 (500K)\n")
    l.append(f"- 市值前{G2_TOP_N_STOCKS}大, 🐟 {G2_FISH_DAYS}d/≥{G2_FISH_MIN_SCORE}分, 每日動能\n")
    l.append(f"- 持有{G2_TOP_N}檔, 金字塔 {n(G2_BASE_SIZE)}→+{G2_PYRAMID_ADD:.0%}+{n(G2_ADD_SIZE)}→{n(G2_MAX_POSITION)}\n")
    l.append(f"- 停損{G2_STOP_LOSS:.0%} / 回落{G2_TRAILING_PCT:.0%} / 停利{G2_TAKE_PROFIT:.0%}\n\n")
    l.append("---\n## 📊 合併績效\n")
    l.append(f"| 指標 | 數值 |\n|------|------|\n")
    l.append(f"| 總投入 | {n(tc)} |\n| **終值** | **{n(tv)}** |\n| **損益** | **{n(tpnl)} ({p(tr)})** |\n| **年化** | **{p(c)}** |\n\n")
    l.append("## 🏆 各池\n")
    l.append("| 池 | 初始 | 終值 | 損益 | 報酬 |\n|------|------|------|------|------|\n")
    l.append(f"| G1 核心 | {n(G1_CAPITAL)} | {n(g1['final_value'])} | {n(g1['total_pnl'])} | {p(g1['total_return'])} |\n")
    l.append(f"| G2 動能 | {n(G2_CAPITAL)} | {n(g2['final_value'])} | {n(g2['total_pnl'])} | {p(g2['total_return'])} |\n")
    l.append(f"| **合計** | **{n(tc)}** | **{n(tv)}** | **{n(tpnl)}** | **{p(tr)}** |\n")
    wr=g2['wins']/(g2['wins']+g2['losses']) if (g2['wins']+g2['losses'])>0 else 0
    l.append(f"| G2 勝率 {wr:.1%} | 交易 {g2['total_sells']}筆 | MaxDD {g2['max_drawdown_pct']:.2%} |\n")
    l.append("\n## 📅 年度\n")
    l.append("| 年 | G1年底 | G1報酬 | G2年底 | G2報酬 | 合計 | 報酬 |\n|-----|-------|-------|-------|-------|-------|-------|\n")
    g1m=g1.get("monthly_records",[]); g2e=g2.get("equity_curve",[]); g2y={}
    for e in g2e:
        y_=int(e["date"][:4]); g2y[y_]=e["total_equity"]
    for yr in range(2022,2026):
        g1y=[r for r in g1m if r["date"].year==yr]; g1e=g1y[-1]["value"] if g1y else 0
        g1py=[r for r in g1m if r["date"].year==yr-1]; g1s=g1py[-1]["value"] if g1py else 0
        g1ypr=(g1e-g1s)/g1s if g1s>0 else (g1e/G1_CAPITAL-1 if yr==2022 else 0)
        g2e_=g2y.get(yr,0); g2p=g2y.get(yr-1,G2_CAPITAL); g2ypr=(g2e_-g2p)/g2p if g2p>0 else 0
        ts=g1s+g2p; te=g1e+g2e_; tr_=(te-ts)/ts if ts>0 else 0
        l.append(f"| {yr} | {n(g1e)} | {p(g1ypr)} | {n(g2e_)} | {p(g2ypr)} | {n(te)} | {p(tr_)} |\n")
    l.append("\n## 📝 G2 交易 (30筆)\n")
    l.append("| 日期 | 動作 | 股票 | 股數 | 價格 | 損益 | 原因 |\n|------|------|------|------|------|------|------|\n")
    for t in g2["trade_log"][-30:]:
        ps_=f"NT${t['pnl']:+,.0f}" if t["action"]=="SELL" and t.get("pnl",0)!=0 else "-"
        l.append(f"| {t['date']} | {t['action']:5s} | {t['stock']} | {t.get('shares',0):>5d} | NT${t['price']:>7.1f} | {ps_:>12s} | {t.get('reason','')} |\n")
    if len(g2["trade_log"])>30: l.append(f"| ... {len(g2['trade_log'])}筆 |\n")
    l.append("\n---\n⚠️ 過去績效不代表未來獲利。已計手續費+稅。未計滑價/股利/MA240過濾。\n")
    return "".join(l)

if __name__=="__main__":
    print(60*"="+"\n📊 100 萬資金 (2022~2025)\n"+60*"=")
    print(f"   G1: {G1_CAPITAL:,}  G2: {G2_CAPITAL:,}  計: {G1_CAPITAL+G2_CAPITAL:,}")
    dl=finmind_login()
    print("\n📥 G1...")
    g1d={}
    for s,_,_ in G1_STOCKS:
        df=load_price(s,dl,G1_CACHE); g1d[s]=df; print(f"  {s}: {len(df)}天")
    g1r=sim_g1(g1d)
    print("\n📥 G2 (既有快取)...")
    sids=get_sids(); print(f"   {len(sids)}檔")
    g2d={}
    for i,s in enumerate(sids):
        cf=G2_CACHE/f"{s}.pkl"
        if cf.exists():
            df=pickle.loads(cf.read_bytes())
            if not df.empty and df["date"].max()>=pd.Timestamp(END_DATE)-timedelta(days=7):
                g2d[s]=df
        if (i+1)%100==0: print(f"   {i+1}/{len(sids)} ({len(g2d)})")
    ad_=sorted(set(d.date() if hasattr(d,"date") else d for df in g2d.values() if not df.empty for d in df["date"]))
    print(f"   交易日: {len(ad_)}")
    print("📥 TWSE..."); twse=fetch_twse_inst(set(ad_)); g2d=merge_inst(g2d,twse)
    print("🔍 低吃分數..."); fs=pre_fish(g2d); print(f"   {len(fs)}檔")
    g2r=sim_g2(g2d,fs)
    r=report(g1r,g2r); print("\n"+60*"="+"\n"+r)
    with open("回溯_100萬_2022_2025.MD","w",encoding="utf-8") as f: f.write(r)
    print(f"\n✅ 回溯_100萬_2022_2025.MD")
