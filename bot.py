import os, asyncio
import httpx

API = None
offset = 0

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
        await tg_post("sendMessage", chat_id=chat_id, text="📊 Stats coming soon")
    elif text == "/help":
        await tg_post("sendMessage", chat_id=chat_id,
                      text="Commands:\n/start\n/stats\n/help")
    else:
        await tg_post("sendMessage", chat_id=chat_id, text=f"You said: {text}")

async def wait_for_token():
    global API
    while True:
        tok = os.getenv("BOT_TOKEN")
        if tok and ":" in tok:
            API = f"https://api.telegram.org/bot{tok}"
            print("BOT_TOKEN detected, starting polling…")
            return
        print("BOT_TOKEN missing/invalid. Set it in Railway → Variables. Retrying in 10s…")
        await asyncio.sleep(10)

async def poll_loop():
    global offset
    while True:
        try:
            data = await tg_get("getUpdates", timeout=25, offset=offset, allowed_updates=["message"])
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                await handle_update(upd)
        except Exception as e:
            print("poll error:", e)
            await asyncio.sleep(3)

async def main():
    await wait_for_token()
    await poll_loop()

if __name__ == "__main__":
    asyncio.run(main())