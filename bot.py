import os
from fastapi import FastAPI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

app = FastAPI()

# Telegram bot setup
application = Application.builder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is online and running on Railway!")

application.add_handler(CommandHandler("start", start))

@app.on_event("startup")
async def startup_event():
    print("🚀 Starting bot...")
    application.run_polling()
