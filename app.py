import os
from fastapi import FastAPI, Request, Header, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Load environment variables
BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

# Initialize FastAPI
app = FastAPI()

# Initialize Telegram application
tg_app = Application.builder().token(BOT_TOKEN).build()

# -------------------
# Telegram Handlers
# -------------------

async def start_cmd(update: Update, ctx):
    await update.message.reply_text("📈 Pocket Option Bot is online 24/7 ✅")

async def stats_cmd(update: Update, ctx):
    # Placeholder — later we’ll hook into worker.py
    await update.message.reply_text("📊 Stats coming soon...")

# Add handlers
tg_app.add_handler(CommandHandler("start", start_cmd))
tg_app.add_handler(CommandHandler("stats", stats_cmd))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start_cmd))

# -------------------
# FastAPI Routes
# -------------------

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None)
):
    # Verify webhook secret
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}

# -------------------
# Run (for local dev)
# -------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
