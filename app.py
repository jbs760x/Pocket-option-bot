import os, json, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
LOG_FILE = "trades.json"

# --- Load/save log ---
def load_log():
    try:
        with open(LOG_FILE,"r") as f: return json.load(f)
    except: return {"trades": [], "wins": 0, "losses": 0, "pnl": 0.0}

# --- Commands ---
async def start_cmd(update, ctx):
    await update.message.reply_text("🤖 Pocket Option Bot 24/7\nCommands:\n/stats")

async def stats_cmd(update, ctx):
    log = load_log()
    total = log["wins"] + log["losses"]
    winrate = (log["wins"]/total*100) if total>0 else 0
    reply = f"📊 Stats:\nTrades: {total}\nWins: {log['wins']}\nLosses: {log['losses']}\nWinrate: {winrate:.1f}%\nPnL: {log['pnl']:.2f}"
    await update.message.reply_text(reply)

# --- Telegram setup ---
tg = Application.builder().token(BOT_TOKEN).build()
tg.add_handler(CommandHandler("start", start_cmd))
tg.add_handler(CommandHandler("stats", stats_cmd))

@asynccontextmanager
async def lifespan(_: FastAPI):
    await tg.initialize()
    await tg.start()
    yield
    await tg.stop()
    await tg.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health(): return {"ok": True}

@app.post("/webhook")
async def webhook(request: Request, x_telegram_bot_api_secret_token: str|None=Header(default=None)):
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(403, "bad secret")
    update = Update.de_json(await request.json(), tg.bot)
    await tg.process_update(update)
    return {"ok": True}
