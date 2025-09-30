# app.py  — crash-proof + health details

import os, json, time
from fastapi import FastAPI, Request, Header, HTTPException
from contextlib import asynccontextmanager
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")                 # <-- won't crash if missing
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

app = FastAPI()
tg_app = None  # will be created during lifespan

# ------------- Telegram handlers -------------
async def start_cmd(update, ctx):
    await update.message.reply_text("📈 Pocket Option Bot is online 24/7 ✅")

async def stats_cmd(update, ctx):
    # Minimal stats placeholder; wire to your log later
    await update.message.reply_text("📊 Stats coming soon…")

# ------------- Lifespan: init/teardown -------------
@asynccontextmanager
async def lifespan(_: FastAPI):
    global tg_app
    app.state.telegram_ready = False
    if BOT_TOKEN:
        tg_app = Application.builder().token(BOT_TOKEN).build()
        tg_app.add_handler(CommandHandler("start", start_cmd))
        tg_app.add_handler(CommandHandler("stats", stats_cmd))
        tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start_cmd))
        # PTB v21 needs explicit init/start
        await tg_app.initialize()
        await tg_app.start()
        app.state.telegram_ready = True
    yield
    if tg_app:
        await tg_app.stop()
        await tg_app.shutdown()

app.router.lifespan_context = lifespan

# ------------- Routes -------------
@app.get("/health")
async def health():
    return {
        "ok": True,
        "telegram_ready": bool(app.state.telegram_ready),
        "has_bot_token": bool(BOT_TOKEN),
    }

@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None)
):
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")
    if not tg_app:
        # This happens if BOT_TOKEN wasn't set when the app booted
        raise HTTPException(status_code=500, detail="Telegram not initialized (missing BOT_TOKEN)")
    update = Update.de_json(await request.json(), tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}

# For local debug (Railway uses CMD in Dockerfile)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))