# utils/telegram.py
import os
import requests

def send_telegram_message(message: str):
    """發送 Telegram 訊息"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("⚠️ Telegram 未設定，跳過通知")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"🤖 TW AutoTrader\n{message}",
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ Telegram 通知已發送")
            return True
        else:
            print(f"❌ Telegram 發送失敗: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Telegram 發送錯誤: {e}")
        return False

def send_trade_alert(symbol: str, action: str, price: float, quantity: int, strategy: str):
    """發送交易警報"""
    message = (
        f"*{action.upper()} {symbol}*\n"
        f"💰 價格: {price:.2f}\n"
        f"📊 數量: {quantity:,} 股\n"
        f"🎯 策略: {strategy}\n"
        f"⏰ 時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return send_telegram_message(message)