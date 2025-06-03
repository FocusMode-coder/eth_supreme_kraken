


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
        with open('eth_prediction.json', 'w') as f:
            json.dump(eth_data, f, indent=4)
        print(f"[UPDATED] {eth_data}")
    else:
        print("[ERROR] Failed to fetch ETH data")

if __name__ == '__main__':
    while True:
        update_prediction_file()
        time.sleep(60)