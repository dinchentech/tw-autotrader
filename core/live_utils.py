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
