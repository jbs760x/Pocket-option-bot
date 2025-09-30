import asyncio, os, time, json, httpx
from playwright.async_api import async_playwright

# === ENV VARIABLES ===
PO_EMAIL = os.environ["PO_EMAIL"]
PO_PASSWORD = os.environ["PO_PASSWORD"]
TD_KEY = os.environ["TWELVE_API_KEY"]

BET_SIZE = float(os.environ.get("BET_SIZE","2"))
STOP_LOSS = float(os.environ.get("STOP_LOSS","-50"))
TAKE_PROFIT = float(os.environ.get("TAKE_PROFIT","100"))
LOG_FILE = "trades.json"

# === SYMBOL MAP for Twelve Data ===
SYMBOL_MAP = {
    "EURUSD": "EUR/USD",
    "USDJPY": "USD/JPY",
    "GBPUSD": "GBP/USD"
}

# === Logging ===
def load_log():
    try: return json.load(open(LOG_FILE))
    except: return {"trades": [], "wins":0,"losses":0,"pnl":0.0}
def save_log(d): json.dump(d, open(LOG_FILE,"w"))

# === Twelve Data helpers ===
async def td_get(endpoint, params):
    url = f"https://api.twelvedata.com/{endpoint}"
    params["apikey"] = TD_KEY
    async with httpx.AsyncClient() as c:
        r = await c.get(url, params=params); r.raise_for_status()
        return r.json()

async def get_rsi(sym, interval="1min", length=14):
    data = await td_get("rsi", {"symbol": SYMBOL_MAP[sym], "interval": interval, "time_period": length})
    vals = data.get("values", [])
    return float(vals[0]["rsi"]) if vals else None

# === Pocket Option actions ===
async def login_po(page):
    await page.goto("https://pocketoption.com/en/")
    await page.fill("input[name=email]", PO_EMAIL)       # TODO: confirm selector
    await page.fill("input[name=password]", PO_PASSWORD) # TODO: confirm selector
    await page.click("button:has-text('Sign in')")
    await page.wait_for_selector("text=Balance")
    print("Logged in ✅")

async def place_trade(page, sig):
    print(f"Placing {sig['dir']} on {sig['symbol']}")
    # TODO: select asset, set amount, click CALL/PUT, confirm
    # Simulate result (replace with real check of outcome on Pocket Option site)
    return {"result":"win","amount":BET_SIZE}

# === Signal generator ===
async def next_signal():
    for sym in SYMBOL_MAP:
        rsi = await get_rsi(sym)
        if rsi is None: continue
        if rsi <= 30: return {"symbol":sym,"dir":"CALL","expiry":60,"odds":0.75,"why":f"RSI {rsi:.1f}"}
        if rsi >= 70: return {"symbol":sym,"dir":"PUT","expiry":60,"odds":0.75,"why":f"RSI {rsi:.1f}"}
    await asyncio.sleep(5)
    return None

# === Runner loop ===
async def runner():
    log = load_log()
    session_pnl = log["pnl"]
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await login_po(page)

        while True:
            sig = await next_signal()
            if not sig: continue

            trade = await place_trade(page, sig)
            if trade["result"]=="win":
                log["wins"]+=1; session_pnl += trade["amount"]*0.8
            else:
                log["losses"]+=1; session_pnl -= trade["amount"]

            log["pnl"]=session_pnl
            log["trades"].append({"symbol":sig["symbol"],"dir":sig["dir"],"result":trade["result"],"time":time.time(),"pnl":session_pnl})
            save_log(log)

            total=log["wins"]+log["losses"]
            wr=(log["wins"]/total*100) if total>0 else 0
            print(f"Trades:{total} W:{log['wins']} L:{log['losses']} WR:{wr:.1f}% PnL:{session_pnl:.2f}")

            if session_pnl<=STOP_LOSS or session_pnl>=TAKE_PROFIT:
                print("Stop condition hit, ending.")
                break

        await browser.close()

if __name__=="__main__":
    asyncio.run(runner())
