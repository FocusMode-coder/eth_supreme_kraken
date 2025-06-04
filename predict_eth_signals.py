import requests
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import time

def fetch_ohlc_data(pair='ETHUSDT', interval='60', since=None):
    url = f'https://api.kraken.com/0/public/OHLC'
    params = {
        'pair': pair,
        'interval': interval,
    }
    response = requests.get(url, params=params)
    data = response.json()
    if 'result' not in data:
        raise Exception("Failed to fetch OHLC data.")
    key = next(iter(data['result']))
    ohlc = data['result'][key]
    df = pd.DataFrame(ohlc, columns=[
        'time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'])
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['close'] = df['close'].astype(float)
    return df

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_ema(series, span=14):
    return series.ewm(span=span, adjust=False).mean()

def generate_prediction(df):
    df['rsi'] = calculate_rsi(df['close'])
    df['ema'] = calculate_ema(df['close'])

    predictions = []
    for i in range(len(df)):
        signal = None
        if i < 15:
            continue
        rsi = df.iloc[i]['rsi']
        close = df.iloc[i]['close']
        ema = df.iloc[i]['ema']
        time_str = df.iloc[i]['time'].strftime('%Y-%m-%d %H:%M:%S')

        if rsi > 70:
            signal = "sell"
        elif rsi < 30:
            signal = "buy"
        elif abs(close - ema) < 5 and 45 <= rsi <= 55:
            signal = "watch"
        else:
            signal = "hold"

        predictions.append({
            'time': time_str,
            'price': close,
            'rsi': round(rsi, 2),
            'ema': round(ema, 2),
            'signal': signal
        })
    return predictions

def save_predictions(predictions, filename='eth_prediction.json'):
    with open(filename, 'w') as f:
        json.dump(predictions, f, indent=2)

def update_eth_memory(df, filename='eth_memory.json'):
    if df.empty:
        return
    latest = df.iloc[-1]
    snapshot = {
        "volume": float(latest["volume"]),
        "time": latest["time"].strftime('%Y-%m-%d %H:%M:%S')
    }
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"balance_snapshots": []}

    data["balance_snapshots"].append(snapshot)

    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    try:
        df = fetch_ohlc_data()
        predictions = generate_prediction(df)
        save_predictions(predictions)
        update_eth_memory(df)
        print("✅ Predicciones generadas y guardadas correctamente.")
    except Exception as e:
        print(f"❌ Error generando predicciones: {e}")


# --- Modo automático: ejecutar cada 5 minutos ---
import schedule

def job():
    try:
        df = fetch_ohlc_data()
        predictions = generate_prediction(df)
        save_predictions(predictions)
        update_eth_memory(df)
        print("✅ Predicciones actualizadas correctamente.")
    except Exception as e:
        print(f"❌ Error en actualización automática: {e}")

schedule.every(5).minutes.do(job)

print("🔁 Modo automático activado. Ejecutando cada 5 minutos...")
job()  # Primera ejecución inmediata

while True:
    schedule.run_pending()
    time.sleep(1)