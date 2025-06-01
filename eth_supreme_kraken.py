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
import random

# Load environment
load_dotenv()
API_KEY = "qDNuQzauoWMtpaGPNA+xvmKHwygn20eX3FDAgSW7Lb/ht9ySiphGB/3r"
PRIVATE_KEY = "NwWqoapf1vNrcK73/YWy3TD+zOe4TPN3cv4XgElGAi4kntwKfn2IIlBhfRcBX2/kIRIJXsxzdB0nwaKDrz1S8w=="
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

def handle_command():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        res = requests.get(url).json()
        for update in res.get("result", []):
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id"))
            if chat_id != CHAT_ID:
                continue
            if "/status" in text.lower():
                from datetime import datetime
                mem = load_memory()
                trades = mem.get("trades", [])
                summary = "📊 Resumen de operaciones del día:\n"
                today = datetime.now().date()
                total_profit = 0
                for t in trades:
                    t_time = datetime.fromisoformat(t["time"])
                    if t_time.date() == today:
                        summary += f"- {t['type']} {t['quantity']} ETH a ${t['price']:.2f} ({t_time.strftime('%H:%M')})\n"
                if not trades or today not in [datetime.fromisoformat(t["time"]).date() for t in trades]:
                    summary += "Sin operaciones hoy.\n"
                send_message("✅ Bot funcionando correctamente. Monitoreando mercado ETH.\n" + summary)
            elif "/balance" in text.lower():
                usdt, eth = get_balance()
                send_message(f"💰 Balance actual:\n- USDT: ${usdt:.2f}\n- ETH: {eth:.5f}")
            elif "/log" in text.lower():
                mem = load_memory()
                last_action = mem["last_action"] if mem["last_action"] else "Ninguna acción registrada."
                send_message(f"🧾 Última acción del bot: {last_action}")
    except Exception as e:
        send_message(f"❌ Error al verificar comandos: {str(e)}")

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
    time.sleep(3)
    res = kraken_request("Balance", {})
    if "result" in res:
        if res["result"]:
            return float(res["result"].get("ZUSD", 0)), float(res["result"].get("XETH", 0))
        else:
            send_message("⚠️ Kraken devolvió balances vacíos o incompletos: " + json.dumps(res))
            return 0, 0
    else:
        if "error" in res and any("lockout" in err.lower() for err in res["error"]):
            send_message("⛔ Kraken API ha devuelto un bloqueo temporal (lockout). Esperando antes de reintentar.")
            time.sleep(60)
        else:
            send_message(f"❌ Error de Kraken al obtener balances: {json.dumps(res)}")
        return 0, 0

def get_price():
    try:
        res = requests.get("https://api.kraken.com/0/public/Ticker?pair=ETHUSD").json()
        return float(res["result"][PAIR]["c"][0])
    except:
        return 0

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        memory = {
            "trades": [],
            "balance_snapshots": [],
            "strategy_notes": "ETH Supreme Kraken initialized. Tracking trade memory and balance snapshots.",
            "last_action": None
        }
        save_memory(memory)
        return memory
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except:
        memory = {
            "trades": [],
            "balance_snapshots": [],
            "strategy_notes": "ETH Supreme Kraken recovered from memory error.",
            "last_action": None
        }
        save_memory(memory)
        return memory

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
    if "last_action" not in memory:
        memory["last_action"] = None
        save_memory(memory)
    # Mejorar mensaje de bienvenida: solo enviar si no ha sido reportado antes
    if not memory.get("last_action"):
        send_message("🧠 ETH SUPREME BOT conectado. Luciano, estoy atento al mercado para ti.")
    # --- Orden de compra inicial de test por $10 USD ---
    try:
        usdt, eth = get_balance()
        price = get_price()
        if price == 0:
            send_message("⚠️ Error inicial: No se pudo obtener el precio actual. Cancelando orden de test.")
        elif usdt < 10:
            send_message(f"⚠️ Fondos insuficientes para la orden de test. Se requieren al menos $10 USDT. Balance actual: ${usdt:.2f}")
        else:
            quantity = round(10 / price, 6)
            res = place_order("BUY", quantity)
            if "error" in res and res["error"]:
                send_message(f"⚠️ Error al ejecutar la orden de test: {res['error']}")
            else:
                memory.setdefault("trades", []).append({
                    "type": "BUY",
                    "price": price,
                    "quantity": quantity,
                    "time": datetime.now().isoformat()
                })
                memory["last_action"] = "BUY"
                save_memory(memory)
                report("BUY", price)
                usdt_post, eth_post = get_balance()
                send_message(f"✅ Orden de test completada.\nBalance nuevo:\nUSDT: ${usdt_post:.2f}\nETH: {eth_post:.6f}")

                time.sleep(5)  # Pausa breve antes de vender

                # Orden de venta de test inmediatamente después de la compra
                price = get_price()
                res_sell = place_order("SELL", quantity)
                if "error" in res_sell and res_sell["error"]:
                    send_message(f"⚠️ Error al ejecutar la orden de venta de test: {res_sell['error']}")
                else:
                    memory.setdefault("trades", []).append({
                        "type": "SELL",
                        "price": price,
                        "quantity": quantity,
                        "time": datetime.now().isoformat()
                    })
                    memory["last_action"] = "SELL"
                    save_memory(memory)
                report("SELL", price)
                usdt_post, eth_post = get_balance()
                send_message(f"✅ Venta de test completada.\nBalance nuevo:\nUSDT: ${usdt_post:.2f}\nETH: {eth_post:.6f}")
                send_message("✅ Test buy done.\nLuciano, ya ejecuté la orden en Kraken: compré y vendí como prueba. Relajate, que me encargo yo desde acá. 🚀")
    except Exception as e:
        send_message(f"❌ Error durante ejecución de orden de test inicial: {str(e)}")
    last_notified_action = memory["last_action"]

    while True:
        time.sleep(1)  # Espera mínima para evitar sobrecarga de Kraken API
        handle_command()
        # --- Idle notification block ---
        idle_minutes = 30
        last_trade_time = None
        if memory.get("trades"):
            last_trade_time = datetime.fromisoformat(memory["trades"][-1]["time"])
            price = get_price()
            if price != 0:
                elapsed = (datetime.now() - last_trade_time).total_seconds() / 60
                if elapsed > idle_minutes:
                    send_message(f"⏳ Luciano, hace {int(elapsed)} minutos que no opero. ETH está en ${price:.2f}")
        # --- End idle notification block ---
        try:
            usdt, eth = get_balance()
            price = get_price()
            if price == 0:
                send_message("⚠️ No pude obtener el precio actual, Luciano. Reintentando...")
                time.sleep(60)
                continue
            action = decision(price, usdt, eth, memory)

            if action in ["BUY", "SELL"]:
                if action == last_notified_action:
                    pass  # no repetir mensaje si es igual a la anterior
                else:
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
                        last_notified_action = action
                        save_memory(memory)
                        report(action, price)

        except Exception as e:
            send_message(f"⚠️ Luciano, algo salió mal: {str(e)}")

        time.sleep(60 + random.randint(0, 5))

if __name__ == "__main__":
    main()