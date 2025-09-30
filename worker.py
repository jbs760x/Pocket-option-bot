import asyncio, os
from playwright.async_api import async_playwright

PO_EMAIL = os.environ["PO_EMAIL"]
PO_PASSWORD = os.environ["PO_PASSWORD"]
BET_SIZE = float(os.environ.get("BET_SIZE","2"))
STOP_LOSS = float(os.environ.get("STOP_LOSS","-50"))
TAKE_PROFIT = float(os.environ.get("TAKE_PROFIT","100"))

async def login_po(page):
    await page.goto("https://pocketoption.com/en/")
    # TODO: add selectors for login (fill in your login fields here)
    return True

async def next_signal():
    await asyncio.sleep(2)
    return None

async def place_trade(page, sig):
    # TODO: add selectors to place trade
    return {"result":"win","amount":BET_SIZE}

async def runner():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await login_po(page)
        session_pnl = 0.0
        while True:
            sig = await next_signal()
            if not sig:
                await asyncio.sleep(3)
                continue
            trade = await place_trade(page, sig)
            if trade["result"] == "win":
                session_pnl += trade["amount"] * 0.8
            elif trade["result"] == "loss":
                session_pnl -= trade["amount"]
            if session_pnl <= STOP_LOSS or session_pnl >= TAKE_PROFIT:
                break
        await browser.close()

if __name__ == "__main__":
    asyncio.run(runner())
