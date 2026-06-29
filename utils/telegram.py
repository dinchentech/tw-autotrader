# utils/telegram.py
import os
import requests
from datetime import datetime


def send_telegram_message(message: str):
    """發送 Telegram 訊息（Markdown 失敗自動降級純文字）"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("⚠️ Telegram 未設定，跳過通知")
        return False

    base_payload = {
        "chat_id": chat_id,
        "text": f"\U0001f916 TW AutoTrader\n{message}",
    }

    try:
        # 嘗試 Markdown
        payload = {**base_payload, "parse_mode": "Markdown"}
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ Telegram 通知已發送")
            return True
        # 400 通常是 Markdown 格式問題，降級純文字重試
        if response.status_code == 400:
            payload.pop("parse_mode")
            response = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json=payload, timeout=10)
            if response.status_code == 200:
                print("✅ Telegram 通知已發送（Markdown 降級為純文字）")
                return True
        print(f"❌ Telegram 發送失敗: {response.status_code}")
        return False
    except Exception as e:
        print(f"❌ Telegram 發送錯誤: {e}")
        return False


def send_trade_alert(symbol: str, action: str, price: float,
                     quantity: int, strategy: str):
    """發送交易警報"""
    message = (
        f"*{action.upper()} {symbol}*\n"
        f"\U0001f4b0 價格: {price:.2f}\n"
        f"\U0001f4ca 數量: {quantity:,} 股\n"
        f"\U0001f3af 策略: {strategy}\n"
        f"\u23f0 時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return send_telegram_message(message)
