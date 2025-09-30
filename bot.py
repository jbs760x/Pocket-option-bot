import os
import json
import asyncio
import aiohttp
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

from fastapi import FastAPI, Request, Header, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------- CONFIG ----------
TOKEN = os.getenv("BOT_TOKEN", "8471181182:AAEKGH1UASa5XvkXscb3jb5d1Yz19B8oJNM")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "Desert760_123")

# Twelve Data API key (your provided key)
TWELVE_API_KEY = os.getenv("TWELVE_API_KEY", "9aa4ea677d00474aa0c3223d0c812425")

API_URL = "https://api.twelvedata.com/time_series"
DEFAULT_INTERVAL = "1min"        # 1min or 5min
POLL_SECONDS = 60                # how often to poll
DATA_POINTS = 60                 # candles fetched for indicators
STATE_FILE = "/app/state.json"   # keep subscriptions & watchlist between restarts
# -----------------------------

app = FastAPI()
tg = Application.builder().token(TOKEN).build()

STATE: Dict[str, Dict] = {}
LAST_SIGNAL: Dict[Tuple[str, str], str] = {}

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(STATE, f)
    except:
        pass

def load_state():
    global STATE
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                STATE = json.load(f)
    except:
        STATE = {}

# ---------- INDICATORS ----------
def ema(series: np.ndarray, span: int) -> np.ndarray:
    return pd.Series(series).ewm(span=span, adjust=False).mean().to_numpy()

def rsi(series: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(series, prepend=series[0])
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = pd.Series(gains).rolling(period).mean()
    avg_loss = pd.Series(losses).rolling(period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))

def generate_signal(closes: np.ndarray) -> Optional[str]:
    if len(closes) < 25:
        return None
    e5 = ema(closes, 5)
    e20 = ema(closes, 20)
    r = rsi(closes, 14)

    prev_buy = e5[-2] > e20[-2]
    now_buy  = e5[-1] > e20[-1]
    prev_sell = e5[-2] < e20[-2]
    now_sell  = e5[-1] < e20[-1]

    if (not prev_buy and now_buy) and r[-1] > 52:
        return "BUY"
    if (not prev_sell and now_sell) and r[-1] < 48:
        return "SELL"
    return None

# ---------- DATA FETCH ----------
async def fetch_series(session: aiohttp.ClientSession, symbol: str, interval: str) -> Optional[np.ndarray]:
    params = {
        "symbol": symbol,
        "interval": interval,
        "apikey": TWELVE_API_KEY,
        "outputsize": DATA_POINTS,
        "format": "JSON",
        "order": "ASC",
    }
    async with session.get(API_URL, params=params, timeout=30) as resp:
        js = await resp.json(content_type=None)
        if "values" not in js:
            return None
        closes = [float(v["close"]) for v in js["values"]]
        return np.array(closes, dtype=float)

# ---------- POLLER ----------
async def poller():
    await tg.wait_until_ready()
    load_state()
    async with aiohttp.ClientSession() as session:
        while True:
            tasks = []
            for chat_id, cfg in STATE.items():
                if not cfg.get("running"):
                    continue
                interval = cfg.get("interval", DEFAULT_INTERVAL)
                for sym in cfg.get("watch", []):
                    tasks.append(handle_symbol(session, chat_id, sym, interval))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(POLL_SECONDS)

async def handle_symbol(session, chat_id: str, symbol: str, interval: str):
    closes = await fetch_series(session, symbol, interval)
    if closes is None or len(closes) < 25:
        return
    sig = generate_signal(closes)
    k = (chat_id, symbol)
    if sig and LAST_SIGNAL.get(k) != sig:
        LAST_SIGNAL[k] = sig
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        text = f"📊 *{symbol}*  `{interval}`\nSignal: *{sig}*\nTime: {now}"
        try:
            await tg.bot.send_message(chat_id=int(chat_id), text=text, parse_mode="Markdown")
        except:
            pass

# ---------- COMMANDS ----------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in STATE:
        STATE[chat_id] = {"watch": [], "interval": DEFAULT_INTERVAL, "running": False}
        save_state()
    msg = (
        "🤖 Trading Bot ready.\n\n"
        "*Commands:*\n"
        "• `/watch add BTC/USD`\n"
        "• `/watch list`\n"
        "• `/interval 1min`\n"
        "• `/go` start signals\n"
        "• `/stop` pause"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    STATE.setdefault(chat_id, {"watch": [], "interval": DEFAULT_INTERVAL, "running": False})
    sub = ctx.args
    if not sub:
        await update.message.reply_text("Usage: /watch add <SYMBOL> | /watch list | /watch remove <SYMBOL>")
        return
    action = sub[0].lower()
    if action == "list":
        lst = STATE[chat_id]["watch"]
        await update.message.reply_text("👀 Watchlist: " + (", ".join(lst) if lst else "(empty)"))
        return
    if len(sub) < 2:
        await update.message.reply_text("Symbol missing")
        return
    symbol = sub[1].upper()
    if action == "add":
        if symbol not in STATE[chat_id]["watch"]:
            STATE[chat_id]["watch"].append(symbol)
            save_state()
        await update.message.reply_text(f"Added {symbol}")
    elif action == "remove":
        if symbol in STATE[chat_id]["watch"]:
            STATE[chat_id]["watch"].remove(symbol)
            save_state()
        await update.message.reply_text(f"Removed {symbol}")

async def cmd_interval(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not ctx.args:
        await update.message.reply_text("Current interval: " + STATE.get(chat_id, {}).get("interval", DEFAULT_INTERVAL))
        return
    val = ctx.args[0].lower()
    if val not in ("1min", "5min"):
        await update.message.reply_text("Allowed: 1min or 5min")
        return
    STATE.setdefault(chat_id, {"watch": [], "interval": DEFAULT_INTERVAL, "running": False})
    STATE[chat_id]["interval"] = val
    save_state()
    await update.message.reply_text(f"Interval set to {val}")

async def cmd_go(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    STATE.setdefault(chat_id, {"watch": [], "interval": DEFAULT_INTERVAL, "running": False})
    STATE[chat_id]["running"] = True
    save_state()
    await update.message.reply_text("▶️ Signals started.")

async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    STATE.setdefault(chat_id, {"watch": [], "interval": DEFAULT_INTERVAL, "running": False})
    STATE[chat_id]["running"] = False
    save_state()
    await update.message.reply_text("⏸️ Signals paused.")

tg.add_handler(CommandHandler("start", cmd_start))
tg.add_handler(CommandHandler("watch", cmd_watch))
tg.add_handler(CommandHandler("interval", cmd_interval))
tg.add_handler(CommandHandler("go", cmd_go))
tg.add_handler(CommandHandler("stop", cmd_stop))

@app.on_event("startup")
async def on_startup():
    load_state()
    await tg.initialize()
    asyncio.create_task(poller())

@app.on_event("shutdown")
async def on_shutdown():
    await tg.shutdown()

@app.post("/webhook")
async def webhook(req: Request, x_telegram_bot_api_secret_token: str = Header(None)):
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="bad secret")
    data = await req.json()
    update = Update.de_json(data, tg.bot)
    await tg.process_update(update)
    return {"ok": True}

@app.get("/")
def home():
    return {"status": "ok"}
    async def fetch_latest_bar(session: aiohttp.ClientSession, symbol: str, interval: str):
    params = {
        "symbol": symbol,
        "interval": interval,
        "apikey": TWELVE_API_KEY,
        "outputsize": 1,
        "format": "JSON",
        "order": "ASC",
    }
    async with session.get(API_URL, params=params, timeout=30) as resp:
        js = await resp.json(content_type=None)
        if "values" not in js or not js["values"]:
            return None
        v = js["values"][-1]
        # v["datetime"] example: "2025-09-30 17:24:00"
        return {
            "datetime": v.get("datetime"),
            "open": float(v["open"]),
            "high": float(v["high"]),
            "low": float(v["low"]),
            "close": float(v["close"]),
            "symbol": symbol,
            "interval": interval,
        