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
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# ---------- CONFIG ----------
TOKEN = os.getenv("BOT_TOKEN", "8471181182:AAEKGH1UASa5XvkXscb3jb5d1Yz19B8oJNM")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "Desert760_123")

# Either set it here (easiest) OR set Railway variable TWELVE_API_KEY
TWELVE_API_KEY = os.getenv("TWELVE_API_KEY", "PUT_TWELVE_KEY_HERE")

API_URL = "https://api.twelvedata.com/time_series"
DEFAULT_INTERVAL = "1min"        # 1min or 5min
POLL_SECONDS = 60                # how often to poll
DATA_POINTS = 60                 # candles fetched for indicators
STATE_FILE = "/app/state.json"   # keep subscriptions & watchlist between restarts
# -----------------------------

app = FastAPI()
tg = Application.builder().token(TOKEN).build()

# ----------- STATE -----------
# { chat_id: {"watch": [symbols...], "interval": "1min", "running": bool } }
STATE: Dict[str, Dict] = {}
LAST_SIGNAL: Dict[Tuple[str, str], str] = {}  # key=(chat_id,symbol) -> "BUY"/"SELL"/""
# -----------------------------

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(STATE, f)
    except Exception:
        pass

def load_state():
    global STATE
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                STATE = json.load(f)
    except Exception:
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
    """
    BUY if EMA5 > EMA20 and RSI > 52
    SELL if EMA5 < EMA20 and RSI < 48
    Only fires when the condition *changes* at the latest bar.
    """
    if len(closes) < 25:
        return None
    e5 = ema(closes, 5)
    e20 = ema(closes, 20)
    r = rsi(closes, 14)

    prev_buy = e5[-2] > e20[-