import os
import time
import json
import hmac
import hashlib
import base64
import requests
import urllib.parse
from datetime import datetime, timedelta
from dotenv import load_dotenv
import random

# Load environment
load_dotenv()
API_KEY = "f+0PG7YffmN2G/a3ebGkKtBwyaCHUcH1WXTHZNBmVN1d+D4nZbaTobcI"
PRIVATE_KEY = "p/3THTJpykhJpVXa2EA3ofg6802Inu9ry/secnKTunfVzvKtINkcGKaznetgf40hpM6+UIL3XJnw8/mDJrYZeA=="
BASE_URL = os.getenv("KRAKEN_BASE_URL")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7613460488")
PAIR = "XETHZUSD"
LOG_FILE = os.getenv("LOG_FILE", "kraken_log.txt")
MEMORY_FILE = "eth_memory.json"
MODE = os.getenv("MODE", "REAL")
TRADE_QUANTITY = float(os.getenv("TRADE_QUANTITY", "0.01"))

def send_message(msg):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
        if not response.ok:
            print(f"[TELEGRAM ERROR] No se pudo enviar mensaje: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[TELEGRAM EXCEPTION] {str(e)}")

def handle_command():
    try:
        offset_file = "telegram_offset.txt"
        offset = 0
        if os.path.exists(offset_file):
            with open(offset_file, "r") as f:
                offset = int(f.read().strip())

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset + 1}"
        res = requests.get(url).json()

        for update in res.get("result", []):
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id"))
            update_id = update["update_id"]

            # Always compare to CHAT_ID variable
            if chat_id != CHAT_ID:
                continue

            if "/status" in text.lower():
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

            elif "/diagnostico" in text.lower():
                try:
                    price = get_price()
                    usdt, eth = get_balance()
                    mem = load_memory()
                    msg = (
                        f"🧪 Diagnóstico del bot Kraken:\n"
                        f"- Precio ETH actual: ${price:.2f}\n"
                        f"- Balance:\n  • USDT: ${usdt:.2f}\n  • ETH: {eth:.6f}\n"
                        f"- Última acción: {mem.get('last_action', 'Ninguna')}\n"
                        f"- Último trade: {mem['trades'][-1] if mem.get('trades') else 'Ninguno'}\n"
                        f"- Estrategia activa: Decision lógica basada en precio y memoria\n"
                        f"- Estado: {'ACTIVO ✅' if price > 0 else 'SIN CONEXIÓN ❌'}"
                    )
                    send_message(msg)
                except Exception as e:
                    send_message(f"❌ Error en diagnóstico: {str(e)}")

            # Guardar el offset actualizado
            with open(offset_file, "w") as f:
                f.write(str(update_id))
    except Exception as e:
        send_message(f"❌ Error al procesar comandos de Telegram: {str(e)}")

def kraken_request(endpoint, data):
    try:
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
        response_json = res.json()
        
        # DEBUG: Telegram log si hay error
        if response_json.get("error"):
            send_message(f"[❌ Kraken Error {endpoint}] {response_json['error']}")
        
        return response_json
    except Exception as e:
        send_message(f"[🔥 Exception in kraken_request] {str(e)}")
        return {}

def get_balance():
    time.sleep(3)
    res = kraken_request("Balance", {})
    if res and "result" in res:
        try:
            raw = res["result"]
            # DEBUG: log crudo para ver si los keys están bien
            send_message(f"📊 Balance crudo: {json.dumps(raw)}")
            # Convertir todos los balances a float por seguridad
            balances = {k.upper(): float(v) for k, v in raw.items()}
            usdt_balance = balances.get("USDT", balances.get("ZUSD", 0))
            eth_balance = balances.get("ETH", balances.get("XETH", 0))
            return usdt_balance, eth_balance
        except Exception as e:
            send_message(f"❌ Error interpretando balances Kraken: {json.dumps(res)} - {str(e)}")
            return 0, 0
    else:
        send_message("❌ Error de Kraken: respuesta vacía o sin 'result' al pedir balances.")
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
            "last_action": None,
            "last_lockout_warning": None,
            "last_funds_warning": None
        }
        save_memory(memory)
        return memory
    try:
        with open(MEMORY_FILE, "r") as f:
            memory = json.load(f)
            # Asegurar claves por defecto
            if "last_lockout_warning" not in memory:
                memory["last_lockout_warning"] = None
            if "last_funds_warning" not in memory:
                memory["last_funds_warning"] = None
            return memory
    except:
        memory = {
            "trades": [],
            "balance_snapshots": [],
            "strategy_notes": "ETH Supreme Kraken recovered from memory error.",
            "last_action": None,
            "last_lockout_warning": None,
            "last_funds_warning": None
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
    msg = random.choice(emotional_msgs[trade_type]).format(qty=TRADE_QUANTITY, prc=price)
    msg += f"\n🤖 Bot Supremo en acción.\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    send_message(f"{emoji} {msg}")

def main():
    send_message("🟢 Test directo: el bot Kraken está vivo y conectado.")
    memory = load_memory()
    send_message("✅ ETH SUPREME BOT relanzado correctamente. Esperando balance y ejecutando chequeos iniciales...")
    print("BOT relanzado correctamente, comenzando chequeo de balance...")
    print("🔍 Verificando estado de conexión inicial...")

    # Verificación de claves esenciales
    if not API_KEY or not PRIVATE_KEY or not BASE_URL:
        send_message("❌ ERROR: Faltan claves esenciales de Kraken en el .env.")
        print("❌ ERROR: Faltan claves esenciales de Kraken en el .env.")
    else:
        print("✅ Claves Kraken cargadas correctamente.")

    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ ERROR: Faltan claves de Telegram en el .env.")
        return
    else:
        print("✅ Claves de Telegram cargadas correctamente.")

        send_message("ℹ️ Bot revisó las claves de entorno. Ver consola de Render para más info.")
        if "last_action" not in memory:
            memory["last_action"] = None
            save_memory(memory)
        # Asegura que la clave last_lockout_warning exista y persiste
        memory.setdefault("last_lockout_warning", None)
        memory.setdefault("last_funds_warning", None)
        save_memory(memory)
        # Mejorar mensaje de bienvenida: solo enviar si no ha sido reportado antes de 1 hora
        if not memory.get("last_action"):
            if not memory.get("last_connection_reported") or (datetime.now() - datetime.fromisoformat(memory.get("last_connection_reported", "1970-01-01T00:00:00"))).total_seconds() > 3600:
                send_message("🧠 ETH SUPREME BOT conectado. Luciano, estoy atento al mercado para ti.")
                memory["last_connection_reported"] = datetime.now().isoformat()
                save_memory(memory)
        # --- Orden de compra inicial de test por $10 USD ---
        try:
            usdt, eth = get_balance()
            price = get_price()
            now = datetime.now()
            if price == 0:
                send_message("⚠️ Error inicial: No se pudo obtener el precio actual. Cancelando orden de test.")
            elif usdt < 10:
                last_warning = memory.get("last_funds_warning")
                if not last_warning or (now - datetime.fromisoformat(last_warning)).total_seconds() > 3600:
                    send_message(f"⚠️ Fondos insuficientes para la orden de test. Se requieren al menos $10 USDT. Balance actual: ${usdt:.2f}")
                    memory["last_funds_warning"] = now.isoformat()
                    save_memory(memory)
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

        # 🔥 MODO DIOS LEGENDARIO ACTIVADO
        def modo_dios_legandario(memory):
            # Detecta si el bot lleva mucho tiempo sin ejecutar una acción o con errores repetidos
            now = datetime.now()
            last_trade_time = None
            if memory.get("trades"):
                last_trade_time = datetime.fromisoformat(memory["trades"][-1]["time"])
            else:
                last_trade_time = now - timedelta(minutes=999)

            elapsed_minutes = (now - last_trade_time).total_seconds() / 60
            memory["last_checkup"] = now.isoformat()

            # Si pasaron más de 90 minutos sin operar y el precio se movió más de 1.5%, enviar alerta
            if elapsed_minutes > 90:
                current_price = get_price()
                if "last_idle_price" not in memory:
                    memory["last_idle_price"] = current_price
                    save_memory(memory)
                else:
                    price_diff = abs(current_price - memory["last_idle_price"]) / memory["last_idle_price"]
                    if price_diff > 0.015:
                        send_message(f"⚠️ MODO DIOS detectó inactividad prolongada con movimiento de mercado.\n"
                                     f"Pasaron {int(elapsed_minutes)} min sin operar y el precio se movió más de 1.5%\n"
                                     f"ETH ahora está en ${current_price:.2f}.\n"
                                     f"👉 Considerá revisar o reiniciar manualmente el bot.")
                        memory["last_idle_price"] = current_price
                        save_memory(memory)

        while True:
            time.sleep(60 + random.randint(0, 5))  # Espera mínima para evitar sobrecarga de Kraken API
            modo_dios_legandario(memory)
            # 🧠 Reporte inteligente de actividad del bot cada 30 minutos
            now = datetime.now()
            last_status = memory.get("last_status_report")
            if not last_status or (now - datetime.fromisoformat(last_status)).total_seconds() > 1800:
                current_price = get_price()
                trend = "📈 al alza" if current_price > memory.get("last_idle_price", current_price) else "📉 a la baja"
                msg_options = [
                    f"✅ Sigo vivo y analizando el mercado ETH. Último precio: ${current_price:.2f} ({trend}).",
                    f"🧠 Estoy monitoreando posibles entradas. ETH a ${current_price:.2f}, esperando oportunidad clara.",
                    f"🔎 Luciano, el bot sigue operativo. ETH se mueve {trend}, sin señales fuertes todavía."
                ]
                send_message(random.choice(msg_options))
                memory["last_status_report"] = now.isoformat()
                save_memory(memory)
            handle_command()
            try:
                usdt, eth = get_balance()
                print(f"[INFO] Balance actual → USDT: ${usdt:.2f}, ETH: {eth:.6f}")
                price = get_price()
                print(f"[INFO] Precio ETH actual: ${price:.2f}")
                if price == 0:
                    send_message("⚠️ No pude obtener el precio actual, Luciano. Reintentando...")
                    time.sleep(60)
                    continue
                # --- Idle notification block ---
                if memory.get("trades") and price != 0:
                    last_trade_time = datetime.fromisoformat(memory["trades"][-1]["time"])
                    elapsed = (datetime.now() - last_trade_time).total_seconds() / 60
                    idle_minutes = 30
                    if elapsed > idle_minutes:
                        send_message(f"⏳ Luciano, hace {int(elapsed)} minutos que no opero. ETH está en ${price:.2f}")
                # --- End idle notification block ---

                action = decision(price, usdt, eth, memory)

                if action in ["BUY", "SELL"]:
                    print(f"[TRADE DECISION] Acción decidida: {action}")
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
                print(f"[ERROR] {str(e)}")
                send_message(f"⚠️ Luciano, algo salió mal: {str(e)}")


# Llamada a main() si el script es ejecutado directamente
if __name__ == "__main__":
    send_message("🔍 Iniciando test de claves Kraken...")
    balance_test = kraken_request("Balance", {})
    send_message(f"📊 Resultado balance test: {json.dumps(balance_test)}")
    # Continuar ejecución normal...
    main()