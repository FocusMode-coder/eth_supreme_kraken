import os
import time
import json
import hmac
import hashlib
import base64
import requests
import urllib.parse
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()
API_KEY = os.getenv("KRAKEN_API_KEY")
PRIVATE_KEY = os.getenv("KRAKEN_PRIVATE_KEY")
BASE_URL = os.getenv("KRAKEN_BASE_URL")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PAIR = "XETHZUSD"
LOG_FILE = os.getenv("LOG_FILE", "kraken_log.txt")
MEMORY_FILE = "eth_memory.json"
MODE = os.getenv("MODE", "REAL")
TRADE_QUANTITY = float(os.getenv("TRADE_QUANTITY", "0.01"))

def send_message(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

def kraken_request(endpoint, data):
    url_path = f"/0/private/{endpoint}"
    url = BASE_URL + url_path
    nonce = str(int(1000 * time.time()))
    data["nonce"] = nonce
    post_data = urllib.parse.urlencode(data)
    encoded = (nonce + post_data).encode()
    message = url_path.encode() + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(PRIVATE_KEY), message, hashlib.sha512)
    sigdigest = base64.b64encode(mac.digest())
    headers = {"API-Key": API_KEY, "API-Sign": sigdigest.decode()}
    return requests.post(url, headers=headers, data=data).json()

def get_balance():
    res = kraken_request("Balance", {})
    if "result" in res:
        return float(res["result"].get("ZUSD", 0)), float(res["result"].get("XETH", 0))
    return 0, 0

def get_price():
    try:
        res = requests.get("https://api.kraken.com/0/public/Ticker?pair=ETHUSD").json()
        return float(res["result"][PAIR]["c"][0])
    except:
        return 0

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"trades": [], "last_action": None}
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def place_order(side, quantity):
    if MODE != "REAL":
        return {"simulated": True, "side": side}
    data = {
        "pair": "XETHZUSD",
        "type": "buy" if side == "BUY" else "sell",
        "ordertype": "market",
        "volume": quantity
    }
    return kraken_request("AddOrder", data)

def decision(price, usdt, eth, memory):
    last = memory["last_action"]
    trades = memory.get("trades", [])
    # Protect profit: if last trade was buy and price increased 3%, sell
    if last == "BUY" and trades:
        last_buy = next((t for t in reversed(trades) if t["type"] == "BUY"), None)
        if last_buy:
            buy_price = last_buy["price"]
            if price >= buy_price * 1.03 and eth >= TRADE_QUANTITY:
                return "SELL"
    # Avoid buying again immediately after buy
    if price < 2400 and usdt >= price * TRADE_QUANTITY and last != "BUY":
        return "BUY"
    # Sell if price high and holding ETH, avoid repeating sell
    if price > 2600 and eth >= TRADE_QUANTITY and last != "SELL":
        return "SELL"
    return "HOLD"

def report(trade_type, price):
    emoji = "📥" if trade_type == "BUY" else "📤"
    verb = "Compré" if trade_type == "BUY" else "Vendí"
    emotional_msgs = {
        "BUY": [
            "¡Vamos Luciano! Entramos en la batalla con {qty} ETH a ${prc:.2f}. Confío en esta jugada.",
            "Luciano, acabo de comprar {qty} ETH a ${prc:.2f}. Sentí la oportunidad y la tomé.",
            "Con determinación, compré {qty} ETH a ${prc:.2f}. A por todas, jefe."
        ],
        "SELL": [
            "Luciano, vendí {qty} ETH a ${prc:.2f}. Protegiendo ganancias, seguimos firmes.",
            "¡Operación exitosa! Vendí {qty} ETH a ${prc:.2f}. Siempre un paso adelante.",
            "Con calma y estrategia, vendí {qty} ETH a ${prc:.2f}. Así se hace, Luciano."
        ]
    }
    import random
    msg = random.choice(emotional_msgs[trade_type]).format(qty=TRADE_QUANTITY, prc=price)
    msg += f"\n🤖 Bot Supremo en acción.\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    send_message(f"{emoji} {msg}")

def main():
    memory = load_memory()
    send_message("🧠 ETH SUPREME BOT conectado. Luciano, estoy atento al mercado para ti.")

    while True:
        try:
            usdt, eth = get_balance()
            price = get_price()
            if price == 0:
                send_message("⚠️ No pude obtener el precio actual, Luciano. Reintentando...")
                time.sleep(60)
                continue
            action = decision(price, usdt, eth, memory)

            if action in ["BUY", "SELL"]:
                res = place_order(action, TRADE_QUANTITY)
                if "error" in res and res["error"]:
                    send_message(f"⚠️ Luciano, error al ejecutar {action}: {res['error']}")
                else:
                    memory.setdefault("trades", []).append({
                        "type": action,
                        "price": price,
                        "quantity": TRADE_QUANTITY,
                        "time": datetime.now().isoformat()
                    })
                    memory["last_action"] = action
                    save_memory(memory)
                    report(action, price)

        except Exception as e:
            send_message(f"⚠️ Luciano, algo salió mal: {str(e)}")

        time.sleep(60)

if __name__ == "__main__":
    main()