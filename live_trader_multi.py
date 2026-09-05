# TW-AUTOTRADER v3.23 -- https://github.com/dinchentech/tw-autotrader (c) 2026 dinchentech
#【軟體使用與免責聲明】本軟體係依「現狀（AS-IS）」提供，不帶有任何形式的明示或暗示之保證（包括但不限於對適銷性、特定目的之適用性以及不侵權的暗示保證）。
# 開發團隊（或本公司）在任何情況下，均不對因使用或無法使用本軟體所引起的任何直接、間接、偶發、特殊、懲罰性或衍生性損失（包括但不限於利潤損失、業務中斷、資料遺失、設備損壞或電腦故障）承擔任何法律及賠償責任，亦不對任何第三方提出的索賠負責。
# 使用者須自行承擔使用本軟體之所有風險。
import os
import json
import time
import requests
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)
SYS_TELEGRAM_BOT_TOKEN = os.getenv('SYS_TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN', '')
SYS_TELEGRAM_CHAT_ID = os.getenv('SYS_TELEGRAM_CHAT_ID') or os.getenv('TELEGRAM_CHAT_ID', '')
from core.config_loader import load_portfolio_config, STRATEGY_PARAM_KEYS, get_strategy_params
PORTFOLIO_CONFIG = load_portfolio_config()
from strategies.vwap_deviation import vwap_deviation_strategy
from strategies.ma_cross import ma_cross_strategy
from strategies.bollinger import bollinger_reverse_strategy
from strategies.breakout import breakout_strategy
from strategies.keep_wait import keep_wait_strategy
from strategies.institutional_momentum import InstitutionalMomentumStrategy
from strategies.auto_sensing import auto_sensing_strategy, route_strategy
from utils.telegram import send_trade_alert, send_telegram_message
from core.risk_manager import RiskManager
from core.live_state import load_json, save_json, load_monthly_budget, save_monthly_budget, check_monthly_budget, update_monthly_spending, load_stock_allocation, save_stock_allocation, check_stock_cap, update_stock_allocation, load_holdings, save_holdings, update_holdings, load_last_trade_times, save_last_trade_times, load_daily_trades, save_daily_trades, load_processed_capital, save_processed_capital
from core.live_notifications import send_line_notification, notify_all, send_daily_report, send_closing_summary, send_sleep_notification, send_startup_holdings, send_rotation_cash_reminder
from core.live_utils import get_next_market_open as _next_market_open, resolve_fill, run_inst_momentum, sell_with_fill_check, notify_order_failure
from core.rotation_hold import is_rotation_buy, check_rotation_hold
from core.live_broker import create_broker as _create_broker
from core.live_capital import read_capital_file, check_capital_injections as _check_capital_injections, execute_keep_wait_on_profit_roll as _execute_keep_wait_on_profit_roll
STRATEGY_FUNCS = {'vwap': vwap_deviation_strategy, 'ma_cross': ma_cross_strategy, 'bollinger': bollinger_reverse_strategy, 'breakout': breakout_strategy, 'keep_wait': keep_wait_strategy, 'auto': auto_sensing_strategy}
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
  global TOTAL_CAPITAL
  # ── 單實例鎖：host 與 docker 共用 logs/ 掛載（同一 inode），第二個實例直接退出 ──
  #    檔案: logs/trader.lock；flock 隨程序結束自動釋放，無殘留問題
  #    退出碼 0 = 正常結束，避免觸發 docker restart 循環加重
  import fcntl
  _lock_file = open(str(Path('logs') / 'trader.lock'), 'w')
  try:
    fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
  except OSError:
    print('⚠️ 已有另一個實盤實例在運行，本實例退出（單實例鎖 logs/trader.lock）')
    raise SystemExit(0)
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
  ROTATE_MODE_VAL = int(os.getenv('ROTATE_MODE', '0'))
  ROTATE_TRADING_DAY_N = int(os.getenv('ROTATE_TRADING_DAY_N', '-1'))
  _rotate_labels = {0: '關閉', 1: '單排程 (1/4/7/10)', 2: '單排程 (2/5/8/11)', 3: '單排程 (3/6/9/12)', 4: '雙排程 (1+2)', 5: '雙排程 (2+3)'}
  print(f'🔄 全輪替模式：ROTATE_MODE={ROTATE_MODE_VAL}（{_rotate_labels.get(ROTATE_MODE_VAL, "未知")}）｜選股日: {"每月最後交易日" if ROTATE_TRADING_DAY_N == -1 else "每月第 " + str(ROTATE_TRADING_DAY_N) + " 個交易日"}')
  for (sym, cfg) in PORTFOLIO_CONFIG.items():
    cap = get_stock_capital(sym)
    print(f"   {sym} → {cfg['strategy']}（上限 NT${cap:,.0f}）")
  send_line_notification(f'''
🤖 TW AutoTrader v{APP_VERSION} 雲端主機已成功啟動！開始全天候監控台股...''')
  _startup_msg = (f'''✅ *TW AutoTrader* v{APP_VERSION} 多股多策略系統已啟動
⚙️ 啟動標記: {datetime.now().strftime('%Y%m%d-%H%M%S')}
🔄 全輪替: ROTATE_MODE={ROTATE_MODE_VAL}（{_rotate_labels.get(ROTATE_MODE_VAL, "未知")}）
📅 選股日: {"每月最後交易日" if ROTATE_TRADING_DAY_N == -1 else "每月第 " + str(ROTATE_TRADING_DAY_N) + " 個交易日"}
📈 監控中: ''' + ', '.join((f"{s}[{c['strategy']}]" for (s, c) in PORTFOLIO_CONFIG.items())))
  print(">>> STARTUP_MSG >>>", repr(_startup_msg))
  send_telegram_message(_startup_msg)
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
    _daily_mode = (cfg.get('strategy') != 'keep_wait')
    # v3.28: 除 keep_wait（signal=0，主程式管理買賣）外全用日K —
    # bollinger/vwap/ma_cross/user 策略回測皆日K；原用分鐘 bars 會讓
    # rolling(20) 變 20 分鐘，訊號隔天反轉亂買賣（2026-09-03 修正）
    if _daily_mode:
      df_init = broker.get_historical_data(symbol, days=260)
    else:
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
  try:
    send_rotation_cash_reminder(datetime.now().strftime('%Y-%m-%d'), broker, holdings,
                                PORTFOLIO_CONFIG, TOTAL_CAPITAL, send_telegram_message)
  except Exception as e:
    print(f'⚠️ 換股日現金提醒失敗: {e}')
  daily_report_sent_date = None
  sleep_notified_date = None
  lccd = None
  pcap = load_processed_capital()
  (daily_symbol_trades, daily_symbol_trades_date) = load_daily_trades()
  if (daily_symbol_trades_date is None):
    daily_symbol_trades = {}
  _order_fail_notified = {}   # {symbol: 'YYYY-MM-DD'} 下單失敗 TG 警示去重
  _risk_notified = {}         # {symbol: 'YYYY-MM-DD'} 風險控管攔截 TG 警示去重（每日一次）
  _buy_fill_notified = {}     # {symbol: 'YYYY-MM-DD'} 買入未補足 TG 警示去重（每日一次）
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
            rm.log_trade(symbol, 1, px, buy_shares, exclude_from_daily=True)
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
    if is_weekday and h == 8 and m >= 40:
      try:
        _cal_file = Path('config/taiwan_holidays.json')
        _need_update = True
        if _cal_file.exists():
          try:
            _cal_data = json.loads(_cal_file.read_text(encoding='utf-8'))
            _last_upd = _cal_data.get('_last_updated', '')
            if _last_upd:
              from datetime import datetime as _dt
              _age = (datetime.now() - _dt.strptime(_last_upd, '%Y-%m-%d %H:%M:%S')).days
              _need_update = _age > 30
          except Exception:
            pass
        if _need_update:
          try:
            import subprocess as _sp
            _r = _sp.run(['python', 'scripts/update_taiwan_holidays.py'], capture_output=True, text=True, timeout=60)
            if _r.returncode == 0:
              print(f'📅 休市日曆已自動更新')
            else:
              print(f'⚠️ 休市日曆更新失敗: {_r.stderr[:200]}')
          except Exception as _e:
            print(f'⚠️ 休市日曆更新異常: {_e}')
      except Exception:
        pass
      try:
        from dotenv import load_dotenv as _reload
        _reload(override=True)
        new_config = load_portfolio_config()
        removed = set(PORTFOLIO_CONFIG.keys()) - set(new_config.keys())
        PORTFOLIO_CONFIG.clear()
        PORTFOLIO_CONFIG.update(new_config)
        for sym in removed:
          portfolio_history.pop(sym, None)
          pyramid_tracker.pop(sym, None)
        for sym in new_config:
          if sym not in portfolio_history:
            # v3.28: 熱重載新標的比照初始化（除 keep_wait 外全用日K）
            _nm = (new_config[sym].get('strategy') != 'keep_wait')
            df_init = (broker.get_historical_data(sym, days=260) if _nm else
                       (broker.get_minute_bars(sym, minutes=60) if USE_REAL_API else broker.get_historical_data(sym, days=30)))
            if not df_init.empty:
              portfolio_history[sym] = df_init
              print(f'✅ {sym} 熱重載初始化成功')
        print(f'🔄 08:40 熱重載 .env 完成，目前監控 {len(PORTFOLIO_CONFIG)} 檔')
      except Exception as e:
        pass
    if (daily_symbol_trades_date != today_str):
      daily_symbol_trades = {}
      daily_symbol_trades_date = today_str
      save_daily_trades(daily_symbol_trades, today_str)
      if (now.weekday() == 6):
        ltt = {}
        save_last_trade_times(ltt)
        print(f'🧹 每週自動清空冷卻紀錄 (last_trade_times.json)')
    _rot_day_buys = set()
    # ── 開盤 09:00-09:05：清倉不在 PORTFOLIO_CONFIG 的舊持股 + 全輪替超額 trim ──
    if (is_weekday and (h == 9) and (m < 5)):
      _cd_key = '_cleanup_date'
      if globals().get(_cd_key) != today_str:
        try:
          _rot_pending = load_json('logs/rotation_pending.json', {})
          _is_rotation_day = (_rot_pending.get('buy_date') == today_str)
        except Exception:
          _is_rotation_day = False
        for old_sym in list(holdings.keys()):
          old_shares = holdings.get(old_sym, 0)
          if old_shares <= 0:
            continue
          if old_sym not in PORTFOLIO_CONFIG:
            try:
              old_px = broker.get_current_price(old_sym)
              if old_px <= 0:
                continue
              _filled, _order_fail_notified = sell_with_fill_check(broker, old_sym, old_shares, _order_fail_notified, today_str, send_telegram_message, '清倉')
              if _filled <= 0:
                continue
              old_shares = _filled
              rm.log_trade(old_sym, -1, old_px, old_shares, exclude_from_daily=True)
              send_trade_alert(old_sym, 'SELL', old_px, old_shares, 'CLEANUP')
              print(f'🧹 清倉 {old_sym} {old_shares} 股 @ {old_px:.0f}（不再在 PORTFOLIO_CONFIG 中）')
              _remaining = holdings.get(old_sym, 0) - old_shares
              if _remaining > 0:
                holdings[old_sym] = _remaining
              else:
                del holdings[old_sym]
              save_holdings(holdings)
              # v3.5: 清倉後同步扣減分帳本，避免舊累積成本擋下未來重新進場
              if old_sym in stock_alloc:
                stock_alloc[old_sym] = {'total_buy_cost': 0, 'total_buy_shares': 0}
                save_stock_allocation(stock_alloc)
                print(f'🧹 分帳本已重置 {old_sym} → 0')
              if old_sym in budget_spent:
                budget_spent.pop(old_sym, None)
                save_monthly_budget(budget_spent)
            except Exception as _e:
              print(f'⚠️ 清倉 {old_sym} 失敗: {_e}')
              _order_fail_notified = notify_order_failure(old_sym, _e, _order_fail_notified, today_str, send_telegram_message, action="清倉賣出")
          elif (_is_rotation_day and (float(PORTFOLIO_CONFIG[old_sym].get('max_entry_price', 0)) == -1)):
            try:
              _cfg_r = PORTFOLIO_CONFIG[old_sym]
              _alloc_pct = float(_cfg_r.get('alloc', 25))
              _target_amount = (TOTAL_CAPITAL * _alloc_pct) / 100.0
              _px_r = broker.get_current_price(old_sym)
              if _px_r <= 0:
                continue
              _target_shares = max(1, int(_target_amount / _px_r))
              _excess = old_shares - _target_shares
              if _excess > 0:
                _trim_filled, _order_fail_notified = sell_with_fill_check(broker, old_sym, _excess, _order_fail_notified, today_str, send_telegram_message, '超額 trim')
                if _trim_filled <= 0:
                  continue
                _excess = _trim_filled
                rm.log_trade(old_sym, -1, _px_r, _excess, exclude_from_daily=True)
                send_trade_alert(old_sym, 'SELL', _px_r, _excess, 'ROTATE_TRIM')
                holdings[old_sym] = old_shares - _excess
                save_holdings(holdings)
                if (old_sym in stock_alloc) and (stock_alloc[old_sym].get('total_buy_shares', 0) > 0):
                  _ad = stock_alloc[old_sym]
                  _avg = (_ad['total_buy_cost'] / _ad['total_buy_shares'])
                  _ad['total_buy_cost'] = max(0.0, (_ad['total_buy_cost'] - (_avg * _excess)))
                  _ad['total_buy_shares'] = max(0, (_ad['total_buy_shares'] - _excess))
                  save_stock_allocation(stock_alloc)
                print(f'✂️ 全輪替 trim {old_sym}: 超額 {_excess} 股 @ {_px_r:.0f}（目標 {_target_shares} 股）')
            except Exception as _e:
              print(f'⚠️ 全輪替 trim {old_sym} 失敗: {_e}')
              _order_fail_notified = notify_order_failure(old_sym, _e, _order_fail_notified, today_str, send_telegram_message, action="超額 trim 賣出")
        globals()[_cd_key] = today_str

    if (is_weekday and (((h == 8) and (m >= 45)) or ((h >= 9) and (h < 13)) or ((h == 13) and (m <= 30)))):
      for (symbol, cfg) in PORTFOLIO_CONFIG.items():
        if (symbol not in portfolio_history):
          continue
        try:
          acd = portfolio_history[symbol]
          sn = cfg['strategy']
          try:
            _rot_pending = load_json('logs/rotation_pending.json', {})
            _is_rotation_day = (_rot_pending.get('buy_date') == today_str)
          except Exception:
            _is_rotation_day = False
          _rot_buy = is_rotation_buy(cfg, _is_rotation_day, strategy=sn) and (os.getenv('ROTATION_BUY_DIRECT', '1') == '1')
          if (MAX_DAILY_TRADES_PER_SYMBOL > 0) and (not _rot_buy):
            sym_trades_today = daily_symbol_trades.get(symbol, 0)
            if (sym_trades_today >= MAX_DAILY_TRADES_PER_SYMBOL):
              continue
          last_sell = ltt.get(symbol)
          if last_sell and (not _rot_buy):
            last_sell_dt = datetime.fromisoformat(last_sell)
            if ((now - last_sell_dt).total_seconds() < 1800):
              continue
          if sn != 'keep_wait':
            # ── 日K模式（v3.28 起除 keep_wait 外全策略）：盤中價格合成當日K ──
            # （原 bollinger/vwap/ma_cross concat 分鐘 bars → rolling(20) 變 20 分鐘，
            #   訊號隔天反轉；以「交易日」為單位才與回測一致）
            px_now = broker.get_current_price(symbol)
            if px_now > 0:
              today_str_dt = now.strftime('%Y-%m-%d')
              acd = acd.copy()
              if not acd.empty and str(acd.index[-1])[:10] == today_str_dt:
                # 當日已有K → 更新 high/low/close
                acd.iloc[-1, acd.columns.get_loc('high')] = max(acd.iloc[-1]['high'], px_now)
                acd.iloc[-1, acd.columns.get_loc('low')] = min(acd.iloc[-1]['low'], px_now)
                acd.iloc[-1, acd.columns.get_loc('close')] = px_now
              else:
                new_row = pd.DataFrame({'open': [px_now], 'high': [px_now], 'low': [px_now], 'close': [px_now], 'volume': [0]}, index=[pd.Timestamp(now)])
                acd = pd.concat([acd, new_row])
            if (len(acd) > 260):
              acd = acd.iloc[(- 260):]
          elif USE_REAL_API:
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
          # SIGNAL_DEBUG（2026-09-03）：驗證 bollinger/vwap/ma_cross 訊號是否被分鐘資料污染
          # （acd = 日K + 當日分鐘 bars 混合 → rolling(20) 變 20 分鐘而非 20 日）
          if (os.getenv('SIGNAL_DEBUG', '0') == '1') and (signal != 0) and (sn in ('bollinger', 'vwap', 'ma_cross')):
            try:
              _tail = acd.tail(20)
              _span_min = (_tail.index[-1] - _tail.index[0]).total_seconds() / 60.0
              _freq = '日K' if _span_min > 60 * 24 else f'{_span_min:.0f}分鐘(懷疑污染)'
              print(f'🔍 SIGNAL_DEBUG {symbol} {sn} signal={signal} px={px:.0f} 最後20根跨度={_span_min:.0f}分 [{_freq}] 最後一根={acd.index[-1]}')
            except Exception as _dbg_e:
              print(f'🔍 SIGNAL_DEBUG {symbol} 失敗: {_dbg_e}')
          if (sn == 'keep_wait'):
            kw_max_entry_price = float(cfg.get('max_entry_price', 0))
            
            # 全輪替模式：max_entry_price=-1，依合併權重補足到目標股數（撞股加倍，與回測一致）
            if kw_max_entry_price == -1:
              alloc_pct = float(cfg.get('alloc', 25))
              target_amount = (TOTAL_CAPITAL * alloc_pct) / 100.0
              target_shares = max(1, int(target_amount / px)) if px > 0 else int(cfg.get('initial_shares', 12))
              existing = holdings.get(symbol, 0)
              if (symbol not in pyramid_tracker):
                pyramid_tracker[symbol] = {'buy_count': 0, 'last_buy_price': 0.0, 'total_cost': 0.0, 'total_shares': 0, 'sold_date': None}
              trk = pyramid_tracker[symbol]
              kw_pre_state = {'buy_count': trk['buy_count'], 'last_buy_price': trk['last_buy_price'], 'total_cost': trk['total_cost'], 'total_shares': trk['total_shares'], 'sold_date': trk['sold_date']}
              # 重啟後 tracker 丟失：從 holdings 恢復（2026-08-26 實盤 bug —
              # 全輪替自己的倉位被誤判成其他策略，每分鐘重複「跳過」通知）
              if trk['buy_count'] == 0 and existing > 0:
                trk['buy_count'] = 1
                trk['total_shares'] = existing
                trk['total_cost'] = px * existing
                trk['last_buy_price'] = px
                print(f'📋 {symbol} 全輪替 重啟恢復 tracker（既有持股 {existing} 股）')
              if (trk['buy_count'] > 0) and (not _is_rotation_day):
                signal = 0
                continue
              if symbol in _rot_day_buys:
                signal = 0
                continue
              # 跨策略防重疊（2026-08-25 規定）：其他策略已持有 → 通知+跳過
              # （全輪替管理的股票 max_entry_price=-1 → 自己的倉位 → 補足不變）
              from core.live_utils import should_skip_rotation_overlap as _skip_rot_overlap
              if _skip_rot_overlap(symbol, holdings, pyramid_tracker, send_telegram_message,
                                   is_rotation_managed=True):
                signal = 0
                continue
              position_size = max(0, target_shares - existing)
              if position_size <= 0:
                signal = 0
                continue
              if trk['buy_count'] == 0:
                trk['buy_count'] = 1
                trk['total_cost'] = px * position_size
                trk['total_shares'] = position_size
              else:
                trk['total_cost'] += px * position_size
                trk['total_shares'] += position_size
              trk['last_buy_price'] = px
              print(f'📥 {symbol} 全輪替 進場 {position_size} 股 @ {px:.0f}（目標 {target_shares} 股，既有 {existing} 股）')
              signal = 1
            if kw_max_entry_price != -1:
            
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
              # bollinger/vwap/ma_cross：與回測 simulate_portfolio 一致
              # 買入量 = 個股資金上限（alloc × TOTAL_CAPITAL）；滿倉不買；賣出 = 全賣
              # 滿倉判定：held ≥ target×(1-BUY_AMOUNT_OFFSET) 即視為足額（2026-09-01）
              alloc_pct = float(cfg.get('alloc', 12.5))
              target_amount = (TOTAL_CAPITAL * alloc_pct) / 100.0
              buy_offset = float(os.getenv('BUY_AMOUNT_OFFSET', '0.02'))
              if (action == 'BUY'):
                held = holdings.get(symbol, 0)
                target_shares = int((target_amount / px)) if px > 0 else 1
                if (held >= target_shares * (1 - buy_offset)):
                  print(f'⏸️  {symbol} 持倉 {held} ≥ 目標 {target_shares}×(1-{buy_offset:.0%})，不重複買入')
                  signal = 0
                  continue
                position_size = max(0, target_shares - held)
                if position_size <= 0:
                  position_size = 1
              else:
                position_size = int(holdings.get(symbol, 0))
              if (position_size <= 0):
                position_size = 1
            elif (sn == 'breakout'):
              buy_alloc_pct = float(cfg.get('alloc', 12.5))
              target_amount = (TOTAL_CAPITAL * buy_alloc_pct) / 100.0
              if (action == 'BUY'):
                position_size = int((target_amount / px)) if px > 0 else int(cfg.get('buy_shares', 50))
              else:
                position_size = int(holdings.get(symbol, 0))
            if (position_size <= 0):
              continue
            if (not _rot_buy):
              (allowed, reject_reason) = rm.check_trade_allowed(symbol, signal, px, total_buy=total_buy_all, total_sell=total_sell_all)
              if (not allowed):
                if (_risk_notified.get(symbol) != today_str):
                  _risk_notified[symbol] = today_str
                  send_telegram_message(f'🛑 *{symbol}* 風險控管攔截（{reject_reason}）')
                continue
            if (action == 'BUY'):
              trade_cost = (px * position_size)
              if (not _rot_buy) and (not check_monthly_budget(symbol, trade_cost, budget_spent)):
                continue
              if (not _rot_buy) and (not check_stock_cap(symbol, trade_cost, stock_alloc)):
                continue
            if ((action == 'BUY') and (not _rot_buy) and (os.getenv('MARKET_TREND_FILTER', 'true').lower() == 'true')):
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
                _order_fail_notified = notify_order_failure(symbol, f'{order_result["error"]}', _order_fail_notified, today_str, send_telegram_message, action=('買入' if action == 'BUY' else '賣出'))
                if (sn == 'keep_wait'):
                  trk['buy_count'] = kw_pre_state['buy_count']
                  trk['last_buy_price'] = kw_pre_state['last_buy_price']
                  trk['total_cost'] = kw_pre_state['total_cost']
                  trk['total_shares'] = kw_pre_state['total_shares']
                  trk['sold_date'] = kw_pre_state['sold_date']
                  trk['tp_tiers_fired'] = list(kw_pre_state.get('tp_tiers_fired', []))
                if (_rot_buy) and (kw_max_entry_price == -1):
                  _rot_day_buys.add(symbol)  # 全輪替下單失敗 → 當日不再重試補足
                continue
              _filled = resolve_fill(broker, symbol, action, order_result, position_size)
              if _filled is not None and _filled < position_size:
                if _filled <= 0:
                  _order_fail_notified = notify_order_failure(symbol, f'委託未成交（排隊中）{order_result}', _order_fail_notified, today_str, send_telegram_message, action='買入')
                  continue
                print(f'⚠️ {symbol} 部分成交 {_filled}/{position_size} 股')
                position_size = _filled
            else:
              broker.place_order(symbol, action, position_size)
            rm.log_trade(symbol, signal, px, position_size, exclude_from_daily=_rot_buy)
            if (action == 'BUY'):
              holdings[symbol] = (holdings.get(symbol, 0) + position_size)
            else:
              holdings[symbol] = max(0, (holdings.get(symbol, 0) - position_size))
            save_holdings(holdings)
            if ((action == 'BUY') and (sn == 'keep_wait') and (kw_max_entry_price == -1)):
              _rot_day_buys.add(symbol)
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
            # auto：把「今日型態路由到的底層策略」帶進通知（依 acd 最新 K 線即時判斷，無前瞻）
            _strat_label = sn.upper()
            if (sn == 'auto'):
              try:
                _routed = route_strategy(acd) if ('close' in acd.columns) else 'ma_cross'
                _strat_label = f'AUTO(路由→{_routed})'
              except Exception:
                _strat_label = 'AUTO'
            notice_msg = f'''
🔔 交易通知
股票: {symbol}
動作: {action_zh}
價格: {px:.2f}
股數: {position_size} 股
策略: {_strat_label}'''
            send_trade_alert(symbol, action, px, position_size, _strat_label)
            send_line_notification(notice_msg)
        except Exception as e:
          print(f'❌ {symbol} 錯誤: {e}')
          _order_fail_notified = notify_order_failure(symbol, e, _order_fail_notified, today_str, send_telegram_message, action="買入")
      run_inst_momentum(INST_MOM_CAPITAL, inst_momentum, broker, rm, holdings, now)
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
      # ── 盤後全輪替選股觸發（13:31~13:35，每月第 N 個交易日）──
      ROTATE_MODE_VAL = int(os.getenv('ROTATE_MODE', '0'))
      ROTATE_TRADING_DAY_N = int(os.getenv('ROTATE_TRADING_DAY_N', '-1'))
      MIN_DRAW_BACK = float(os.getenv('MIN_DRAW_BACK', '0'))
      if ROTATE_MODE_VAL > 0 and 31 <= m <= 35:
          _rotate_key = '_rotate_done_date'
          if globals().get(_rotate_key) != today_str:
              try:
                  from core.trading_calendar import TradingCalendar
                  from core.rotate_scheduler import should_rotate_today, update_env_section, backup_env, remove_monitored_only_entries
                  _rc = TradingCalendar()
                  schedule = should_rotate_today(now.date(), ROTATE_MODE_VAL, _rc, ROTATE_TRADING_DAY_N)
                  if schedule:
                      _rotation_held = False
                      if MIN_DRAW_BACK > 0:
                          _hold, _dd = check_rotation_hold(MIN_DRAW_BACK, TOTAL_CAPITAL, broker, holdings, today_str)
                          if _hold:
                              _dd_txt = f'{_dd:+.1%}' if _dd is not None else '?'
                              print(f'⚠️ 全輪替 {schedule}排程：總回撤 {_dd_txt} 超過 MIN_DRAW_BACK={MIN_DRAW_BACK:g}%，跳過本次換股（續抱，最多延長一季）')
                              send_telegram_message(f'⚠️ *全輪替 {schedule}排程 跳過換股*\n總回撤 {_dd_txt} 超過 {MIN_DRAW_BACK:g}%（MIN_DRAW_BACK），本季續抱不換股。若下一季仍超標將強制換股。')
                              _rotation_held = True
                      if not _rotation_held:
                          import subprocess as _sp
                          print(f'🔄 全輪替觸發：{schedule}排程，執行選股程式...')
                          result = _sp.run(
                              ['python', 'scripts/stock_selector_grid.py', '--recommend', '--output-env',
                               '--schedule-label', schedule, '--top-n', os.getenv('ROTATE_TOP_N', '4')],
                              capture_output=True, text=True, timeout=120,
                              env={**os.environ, 'SELECTOR_LOOKBACK_DAYS': os.getenv('ROTATE_LOOKBACK_DAYS', '250')}
                          )
                          if result.returncode == 0:
                              pc_lines = [l for l in result.stdout.strip().split('\n') if l.startswith('PC_')]
                              if pc_lines:
                                  backup_env('.env', 'backups')
                                  update_env_section('.env', schedule, pc_lines)
                                  # v3.24: 選入標的若被其他策略僅監控（未持有）→ 移除監控條目 + TG 通知
                                  _sel_syms = [l.split('=')[0].replace('PC_', '') for l in pc_lines]
                                  _removed_m = remove_monitored_only_entries('.env', _sel_syms, holdings)
                                  for _rm_sym, _rm_line in _removed_m:
                                      try:
                                          _rm_strat = json.loads(_rm_line.split('=', 1)[1]).get('strategy', '?')
                                      except Exception:
                                          _rm_strat = '?'
                                      send_telegram_message(
                                          f'🗑️ *全輪替* {_rm_sym} 已選入全輪替，原 {_rm_strat} 監控策略（未持有）已移除')
                                  # v3.25: 選股日資金預估 — 新配置所需 vs 目前可用 + 次日清倉回籠
                                  # （必須在 v3.5 重置分帳本之前，否則 stock_alloc 全 0）
                                  stocks_list = ', '.join(l.split('=')[0].replace('PC_', '') for l in pc_lines)
                                  try:
                                    from core.live_notifications import estimate_rotation_capital as _est_cap
                                    _cap = _est_cap(pc_lines, TOTAL_CAPITAL, stock_alloc)
                                    if _cap['sufficient']:
                                        _cap_txt = ('✅ 資金足夠'
                                                    f"\n💰 所需 NT${_cap['need']:,.0f} ｜ 可用 NT${_cap['available']:,.0f}"
                                                    f"\n🧹 換股日清倉回籠 ≈ NT${_cap['released']:,.0f}")
                                    else:
                                        _cap_txt = ('⚠️ *資金不足*'
                                                    f"\n💰 所需 NT${_cap['need']:,.0f} ｜ 可用 NT${_cap['available']:,.0f}"
                                                    f"\n🧹 清倉回籠 ≈ NT${_cap['released']:,.0f}"
                                                    f"\n📉 短少 ≈ NT${_cap['shortfall']:,.0f}（請補資金或調低 alloc）")
                                  except Exception as _e:
                                    _cap_txt = f'⚠️ 資金預估失敗: {_e}'
                                  # v3.9: 排定次日為全輪替買賣日（撞股補足/超額 trim 的開關）
                                  try:
                                    _next_buy_date = _next_market_open(now).strftime('%Y-%m-%d')
                                    save_json({'buy_date': _next_buy_date}, 'logs/rotation_pending.json')
                                    print(f'📅 全輪替買賣日已排定: {_next_buy_date}')
                                  except Exception as _e:
                                    print(f'⚠️ 排定買賣日失敗: {_e}')
                                  # v3.5: 換季換股成功後，重置分帳本讓新一季從零開始
                                  for _s in list(stock_alloc.keys()):
                                    stock_alloc[_s] = {'total_buy_cost': 0, 'total_buy_shares': 0}
                                  save_stock_allocation(stock_alloc)
                                  budget_spent.clear()
                                  save_monthly_budget(budget_spent)
                                  print('🧹 全輪替換季：分帳本與每月預算已全部重置')
                                  send_telegram_message(f'🔄 *全輪替 {schedule}排程 選股完成*\n📋 選出 {len(pc_lines)} 檔: {stocks_list}\n{_cap_txt}\n📁 舊 .env 已備份至 backups/')
                                  print(f'✅ 全輪替 {schedule}排程: .env 已更新 {len(pc_lines)} 檔')
                              else:
                                  print(f'⚠️ 全輪替: selector 無輸出')
                          else:
                              print(f'❌ 全輪替: selector 執行失敗\n{result.stderr[:500]}')
                  else:
                      print(f'ℹ️ 全輪替: 今日({today_str})非選股日（schedule=None）')
              except ImportError:
                  pass
              except Exception as e:
                  print(f'❌ 全輪替選股異常: {e}')
              globals()[_rotate_key] = today_str
      run_inst_momentum(INST_MOM_CAPITAL, inst_momentum, broker, rm, holdings, now)
      time.sleep(60)
      continue
    # ── 每日一次：bollinger/vwap/ma_cross 買入不足主動補足（方案 B，2026-09-01）──
    # 回測假設全額成交；實盤部分成交/資金不足會導致倉位不足 → 每日主動補到目標
    # （不看策略訊號）；逾 3 交易日仍未滿 → TG 通知（每日一次去重）
    # 補買僅盤中執行（09:00-13:30）；逾時通知任何時段都檢查
    try:
      _buy_offset = float(os.getenv('BUY_AMOUNT_OFFSET', '0.02'))
      if _buy_offset > 0:
        _market_open_now = is_weekday and (h > 9 or (h == 9 and m >= 0)) and (h < 13 or (h == 13 and m <= 30))
        _last_buy_map = {}
        if os.path.exists('logs/performance.csv'):
          import csv as _c
          with open('logs/performance.csv', newline='', encoding='utf-8') as _f:
            for _row in _c.reader(_f):
              if len(_row) >= 6 and _row[5].upper() == 'BUY':
                _last_buy_map[_row[1]] = _row[0]
        for (symbol, cfg) in PORTFOLIO_CONFIG.items():
          sn = cfg['strategy']
          if sn in ('bollinger', 'vwap', 'ma_cross'):
            held = holdings.get(symbol, 0)
            try:
              px = broker.get_current_price(symbol)
            except Exception:
              px = 0
            if px > 0:
              _alloc_pct = float(cfg.get('alloc', 12.5))
              _target = int((TOTAL_CAPITAL * _alloc_pct / 100.0) / px)
              # v3.27: 僅補「已有持股但不足」；空倉（held=0）等策略訊號不建倉
              from core.live_utils import calc_topup_need as _calc_need
              _need = _calc_need(held, _target, _buy_offset, _market_open_now)
              if _need > 0:
                  # 主動補足到目標（不看訊號）
                  try:
                    if USE_REAL_API:
                      _order_ret = broker.place_order(symbol, 'buy', _need)
                      _filled = resolve_fill(broker, symbol, 'buy', _order_ret, _need)
                      if _filled is not None and _filled <= 0:
                        _order_fail_notified = notify_order_failure(
                            symbol, f'補足未成交（{_order_ret}）', _order_fail_notified,
                            today_str, send_telegram_message, action='買入補足')
                        _filled = 0
                      else:
                        _filled = _filled if _filled is not None else _need
                    else:
                      broker.place_order(symbol, 'buy', _need)
                      _filled = _need
                    if _filled > 0:
                      holdings[symbol] = held + _filled
                      save_holdings(holdings)
                      rm.log_trade(symbol, 1, px, _filled, exclude_from_daily=True)
                      # v3.29: 補買同步更新分帳本（否則 avg_cost 失真/資金上限失效）
                      from core.live_utils import add_stock_allocation as _add_alloc
                      _add_alloc(stock_alloc, symbol, px * _filled, _filled)
                      save_stock_allocation(stock_alloc)
                      print(f'📥 {symbol} 買入補足 {_filled} 股 @ {px:.0f}（{held}→{held+_filled}，目標 {_target}）')
                  except Exception as _e:
                    print(f'⚠️ {symbol} 買入補足失敗: {_e}')
                    _order_fail_notified = notify_order_failure(
                        symbol, _e, _order_fail_notified, today_str,
                        send_telegram_message, action='買入補足')
              # 逾 3 交易日仍未滿 → TG 通知
              from core.live_utils import check_buy_fill_shortfall
              _buy_fill_notified = check_buy_fill_shortfall(
                  symbol, holdings.get(symbol, 0), _target, _buy_offset,
                  _last_buy_map.get(symbol), now.date(),
                  send_telegram_message, _buy_fill_notified, label=sn.upper())
    except Exception as _e:
      print(f'⚠️ 買入補足檢查異常: {_e}')
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