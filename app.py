import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

app = FastAPI()
tg_app = None  # will be created in startup

# --- Telegram handlers ---
async def start_cmd(update: Update, ctx):
    await update.message.reply_text("📈 Pocket Option Bot is online 24/7 ✅")

async def stats_cmd(update: Update, ctx):
    await update.message.reply_text("📊 Stats coming soon…")

# --- Lifespan (startup/shutdown) ---
@asynccontextmanager
async def lifespan(_: FastAPI):
    global tg_app
    app.state.telegram_ready = False
    app.state.start_error = None
    try:
        if BOT_TOKEN:
            tg_app = Application.builder().token(BOT_TOKEN).build()
            tg_app.add_handler(CommandHandler("start", start_cmd))
            tg_app.add_handler(CommandHandler("stats", stats_cmd))
            tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start_cmd))
            await tg_app.initialize()
            await tg_app.start()
            app.state.telegram_ready = True
        else:
            app.state.start_error = "Missing BOT_TOKEN"
    except Exception as e:
        app.state.start_error = f"{type(e).__name__}: {e}"
    yield
    if tg_app:
        await tg_app.stop()
        await tg_app.shutdown()

app.router.lifespan_context = lifespan

# --- Routes ---
@app.get("/health")
async def health():
    return {
        "ok": True,
        "telegram_ready": bool(app.state.telegram_ready),
        "has_bot_token": bool(BOT_TOKEN),
        "start_error": app.state.start_error,
    }

@app.post("/webhook")
async def webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")
    if not tg_app:
        raise HTTPException(status_code=500, detail="Telegram not initialized")
    update = Update.de_json(await request.json(), tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}