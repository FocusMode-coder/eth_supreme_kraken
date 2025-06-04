def check_guardian_exit(price_now, price_entry, threshold_pct=1.0):
    return price_now < price_entry * (1 - threshold_pct / 100)

last_entry_price = None
import json
import datetime
from datetime import datetime, timedelta

# --- ETH Prediction Logging & Simple Forecast ---
def update_eth_prediction(price):
    try:
        with open("eth_prediction.json", "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"history": [], "prediction": []}

    timestamp = datetime.now().isoformat()
    data["history"].append({"time": timestamp, "price": price})
    data["history"] = data["history"][-120:]  # mantén últimos 120 puntos (~5 días si cada hora)

    # Simula una predicción simple (placeholder)
    last_price = price
    prediction = []
    for i in range(1, 6):
        future_time = (datetime.now() + timedelta(days=i)).isoformat()
        future_price = last_price * (1 + 0.01 * i)  # ejemplo de tendencia alcista
        prediction.append({"time": future_time, "price": round(future_price, 2)})
    data["prediction"] = prediction

    with open("eth_prediction.json", "w") as f:
        json.dump(data, f, indent=2)
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
PAIR = "ETHUSDT"
LOG_FILE = os.getenv("LOG_FILE", "kraken_log.txt")
MEMORY_FILE = "eth_memory.json"
MODE = os.getenv("MODE", "REAL")
TRADE_QUANTITY = float(os.getenv("TRADE_QUANTITY", "0.01"))

_last_telegram_msg = {"msg": None}
def send_message(msg):
    # Evitar mensajes idénticos repetidos
    global _last_telegram_msg
    try:
        if _last_telegram_msg["msg"] == msg:
            return
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
        if response.ok:
            _last_telegram_msg["msg"] = msg
        else:
            print(f"[TELEGRAM ERROR] No se pudo enviar mensaje: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[TELEGRAM EXCEPTION] {str(e)}")
def log_info(msg):
    # Log discreto, solo consola
    print(f"[INFO] {msg}")

# Función auxiliar para formatear logs de trade (orden de compra/venta real)
def format_trade_log(order_type, amount, payload, response):
    return f"""{order_type} ORDER (REAL)
Amount: {amount}
Payload: {payload}
Response: {response}"""

# Nueva función para enviar logs compactados
def send_compact_log(entries):
    # Agrupa los logs en un solo mensaje, evitando repeticiones excesivas.
    if not entries:
        return
    unique_entries = []
    seen = set()
    for entry in entries:
        if entry not in seen:
            unique_entries.append(entry)
            seen.add(entry)
    message = "\n\n".join(unique_entries)
    # Telegram limita mensajes a 4096 caracteres
    if len(message) > 4000:
        send_message(message[:4000] + "\n...(truncado)")
    else:
        send_message(message)

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

def kraken_request(endpoint, data, log_entries=None):
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
        # Registrar errores en log_entries si se provee
        if response_json.get("error") and response_json["error"]:
            if log_entries is not None:
                log_entries.append(f"[❌ Kraken Error {endpoint}] {response_json['error']}")
            else:
                send_message(f"[❌ Kraken Error {endpoint}] {response_json['error']}")
        return response_json
    except Exception as e:
        if log_entries is not None:
            log_entries.append(f"[🔥 Exception in kraken_request] {str(e)}")
        else:
            send_message(f"[🔥 Exception in kraken_request] {str(e)}")
        return {}

def get_balance(log_entries=None):
    # Solo una llamada a get_balance por ciclo, evitar repeticiones innecesarias
    time.sleep(3)
    res = kraken_request("Balance", {}, log_entries=log_entries)
    if res and "result" in res:
        try:
            raw = res["result"]
            memory = load_memory()
            # Report only if changed
            if memory.get("last_balance_report") != raw:
                balance_msg = f"BALANCE CHECK\n"
                usdt_balance = 0
                for k, v in raw.items():
                    if "USDT" in k.upper():
                        usdt_balance = float(v)
                        break
                eth_balance = float(raw.get("ETH", raw.get("XETH", 0)))
                balance_msg += f"USDT: {usdt_balance:.2f}\nETH: {eth_balance:.5f}"
                if log_entries is not None:
                    log_entries.append(balance_msg)
                else:
                    send_message(balance_msg)
                memory["last_balance_report"] = raw
                save_memory(memory)
            else:
                usdt_balance = 0
                for k, v in raw.items():
                    if "USDT" in k.upper():
                        usdt_balance = float(v)
                        break
                eth_balance = float(raw.get("ETH", raw.get("XETH", 0)))
            return usdt_balance, eth_balance
        except Exception as e:
            err_msg = f"❌ Error interpretando balances Kraken: {json.dumps(res)} - {str(e)}"
            if log_entries is not None:
                log_entries.append(err_msg)
            else:
                send_message(err_msg)
            return 0, 0
    else:
        err_msg = "❌ Error de Kraken: respuesta vacía o sin 'result' al pedir balances."
        if log_entries is not None:
            log_entries.append(err_msg)
        else:
            send_message(err_msg)
        return 0, 0

def get_price():
    try:
        res = requests.get(f"https://api.kraken.com/0/public/Ticker?pair={PAIR}").json()
        return float(res["result"][PAIR]["c"][0])
    except Exception as e:
        print(f"[ERROR] No se pudo obtener el precio ETH: {str(e)}")
        return 0

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        memory = {
            "trades": [],
            "balance_snapshots": [],
            "strategy_notes": "ETH Supreme Kraken initialized. Tracking trade memory and balance snapshots.",
            "last_action": None,
            "last_lockout_warning": None,
            "last_funds_warning": None,
            "last_alert_time": None
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
            if "last_alert_time" not in memory:
                memory["last_alert_time"] = None
            return memory
    except:
        memory = {
            "trades": [],
            "balance_snapshots": [],
            "strategy_notes": "ETH Supreme Kraken recovered from memory error.",
            "last_action": None,
            "last_lockout_warning": None,
            "last_funds_warning": None,
            "last_alert_time": None
        }
        save_memory(memory)
        return memory

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def place_order(side, quantity, log_entries=None, validate=False):
    # Ejecutar orden real
    nonce = str(int(1000 * time.time()))
    data = {
        "pair": "ETHUSDT",
        "type": "buy" if side == "BUY" else "sell",
        "ordertype": "market",
        "volume": f"{quantity:.6f}",
        "validate": validate,  # Real order, not validate/simulated
        "nonce": nonce
    }
    response = kraken_request("AddOrder", data, log_entries=log_entries)
    order_msg = (
        f"✅ ORDEN REAL ENVIADA A KRAKEN\n"
        f"Tipo: {side}\n"
        f"Monto: {data['volume']} ETH\n"
        f"Precio estimado: {json.dumps(response.get('result', {}))}\n"
        f"{format_trade_log(side, data['volume'], json.dumps(data), json.dumps(response))}"
    )
    if log_entries is not None:
        log_entries.append(order_msg)
    else:
        send_message(order_msg)
    return response

def decision(price, usdt, eth, memory):
    last = memory["last_action"]
    trades = memory.get("trades", [])

    # Estrategia: sniper + protección
    if last == "BUY" and trades:
        last_buy = next((t for t in reversed(trades) if t["type"] == "BUY"), None)
        if last_buy:
            buy_price = last_buy["price"]
            # Protección: vender si cae más de 2.5%
            if price < buy_price * 0.975 and eth >= TRADE_QUANTITY:
                return "SELL"
            # Ganancia: vender si sube más de 3%
            if price >= buy_price * 1.03 and eth >= TRADE_QUANTITY:
                return "SELL"

    # Entrada sniper: comprar fuerte bajo $2425 con confianza
    if price > 0 and price < 2425 and usdt >= price * TRADE_QUANTITY and last != "BUY":
        return "BUY"

    # Venta sniper: vender fuerte si supera los $2720
    if price > 2720 and eth >= TRADE_QUANTITY and last != "SELL":
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
    memory.setdefault("last_balance_report", None)
    send_message("✅ ETH SUPREME BOT relanzado correctamente. Esperando balance y ejecutando chequeos iniciales...")
    send_message("📡 Sniper activo. Analizando condiciones...\nPróximo log automático en 2h. Te avisaré si detecto señales reales. 🚀")

    # Verificación de claves esenciales
    if not API_KEY or not PRIVATE_KEY or not BASE_URL:
        send_message("❌ ERROR: Faltan claves esenciales de Kraken en el .env.")
        return

    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    else:
        send_message("ℹ️ Bot revisó las claves de entorno. Ver consola de Render para más info.")
        if "last_action" not in memory:
            memory["last_action"] = None
            save_memory(memory)
        memory.setdefault("last_lockout_warning", None)
        memory.setdefault("last_funds_warning", None)
        save_memory(memory)
        if not memory.get("last_action"):
            if not memory.get("last_connection_reported") or (datetime.now() - datetime.fromisoformat(memory.get("last_connection_reported", "1970-01-01T00:00:00"))).total_seconds() > 3600:
                send_message("🧠 ETH SUPREME BOT conectado. Luciano, estoy atento al mercado para ti.")
                memory["last_connection_reported"] = datetime.now().isoformat()
                save_memory(memory)
        last_notified_action = memory["last_action"]

        # --- Función para cargar señal externa desde JSON ---
        def cargar_senal_desde_json():
            try:
                with open("eth_prediction.json", "r") as f:
                    data = json.load(f)
                    if isinstance(data, list) and data:
                        return data[-1]  # Toma la última señal
            except Exception as e:
                print(f"[ERROR] Fallo al leer señales: {e}")
            return None

        # --- Cargar memoria adicional desde eth_memory.json ---
        try:
            with open("eth_memory.json", "r") as memory_file:
                eth_memory = json.load(memory_file)
        except (FileNotFoundError, json.JSONDecodeError):
            eth_memory = {"last_volume": None, "last_timestamp": None}

        def modo_dios_legandario(memory):
            now = datetime.now()
            last_trade_time = None
            if memory.get("trades"):
                last_trade_time = datetime.fromisoformat(memory["trades"][-1]["time"])
            else:
                last_trade_time = now - timedelta(minutes=999)

            elapsed_minutes = (now - last_trade_time).total_seconds() / 60
            memory["last_checkup"] = now.isoformat()

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

        sniper_entry_price = float(os.getenv("SNIPER_ENTRY_PRICE", "2425"))
        sniper_exit_price = float(os.getenv("SNIPER_EXIT_PRICE", "2720"))
        min_trade_usdt = float(os.getenv("MIN_TRADE_USDT", "10"))
        min_eth_amount = float(os.getenv("MIN_ETH_AMOUNT", "0.005"))

        log_entries = []
        last_log_time = time.time()
        last_status_log_time = time.time()
        last_full_message = None

        # --- Sniper y Guardian logic helpers ---
        def detect_whale_spike():
            # Implementar lógica real de ballenas aquí. Por ahora, simulación simple:
            # Por ejemplo, si el volumen actual supera 2x el promedio reciente
            if len(volumes) < 5:
                return False
            avg_vol = sum(volumes[-5:-1]) / 4
            return volumes[-1] > avg_vol * 2

        def is_sniper_entry(price_data, volume_data):
            # Obsoleta, reemplazada por lógica más afinada abajo
            return False

        def should_exit_trade(entry_price, current_price):
            gain = current_price - entry_price
            return gain >= 2 or gain <= -1  # toma ganancia o corta pérdida

        # --- Main loop ---
        prices = []
        volumes = []
        price_history_length = 15
        current_position = "USDT"
        global last_entry_price
        import traceback
        while True:
            try:
                time.sleep(120 + random.randint(0, 30))
                modo_dios_legandario(memory)
                now = datetime.now()
                handle_command()
                usdt_balance, eth_balance = get_balance(log_entries=log_entries)
                current_price = get_price()

                # Guardian exit check BEFORE evaluating new signals/decisions
                if current_position == "ETH" and last_entry_price is not None:
                    if check_guardian_exit(current_price, last_entry_price):
                        print("🛡️ Guardian activado: vendiendo ETH para proteger capital")
                        bot = type("Bot", (), {"send_message": send_message})  # dummy for context if needed
                        chat_id = CHAT_ID
                        bot.send_message(chat_id, f'🛡️ Guardian activado: vendiendo ETH para proteger capital')
                        with open("kraken_log.txt", "a") as log_file:
                            log_file.write(f"{datetime.datetime.now()} - Guardian: Vendida posición ETH para proteger capital a {current_price}\n")
                        def sell_eth():
                            sell_qty = eth_balance if eth_balance < TRADE_QUANTITY else TRADE_QUANTITY
                            res = place_order("SELL", sell_qty, log_entries=log_entries)
                            if "error" in res and res["error"]:
                                log_entries.append(f"⚠️ Error en venta guardian: {res['error']}")
                                send_compact_log(log_entries)
                                log_entries.clear()
                            else:
                                memory.setdefault("trades", []).append({
                                    "type": "SELL",
                                    "price": current_price,
                                    "quantity": sell_qty,
                                    "time": datetime.now().isoformat()
                                })
                                memory["last_action"] = "SELL"
                                save_memory(memory)
                                report("SELL", current_price)
                                send_message(f"🚨 Guardian activado: vendido {sell_qty:.5f} ETH a ${current_price:.2f} para proteger capital.")
                        sell_eth()
                        current_position = "USDT"
                        last_entry_price = None
                        continue
                # --- Señal externa desde JSON ---
                senal = cargar_senal_desde_json()
                if senal:
                    accion = senal.get("signal")
                    if accion == "buy":
                        print("⚡ Señal externa detectada: COMPRAR")
                        # ejecutar_compra_eth()
                    elif accion == "sell":
                        print("⚡ Señal externa detectada: VENDER")
                        # ejecutar_venta_eth()

                # --- Mostrar volumen y timestamp desde eth_memory.json en logs ---
                print(f"🔁 Último volumen registrado: {eth_memory['last_volume']} a las {eth_memory['last_timestamp']}")
                # --- Registro de precio y predicción ETH ---
                update_eth_prediction(current_price)
                if current_price == 0:
                    log_entries.append("⚠️ No pude obtener el precio actual, Luciano. Reintentando...")
                    if log_entries:
                        send_compact_log(log_entries)
                        log_entries.clear()
                    time.sleep(60)
                    continue
                # --- Price & volume history for Sniper logic ---
                try:
                    res = requests.get(f"https://api.kraken.com/0/public/Ticker?pair={PAIR}").json()
                    ticker = res["result"][PAIR]
                    price_tick = float(ticker["c"][0])
                    volume_tick = float(ticker["v"][1])
                except Exception:
                    price_tick = current_price
                    volume_tick = 0
                prices.append(price_tick)
                volumes.append(volume_tick)
                if len(prices) > price_history_length:
                    prices = prices[-price_history_length:]
                    volumes = volumes[-price_history_length:]
                # --- Sniper Entrada (compra) ---
                sniper_signal = False
                strong_conditions = []
                if len(prices) >= 6 and len(volumes) >= 5:
                    previous_price = prices[-6]
                    price_change = (prices[-1] - previous_price) / previous_price * 100 if previous_price != 0 else 0
                    average_volume = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else (sum(volumes) / len(volumes) if len(volumes) > 0 else 1)
                    current_volume = volumes[-1]
                    volume_change = current_volume / average_volume if average_volume > 0 else 0
                    whale_activity_detected = detect_whale_spike()
                    # Condiciones fuertes
                    if volume_change > 1.5:
                        strong_conditions.append("Volumen superior al promedio")
                    if price_change > 2.0:
                        strong_conditions.append("Spike de precio")
                    if whale_activity_detected:
                        strong_conditions.append("Ballena detectada")
                    # Confirmación de tendencia: al menos dos condiciones fuertes
                    if len(strong_conditions) >= 2:
                        sniper_signal = True
                    # Solo enviar log automático cada 2 horas y solo si ya se hizo la compra inicial forzada
                    if time.time() - last_status_log_time > 7200 and memory.get("initial_forced_buy_done"):
                        msg = (f"🔁 Estado del bot (Sniper)\n"
                               f"Precio: ${current_price:.2f}\n"
                               f"Cambio precio: {price_change:.2f}%\n"
                               f"Volumen: {current_volume:.2f} ({volume_change:.2f}x)\n"
                               f"Condiciones: {', '.join(strong_conditions) if strong_conditions else 'Ninguna fuerte'}\n"
                               f"Próximo log automático en 2h.\n"
                               f"🔁 Último volumen registrado: {eth_memory['last_volume']} a las {eth_memory['last_timestamp']}")
                        send_message(msg)
                        last_status_log_time = time.time()
                    # Señal fuerte inmediata
                    if sniper_signal and memory.get("last_action") != "BUY" and usdt_balance >= min_trade_usdt:
                        buy_qty = TRADE_QUANTITY
                        max_qty = usdt_balance / current_price
                        if buy_qty > max_qty:
                            buy_qty = max_qty
                        if usdt_balance < min_trade_usdt:
                            log_entries.append("❌ Capital insuficiente para operar (mínimo $10 USDT).")
                        else:
                            res = place_order("BUY", buy_qty, log_entries=log_entries)
                            if "error" in res and res["error"]:
                                log_entries.append(f"⚠️ Error en compra sniper: {res['error']}")
                                send_compact_log(log_entries)
                                log_entries.clear()
                            else:
                                memory.setdefault("trades", []).append({
                                    "type": "BUY",
                                    "price": current_price,
                                    "quantity": buy_qty,
                                    "time": datetime.now().isoformat()
                                })
                                memory["last_action"] = "BUY"
                                memory["last_action_reason"] = f"Sniper entry: {' y '.join(strong_conditions)}"
                                save_memory(memory)
                                report("BUY", current_price)
                                # Log conciso tras operación
                                send_message(f"🚀 Señal fuerte de compra detectada: {', '.join(strong_conditions)}.\nComprado {buy_qty:.5f} ETH a ${current_price:.2f}.")
                                last_status_log_time = time.time()
                                # GUARDIAN: registrar precio de entrada
                                last_entry_price = current_price
                                current_position = "ETH"

                    # === Alerta visual para Dashboard ===
                    if sniper_signal and strong_conditions:
                        alert = {
                            "time": int(time.time() * 1000),
                            "message": f"⚠️ Señal fuerte detectada: {', '.join(strong_conditions)} a ${current_price:.2f}"
                        }
                        try:
                            if os.path.exists("eth_alerts.json"):
                                with open("eth_alerts.json", "r") as f:
                                    alert_data = json.load(f)
                            else:
                                alert_data = []
                            alert_data.append(alert)
                            alert_data = alert_data[-20:]
                            with open("eth_alerts.json", "w") as f:
                                json.dump(alert_data, f, indent=2)
                        except Exception as e:
                            print(f"[ERROR] No se pudo guardar alerta visual: {str(e)}")
                # --- Guardian Salida (venta) ---
                trades = memory.get("trades", [])
                entry_price = None
                if trades:
                    last_buy = next((t for t in reversed(trades) if t["type"] == "BUY"), None)
                    if last_buy:
                        entry_price = last_buy["price"]

                # Protección automática si ETH cae más de 1.5%
                if entry_price and eth_balance > min_eth_amount:
                    drop_pct = ((entry_price - current_price) / entry_price) * 100
                    if drop_pct >= 1.5:
                        log_entries.append(f"⚠️ ETH cayó {drop_pct:.2f}% desde la compra (${entry_price:.2f} ➜ ${current_price:.2f})")
                        sell_qty = eth_balance
                        res = place_order("SELL", sell_qty, log_entries=log_entries)
                        if "error" in res and res["error"]:
                            log_entries.append(f"❌ Error al vender por caída: {res['error']}")
                        else:
                            memory.setdefault("trades", []).append({
                                "type": "SELL",
                                "price": current_price,
                                "quantity": sell_qty,
                                "time": datetime.now().isoformat()
                            })
                            memory["last_action"] = "SELL"
                            save_memory(memory)
                            report("SELL", current_price)
                            send_message(f"💥 Protección activada. Vendido {sell_qty:.5f} ETH a ${current_price:.2f} por caída de mercado.")
                guardian_signal = False
                if entry_price is not None and eth_balance >= min_eth_amount:
                    if should_exit_trade(entry_price, current_price):
                        guardian_signal = True
                if guardian_signal and memory.get("last_action") != "SELL":
                    sell_qty = eth_balance if eth_balance < TRADE_QUANTITY else TRADE_QUANTITY
                    res = place_order("SELL", sell_qty, log_entries=log_entries)
                    if "error" in res and res["error"]:
                        log_entries.append(f"⚠️ Error en venta guardian: {res['error']}")
                        send_compact_log(log_entries)
                        log_entries.clear()
                    else:
                        memory.setdefault("trades", []).append({
                            "type": "SELL",
                            "price": current_price,
                            "quantity": sell_qty,
                            "time": datetime.now().isoformat()
                        })
                        memory["last_action"] = "SELL"
                        save_memory(memory)
                        report("SELL", current_price)
                        send_message(f"🚨 Señal fuerte de venta: condiciones Guardian alcanzadas.\nVendido {sell_qty:.5f} ETH a ${current_price:.2f}.")
                        last_status_log_time = time.time()

                # Fuerza una compra inicial apenas inicie el bot (solo una vez)
                if not memory.get("initial_forced_buy_done", False):
                    current_price = get_price()  # asegurar que este valor esté actualizado
                    usdt_balance, eth_balance = get_balance(log_entries=log_entries)

                    # Nueva verificación: no forzar compra inicial si ya hay ETH suficiente
                    if eth_balance > min_eth_amount:
                        log_entries.append(f"✅ Ya tenés ETH ({eth_balance:.5f}), se omite compra inicial forzada.")
                        memory["initial_forced_buy_done"] = True
                        save_memory(memory)
                    else:
                        if usdt_balance >= min_trade_usdt:
                            trade_qty = round(usdt_balance / current_price, 6)
                            log_entries.append(f"🚨 Forzando compra inicial de {trade_qty} ETH...")
                            res = place_order("BUY", trade_qty, log_entries=log_entries, validate=False)

                            # Nuevo bloque: registrar la compra inicial solo si fue exitosa
                            if "error" not in res or not res["error"]:
                                memory["last_action"] = "BUY"
                                memory["last_action_reason"] = "Compra inicial forzada"
                                memory.setdefault("trades", []).append({
                                    "type": "BUY",
                                    "price": current_price,
                                    "quantity": trade_qty,
                                    "time": datetime.now().isoformat()
                                })
                                save_memory(memory)
                                report("BUY", current_price)
                                # GUARDIAN: registrar precio de entrada
                                last_entry_price = current_price
                                current_position = "ETH"

                            if res["error"]:
                                log_entries.append(f"⚠️ Error en compra inicial forzada: {res['error']}")
                            else:
                                log_entries.append("✅ Compra inicial forzada ejecutada correctamente.")

                        else:
                            log_entries.append("❌ Capital insuficiente para compra inicial forzada.")

                        memory["initial_forced_buy_done"] = True
                        save_memory(memory)

                # Enviar logs de errores o eventos críticos de Kraken inmediatamente
                if log_entries:
                    # Si hay logs importantes, agregar info de memoria extra al mensaje para dashboard
                    # Si se está generando un mensaje JSON para dashboard, aquí ejemplo:
                    # dashboard_data = {..., "last_volume": eth_memory['last_volume'], "last_timestamp": eth_memory['last_timestamp']}
                    send_compact_log(log_entries)
                    log_entries.clear()
            except Exception as e:
                log_entries.append(f"⚠️ Luciano, algo salió mal: {str(e)}\n{traceback.format_exc()}")
                if log_entries:
                    send_compact_log(log_entries)
                    log_entries.clear()



# === Bloque para cargar último estado de memoria ETH y preparar datos para dashboard ===
import json

# Cargar último estado de memoria ETH
try:
    # Placeholder logic if needed, currently does nothing.
    pass
except Exception as e:
    print(f"❌ Error durante ejecución final: {str(e)}")


if __name__ == "__main__":
    send_message("🔍 Iniciando test de claves Kraken...")
    log_entries = []
    balance_test = kraken_request("Balance", {}, log_entries=log_entries)
    log_entries.append(f"📊 Resultado balance test: {json.dumps(balance_test)}")
    if log_entries:
        send_compact_log(log_entries)
        log_entries.clear()
    main()