# Ultra-robust minimal Telegram bot using pure HTTP long-polling
# It will NOT crash: it waits for BOT_TOKEN, validates it, and retries forever on errors.

import os, asyncio, time
import httpx

API = None
offset = 0

async def api_get(path, **params):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{API}/{path}", params=params)
        r.raise_for_status()
        return r.json()

async def api_post(path, **params):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{API}/{path}", data=params)
        r.raise_for_status()
        return r.json()

async def wait_for_valid_token():
    """Loop until a valid BOT_TOKEN is present and passes getMe."""
    global API
    while True:
        tok = (os.getenv("BOT_TOKEN") or "").strip()
        if not tok or ":" not in tok:
            print("⚠️ BOT_TOKEN missing/invalid. Add it in Railway → Variables. Retrying in 10s…")
            await asyncio.sleep(10)
            continue
        API = f"https://api.telegram.org/bot{tok}"
        try:
            data = await api_get("getMe")
            if data.get("ok"):
                me = data["result"]["username"]
                print(f"✅ BOT_TOKEN valid. Logged in as @{me}. Starting polling…")
                return
            else:
                print(f"❌ getMe not ok: {data}. Retrying in 10s…")
        except httpx.HTTPStatusError as e:
            # 401 Unauthorized = bad token
            if e.response is not None and e.response.status_code == 401:
                print("❌ BOT_TOKEN unauthorized (401). Check the token value in Railway → Variables. Retrying in 10s…")
            else:
                print(f"❌ HTTPStatusError on getMe: {e}. Retrying in 10s…")
        except Exception as e:
            print(f"❌ Error on getMe: {e}. Retrying in 10s…")
        await asyncio.sleep(10)

async def handle_update(upd):
    msg = upd.get("message")
    if not msg or "text" not in msg:
        return
    chat_id = msg["chat"]["id"]
    text = (msg["text"] or "").strip()

    if text == "/start":
        await api_post("sendMessage", chat_id=chat_id,
                       text="✅ Bot online (polling). Commands: /start, /stats, /help")
    elif text == "/stats":
        await api_post("sendMessage", chat_id=chat_id, text="📊 Stats feature coming soon")
    elif text == "/help":
        await api_post("sendMessage", chat_id=chat_id,
                       text="Commands:\n/start – check bot\n/stats – show counters\n/help – this help")
    else:
        await api_post("sendMessage", chat_id=chat_id, text=f"You said: {text}")

async def poll_loop():
    global offset
    print("⏳ Polling started…")
    while True:
        try:
            data = await api_get("getUpdates", timeout=25, offset=offset, allowed_updates=["message"])
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                await handle_update(upd)
        except httpx.HTTPError as e:
            print("🌐 HTTP error while polling:", repr(e))
            await asyncio.sleep(3)
        except Exception as e:
            print("⚠️ Poll loop error:", repr(e))
            await asyncio.sleep(3)

async def main():
    while True:
        try:
            await wait_for_valid_token()
            await poll_loop()
        except Exception as e:
            print("💥 Top-level error, restarting in 5s:", repr(e))
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())