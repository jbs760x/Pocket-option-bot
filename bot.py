import os
import requests
from fastapi import FastAPI, Request, Query
from typing import Optional

# Hardcoded fallbacks so you don't need to touch env vars to test:
BOT_TOKEN = os.getenv("BOT_TOKEN", "8471181182:AAEKGH1UASa5XvkXscb3jb5d1Yz19B8oJNM")
TWELVE_API_KEY = os.getenv("TWELVE_API_KEY", "9aa4ea677d00474aa0c3223d0c812425")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # optional

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TD_URL  = "https://api.twelvedata.com/time_series"

app = FastAPI()

def tg_send(chat_id: int, text: str, parse_mode: Optional[str] = None):
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    r = requests.post(f"{TG_API}/sendMessage", json=data, timeout=20)
    print("[sendMessage]", r.status_code, r.text[:200], flush=True)
    return r.ok, r.text

def td_last(symbol: str, interval: str = "1min"):
    s = symbol.replace("/", "")
    params = {"symbol": s, "interval": interval, "apikey": TWELVE_API_KEY,
              "outputsize": 1, "order": "ASC"}
    r = requests.get(TD_URL, params=params, timeout=30)
    try:
        js = r.json()
    except Exception:
        js = {"error": r.text}
    if "values" not in js or not js["values"]:
        return None, js
    v = js["values"][-1]
    return {
        "dt": v.get("datetime"),
        "open": v.get("open"), "high": v.get("high"),
        "low": v.get("low"), "close": v.get("close"),
        "symbol": symbol
    }, js

@app.get("/")
def home():
    return {"ok": True, "routes": ["/health", "/echo", "/__test", "/webhook (POST)"]}

@app.get("/health")
def health():
    return {"ok": True}

# ----- Zero-setup test: send yourself a message WITHOUT env vars -----
# Use: /echo?chat_id=123456789&text=ping
@app.get("/echo")
def echo(chat_id: int = Query(...), text: str = Query("hello from server")):
    ok, body = tg_send(chat_id, f"✅ ECHO: {text}")
    return {"ok": ok, "telegram_response": body}

# ----- Env-var test (optional) -----
# If you set ADMIN_CHAT_ID in Railway Variables, this sends a test message.
@app.get("/__test")
def test(msg: str = "ping"):
    if not ADMIN_CHAT_ID:
        return {"ok": False, "error": "Set ADMIN_CHAT_ID env var to your numeric chat id."}
    ok, body = tg_send(int(ADMIN_CHAT_ID), f"✅ TEST: {msg}")
    return {"ok": ok, "telegram_response": body}

# ----- Webhook: replies to /start, /last, /latency -----
@app.post("/webhook")
async def webhook(req: Request):
    upd = await req.json()
    print("[webhook] update:", upd, flush=True)

    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return {"ok": True}

    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()

    if text.lower().startswith("/start"):
        tg_send(chat_id,
            "🤖 Bot is live!\n\n"
            "Commands:\n"
            "• /last EUR/USD\n"
            "• /latency EUR/USD"
        )
        return {"ok": True}

    if text.lower().startswith("/last"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            tg_send(chat_id, "Usage: /last EUR/USD")
            return {"ok": True}
        sym = parts[1].upper()
        data, raw = td_last(sym)
        if not data:
            tg_send(chat_id, f"❌ Could not fetch {sym}.")
            return {"ok": True}
        tg_send(chat_id,
            f"📊 {data['symbol']} 1m\n"
            f"Time(UTC): {data['dt']}\n"
            f"O:{data['open']} H:{data['high']} L:{data['low']} C:{data['close']}"
        )
        return {"ok": True}

    if text.lower().startswith("/latency"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            tg_send(chat_id, "Usage: /latency EUR/USD")
            return {"ok": True}
        sym = parts[1].upper()
        data, raw = td_last(sym)
        if not data:
            tg_send(chat_id, f"❌ Could not fetch {sym}.")
            return {"ok": True}
        tg_send(chat_id, f"🕒 Last bar for {sym} (1m): {data['dt']} UTC")
        return {"ok": True}

    return {"ok": True}