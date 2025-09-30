# Telegram long-polling + signals (Twelve Data) + real trading (Playwright) + stats
import os, json, time, asyncio, signal
from collections import defaultdict

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ========= ENV =========
BOT_TOKEN = os.environ["BOT_TOKEN"]                                  # Telegram token
PO_EMAIL = os.environ["PO_EMAIL"]                                    # Pocket Option login
PO_PASSWORD = os.environ["PO_PASSWORD"]
TD_KEY = os.environ["TWELVE_API_KEY"]                                # Twelve Data API key

BET_SIZE = float(os.environ.get("BET_SIZE", "2"))
TAKE_PROFIT = float(os.environ.get("TAKE_PROFIT", "100"))
STOP_LOSS = float(os.environ.get("STOP_LOSS", "-50"))
DEFAULT_EXPIRY = int(os.environ.get("DEFAULT_EXPIRY", "60"))
PAYOUT_NET = float(os.environ.get("PAYOUT", "0.80"))                 # 80% default

LOG_FILE = "trades.json"

# Watchlist (edit as you like)
WATCH = ["EURUSD", "USDJPY", "GBPUSD"]
SYMBOL_MAP = { "EURUSD":"EUR/USD", "USDJPY":"USD/JPY", "GBPUSD":"GBP/USD" }

# ========= STATE =========
class State:
    def __init__(self):
        self.running = True
        self.paused = False
        self.bet = BET_SIZE
        self.tp = TAKE_PROFIT
        self.sl = STOP_LOSS
        self.expiry = DEFAULT_EXPIRY
        self.pnl = 0.0
        self.wins = 0
        self.losses = 0
        self.per_symbol = defaultdict(lambda: {"trades":0,"wins":0,"losses":0})
        self.last_msg_chat = None  # remember last chat to push errors

state = State()

# ========= LOGGING =========
def load_log():
    try:
        with open(LOG_FILE,"r") as f: d = json.load(f)
        state.pnl = float(d.get("pnl",0))
        state.wins = int(d.get("wins",0))
        state.losses = int(d.get("losses",0))
        state.per_symbol.update(d.get("per_symbol",{}))
        return d
    except:
        return {"trades":[],"wins":0,"losses":0,"pnl":0.0,"per_symbol":{}}

def save_log(trades, d_extra=None):
    out = {
        "trades": trades,
        "wins": state.wins,
        "losses": state.losses,
        "pnl": state.pnl,
        "per_symbol": state.per_symbol
    }
    if d_extra: out.update(d_extra)
    with open(LOG_FILE,"w") as f: json.dump(out,f)

trades_log = load_log().get("trades",[])

# ========= TWELVE DATA =========
async def td_get(endpoint: str, params: dict):
    url = f"https://api.twelvedata.com/{endpoint}"
    params = {**params, "apikey": TD_KEY}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url, params=params)
        r.raise_for_status()
        return r.json()

async def get_rsi(sym: str, interval="1min", length=14):
    td_symbol = SYMBOL_MAP.get(sym, sym)
    data = await td_get("rsi", {"symbol": td_symbol, "interval": interval, "time_period": length})
    vals = data.get("values", [])
    return float(vals[0]["rsi"]) if vals else None

async def next_signal():
    # Example rule: RSI oversold/overbought → CALL/PUT
    for sym in WATCH:
        rsi = await get_rsi(sym)
        if rsi is None: continue
        if rsi <= 30:  # oversold
            return {"symbol": sym, "dir": "CALL", "expiry": state.expiry, "odds": 0.75, "why": f"RSI={rsi:.1f} oversold"}
        if rsi >= 70:  # overbought
            return {"symbol": sym, "dir": "PUT",  "expiry": state.expiry, "odds": 0.75, "why": f"RSI={rsi:.1f} overbought"}
    await asyncio.sleep(4)
    return None

# ========= POCKET OPTION (Playwright) =========
async def po_login(page):
    await page.goto("https://pocketoption.com/en/", wait_until="domcontentloaded")

    # --- IMPORTANT ---
    # These selectors can vary. If any fail, open the site with Playwright headed locally once to confirm.
    await page.fill("input[name=email]", PO_EMAIL)
    await page.fill("input[name=password]", PO_PASSWORD)
    await page.click("button:has-text('Sign in')")
    await page.wait_for_selector("text=Balance")  # some element that only shows when logged in

async def po_place_trade(page, sig):
    """
    This is a placeholder — you MUST confirm selectors.
    Steps usually are:
      - Select asset
      - Set amount
      - Set expiry
      - Click CALL/PUT
      - Wait until expiry & read result
    """
    sym, direction, amount = sig["symbol"], sig["dir"], state.bet
    print(f"Placing {direction} on {sym} for ${amount} / {sig['expiry']}s — {sig.get('why','')}")
    # TODO: select the asset
    # TODO: set amount field to 'amount'
    # TODO: set expiry to sig["expiry"]
    # TODO: if direction == "CALL": click call button; else click put button

    # Wait expiry then determine result. You must replace selector below with the one that shows win/loss.
    await asyncio.sleep(sig["expiry"] + 2)
    # TODO: read result from UI. For now, simulate alternating results so bot runs.
    # Replace this with real outcome detection.
    simulated = "win" if int(time.time()) % 2 == 0 else "loss"
    return {"result": simulated, "amount": amount}

# =========
