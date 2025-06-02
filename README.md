

# ETH Supreme Kraken Bot

Bienvenido al bot ETH_SUPREME para Kraken Pro – versión definitiva.

## 🚀 Funcionalidades Clave

- Compra y venta automática de ETH usando la API real de Kraken Pro.
- Lógica híbrida: Sniper + Guardian + Whale.
- Logs en tiempo real y reportes controlados cada 2 horas.
- Integración completa con Telegram: notifica solo cuando importa.
- Soporte para operaciones forzadas al iniciar.
- Memoria estratégica activada (`eth_memory.json`).

## 🛠️ Requisitos

- Python 3.11+
- Claves API reales de Kraken (con permisos de trading)
- Archivo `.env` con:
  ```
  KRAKEN_API_KEY=TU_API_KEY
  KRAKEN_API_SECRET=TU_API_SECRET
  TELEGRAM_TOKEN=TU_TOKEN
  TELEGRAM_CHAT_ID=TU_CHAT_ID
  ```

## 📦 Instalación

```
pip install -r requirements.txt
python eth_supreme_kraken.py
```

## 📡 Comandos útiles (Telegram)

- `/status` → Muestra el estado actual.
- `/log` → Último log relevante.
- `/forzar_compra` → Fuerza una compra mínima al precio actual.

## 🧠 Lógica Operativa

- El bot analiza condiciones de mercado cada X minutos.
- Solo actúa si las condiciones de Sniper/Guardian son óptimas.
- Evita pérdidas mayores y actúa en oportunidades reales.

## 🧪 Modo Dios

El bot está optimizado para operar sin supervisión humana. Todo ha sido revisado y afinado para asegurar una ejecución impecable desde el inicio.

---
Desarrollado por LucianoAI 🧠