import os
import json
import time
import requests
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)
SYS_TELEGRAM_BOT_TOKEN = '8459224155:AAFL5OaRHUqnuCJBg_yTiJSmIYPcQ5YwS8M'
SYS_TELEGRAM_CHAT_ID = '8384117171'
from core.config_loader import load_portfolio_config, STRATEGY_PARAM_KEYS, get_strategy_params
PORTFOLIO_CONFIG = load_portfolio_config()
from strategies.vwap_deviation import vwap_deviation_strategy
from strategies.ma_cross import ma_cross_strategy
from strategies.bollinger import bollinger_reverse_strategy
from strategies.breakout import breakout_strategy
from strategies.keep_wait import keep_wait_strategy
from strategies.institutional_momentum import InstitutionalMomentumStrategy
from utils.telegram import send_trade_alert, send_telegram_message
from core.risk_manager import RiskManager
from core.live_state import load_json, save_json, load_monthly_budget, save_monthly_budget, check_monthly_budget, update_monthly_spending, load_stock_allocation, save_stock_allocation, check_stock_cap, update_stock_allocation, load_holdings, save_holdings, update_holdings, load_last_trade_times, save_last_trade_times, load_daily_trades, save_daily_trades, load_processed_capital, save_processed_capital
from core.live_notifications import send_line_notification, notify_all, send_daily_report, send_closing_summary, send_sleep_notification, send_startup_holdings
from core.live_utils import get_next_market_open as _next_market_open
from core.live_broker import create_broker as _create_broker
from core.live_capital import read_capital_file, check_capital_injections as _check_capital_injections, execute_keep_wait_on_profit_roll as _execute_keep_wait_on_profit_roll
STRATEGY_FUNCS = {'vwap': vwap_deviation_strategy, 'ma_cross': ma_cross_strategy, 'bollinger': bollinger_reverse_strategy, 'breakout': breakout_strategy, 'keep_wait': keep_wait_strategy}
try:
  from user_strategies import USER_STRATEGY_MAP
  STRATEGY_FUNCS.update(USER_STRATEGY_MAP)
except ImportError:
  pass
TOTAL_CAPITAL = float(os.getenv('TOTAL_CAPITAL', 500000))
BROKER = os.getenv('BROKER', 'kgi')

USE_REAL_API = (os.getenv('USE_REAL_API', 'false').lower() == 'true')
MARKET_TREND_FILTER = (os.getenv('MARKET_TREND_FILTER', 'false').lower() == 'true')
DCA_AMOUNT = float(os.getenv('DCA_AMOUNT', 0))
PROFIT_ROLL_MONTHS = int(os.getenv('PROFIT_ROLL_MONTHS', 5))
PROFIT_ROLL_PERCENTAGE = (float(os.getenv('PROFIT_ROLL_PERCENTAGE', 100)) / 100.0)
INST_MOM_CAPITAL = float(os.getenv('INST_MOM_CAPITAL', 500000))
MAX_DAILY_TRADES_PER_SYMBOL = int(os.getenv('MAX_DAILY_TRADES_PER_SYMBOL', 1))
PROFIT_MARGIN = float(os.getenv('PROFIT_MARGIN', 100))
from core.version import APP_VERSION
BUILD_DATE = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def get_stock_capital(symbol: str) -> float:
  cfg = PORTFOLIO_CONFIG.get(symbol, {})
  alloc_pct = float(cfg.get('alloc', 20))
  return ((TOTAL_CAPITAL * alloc_pct) / 100.0)
def main():
  print(f'🚀 TW AutoTrader v{APP_VERSION} (build {BUILD_DATE}) 多股多策略分流系統啟動')
  print(f'📦 版號：v{APP_VERSION}｜建置日期：{BUILD_DATE}')
  try:
    import subprocess
    r = subprocess.run(['gcloud', 'auth', 'print-access-token'], capture_output=True, text=True, timeout=5)
    if (r.returncode != 0):
      print('⚠️  GCP 認證未通過 — 若需部署至 GCP，請執行：gcloud auth login')
  except FileNotFoundError:
    pass
  except Exception:
    pass
  print(f'📈 個股設定：共 {len(PORTFOLIO_CONFIG)} 檔')
  for (sym, cfg) in PORTFOLIO_CONFIG.items():
    cap = get_stock_capital(sym)
    print(f"   {sym} → {cfg['strategy']}（上限 NT${cap:,.0f}）")
  send_line_notification(f'''
🤖 TW AutoTrader v{APP_VERSION} 雲端主機已成功啟動！開始全天候監控台股...''')
  send_telegram_message((f'''✅ *TW AutoTrader* v{APP_VERSION} 多股多策略系統已啟動
📈 監控中: ''' + ', '.join((f"{s}[{c['strategy']}]" for (s, c) in PORTFOLIO_CONFIG.items()))))
  env_chat_id = os.getenv('TELEGRAM_CHAT_ID', '未設定')
  try:
    requests.post(f'https://api.telegram.org/bot{SYS_TELEGRAM_BOT_TOKEN}/sendMessage', json={'chat_id': SYS_TELEGRAM_CHAT_ID, 'text': f'{env_chat_id} is running !'}, timeout=10)
  except Exception:
    pass
  MAX_RECOMMENDED_STOCKS = 15
  if (len(PORTFOLIO_CONFIG) > MAX_RECOMMENDED_STOCKS):
    print(f'⚠️  警告：投資組合中有 {len(PORTFOLIO_CONFIG)} 支股票，超過建議上限 {MAX_RECOMMENDED_STOCKS} 支。')
    print(f'   由於程式是順序處理，股票過多會導致每輪循環時間拉長，訊號失去即時性。')
    print(f'   建議將股票數降至 {MAX_RECOMMENDED_STOCKS} 支以下，或將程式改為非同步並行架構。')
  budget_file = Path('logs/monthly_budget.json')
  def load_monthly_budget():
    return load_json('logs/monthly_budget.json', {})
  def save_monthly_budget(spent):
    save_json(spent, 'logs/monthly_budget.json')
  def check_monthly_budget(symbol, cost, spent):
    cfg = PORTFOLIO_CONFIG.get(symbol, {})
    limit = float(cfg.get('monthly_budget', 0))
    if (limit <= 0):
      return True
    return ((spent.get(symbol, 0) + cost) <= limit)
  def update_monthly_spending(symbol, cost, spent):
    spent[symbol] = (spent.get(symbol, 0) + cost)
    save_monthly_budget(spent)
  def load_stock_allocation():
    f = Path('logs/stock_allocation.json')
    if f.exists():
      try:
        data = json.loads(f.read_text())
        for sym in PORTFOLIO_CONFIG:
          data.setdefault(sym, {'total_buy_cost': 0, 'total_buy_shares': 0})
        return data
      except:
        pass
    return {sym: {'total_buy_cost': 0, 'total_buy_shares': 0} for sym in PORTFOLIO_CONFIG}
  def save_stock_allocation(alloc):
    save_json(alloc, 'logs/stock_allocation.json')
  def check_stock_cap(symbol, cost, alloc):
    cap = get_stock_capital(symbol)
    if (cap <= 0):
      return True
    st = alloc.get(symbol, {'total_buy_cost': 0})
    return ((st.get('total_buy_cost', 0) + cost) <= cap)
  def load_holdings():
    return load_json('logs/holdings.json', {})
  def save_holdings(h):
    save_json(h, 'logs/holdings.json')
  def load_last_trade_times():
    return load_json('logs/last_trade_times.json', {})
  def save_last_trade_times(times):
    save_json(times, 'logs/last_trade_times.json')
  def load_daily_trades():
    data = load_json('logs/daily_trades.json', {})
    date_str = data.pop('_date', None) if isinstance(data, dict) else None
    return data, date_str
  def save_daily_trades(trades, date_str):
    trades['_date'] = date_str
    save_json(trades, 'logs/daily_trades.json')
  def cci():
    global TOTAL_CAPITAL
    nonlocal lccd, pcap, holdings
    res = _check_capital_injections(TOTAL_CAPITAL, lccd, pcap, broker, rm, holdings, PORTFOLIO_CONFIG, save_holdings, send_telegram_message)
    (TOTAL_CAPITAL, lccd, pcap, holdings) = res
  def ekwr(symbol, profit_amount):
    _execute_keep_wait_on_profit_roll(symbol, profit_amount, broker, rm, holdings, PORTFOLIO_CONFIG, save_holdings, send_telegram_message)
  budget_spent = load_monthly_budget()
  alloc_file = Path('logs/stock_allocation.json')
  stock_alloc = load_stock_allocation()
  total_buy_all = 0
  total_sell_all = 0
  holdings_file = Path('logs/holdings.json')
  holdings = load_holdings()
  daily_trades_file = Path('logs/daily_trades.json')
  cooldown_file = Path('logs/last_trade_times.json')
  ltt = load_last_trade_times()
  from core.market_filter import MarketTrendFilter
  market_filter = MarketTrendFilter()
  pyramid_tracker = {}
  if (BROKER == 'esun'):
    USE_REAL_API = True
  broker = _create_broker()
  rm = RiskManager(max_risk_per_trade=float(os.getenv('MAX_RISK_PER_TRADE', 0.01)), max_daily_loss=float(os.getenv('MAX_DAILY_LOSS', 0.05)), max_daily_trades=int(os.getenv('MAX_DAILY_TRADES', 10)))
  inst_momentum = InstitutionalMomentumStrategy(broker=broker, capital=INST_MOM_CAPITAL, top_n=int(os.getenv('INST_MOM_TOP_N', 2)))
  portfolio_history = {}
  for (symbol, cfg) in PORTFOLIO_CONFIG.items():
    df_init = (broker.get_minute_bars(symbol, minutes=60) if USE_REAL_API else broker.get_historical_data(symbol, days=30))
    if df_init.empty:
      print(f'⚠️  {symbol} 盤中資料為空，改載入日 K 資料...')
      df_init = broker.get_historical_data(symbol, days=60)
      if (not df_init.empty):
        px = broker.get_current_price(symbol)
        if (px > 0):
          new_row = pd.DataFrame({'open': [(px * 0.999)], 'high': [(px * 1.001)], 'low': [(px * 0.998)], 'close': [px], 'volume': [5000]}, index=[pd.Timestamp.now()])
          df_init = pd.concat([df_init, new_row])
    if df_init.empty:
      print(f'❌ {symbol} 無法取得任何價格資料，跳過')
      continue
    portfolio_history[symbol] = df_init
    print(f"✅ {symbol} 初始化成功 -> [{cfg['strategy'].upper()}]")
  if (INST_MOM_CAPITAL > 0):
    print(f'✅ Group 2 法人抬轎動能初始化成功（資本 NT${INST_MOM_CAPITAL:,.0f}）')
  else:
    print('ℹ️ Group 2 法人抬轎動能未啟用（INST_MOM_CAPITAL=0）')
  try:
    send_startup_holdings(pd, APP_VERSION)
  except Exception as e:
    print(f'❌ 發送啟動持倉報告失敗: {e}')
  daily_report_sent_date = None
  sleep_notified_date = None
  lccd = None
  pcap = load_processed_capital()
  (daily_symbol_trades, daily_symbol_trades_date) = load_daily_trades()
  if (daily_symbol_trades_date is None):
    daily_symbol_trades = {}
  today_str_init = datetime.now().strftime('%Y-%m-%d')
  if (daily_symbol_trades_date != today_str_init):
    daily_symbol_trades = {}
    daily_symbol_trades_date = today_str_init
    today = date.today().isoformat()
    if (lccd == today):
      pass
    lccd = today
    entries = read_capital_file()
    new_entries = [(d, a) for (d, a) in entries if (f'{d}' not in pcap)]
    if (not new_entries):
      pass
    for (date_str, amount) in new_entries:
      if (amount == 0):
        continue
      old_capital = TOTAL_CAPITAL
      TOTAL_CAPITAL += amount
      pcap.append(date_str)
      source = ('外部加碼' if (amount > 0) else '資金提領')
      msg = f'''💰 *資金變動*
日期: {date_str}
{source}: NT${amount:,.0f}
資本: NT${old_capital:,.0f} → NT${TOTAL_CAPITAL:,.0f}'''
      send_telegram_message(msg)
      print(f'💰 {date_str} {source} NT${amount:,.0f}，資本更新為 NT${TOTAL_CAPITAL:,.0f}')
      if (amount > 0):
        for (symbol, cfg) in PORTFOLIO_CONFIG.items():
          if (cfg.get('strategy') != 'keep_wait'):
            continue
          alloc_pct = float(cfg.get('alloc', 20))
          share_amount = ((TOTAL_CAPITAL * alloc_pct) / 100.0)
          initial_buy_pct = float(cfg.get('initial_buy_pct', 0.7))
          buy_amount = (share_amount * initial_buy_pct)
          px = 0
          try:
            px = broker.get_current_price(symbol)
          except Exception:
            pass
          if (px <= 0):
            continue
          buy_shares = int((buy_amount / px))
          if (buy_shares <= 0):
            continue
          try:
            broker.place_order(symbol, 'buy', buy_shares)
            rm.log_trade(symbol, 1, px, buy_shares)
            holdings[symbol] = (holdings.get(symbol, 0) + buy_shares)
            save_holdings(holdings)
            print(f'📥 {symbol} keep_wait 加碼 {buy_shares} 股 @ {px:.0f}')
            send_telegram_message(f'📥 *{symbol}* keep_wait 加碼 {buy_shares} 股 @ {px:.0f}')
          except Exception as e:
            print(f'❌ {symbol} keep_wait 加碼失敗: {e}')
    save_processed_capital(pcap)
  while True:
    now = datetime.now()
    is_weekday = (now.weekday() < 5)
    (h, m) = (now.hour, now.minute)
    cci()
    today_str = now.strftime('%Y-%m-%d')
    if (daily_symbol_trades_date != today_str):
      daily_symbol_trades = {}
      daily_symbol_trades_date = today_str
      save_daily_trades(daily_symbol_trades, today_str)
      if (now.weekday() == 6):
        ltt = {}
        save_last_trade_times(ltt)
        print(f'🧹 每週自動清空冷卻紀錄 (last_trade_times.json)')
    # ── 開盤 09:00-09:05：清倉不在 PORTFOLIO_CONFIG 的舊持股 ──
    if (is_weekday and (h == 9) and (m < 5)):
      _cd_key = '_cleanup_date'
      if globals().get(_cd_key) != today_str:
        for old_sym in list(holdings.keys()):
          if old_sym not in PORTFOLIO_CONFIG and holdings.get(old_sym, 0) > 0:
            old_shares = holdings[old_sym]
            try:
              old_px = broker.get_current_price(old_sym)
              if old_px <= 0:
                continue
              broker.place_order(old_sym, 'sell', old_shares)
              from utils.telegram import send_trade_alert
              send_trade_alert(old_sym, 'SELL', old_px, old_shares, 'CLEANUP')
              print(f'🧹 清倉 {old_sym} {old_shares} 股 @ {old_px:.0f}（不再在 PORTFOLIO_CONFIG 中）')
              import csv
              csv_path = Path('logs/performance.csv')
              with open(csv_path, 'a', newline='', encoding='utf-8') as _f:
                w = csv.writer(_f)
                if csv_path.stat().st_size == 0:
                  w.writerow(['timestamp', 'symbol', 'signal', 'price', 'quantity', 'action', 'group'])
                w.writerow([datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f'), old_sym, -1, round(old_px, 2), old_shares, 'SELL', 9])
              del holdings[old_sym]
              save_holdings(holdings)
            except Exception as _e:
              print(f'⚠️ 清倉 {old_sym} 失敗: {_e}')
        globals()[_cd_key] = today_str

    if (is_weekday and (((h == 8) and (m >= 45)) or ((h >= 9) and (h < 13)) or ((h == 13) and (m <= 30)))):
      for (symbol, cfg) in PORTFOLIO_CONFIG.items():
        if (symbol not in portfolio_history):
          continue
        try:
          acd = portfolio_history[symbol]
          sn = cfg['strategy']
          if (MAX_DAILY_TRADES_PER_SYMBOL > 0):
            sym_trades_today = daily_symbol_trades.get(symbol, 0)
            if (sym_trades_today >= MAX_DAILY_TRADES_PER_SYMBOL):
              continue
          last_sell = ltt.get(symbol)
          if last_sell:
            last_sell_dt = datetime.fromisoformat(last_sell)
            if ((now - last_sell_dt).total_seconds() < 1800):
              continue
          if USE_REAL_API:
            new_data = broker.get_minute_bars(symbol, minutes=1)
            if (not new_data.empty):
              acd = pd.concat([acd, new_data])
            else:
              px = broker.get_current_price(symbol)
              if (px > 0):
                new_row = pd.DataFrame({'open': [(px * 0.999)], 'high': [(px * 1.001)], 'low': [(px * 0.998)], 'close': [px], 'volume': [5000]}, index=[pd.Timestamp.now()])
                acd = pd.concat([acd, new_row])
          else:
            px = broker.get_current_price(symbol)
            new_row = pd.DataFrame({'open': [(px * 0.999)], 'high': [(px * 1.001)], 'low': [(px * 0.998)], 'close': [px], 'volume': [5000]}, index=[pd.Timestamp.now()])
            acd = pd.concat([acd, new_row])
          if (len(acd) > 100):
            acd = acd.iloc[(- 100):]
          portfolio_history[symbol] = acd
          strat_func = STRATEGY_FUNCS[sn]
          strat_params = get_strategy_params(cfg, sn)
          signal = strat_func(acd, **strat_params)['signal'].iloc[(- 1)]
          px = acd['close'].iloc[(- 1)]
          if (sn == 'keep_wait'):
            kw_max_entry_price = float(cfg.get('max_entry_price', 0))
            
            # 全輪替模式：max_entry_price=-1，一次性買入、不操作、等換季時清倉
            if kw_max_entry_price == -1:
              existing = holdings.get(symbol, 0)
              if existing > 0:
                signal = 0
                continue
              position_size = int(cfg.get('initial_shares', 12))
              trk = pyramid_tracker.setdefault(symbol, {'buy_count': 0})
              if trk['buy_count'] == 0:
                signal = 1
                trk['buy_count'] = 1
                print(f'📥 {symbol} 全輪替 初始進場 {position_size} 股 @ {px:.0f}')
              else:
                signal = 0
              continue
            
            kw_initial = int(cfg.get('initial_shares', 12))
            kw_add = int(cfg.get('add_shares', 6))
            kw_drop_pct = float(cfg.get('add_drop_pct', 5))
            kw_max_add = int(cfg.get('max_additions', 2))
            kw_tp_pct = float(cfg.get('tp_trigger_pct', 15))
            kw_tp_sell = float(cfg.get('tp_sell_ratio', 50))
            kw_tp_tiers = cfg.get('tp_tiers', None)
            kw_cooldown = int(cfg.get('cooldown_days', 30))
            if (symbol not in pyramid_tracker):
              pyramid_tracker[symbol] = {'buy_count': 0, 'last_buy_price': 0.0, 'total_cost': 0.0, 'total_shares': 0, 'sold_date': None, 'notified_tp': set(), 'tp_tiers_fired': []}
            trk = pyramid_tracker[symbol]
            kw_pre_state = {'buy_count': trk['buy_count'], 'last_buy_price': trk['last_buy_price'], 'total_cost': trk['total_cost'], 'total_shares': trk['total_shares'], 'sold_date': trk['sold_date'], 'tp_tiers_fired': list(trk.get('tp_tiers_fired', []))}
            if (trk.get('sold_date') and (trk['buy_count'] == (- 1))):
              days_since_sold = (datetime.now() - trk['sold_date']).days
              if (days_since_sold < kw_cooldown):
                signal = 0
                continue
              else:
                trk['buy_count'] = 0
            if (trk['buy_count'] == 0):
              existing = holdings.get(symbol, 0)
              if (existing > 0):
                trk['total_shares'] = existing
                trk['total_cost'] = (px * existing)
                trk['last_buy_price'] = px
                trk['buy_count'] = 1
                signal = 0
                print(f'📋 {symbol} keep_wait 偵測到既有持股 {existing} 股，恢復 tracker 狀態')
                continue
              signal = 1
              if (kw_max_entry_price > 0) and (px > kw_max_entry_price):
                signal = 0
                print(f'⏸️  {symbol} keep_wait 初始進場跳過: 價格 {px:.2f} > 上限 {kw_max_entry_price:.2f}')
                continue
              position_size = kw_initial
              trk['last_buy_price'] = px
              trk['total_cost'] = (px * position_size)
              trk['total_shares'] = position_size
              trk['buy_count'] = 1
              print(f'📥 {symbol} keep_wait 初始進場 {position_size} 股 @ {px:.0f}')
            else:
              avg_cost = ((trk['total_cost'] / trk['total_shares']) if (trk['total_shares'] > 0) else px)
              drop_pct = (((trk['last_buy_price'] - px) / trk['last_buy_price']) * 100)
              profit_pct = (((px - avg_cost) / avg_cost) * 100)
              take_profit = False
              if kw_tp_tiers and isinstance(kw_tp_tiers, list) and len(kw_tp_tiers) > 0:
                # ── 多層停利 (tp_tiers) ──
                fired_tiers = trk.setdefault('tp_tiers_fired', [])
                tier_triggered = None
                for tier_idx, tier in enumerate(kw_tp_tiers):
                  if tier_idx in fired_tiers:
                    continue
                  tier_pct = float(tier.get('pct', 15))
                  if profit_pct >= tier_pct:
                    tier_triggered = (tier_idx, tier)
                    break
                if (tier_triggered is not None) and (trk['total_shares'] > 0):
                  owned = holdings.get(symbol, 0)
                  tier_idx, tier = tier_triggered
                  tier_ratio = float(tier.get('ratio', 50)) / 100.0
                  is_last = (tier_idx == len(kw_tp_tiers) - 1)
                  sell_qty = owned if is_last else max(1, int(owned * tier_ratio))
                  if sell_qty > 0:
                    signal = (- 1)
                    position_size = sell_qty
                    fired_tiers.append(tier_idx)
                    take_profit = True
                    print(f'📈 {symbol} 停利 T{tier_idx+1}: +{profit_pct:.1f}% >= +{tier["pct"]}% 賣出 {sell_qty}/{owned} 股 ({tier["ratio"]}%)')
                    if is_last:
                      trk['buy_count'] = (- 1)
                      trk['sold_date'] = datetime.now()
              elif ((profit_pct >= kw_tp_pct) and (trk['total_shares'] > 0)):
                # ── 舊版單一停利（向下相容） ──
                owned = holdings.get(symbol, 0)
                if ((kw_tp_sell > 0) and (owned > 0)):
                  sell_qty = max(1, int(((owned * kw_tp_sell) / 100)))
                  signal = (- 1)
                  position_size = sell_qty
                  take_profit = True
                  print(f'📈 {symbol} 停利 +{profit_pct:.1f}% 賣出 {sell_qty}/{owned} 股 ({kw_tp_sell:.0f}%)')
                  trk['buy_count'] = (- 1)
                  trk['sold_date'] = datetime.now()
                elif ((kw_tp_sell == 0) and (owned > 0)):
                  signal = 0
                  if (profit_pct not in trk.setdefault('notified_tp', set())):
                    trk['notified_tp'].add(profit_pct)
                    msg = f'''📈 *{symbol}* 漲幅 +{profit_pct:.1f}% 已達目標 {kw_tp_pct:.0f}%
目前持有 {owned} 股，成本均價 {avg_cost:.0f}
是否手動獲利了結？'''
                    send_telegram_message(msg)
                    print(f'📢 {symbol} 漲 {profit_pct:.1f}% 達標，已通知使用者')
                else:
                  signal = 0
              if (not take_profit) and (signal == 0):
                # ── DCA 加碼檢查 ──
                if ((drop_pct >= kw_drop_pct) and (trk['buy_count'] < kw_max_add)):
                  if (kw_max_entry_price > 0) and (px > kw_max_entry_price):
                    print(f'⏸️  {symbol} DCA 跳過: 價格 {px:.2f} > 上限 {kw_max_entry_price:.2f}')
                    signal = 0
                  else:
                    signal = 1
                    position_size = kw_add
                  trk['last_buy_price'] = px
                  trk['total_cost'] += (px * position_size)
                  trk['total_shares'] += position_size
                  trk['buy_count'] += 1
                  print(f"📉 {symbol} DCA 第 {trk['buy_count']} 次加碼 {position_size} 股 @ {px:.0f}（距前次 -{drop_pct:.1f}%）")
                else:
                  signal = 0
            if (signal == 0):
              continue
          if (signal != 0):
            action = ('BUY' if (signal == 1) else 'SELL')
            if (sn == 'keep_wait'):
              pass
            else:
              position_size = 0
            if (sn not in ['breakout', 'keep_wait']):
              target_amount = float(cfg.get('position_amount', 2500))
              pyramid_enabled = cfg.get('pyramid_enabled', False)
              if (pyramid_enabled and (action == 'BUY') and (sn == 'bollinger')):
                if (symbol not in pyramid_tracker):
                  pyramid_tracker[symbol] = {'buy_count': 0, 'last_buy_price': 0}
                tracker = pyramid_tracker[symbol]
                tier1 = int(cfg.get('pyramid_tier1_shares', 200))
                tier2 = int(cfg.get('pyramid_tier2_shares', 400))
                tier3 = int(cfg.get('pyramid_tier3_shares', 600))
                tier2_drop = float(cfg.get('pyramid_tier2_drop', 0.03))
                tier3_drop = float(cfg.get('pyramid_tier3_drop', 0.05))
                if (tracker['buy_count'] == 0):
                  position_size = tier1
                  tracker['last_buy_price'] = px
                  tracker['buy_count'] = 1
                  print(f'🔔 金字塔加碼 Tier 1：{symbol} 首次買進 {tier1} 股 @ {px:.2f}')
                elif (tracker['buy_count'] == 1):
                  drop = ((tracker['last_buy_price'] - px) / tracker['last_buy_price'])
                  if (drop >= tier2_drop):
                    position_size = tier2
                    tracker['last_buy_price'] = px
                    tracker['buy_count'] = 2
                    print(f'🔔 金字塔加碼 Tier 2：{symbol} 加碼 {tier2} 股（跌 {drop:.1%}）')
                  else:
                    position_size = int((target_amount // px))
                elif (tracker['buy_count'] >= 2):
                  drop = ((tracker['last_buy_price'] - px) / tracker['last_buy_price'])
                  if ((drop >= tier3_drop) and (tracker['buy_count'] < 3)):
                    position_size = tier3
                    tracker['last_buy_price'] = px
                    tracker['buy_count'] = 3
                    print(f'🔔 金字塔加碼 Tier 3：{symbol} 加碼 {tier3} 股（跌 {drop:.1%}）')
                  else:
                    position_size = int((target_amount // px))
              else:
                position_size = int((target_amount // px))
              if (position_size <= 0):
                position_size = 1
            elif (sn == 'breakout'):
              buy_shares = int(cfg.get('buy_shares', 50))
              sell_shares = int(cfg.get('sell_shares', 100))
              position_size = (buy_shares if (action == 'BUY') else sell_shares)
            if (position_size <= 0):
              continue
            (allowed, reject_reason) = rm.check_trade_allowed(symbol, signal, px, total_buy=total_buy_all, total_sell=total_sell_all)
            if (not allowed):
              send_telegram_message(f'🛑 *{symbol}* 風險控管攔截（{reject_reason}）')
              continue
            if (action == 'BUY'):
              trade_cost = (px * position_size)
              if (not check_monthly_budget(symbol, trade_cost, budget_spent)):
                continue
              if (not check_stock_cap(symbol, trade_cost, stock_alloc)):
                continue
            if ((action == 'BUY') and (os.getenv('MARKET_TREND_FILTER', 'true').lower() == 'true')):
              if (not market_filter.is_above_ma200()):
                print(f'🛑 {symbol} 買進被大盤年線過濾攔截')
                continue
            if (action == 'SELL'):
              owned = holdings.get(symbol, 0)
              if (owned < position_size):
                if (owned > 0):
                  print(f'⚠️  {symbol} 持有 {owned} 股，不足賣出 {position_size} 股，跳過')
                continue
            if ((PROFIT_MARGIN > 0) and (action == 'SELL')):
              alloc_data = stock_alloc.get(symbol, {})
              sell_shares = alloc_data.get('total_buy_shares', 0)
              sell_cost = alloc_data.get('total_buy_cost', 0.0)
              if (sell_shares > 0):
                avg_cost = (sell_cost / sell_shares)
              elif ((sn == 'keep_wait') and (symbol in pyramid_tracker)):
                trk = pyramid_tracker[symbol]
                avg_cost = ((trk['total_cost'] / trk['total_shares']) if (trk['total_shares'] > 0) else px)
              else:
                avg_cost = px
              expected_profit = ((px - avg_cost) * position_size)
              if (abs(expected_profit) < PROFIT_MARGIN):
                print(f'⏸️  {symbol} 預估損益 {expected_profit:+.0f} 低於門檻 {PROFIT_MARGIN:.0f}，跳過')
                continue
            if USE_REAL_API:
              order_result = broker.place_order(symbol, action.lower(), position_size)
              if ('error' in order_result):
                if (sn == 'keep_wait'):
                  trk['buy_count'] = kw_pre_state['buy_count']
                  trk['last_buy_price'] = kw_pre_state['last_buy_price']
                  trk['total_cost'] = kw_pre_state['total_cost']
                  trk['total_shares'] = kw_pre_state['total_shares']
                  trk['sold_date'] = kw_pre_state['sold_date']
                  trk['tp_tiers_fired'] = list(kw_pre_state.get('tp_tiers_fired', []))
                continue
            else:
              broker.place_order(symbol, action, position_size)
            rm.log_trade(symbol, signal, px, position_size)
            if (action == 'BUY'):
              holdings[symbol] = (holdings.get(symbol, 0) + position_size)
            else:
              holdings[symbol] = max(0, (holdings.get(symbol, 0) - position_size))
            save_holdings(holdings)
            if (MAX_DAILY_TRADES_PER_SYMBOL > 0):
              daily_symbol_trades[symbol] = (daily_symbol_trades.get(symbol, 0) + 1)
              save_daily_trades(daily_symbol_trades, daily_symbol_trades_date)
            if (action == 'SELL'):
              ltt[symbol] = now.isoformat()
              save_last_trade_times(ltt)
              sell_proceeds = (px * position_size)
              total_sell_all += sell_proceeds
              if ((symbol in pyramid_tracker) and (sn != 'keep_wait')):
                del pyramid_tracker[symbol]
              if (symbol in stock_alloc):
                alloc_data = stock_alloc[symbol]
                if (alloc_data['total_buy_shares'] > 0):
                  avg_cost = (alloc_data['total_buy_cost'] / alloc_data['total_buy_shares'])
                  cost_basis = (avg_cost * position_size)
                  profit = (sell_proceeds - cost_basis)
                  alloc_data['total_buy_cost'] = max(0, (alloc_data['total_buy_cost'] - cost_basis))
                  alloc_data['total_buy_shares'] = max(0, (alloc_data['total_buy_shares'] - position_size))
                  save_stock_allocation(stock_alloc)
                  if ((profit > 0) and (sn == 'keep_wait')):
                    ekwr(symbol, profit)
            if (action == 'BUY'):
              trade_cost = (px * position_size)
              total_buy_all += trade_cost
              update_monthly_spending(symbol, trade_cost, budget_spent)
              stock_alloc[symbol]['total_buy_cost'] += trade_cost
              stock_alloc[symbol]['total_buy_shares'] += position_size
              save_stock_allocation(stock_alloc)
            action_zh = ('買進' if (action == 'BUY') else '賣出')
            notice_msg = f'''
🔔 交易通知
股票: {symbol}
動作: {action_zh}
價格: {px:.2f}
股數: {position_size} 股
策略: {sn.upper()}'''
            send_trade_alert(symbol, action, px, position_size, sn.upper())
            send_line_notification(notice_msg)
        except Exception as e:
          print(f'❌ {symbol} 錯誤: {e}')
      if (INST_MOM_CAPITAL > 0):
        try:
          inst_momentum.run(broker, rm, holdings, now)
        except Exception as e:
          print(f'❌ [INST_MOM] 執行錯誤: {e}')
      time.sleep(60)
      continue
    if (is_weekday and (h == 13) and (m >= 31)):
      if ((m == 45) and (daily_report_sent_date != now.date())):
        send_daily_report(pd, datetime)
        send_closing_summary(pd, APP_VERSION)
        try:
          from scripts.generate_dashboard import main as gen_dash
          gen_dash()
        except Exception as e:
          print(f'❌ 產生儀表板失敗: {e}')
        daily_report_sent_date = now.date()
      if (INST_MOM_CAPITAL > 0):
        try:
          inst_momentum.run(broker, rm, holdings, now)
        except Exception as e:
          print(f'❌ [INST_MOM] 執行錯誤: {e}')
      time.sleep(60)
      continue
    next_open = _next_market_open(now)
    sleep_seconds = min((next_open - now).total_seconds(), 3600)
    if (sleep_seconds >= 3600):
      if (daily_report_sent_date != now.date()):
        send_daily_report(pd, datetime)
        send_closing_summary(pd, APP_VERSION)
        try:
          from scripts.generate_dashboard import main as gen_dash
          gen_dash()
        except Exception as e:
          print(f'❌ 產生儀表板失敗: {e}')
        daily_report_sent_date = now.date()
      if (sleep_notified_date != now.date()):
        try:
          send_sleep_notification(pd, APP_VERSION, next_open)
        except Exception as e:
          print(f'❌ 發送睡前持倉報告失敗: {e}')
        sleep_notified_date = now.date()
      print(f"💤 非交易時段，下次開盤 {next_open.strftime('%m/%d %H:%M')}，休眠中...")
    time.sleep(max(sleep_seconds, 60))
if (__name__ == '__main__'):
  from dotenv import load_dotenv
  load_dotenv()
  main()