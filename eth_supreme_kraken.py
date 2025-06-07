import os
import time
import requests
import hmac
import hashlib
import base64
import urllib.parse
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("KRAKEN_API_KEY")
PRIVATE_KEY = os.getenv("KRAKEN_SECRET_KEY")
BASE_URL = "https://api.kraken.com"
PAIR = "ETHUSDT"
TRADE_QUANTITY = float(os.getenv("TRADE_QUANTITY", "0.01"))

def kraken_request(endpoint, data):
    url_path = f"/0/private/{endpoint}"
    url = f"{BASE_URL}{url_path}"
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

def get_balance():
    res = kraken_request("Balance", {})
    usdt = float(res["result"].get("ZUSD", 0))
    eth = float(res["result"].get("XETH", 0))
    return usdt, eth

def get_price():
    res = requests.get(f"https://api.kraken.com/0/public/Ticker?pair=ETHUSDT").json()
    return float(res["result"]["XETHZUSD"]["c"][0])

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

        # BUY logic: price dropped 2.5% from last price
        if entry_price is None and price < last_price * 0.975 and usdt >= price * TRADE_QUANTITY:
            res = place_order("buy", TRADE_QUANTITY)
            entry_price = price
            print(f"Bought ETH at ${price}")

        # SELL logic: price increased 3% from entry
        elif entry_price and price > entry_price * 1.03 and eth >= TRADE_QUANTITY:
            res = place_order("sell", TRADE_QUANTITY)
            print(f"Sold ETH at ${price}")
            entry_price = None

        last_price = price

if __name__ == "__main__":
    main()