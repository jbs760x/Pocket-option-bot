# Telegram bot on Railway using FastAPI webhook (no polling needed).
# Plug-and-play: requires two env vars in Railway:
# - BOT_TOKEN: your BotFather token (looks like 123456:ABC...).
# - WEBHOOK_SECRET: any string you choose (must match when setting the webhook).

import os
from fastapi import FastAPI, Request, Header, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")                      # <== must be set in Railway → Variables
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change")  # <== set this too

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in Railway Variables")

# Build Telegram app (do NOT run_polling here)
tg = Application.builder().token(BOT_TOKEN).build()

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is online on Railway (webhook mode).")

tg.add_handler(CommandHandler("start", cmd_start))

# FastAPI app
app = FastAPI()

@app.on_event("startup")
async def startup():
    await tg.initialize()
    print("🚀 FastAPI started; Telegram initialized.")

@app.on_event("shutdown")
async def shutdown():
    await tg.shutdown()
    print("👋 Shutdown complete.")

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    # Optional security: require Telegram’s secret header to match our WEBHOOK_SECRET
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Bad secret")
    data = await request.json()
    update = Update.de_json(data, tg.bot)
    await tg.process_update(update)
    return {"ok": True}
