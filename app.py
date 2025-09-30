import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

async def start_cmd(update, ctx):
    await update.message.reply_text("Pocket Option bot is online 24/7 ✅")

async def text_handler(update, ctx):
    msg = (update.message.text or "").lower()
    if msg == "/stats":
        await update.message.reply_text("Stats coming soon…")
    else:
        await update.message.reply_text("Send /stats or /help.")

tg = Application.builder().token(BOT_TOKEN).build()
tg.add_handler(CommandHandler("start", start_cmd))
tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

@asynccontextmanager
async def lifespan(_: FastAPI):
    await tg.initialize()
    await tg.start()
    yield
    await tg.stop()
    await tg.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/webhook")
async def webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="bad secret")
    update = Update.de_json(await request.json(), tg.bot)
    await tg.process_update(update)
    return {"ok": True}
