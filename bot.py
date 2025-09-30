import os
import requests
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters

TOKEN = os.getenv("BOT_TOKEN", "8471181182:AAEKGH1UASa5XvkXscb3jb5d1Yz19B8oJNM")
TWELVE_API_KEY = os.getenv("TWELVE_API_KEY", "9aa4ea677d00474aa0c3223d0c812425")

bot = Bot(token=TOKEN)
app = FastAPI()
dispatcher = Dispatcher(bot, None, workers=0)

# ---------- COMMANDS ----------
def start(update, context):
    update.message.reply_text(
        "🤖 Bot is live!\n\n"
        "Commands:\n"
        "/last EUR/USD → get last candle\n"
        "/latency EUR/USD → check data freshness\n"
    )

def last(update, context):
    if len(context.args) == 0:
        update.message.reply_text("⚠️ Usage: /last EUR/USD")
        return
    symbol = context.args[0].replace("/", "")
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1min&apikey={TWELVE_API_KEY}&outputsize=1"
    r = requests.get(url).json()
    if "values" in r:
        v = r["values"][0]
        update.message.reply_text(
            f"📊 {context.args[0]} (1min)\n"
            f"Time: {v['datetime']}\n"
            f"Open: {v['open']} High: {v['high']} Low: {v['low']} Close: {v['close']}"
        )
    else:
        update.message.reply_text("❌ Error fetching data.")

def latency(update, context):
    if len(context.args) == 0:
        update.message.reply_text("⚠️ Usage: /latency EUR/USD")
        return
    symbol = context.args[0].replace("/", "")
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1min&apikey={TWELVE_API_KEY}&outputsize=1"
    r = requests.get(url).json()
    if "values" in r:
        v = r["values"][0]
        update.message.reply_text(
            f"🕒 Last bar time: {v['datetime']} (server time UTC)"
        )
    else:
        update.message.reply_text("❌ Error fetching latency.")

# ---------- DISPATCH ----------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("last", last))
dispatcher.add_handler(CommandHandler("latency", latency))

# ---------- FASTAPI ----------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot)
    dispatcher.process_update(update)
    return {"ok": True}

@app.get("/health")
async def health():
    return {"ok": True}