# bot.py — Telegram Pocket Option bot with stats & Twelve Data
import os, asyncio, time
from collections import defaultdict
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ========= ENVIRONMENT VARIABLES =========
BOT_TOKEN = os.environ["BOT_TOKEN"]                     # Telegram bot token
PO_EMAIL = os.environ.get("PO_EMAIL")                   # Pocket Option email
PO_PASS = os.environ.get("PO_PASS")                     # Pocket Option password
TWELVE_API_KEY = os.environ.get("TWELVE_API_KEY")       # Twelve Data API key

# ========= TRACKING =========
stats = defaultdict(lambda: {"wins": 0, "losses": 0, "entries": 0})

# ========= TELEGRAM COMMANDS =========
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Pocket Option Bot is online 24/7.\nUse /stats to check performance.")

async def show_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = stats["main"]
    msg = (
        f"📊 Stats:\n"
        f"Entries: {s['entries']}\n"
        f"Wins: {s['wins']}\n"
        f"Losses: {s['losses']}\n"
    )
    await update.message.reply_text(msg)

# ========= TWELVE DATA =========
async def get_signal(symbol="EUR/USD"):
    url = f"https://api.twelvedata.com/quote?symbol={symbol}&apikey={TWELVE_API_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        data = r.json()
        return data if "close" in data else {"error": "No data"}

# ========= TRADE EXECUTION (Pocket Option via Playwright) =========
async def place_trade(symbol="EUR/USD", direction="call", amount=1):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://pocketoption.com/en/login/")
        await page.fill("input[type='email']", PO_EMAIL)
        await page.fill("input[type='password']", PO_PASS)
        await page.click("button[type='submit']")
        await page.wait_for_timeout(5000)  # wait for login

        # here you would automate choosing the asset and placing a trade
        # this is placeholder
        print(f"Placing {direction.upper()} trade on {symbol} with {amount}$")

        await browser.close()
        return True

# ========= MESSAGE HANDLER =========
async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (update.message.text or "").lower()

    if msg.startswith("/signal"):
        data = await get_signal()
        await update.message.reply_text(f"📈 Signal Data: {data}")
    elif msg.startswith("/trade"):
        stats["main"]["entries"] += 1
        await place_trade()
        await update.message.reply_text("🟢 Trade placed!")
    else:
        await update.message.reply_text("Commands:\n/start\n/stats\n/signal\n/trade")

# ========= MAIN =========
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()