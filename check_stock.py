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

# La página publica un estado en el JSON-LD de schema.org y en una meta etiqueta:
#   "availability": "https://schema.org/OutOfStock"
#   <meta property="product:availability" content="out of stock">
# OJO: ese estado puede decir "InStock" antes de que la tienda habilite la compra,
# así que solo se muestra como información; NO decide si avisar.
JSONLD_RE = re.compile(r'"availability"\s*:\s*"https?://schema\.org/(\w+)"', re.I)
META_RE = re.compile(r'property="product:availability"\s+content="([^"]+)"', re.I)
PRICE_RE = re.compile(r'property="product:price:amount"\s+content="(\d+)"', re.I)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
# Lo que realmente indica que se puede comprar es el botón "Agregar al carro", que llama a
# agregarCarro('{UID}'). Ese UID arma CART_ADD_URL: al abrir el link en tu navegador,
# el producto se agrega a TU carro (tu sesión).
CART_UID_RE = re.compile(r"agregarCarro\('(\{[0-9A-F-]+\})'\)", re.I)
CART_ADD_URL = "https://www.todojuegos.cl/CarroCompra/Carro_Agregar/?uidProducto={uid}"
CART_URL = "https://www.todojuegos.cl/CarroCompra/"


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
    """Devuelve (estado_texto, precio, link_agregar_al_carro o None si no hay botón)."""
    html = fetch(url)

    # Si no viene la ficha del producto, la página falló (no significa "agotado").
    match = JSONLD_RE.search(html) or META_RE.search(html)
    if not match:
        raise RuntimeError("No se encontró la información del producto en la página")
    status = match.group(1).strip()

    price_match = PRICE_RE.search(html)
    price = price_match.group(1) if price_match else None

    # Se ignoran los botones comentados en el HTML (la tienda deja algunos desactivados así).
    uid_match = CART_UID_RE.search(HTML_COMMENT_RE.sub("", html))
    cart_link = CART_ADD_URL.format(uid=uid_match.group(1)) if uid_match else None
    return status, price, cart_link


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
            status, price, cart_link = check_product(url)
        except Exception as exc:
            print(f"  [!] Error revisando el producto: {exc}")
            errors += 1
            continue

        can_buy = cart_link is not None
        print(
            f"  Estado: {status} | Precio: {format_price(price)} | "
            f"Botón carro: {'SÍ' if can_buy else 'NO'}"
        )

        # El estado guarda {"can_buy": bool}. Versiones anteriores guardaban solo true/false
        # según el "InStock" de la página; eso no sirve, así que se toma como "no comprable"
        # (y no se avisa "agotado" por ese cambio de formato).
        previous = state.get(url)
        could_buy = previous.get("can_buy", False) if isinstance(previous, dict) else False

        # Solo avisamos cuando cambia el estado, para no hacer spam.
        if can_buy and not could_buy:
            send_telegram(
                f"🟢 ¡{name} ya se puede AGREGAR AL CARRO!\n"
                f"Precio: {format_price(price)}\n\n"
                f"🛒 Agregar al carro (1 toque):\n{cart_link}\n\n"
                f"💳 Ir al carro a pagar:\n{CART_URL}\n\n"
                f"Ver producto:\n{url}"
            )
            print("  -> Aviso de disponibilidad enviado por Telegram")
        elif not can_buy and could_buy:
            send_telegram(
                f"🔴 {name} se AGOTÓ\n"
                f"(ya no aparece el botón \"Agregar al carro\")\n\n"
                f"Te avisaré si vuelve a estar disponible.\n{url}"
            )
            print("  -> Aviso de agotado enviado por Telegram")

        new_state[url] = {"can_buy": can_buy}

    if new_state != state:
        STATE_FILE.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")

    return 1 if errors == len(products) else 0


if __name__ == "__main__":
    sys.exit(main())
