import asyncio
import websockets
import json
import datetime

# CONFIGURATION
SYMBOL = "solusdt"
CAPITAL = 1000
LEVERAGE = 5
TRADE_LOG_FILE = "trade_log.txt"
TAKE_PROFIT_PERCENT = 0.01     # 1%
STOP_LOSS_PERCENT = 0.005      # 0.5%
TRAILING_TP_SL = 0.005         # 0.5%

WS_URL = f"wss://fstream.binance.com/ws/{SYMBOL}@kline_1m"

# STATE
in_position = False
entry_price = 0
qty = 0
tp = 0
sl = 0
trailing_tp = 0
trailing_sl = 0
side = None  # "BUY" or "SELL"

def log_trade(entry, tp, sl, exit_price, exit_reason, pnl, side):
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    log = (f"{timestamp} | SIDE: {side} | Entry: {entry:.2f} | TP: {tp:.2f} | SL: {sl:.2f} | "
           f"Exit: {exit_price:.2f} | Reason: {exit_reason} | PnL: {pnl:.2f} USDT")
    print(log)
    with open(TRADE_LOG_FILE, "a") as f:
        f.write(log + "\n")

def get_trade_signal(closing_prices):
    if len(closing_prices) < 2:
        return None

    if closing_prices[-1] > closing_prices[-2]:
        return "BUY"
    elif closing_prices[-1] < closing_prices[-2]:
        return "SELL"

    return None


async def main():
    global in_position, entry_price, qty, tp, sl, trailing_tp, trailing_sl, side

    closing_prices = []

    async with websockets.connect(WS_URL) as websocket:
        print("✅ WebSocket connected, simulation started.\n")
        while True:
            try:
                msg = await websocket.recv()
                data = json.loads(msg)

                if "k" in data:
                    k = data["k"]
                    if k["x"]:  # candle closed
                        close = float(k["c"])
                        high = float(k["h"])
                        low = float(k["l"])
                        time_utc = datetime.datetime.utcfromtimestamp(k["T"] / 1000).strftime('%Y-%m-%d %H:%M:%S')

                        # Print live price on candle close
                        print(f"[{time_utc}] 🔔 Closed Price: {close:.2f}")

                        closing_prices.append(close)
                        if len(closing_prices) > 100:
                            closing_prices.pop(0)

                        if not in_position:
                            signal = get_trade_signal(closing_prices)
                            if signal:
                                side = signal
                                entry_price = close
                                qty = round((CAPITAL * LEVERAGE) / entry_price, 4)

                                if side == "BUY":
                                    tp = entry_price * (1 + TAKE_PROFIT_PERCENT)
                                    sl = entry_price * (1 - STOP_LOSS_PERCENT)
                                else:  # SELL
                                    tp = entry_price * (1 - TAKE_PROFIT_PERCENT)
                                    sl = entry_price * (1 + STOP_LOSS_PERCENT)

                                trailing_tp = tp
                                trailing_sl = sl
                                in_position = True

                                print(f"\n📊 ENTER {side} @ {entry_price:.2f} | TP: {tp:.2f}, SL: {sl:.2f}\n")

                        else:
                            current_price = close
                            exit_reason = ""
                            pnl = 0

                            # Adjust trailing TP and SL
                            if side == "BUY" and current_price >= trailing_tp:
                                trailing_tp = current_price * (1 + TRAILING_TP_SL)
                                trailing_sl = current_price * (1 - STOP_LOSS_PERCENT)
                                print(f"🔁 [BUY] TP moved to {trailing_tp:.2f} | SL moved to {trailing_sl:.2f}")

                            elif side == "SELL" and current_price <= trailing_tp:
                                trailing_tp = current_price * (1 - TRAILING_TP_SL)
                                trailing_sl = current_price * (1 + STOP_LOSS_PERCENT)
                                print(f"🔁 [SELL] TP moved to {trailing_tp:.2f} | SL moved to {trailing_sl:.2f}")

                            # Exit conditions
                            if side == "BUY":
                                if current_price >= trailing_tp:
                                    pnl = (current_price - entry_price) * qty
                                    exit_reason = "TP hit"
                                elif current_price <= trailing_sl:
                                    pnl = (current_price - entry_price) * qty
                                    exit_reason = "SL hit"
                            else:  # SELL
                                if current_price <= trailing_tp:
                                    pnl = (entry_price - current_price) * qty
                                    exit_reason = "TP hit"
                                elif current_price >= trailing_sl:
                                    pnl = (entry_price - current_price) * qty
                                    exit_reason = "SL hit"

                            if exit_reason:
                                log_trade(entry_price, tp, sl, current_price, exit_reason, pnl, side)
                                in_position = False

            except Exception as e:
                print("❌ Error:", str(e))
                await asyncio.sleep(1)

asyncio.run(main())
