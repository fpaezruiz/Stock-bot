"""
Verifica la disponibilidad de productos en todojuegos.cl y avisa por Telegram
cuando un producto pasa de "sin stock" a "disponible".

Credenciales (NUNCA se escriben en el código):
  TELEGRAM_BOT_TOKEN  -> token del bot (de @BotFather)
  TELEGRAM_CHAT_ID    -> tu chat id

En GitHub Actions vienen de los "Secrets" del repositorio.
En local se pueden poner en un archivo .env (ignorado por git).
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent
PRODUCTS_FILE = BASE_DIR / "products.json"
STATE_FILE = BASE_DIR / "state.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# La página publica el estado en el JSON-LD de schema.org y en una meta etiqueta:
#   "availability": "https://schema.org/OutOfStock"
#   <meta property="product:availability" content="out of stock">
JSONLD_RE = re.compile(r'"availability"\s*:\s*"https?://schema\.org/(\w+)"', re.I)
META_RE = re.compile(r'property="product:availability"\s+content="([^"]+)"', re.I)
PRICE_RE = re.compile(r'property="product:price:amount"\s+content="(\d+)"', re.I)

IN_STOCK_VALUES = {"instock", "in stock", "preorder", "presale", "limitedavailability"}


def load_env_file():
    """Carga un .env local si existe (solo para pruebas en tu PC)."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def check_product(url):
    """Devuelve (disponible: bool, estado_texto: str, precio: str|None)."""
    html = fetch(url)

    match = JSONLD_RE.search(html) or META_RE.search(html)
    if not match:
        raise RuntimeError("No se encontró el estado de disponibilidad en la página")

    status = match.group(1).strip()
    available = status.lower() in IN_STOCK_VALUES

    price_match = PRICE_RE.search(html)
    price = price_match.group(1) if price_match else None
    return available, status, price


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("  [!] Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID; no se envía mensaje.")
        return False

    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("ok", False)


def print_chat_ids():
    """Muestra los chat id de quienes le escribieron al bot (para configurar TELEGRAM_CHAT_ID)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Falta TELEGRAM_BOT_TOKEN en el archivo .env")
        return 1

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    with urllib.request.urlopen(url, timeout=30) as resp:
        updates = json.load(resp).get("result", [])

    chats = {}
    for update in updates:
        chat = (update.get("message") or {}).get("chat")
        if chat:
            chats[chat["id"]] = chat.get("first_name") or chat.get("title") or ""

    if not chats:
        print("No hay mensajes. Escríbele algo a tu bot en Telegram y vuelve a ejecutar.")
        return 1
    for chat_id, name in chats.items():
        print(f"chat id: {chat_id}  ({name})")
    return 0


def format_price(price):
    return f"${int(price):,}".replace(",", ".") if price else "?"


def main():
    load_env_file()

    if "--chat-id" in sys.argv:
        return print_chat_ids()

    if "--test" in sys.argv:
        ok = send_telegram("✅ Prueba del bot de stock: ¡la conexión con Telegram funciona!")
        print("Mensaje de prueba enviado" if ok else "No se pudo enviar el mensaje de prueba")
        return 0 if ok else 1

    products = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    new_state = dict(state)
    errors = 0

    for product in products:
        name, url = product["name"], product["url"]
        print(f"- {name}")
        try:
            available, status, price = check_product(url)
        except Exception as exc:
            print(f"  [!] Error revisando el producto: {exc}")
            errors += 1
            continue

        print(f"  Estado: {status} | Precio: {format_price(price)}")
        was_available = state.get(url, False)

        # Solo avisamos cuando cambia de "sin stock" a "disponible" para no hacer spam.
        if available and not was_available:
            send_telegram(
                f"🟢 ¡{name} está DISPONIBLE!\n"
                f"Precio: {format_price(price)}\n\n"
                f"{url}"
            )
            print("  -> Aviso enviado por Telegram")
        elif not available and was_available:
            print("  -> Volvió a quedar sin stock")

        new_state[url] = available

    if new_state != state:
        STATE_FILE.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")

    return 1 if errors == len(products) else 0


if __name__ == "__main__":
    sys.exit(main())
