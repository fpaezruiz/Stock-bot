# Bot de stock → Telegram

Revisa cada 15 minutos (con GitHub Actions, gratis en repos públicos) si los productos
de `products.json` están disponibles en todojuegos.cl y envía un mensaje a Telegram con
el link cuando un producto pasa de "sin stock" a "disponible".

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `check_stock.py` | Script principal (solo usa la librería estándar de Python) |
| `products.json` | Lista de productos a vigilar (nombre + URL) |
| `state.json` | Último estado conocido (lo crea/actualiza el bot) |
| `.github/workflows/check-stock.yml` | Programación en GitHub Actions |
| `.env.example` | Plantilla para credenciales locales |

## 1. Crear el bot de Telegram

1. En Telegram habla con **@BotFather** → `/newbot` → elige nombre y usuario.
   Te entregará el **token** (`123456789:ABC...`).
2. Abre el chat con tu nuevo bot y envíale cualquier mensaje (por ej. `hola`).
3. Copia `.env.example` como `.env`, pon tu token y ejecuta `python check_stock.py --chat-id`
   → te muestra tu **chat id**.

## 2. Probar en local (opcional)

```
copy .env.example .env      # y rellena tus datos
python check_stock.py --test    # envía un mensaje de prueba
python check_stock.py           # revisa el stock
```

## 3. Subir a GitHub y configurar los Secrets

1. Crea un repositorio nuevo (público) y sube esta carpeta.
2. En el repo: **Settings → Secrets and variables → Actions → New repository secret**:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. Pestaña **Actions** → "Revisar stock" → **Run workflow** para probarlo a mano.

Los secrets quedan cifrados: no aparecen en el código ni en los logs, aunque el repo sea público.

## Agregar más productos

Añade otro objeto a `products.json`:

```json
{ "name": "Otro producto", "url": "https://www.todojuegos.cl/Productos/..." }
```

## Notas

- El cron de GitHub usa hora UTC y puede retrasarse algunos minutos en horas de alta carga.
- GitHub desactiva los workflows programados en repos públicos tras **60 días sin actividad**
  en el repo; si eso pasa, te llega un correo y basta con reactivarlo desde la pestaña Actions.
