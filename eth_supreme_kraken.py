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

# Nueva función para enviar logs compactados
def send_compact_log(entries):
    # Agrupa los logs en un solo mensaje, evitando repeticiones excesivas.
    # Limita la longitud para evitar saturar Telegram
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
                eth_balance = float(raw.get("XETH", raw.get("ETH", 0)))
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
                eth_balance = float(raw.get("XETH", raw.get("ETH", 0)))
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

def place_order(side, quantity, log_entries=None):
    # Ejecutar orden real (validate=False)
    data = {
        "pair": PAIR,
        "type": "buy" if side == "BUY" else "sell",
        "ordertype": "market",
        "volume": f"{quantity:.6f}",
        "validate": False
    }
    response = kraken_request("AddOrder", data, log_entries=log_entries)
    order_msg = (
        f"✅ Orden REAL enviada correctamente a Kraken.\n"
        f"{side} ORDER\nAmount: {data['volume']}\nPayload: {json.dumps(data)}\nResponse: {json.dumps(response)}"
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
        last_notified_action = memory["last_action"]

        # 🔥 MODO DIOS LEGENDARIO ACTIVADO
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

        # Parámetros clave para sniper y protección
        sniper_entry_price = float(os.getenv("SNIPER_ENTRY_PRICE", "2425"))
        sniper_exit_price = float(os.getenv("SNIPER_EXIT_PRICE", "2720"))
        min_trade_usdt = float(os.getenv("MIN_TRADE_USDT", "10"))
        min_eth_amount = float(os.getenv("MIN_ETH_AMOUNT", "0.005"))

        log_entries = []
        last_log_time = time.time()
        last_full_message = None
        while True:
            try:
                # Cooldown entre ciclos: 120-150 segundos
                time.sleep(120 + random.randint(0, 30))
                modo_dios_legandario(memory)
                # 🧠 Reporte inteligente de actividad del bot cada 2 horas
                now = datetime.now()
                last_status = memory.get("last_status_report")
                if not last_status or (now - datetime.fromisoformat(last_status)).total_seconds() > 7200:
                    current_price = get_price()
                    trend = "📈 al alza" if current_price > memory.get("last_idle_price", current_price) else "📉 a la baja"
                    if memory.get("last_action") != "BUY" and memory.get("last_action") != "SELL":
                        msg_options = [
                            f"✅ Sigo vivo y analizando el mercado ETH. Último precio: ${current_price:.2f} ({trend}).",
                            f"🧠 Estoy monitoreando posibles entradas. ETH a ${current_price:.2f}, esperando oportunidad clara.",
                            f"🔎 Luciano, el bot sigue operativo. ETH se mueve {trend}, sin señales fuertes todavía."
                        ]
                        send_message(random.choice(msg_options))
                    memory["last_status_report"] = now.isoformat()
                    save_memory(memory)
                handle_command()
                # --- BLOQUE PRINCIPAL DE ANÁLISIS DE PRECIO Y DECISIONES ---
                usdt_balance, eth_balance = get_balance(log_entries=log_entries)
                current_price = get_price()
                print(f"[INFO] Balance actual → USDT: ${usdt_balance:.2f}, ETH: {eth_balance:.6f}")
                print(f"[INFO] Precio ETH actual: ${current_price:.2f}")
                if current_price == 0:
                    log_entries.append("⚠️ No pude obtener el precio actual, Luciano. Reintentando...")
                    if log_entries:
                        send_compact_log(log_entries)
                        log_entries.clear()
                    time.sleep(60)
                    continue

                # Obtener last_buy_price para protección
                trades = memory.get("trades", [])
                last_buy_price = None
                if trades:
                    last_buy = next((t for t in reversed(trades) if t["type"] == "BUY"), None)
                    if last_buy:
                        last_buy_price = last_buy["price"]
                # Protección contra pérdidas: vender si cae 2.5% desde la última compra
                if last_buy_price is not None:
                    if current_price <= last_buy_price * 0.975 and eth_balance >= min_eth_amount:
                        # lógica de venta defensiva
                        if memory.get("last_action") != "SELL":
                            res = place_order("SELL", eth_balance if eth_balance < TRADE_QUANTITY else TRADE_QUANTITY, log_entries=log_entries)
                            if "error" in res and res["error"]:
                                log_entries.append(f"⚠️ Error en venta defensiva: {res['error']}")
                            else:
                                memory.setdefault("trades", []).append({
                                    "type": "SELL",
                                    "price": current_price,
                                    "quantity": eth_balance if eth_balance < TRADE_QUANTITY else TRADE_QUANTITY,
                                    "time": datetime.now().isoformat()
                                })
                                memory["last_action"] = "SELL"
                                save_memory(memory)
                                report("SELL", current_price)

                # --- Análisis Sniper + Guardian para entrada inteligente ---
                def get_kraken_ticker():
                    try:
                        res = requests.get(f"https://api.kraken.com/0/public/Ticker?pair={PAIR}").json()
                        ticker = res["result"][PAIR]
                        # price: last trade close, volume: today, price_change_percent: 1h change
                        last_price = float(ticker["c"][0])
                        vol = float(ticker["v"][1])
                        # Calcular cambio porcentaje última hora (si disponible)
                        # Kraken no da cambio 1h directo, así que estimamos con precios históricos si fuera necesario
                        # Pero aquí solo usamos el cambio diario como aproximación
                        open_price = float(ticker.get("o", last_price))
                        price_change_percent = ((last_price - open_price) / open_price) * 100 if open_price else 0.0
                        return {
                            "price": last_price,
                            "volume": vol,
                            "price_change_percent": price_change_percent
                        }
                    except Exception as e:
                        print(f"[ERROR] get_kraken_ticker: {str(e)}")
                        return {"price": current_price, "volume": 0, "price_change_percent": 0}

                def should_enter_trade(ticker_data):
                    # Análisis Sniper + Guardian
                    current_price = float(ticker_data["price"])
                    volume = float(ticker_data["volume"])
                    price_change = float(ticker_data["price_change_percent"])
                    direction_confirmed = price_change > 1.0 and volume > 500  # parámetros ajustables

                    if direction_confirmed:
                        print(f"[SNIPER] Entry confirmed at ${current_price}")
                        return True
                    else:
                        print(f"[GUARDIAN] Entry denied at ${current_price} (vol={volume}, change={price_change}%)")
                        return False

                # Actualizar ticker_data en tiempo real antes del análisis
                ticker_data = get_kraken_ticker()
                # Protección: evitar entrar si el precio cae más de 1% en la última hora
                if ticker_data["price_change_percent"] < -1.0:
                    print("[ALERTA] El mercado está cayendo con fuerza. Entrada abortada.")
                    if memory.get("last_alert_time") is None or (datetime.now() - datetime.fromisoformat(memory.get("last_alert_time"))).total_seconds() > 3600:
                        log_entries.append("[ALERTA] El mercado está cayendo con fuerza. Entrada abortada.")
                        memory["last_alert_time"] = datetime.now().isoformat()
                        save_memory(memory)
                elif current_price <= sniper_entry_price and usdt_balance >= min_trade_usdt:
                    if memory.get("last_action") != "BUY":
                        # Solo proceder si el análisis Sniper+Guardian lo permite
                        if should_enter_trade(ticker_data):
                            buy_qty = TRADE_QUANTITY
                            max_qty = usdt_balance / current_price
                            if buy_qty > max_qty:
                                buy_qty = max_qty
                            res = place_order("BUY", buy_qty, log_entries=log_entries)
                            if "error" in res and res["error"]:
                                log_entries.append(f"⚠️ Error en compra sniper: {res['error']}")
                            else:
                                memory.setdefault("trades", []).append({
                                    "type": "BUY",
                                    "price": current_price,
                                    "quantity": buy_qty,
                                    "time": datetime.now().isoformat()
                                })
                                memory["last_action"] = "BUY"
                                save_memory(memory)
                                report("BUY", current_price)

                # Venta sniper con toma de ganancia
                if current_price >= sniper_exit_price and eth_balance >= min_eth_amount:
                    if memory.get("last_action") != "SELL":
                        # lógica de venta con toma de ganancia
                        sell_qty = eth_balance if eth_balance < TRADE_QUANTITY else TRADE_QUANTITY
                        res = place_order("SELL", sell_qty, log_entries=log_entries)
                        if "error" in res and res["error"]:
                            log_entries.append(f"⚠️ Error en venta sniper: {res['error']}")
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

                # --- FIN BLOQUE PRINCIPAL DE ANÁLISIS ---

                # Compactar logs de Telegram y reporte de estado al final del ciclo principal
                percent_change = 0.0
                if last_buy_price:
                    percent_change = ((current_price - last_buy_price) / last_buy_price) * 100
                full_message = f"""
🧠 ETH Price: ${current_price}
💰 USDT: {usdt_balance} | ETH: {eth_balance}
📈 Last Buy: ${last_buy_price if last_buy_price else 'N/A'} | P/L: {percent_change:.2f}%
"""
                # Enviar solo si el mensaje relevante cambió
                if full_message != last_full_message:
                    send_telegram_message = send_message  # alias for clarity
                    send_telegram_message(full_message)
                    last_full_message = full_message

                # Compactar logs de Telegram si hay entradas
                if log_entries and (time.time() - last_log_time > 90):
                    send_compact_log(log_entries)
                    log_entries.clear()
                    last_log_time = time.time()
            except Exception as e:
                import traceback
                print(f"[ERROR] {str(e)}")
                log_entries.append(f"⚠️ Luciano, algo salió mal: {str(e)}\n{traceback.format_exc()}")
                if log_entries:
                    send_compact_log(log_entries)
                    log_entries.clear()
                last_log_time = time.time()


# Llamada a main() si el script es ejecutado directamente
if __name__ == "__main__":
    send_message("🔍 Iniciando test de claves Kraken...")
    log_entries = []
    balance_test = kraken_request("Balance", {}, log_entries=log_entries)
    log_entries.append(f"📊 Resultado balance test: {json.dumps(balance_test)}")
    if log_entries:
        send_compact_log(log_entries)
        log_entries.clear()
    # Continuar ejecución normal...
    main()