


import time
import json
import requests
from datetime import datetime

def fetch_eth_data():
    url = 'https://api.kraken.com/0/public/Ticker?pair=ETHUSDT'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        ticker = data['result'].get('XETHZUSD') or data['result'].get('ETHUSDT')
        if ticker:
            price = float(ticker['c'][0])
            volume = float(ticker['v'][1])
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'price': price,
                'volume': volume
            }
    return None

def update_prediction_file():
    eth_data = fetch_eth_data()
    if eth_data:
        with open('./eth_prediction.json', 'w') as f:
            json.dump(eth_data, f, indent=4)
        # Also update eth_memory.json with latest price and time
        with open('./eth_memory.json', 'w') as mem_file:
            memory_data = {
                "last_price": eth_data['price'],
                "last_volume": eth_data['volume'],
                "last_updated": eth_data['timestamp']
            }
            json.dump(memory_data, mem_file, indent=4)
        print(f"[UPDATED] {eth_data}")
    else:
        print("[ERROR] Failed to fetch ETH data")

if __name__ == '__main__':
    while True:
        update_prediction_file()
        with open("./public/eth_prediction.json", "w") as f:
            with open("./eth_prediction.json", "r") as source:
                f.write(source.read())
        with open("./public/eth_memory.json", "w") as f:
            with open("./eth_memory.json", "r") as source:
                f.write(source.read())
        time.sleep(60)