import time
import os
import requests
import urllib.parse
import hashlib
import hmac
import base64
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
API_KEY = os.getenv("KRAKEN_API_KEY")
PRIVATE_KEY = os.getenv("KRAKEN_SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TRADE_QUANTITY = float(os.getenv("TRADE_QUANTITY", "0.01"))

def send_telegram_message(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        try:
            requests.post(url, data=data)
        except Exception as e:
            print(f"Telegram error: {e}")

def kraken_request(endpoint, data):
    url_path = f"/0/private/{endpoint}"
    url = f"https://api.kraken.com{url_path}"
    nonce = str(int(1000 * time.time()))
    data["nonce"] = nonce
    post_data = urllib.parse.urlencode(data)
    encoded = (nonce + post_data).encode()
    message = url_path.encode() + hashlib.sha256(encoded).digest()
    signature = hmac.new(base64.b64decode(PRIVATE_KEY), message, hashlib.sha512)
    sig_digest = base64.b64encode(signature.digest())
    headers = {
        "API-Key": API_KEY,
        "API-Sign": sig_digest.decode()
    }
    res = requests.post(url, headers=headers, data=data)
    return res.json()

def get_price():
    res = requests.get("https://api.kraken.com/0/public/Ticker?pair=ETHUSDT").json()
    result = res.get("result", {})
    pair_key = next(iter(result), None)
    if pair_key:
        return float(result[pair_key]["c"][0])
    raise ValueError("ETHUSDT pair not found in Kraken response")

def get_balance():
    res = kraken_request("Balance", {})
    usdt = float(res["result"].get("ZUSD", 0))
    eth = float(res["result"].get("XETH", 0))
    return usdt, eth

def place_order(side, qty):
    data = {
        "pair": "ETHUSDT",
        "type": side.lower(),
        "ordertype": "market",
        "volume": f"{qty:.6f}",
    }
    res = kraken_request("AddOrder", data)
    print(f"{side.upper()} order: {res}")
    return res

def main():
    last_price = get_price()
    entry_price = None

    while True:
        time.sleep(60)
        price = get_price()
        usdt, eth = get_balance()

        if entry_price is None and price < last_price * 0.975 and usdt >= price * TRADE_QUANTITY:
            place_order("buy", TRADE_QUANTITY)
            send_telegram_message(f"🟢 Comprado ETH a ${price:.2f}")
            entry_price = price

        elif entry_price and price > entry_price * 1.03 and eth >= TRADE_QUANTITY:
            place_order("sell", TRADE_QUANTITY)
            send_telegram_message(f"🔴 Vendido ETH a ${price:.2f}")
            entry_price = None

        last_price = price

if __name__ == "__main__":
    main()