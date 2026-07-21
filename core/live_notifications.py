import requests
import os
from utils.telegram import send_telegram_message

def send_line_notification(message):
    line_token = os.getenv("LINE_NOTIFY_TOKEN")
    if not line_token:
        return
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {line_token}"}
    payload = {"message": message}
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=5)
        if response.status_code != 200:
            print(f"LINE Notify 發送失敗: {response.text}")
    except Exception as e:
        print(f"LINE Notify 發送異常: {e}")

def notify_all(message):
    send_telegram_message(message)
    send_line_notification(message)

def send_daily_report(pd, date):
    """讀取 logs/performance.csv，產生今日交易摘要發送到 Telegram"""
    from pathlib import Path
    csv_path = Path("logs/performance.csv")
    if not csv_path.exists():
        notify_all("📊 *今日交易日報*\n📅 今日無交易紀錄")
        return

    try:
        df = pd.read_csv(csv_path)
        today = date.today()
        df["timestamp"] = pd.to_datetime(df["timestamp"], format='mixed')
        today_df = df[df["timestamp"].dt.date == today]
    except Exception as e:
        notify_all(f"❌ 讀取交易紀錄失敗: {e}")
        return

    if today_df.empty:
        notify_all("📊 *今日交易日報*\n📅 今日無交易紀錄")
        return

    buys = today_df[today_df["action"].str.upper() == "BUY"]
    sells = today_df[today_df["action"].str.upper() == "SELL"]

    msg = f"📊 *今日交易日報 ({today.isoformat()})*\n"
    msg += "─" * 20 + "\n"

    if not buys.empty:
        msg += "🔹 *買進*\n"
        for _, row in buys.iterrows():
            t = pd.Timestamp(row["timestamp"]).strftime("%H:%M")
            s = row["symbol"]
            msg += f"  {s}  {t}  @${row['price']:.2f}  {int(row['quantity'])}股\n"
        total_buy = (buys["price"] * buys["quantity"]).sum()
        msg += f"  買進總成本: NT${total_buy:,.0f}\n"

    if not sells.empty:
        msg += "🔸 *賣出*\n"
        for _, row in sells.iterrows():
            t = pd.Timestamp(row["timestamp"]).strftime("%H:%M")
            s = row["symbol"]
            msg += f"  {s}  {t}  @${row['price']:.2f}  {int(row['quantity'])}股\n"
        total_sell = (sells["price"] * sells["quantity"]).sum()
        msg += f"  賣出總收入: NT${total_sell:,.0f}\n"

    msg += "─" * 20
    notify_all(msg)


def _build_holdings_message(pd, app_version, title_emoji, title):
    """讀取 logs/holdings.json 並組裝持倉訊息文字（共用 helper，不發送）"""
    import json
    from pathlib import Path
    from datetime import datetime

    holdings_path = Path("logs/holdings.json")
    alloc_path = Path("logs/stock_allocation.json")
    csv_path = Path("logs/performance.csv")

    if not holdings_path.exists():
        return None

    with open(holdings_path) as f:
        holdings = json.load(f)
    if not holdings:
        return None

    alloc = {}
    if alloc_path.exists():
        with open(alloc_path) as f:
            alloc = json.load(f)

    date_str = datetime.now().strftime("%Y-%m-%d")
    msg = f"{title_emoji} *{title} ({date_str})* V{app_version}\n"
    msg += "─" * 20 + "\n"

    total_cost = 0
    total_value = 0
    total_unrealized = 0

    for sym in sorted(holdings.keys()):
        shares = holdings.get(sym, 0)
        if isinstance(shares, dict):
            qty = shares.get("qty", 0)
            if qty <= 0:
                continue
            avg_cost = shares.get("avg_price", 0)
            shares = qty
        else:
            if shares <= 0:
                continue
            avg_cost = 0
            alloc_data = alloc.get(sym, {})
            if isinstance(alloc_data, dict) and alloc_data.get("total_buy_shares", 0) > 0:
                avg_cost = alloc_data["total_buy_cost"] / alloc_data["total_buy_shares"]

        current_price = avg_cost
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                sym_df = df[df["symbol"] == str(sym)]
                if not sym_df.empty:
                    current_price = sym_df["price"].iloc[-1]
                    if avg_cost == 0:
                        avg_cost = current_price
            except Exception:
                pass

        cost_basis = avg_cost * shares if avg_cost > 0 else 0
        market_value = current_price * shares
        unrealized = market_value - cost_basis
        pct = (current_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0

        total_cost += cost_basis
        total_value += market_value
        total_unrealized += unrealized

        emoji = "🟢" if unrealized >= 0 else "🔴"
        msg += f"{emoji} {sym}: {shares}股\n"
        msg += f"   成本均價 {avg_cost:,.0f} | 參考市價 {current_price:,.0f}\n"
        msg += f"   未實現損益 {unrealized:+,.0f} ({pct:+.2f}%)\n"

    msg += "─" * 20 + "\n"
    msg += f"總成本: NT${total_cost:,.0f}\n"
    msg += f"總市值: NT${total_value:,.0f}\n"
    msg += f"未實現損益: {'+' if total_unrealized >= 0 else ''}{total_unrealized:,.0f}\n"
    return msg


def _build_inst_screening_msg() -> str:
    """讀取法人動能篩選結果，回傳訊息文字（無結果時回傳空字串）
    
    💡 若無檔案或非今日，自動 new 一個 InstitutionalMomentumStrategy 執行篩選再產生檔案，
       讓休眠前可以直接看到最新篩選結果，不必等到隔天 13:31-13:45。
    """
    import json
    from pathlib import Path

    inst_path = Path("logs/inst_momentum_screening.json")

    # 檢查是否需要重新篩選（無檔案、非今日、或解析失敗）
    need_refresh = False
    if not inst_path.exists():
        need_refresh = True
    else:
        try:
            from datetime import datetime
            inst_data = json.loads(inst_path.read_text())
            if inst_data.get("screen_date") != datetime.now().strftime("%Y-%m-%d"):
                need_refresh = True
        except Exception:
            need_refresh = True

    if need_refresh:
        try:
            from strategies.institutional_momentum import InstitutionalMomentumStrategy
            inst_mom = InstitutionalMomentumStrategy(broker=None, capital=0, top_n=3)
            inst_mom.get_candidates()
            print("✅ 休眠前自動執行法人動能篩選完成")
        except Exception as e:
            print(f"⚠️ 休眠前自動篩選失敗: {e}")

    if not inst_path.exists():
        return ""
    try:
        from datetime import datetime
        inst_data = json.loads(inst_path.read_text())
        if inst_data.get("screen_date") != datetime.now().strftime("%Y-%m-%d"):
            return ""
        qualified = inst_data.get("qualified", [])
        near_misses = inst_data.get("near_misses", [])
        parts = []
        if qualified:
            names = ", ".join(f"{s['stock_id']}({s['score']:.2%})" for s in qualified)
            parts.append(f"✅ 入選: {names}")
        if near_misses:
            names = ", ".join(f"{s['stock_id']}(魚{s['fish_score']:.1f})" for s in near_misses)
            parts.append(f"⚠️ 未達標前三: {names}")
        if parts:
            return "\n📡 *法人動能篩選*\n" + "\n".join(parts) + "\n"
        return "\n📡 *法人動能篩選*\n❌ 今日無符合標的\n"
    except Exception:
        return ""


def send_sleep_notification(pd, app_version, next_open):
    """發送睡前持倉報告到 Telegram"""
    import os
    from datetime import datetime
    footer = f"💤 休眠到 {next_open.strftime('%m/%d %H:%M')}" if next_open else ""
    msg = _build_holdings_message(pd, app_version, "💤", "睡前持倉報告")
    if msg is None:
        msg = f"💤 *睡前持倉報告 ({datetime.now().strftime('%Y-%m-%d')})* V{app_version}\n"
        msg += "─" * 20 + "\n📭 目前無持倉\n"

    # 法人動能篩選（獨立於持倉）
    inst_msg = _build_inst_screening_msg()
    if inst_msg:
        msg += inst_msg
    elif float(os.getenv("INST_MOM_CAPITAL", "0")) > 0:
        msg += "\n📡 *法人動能篩選*\n⏳ 尚未產出篩選檔案\n"

    if footer and "休眠" not in msg:
        msg += footer
    notify_all(msg)
    print("✅ 睡前持倉報告已發送")


def send_startup_holdings(pd, app_version):
    """發送啟動持倉報告到 Telegram"""
    msg = _build_holdings_message(pd, app_version, "🚀", "啟動持倉報告")
    if msg:
        notify_all(msg)
        print("✅ 啟動持倉報告已發送")


def send_closing_summary(pd, app_version):
    import json
    from pathlib import Path
    from datetime import datetime
    try:
        holdings_path = Path("logs/holdings.json")
        alloc_path = Path("logs/stock_allocation.json")
        csv_path = Path("logs/performance.csv")

        if not holdings_path.exists():
            return

        with open(holdings_path) as f:
            holdings = json.load(f)
        if not holdings:
            return

        alloc = {}
        if alloc_path.exists():
            with open(alloc_path) as f:
                alloc = json.load(f)

        date_str = datetime.now().strftime("%Y-%m-%d")

        msg = f"📋 *收盤持倉報告 ({date_str})* V{app_version}\n"
        msg += "─" * 20 + "\n"

        total_cost = 0
        total_value = 0
        total_unrealized = 0

        for sym in sorted(holdings.keys()):
            shares = holdings.get(sym, 0)
            if isinstance(shares, dict):
                # New format
                qty = shares.get("qty", 0)
                if qty <= 0: continue
                avg_cost = shares.get("avg_price", 0)
                shares = qty
            else:
                # Old format
                if shares <= 0: continue
                avg_cost = 0
                alloc_data = alloc.get(sym, {})
                if isinstance(alloc_data, dict) and alloc_data.get("total_buy_shares", 0) > 0:
                    avg_cost = alloc_data["total_buy_cost"] / alloc_data["total_buy_shares"]

            current_price = avg_cost
            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    sym_df = df[df["symbol"] == str(sym)]
                    if not sym_df.empty:
                        current_price = sym_df["price"].iloc[-1]
                except Exception:
                    pass

            cost_basis = avg_cost * shares if avg_cost > 0 else 0
            market_value = current_price * shares
            unrealized = market_value - cost_basis
            pct = (current_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0

            total_cost += cost_basis
            total_value += market_value
            total_unrealized += unrealized

            emoji = "🟢" if unrealized >= 0 else "🔴"
            msg += f"{emoji} {sym}: {shares}股\n"
            msg += f"   成本均價 {avg_cost:,.0f} | 參考市價 {current_price:,.0f}\n"
            msg += f"   未實現損益 {unrealized:+,.0f} ({pct:+.2f}%)\n"

        msg += "─" * 20 + "\n"
        msg += f"總成本: NT${total_cost:,.0f}\n"
        msg += f"總市值: NT${total_value:,.0f}\n"
        msg += f"未實現損益: {'+' if total_unrealized >= 0 else ''}{total_unrealized:,.0f}\n"

        # 法人抬轎動能篩選結果
        inst_msg = _build_inst_screening_msg()
        if inst_msg:
            msg += inst_msg
        elif float(os.getenv("INST_MOM_CAPITAL", "0")) > 0:
            msg += "\n📡 *法人動能篩選*\n⏳ 尚未產出篩選檔案\n"

        notify_all(msg)
        print("✅ 收盤持倉報告已發送")
    except Exception as e:
        print(f"❌ 發送收盤持倉報告失敗: {e}")
