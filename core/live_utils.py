"""Live trader 公用函式（市場時間、輔助工具）"""

from datetime import datetime, timedelta, time
import pytz

TAIPEI_TZ = pytz.timezone("Asia/Taipei")
MARKET_OPEN = time(9, 0)
MARKET_CLOSE = time(13, 30)


def get_next_market_open(now: datetime) -> datetime:
    """
    回傳下一個台股開盤時間 (Asia/Taipei 09:00)。
    考量：
      - 開盤前 → 當日 09:00
      - 盤中   → 立即回傳（不延遲）
      - 收盤後 → 下一個交易日 09:00
      - 週末   → 下週一 09:00
    """
    now_tw = now.astimezone(TAIPEI_TZ) if now.tzinfo else TAIPEI_TZ.localize(now)

    # 如果是週末，跳到下週一 09:00
    if now_tw.weekday() >= 5:
        days_ahead = 7 - now_tw.weekday()
        next_open = now_tw.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        return next_open.astimezone(now.tzinfo) if now.tzinfo else next_open.replace(tzinfo=None)

    today_open = now_tw.replace(hour=9, minute=0, second=0, microsecond=0)
    today_close = now_tw.replace(hour=13, minute=30, second=0, microsecond=0)

    if now_tw < today_open:
        # 開盤前 → 等今天開盤
        return today_open.astimezone(now.tzinfo) if now.tzinfo else today_open.replace(tzinfo=None)
    elif today_open <= now_tw <= today_close:
        # 盤中 → 立刻回傳（不 sleep）
        return now_tw.astimezone(now.tzinfo) if now.tzinfo else now_tw.replace(tzinfo=None)
    else:
        # 收盤後 → 下一個交易日 09:00
        next_day = now_tw + timedelta(days=1)
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)
        next_open = next_day.replace(hour=9, minute=0, second=0, microsecond=0)
        return next_open.astimezone(now.tzinfo) if now.tzinfo else next_open.replace(tzinfo=None)


def notify_order_failure(symbol, error, notified, today_str, notify_fn, action="交易", retry_hint=None):
    """交易失敗的 TG 警示 — 每檔每日只發一次（避免每分鐘重試洗版）。

    notified: {symbol: 'YYYY-MM-DD'} 已警示紀錄（由呼叫端持有）
    retry_hint: 後續處理說明（預設依買/賣動作給出）
    回傳更新後的 notified dict。
    """
    if notified.get(symbol) == today_str:
        return notified
    notified[symbol] = today_str
    if retry_hint is None:
        if "賣出" in action or "清倉" in action or "trim" in action:
            retry_hint = "系統將於下一個交易日 09:00 自動重試。"
        else:
            retry_hint = "系統會自動重試至收盤；若當日無法成交，該季將少持此檔。"
    try:
        notify_fn(f"⚠️ *{symbol}* {action}失敗：{error}\n{retry_hint}")
    except Exception:
        pass
    return notified


def resolve_fill(broker, symbol, action, order_ret, requested):
    """解析實際成交股數（下單後確認，避免「委託成功≠成交」誤判持股）。

    - order_ret 為含 error 的 dict → 0（委託失敗）
    - order_ret 為 mock 的 filled → requested（模擬全成交）
    - 其餘 → 呼叫 broker.check_fill() 查詢；無法查詢（None）→ 維持原行為視為全成交
    回傳: 實際成交股數（int）或 None（無法得知）。
    """
    if isinstance(order_ret, dict):
        if order_ret.get("error"):
            return 0
        if order_ret.get("status") == "filled":
            return requested
    check = getattr(broker, "check_fill", None)
    if check is not None:
        try:
            filled = check(symbol, action, order_ret, requested)
            if filled is not None:
                return int(filled)
        except Exception:
            pass
    return None
