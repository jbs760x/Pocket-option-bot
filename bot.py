from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler

# Your real token hardcoded
TOKEN = "847181182:AAHmg0kbRTuhDUtp15Vj6rhp8f-bZcLzj8"
SECRET = "Desert760_123"  # Secret you chose

app = FastAPI()
tg_app = Application.builder().token(TOKEN).build()

# /start command
async def start(update: Update, context):
    await update.message.reply_text("✅ Bot is alive and working!")

tg_app.add_handler(CommandHandler("start", start))

@app.on_event("startup")
async def on_startup():
    await tg_app.initialize()

@app.on_event("shutdown")
async def on_shutdown():
    await tg_app.shutdown()

@app.post("/webhook")
async def webhook(req: Request):
    if req.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET:
        return {"ok": False}
    data = await req.json()
    await tg_app.update_queue.put(Update.de_json(data, tg_app.bot))
    return {"ok": True}

@app.get("/health")
def health():
    return {"ok": True}
