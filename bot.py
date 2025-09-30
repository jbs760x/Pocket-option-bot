# Minimal Telegram bot using only httpx long-polling (no webhooks, no Docker)
import os, asyncio
import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN env var missing in Railway > Variables")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
offset = 0  # tells Telegram we've processed up to this update_id

async def tg_get(path, **params):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{API}/{path}", params=params)
        r.raise_for_status()
        return r.json()

async def tg_post(path, **params):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{API}/{path}", data=params)
        r.raise_for_status()
        return r.json()

async def handle_update(upd):
    msg = upd.get("message")
    if not msg or "text" not in msg:
        return
    chat_id = msg["chat"]["id"]
    text = (msg["text"] or "").strip()

    if text == "/start":
        await tg_post("sendMessage", chat_id=chat_id,
                      text="✅ Bot online (polling). Commands: /start, /stats, /help")
    elif text == "/stats":
        await tg_post("sendMessage", chat_id=chat_id,
                      text="📊 Stats coming soon")
    elif text == "/help":
        await tg_post("sendMessage", chat_id=chat_id,
                      text="Commands:\n/start – check bot\n/stats – show counters\n/help – this message")
    else:
        await tg_post("sendMessage", chat_id=chat_id,
                      text=f"You said: {text}")

async def main():
    global offset
    while True:
        try:
            data = await tg_get("getUpdates", timeout=25, offset=offset, allowed_updates=["message"])
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                await handle_update(upd)
        except Exception as e:
            print("poll error:", e)
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
