import os, time, threading, requests, signal
from datetime import datetime, timedelta, timezone, date
from telegram import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# ===== ENV (set these in Render → Environment) =====
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TWELVE_API_KEY     = os.environ.get("TWELVE_API_KEY", "")
PUBLIC_URL         = os.environ.get("PUBLIC_URL", "")
PORT               = int(os.environ.get("PORT", "10000"))

if not TELEGRAM_BOT_TOKEN or not TWELVE_API_KEY or not PUBLIC_URL:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN, TWELVE_API_KEY, PUBLIC_URL in Render env.")

# ===== State tuned for OTC & API-thrift =====
STATE = {
    "watchlist": ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDUSD-OTC", "USDCHF-OTC"],  # exactly 5 by default
    "autopoll_running": False, "autopoll_thread": None,
    "tf": "5min", "duration_min": 60,
    "amount": 5.0,

    # Accuracy first (strict)
    "threshold": 0.78,          # need >= 78% confidence
    "require_votes": 4,         # 4/4 confluence for OTC
    "atr_floor": 0.0005,        # skip dead/chop

    # Cadence & API thrift
    "candle_close_only": True,  # only at M5 close
    "cooldown_min": 5,          # per-pair cooldown
    "min_signal_gap_min": 7,    # global min gap
    "max_calls_per_hour": 60,   # 5 pairs × 12 scans/hr
    "daily_call_cap": 800,

    # Guardrails & stats
    "loss_streak_stop": 3,
    "stats": {"wins":0,"losses":0,"skips":0,"consec_losses":0,"consec_wins":0,"last_reset_date":None},

    # internals
    "last_signal_time": None,
    "pair_last_signal_time": {},
    "last_chat_id": None,
    "last_signal_message_ids": {},
}

CALL_METER = {"hour_bucket": None, "hour_calls": 0, "day_bucket": None, "day_calls": 0}
STOP_EVENT = threading.Event()

# ---------- helpers ----------
def now_utc(): return datetime.now(timezone.utc)

def reset_counters_if_needed():
    hb = now_utc().replace(minute=0, second=0, microsecond=0)
    if CALL_METER["hour_bucket"] != hb:
        CALL_METER["hour_bucket"] = hb; CALL_METER["hour_calls"] = 0
    db = now_utc().date()
    if CALL_METER["day_bucket"] != db:
        CALL_METER["day_bucket"] = db; CALL_METER["day_calls"] = 0

def budget_ok():
    reset_counters_if_needed()
    return CALL_METER["hour_calls"] < STATE["max_calls_per_hour"] and CALL_METER["day_calls"] < STATE["daily_call_cap"]

def count_call():
    CALL_METER["hour_calls"] += 1; CALL_METER["day_calls"] += 1

def wait_until_next_m5_close():
    now = now_utc()
    secs = (5 - (now.minute % 5)) * 60 - now.second
    if secs <= 0: secs += 300
    time.sleep(secs + 2)  # +2s to ensure close

# ---------- data fetch ----------
def fetch_ohlcv_twelve(pair, interval="5min", limit=120):
    url = "https://api.twelvedata.com/time_series"
    params = {"symbol": pair, "interval": interval, "outputsize": limit, "apikey": TWELVE_API_KEY, "order":"ASC", "timezone":"UTC"}
    try:
        if not budget_ok(): return None
        r = requests.get(url, params=params, timeout=12)
        count_call()
        r.raise_for_status()
        j = r.json()
        if "values" not in j: return None
        out = []
        for v in j["values"]:
            out.append({
                "time": datetime.fromisoformat(v["datetime"]).replace(tzinfo=timezone.utc),
                "open": float(v["open"]), "high": float(v["high"]),
                "low": float(v["low"]), "close": float(v["close"])
            })
        out.sort(key=lambda b: b["time"])
        return out[-limit:]
    except Exception:
        return None

def fetch_ohlcv(pair, interval="5min", limit=120):
    return fetch_ohlcv_twelve(pair, interval, limit)  # OTC primary; no fallback to avoid waste

# ---------- indicators ----------
def ema(values, period):
    if len(values) < period: return []
    k = 2/(period+1); out = [None]*(period-1); sma = sum(values[:period])/period; out.append(sma)
    for i in range(period, len(values)): out.append(out[-1] + k*(values[i]-out[-1]))
    return out

def rsi(values, period=14):
    if len(values) < period+1: return []
    gains, losses = [], []
    for i in range(1, len(values)):
        ch = values[i]-values[i-1]; gains.append(max(ch,0)); losses.append(max(-ch,0))
    avg_gain = sum(gains[:period])/period; avg_loss = sum(losses[:period])/period
    rsis = [None]*period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain*(period-1)+gains[i])/period
        avg_loss = (avg_loss*(period-1)+losses[i])/period
        rs = (avg_gain/avg_loss) if avg_loss!=0 else 999
        rsis.append(100 - 100/(1+rs))
    return rsis

def macd(values, fast=12, slow=26, signal=9):
    ef, es = ema(values, fast), ema(values, slow)
    line = [None if (i>=len(ef) or i>=len(es) or ef[i] is None or es[i] is None) else ef[i]-es[i] for i in range(len(values))]
    valid = [v for v in line if v is not None]
    if len(valid) < signal: return line, []
    sig = ema(valid, signal); sig = [None]*(len(line)-len(sig)) + sig
    return line, sig

def atr(highs, lows, closes, period=14):
    if len(closes) < period+1: return []
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    out = [None]*(period-1); out.append(sum(trs[:period])/period)
    for i in range(period, len(trs)): out.append((out[-1]*(period-1)+trs[i])/period)
    return out

def aggregate_m15_from_m5(bars):
    if not bars: return []
    out = []; agg = None; curr = None
    for b in bars:
        bs = b["time"].replace(minute=(b["time"].minute//15)*15, second=0, microsecond=0)
        if curr is None or bs != curr:
            if agg: out.append(agg)
            curr = bs; agg = {"time": bs, "open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"]}
        else:
            agg["high"] = max(agg["high"], b["high"]); agg["low"] = min(agg["low"], b["low"]); agg["close"] = b["close"]
    if agg: out.append(agg)
    return out[-120:]

# ---------- evaluator (OTC strict) ----------
def evaluate_pair_otc(pair, bars):
    closes = [b["close"] for b in bars]
    highs  = [b["high"]  for b in bars]
    lows   = [b["low"]   for b in bars]
    if len(closes) < 220: return (False, None, 0.0, "Not enough history")

    ema200_m5 = ema(closes, 200); ema50_m5 = ema(closes, 50); ema20_m5 = ema(closes, 20)
    rsi14 = rsi(closes, 14); macd_line, macd_sig = macd(closes); atr14 = atr(highs, lows, closes, 14)
    if not atr14 or atr14[-1] is None or atr14[-1] < STATE["atr_floor"]: return (False, None, 0.0, f"ATR too low")

    m15 = aggregate_m15_from_m5(bars); m15_closes = [b["close"] for b in m15]; ema200_m15 = ema(m15_closes, 200)
    if not ema200_m15 or ema200_m15[-1] is None: return (False, None, 0.0, "No M15 trend")

    if STATE["candle_close_only"]:
        last_bar = bars[-1]["time"]
        if (now_utc() - last_bar).total_seconds() < 5: return (False, None, 0.0, "Waiting M5 close")

    bias_up = closes[-1] > ema200_m15[-1]; bias_dn = closes[-1] < ema200_m15[-1]
    up, dn = 0, 0
    if bias_up: up += 1
    if bias_dn: dn += 1
    if rsi14[-2] is not None and rsi14[-1] is not None:
        if rsi14[-2] <= 50 < rsi14[-1]: up += 1
        if rsi14[-2] >= 50 > rsi14[-1]: dn += 1
    if macd_line[-1] is not None and macd_sig[-1] is not None:
        if macd_line[-1] > macd_sig[-1]: up += 1
        if macd_line[-1] < macd_sig[-1]: dn += 1
    if ema20_m5[-1] and ema50_m5[-1]:
        if bias_up and closes[-1] > ema20_m5[-1] and closes[-1] > ema50_m5[-1]: up += 1
        if bias_dn and closes[-1] < ema20_m5[-1] and closes[-1] < ema50_m5[-1]: dn += 1

    need = STATE["require_votes"]; side = None; votes = 0
    if up >= need and up > dn:   side, votes = "BUY",  up
    elif dn >= need and dn > up: side, votes = "SELL", dn
    else: return (False, None, 0.0, f"No side: up={up} dn={dn}")

    conf = max(0.0, min(0.95, 0.65 + 0.05*(votes-3)))  # 3->0.70, 4->0.75
    return (True, side, conf, f"votes up={up} dn={dn} ATR={atr14[-1]:.5f}")

# ---------- stats / guardrails / UI ----------
def _maybe_reset_daily():
    today = date.today()
    if STATE["stats"]["last_reset_date"] != today:
        STATE["stats"].update({"wins":0,"losses":0,"skips":0,"consec_losses":0,"consec_wins":0,"last_reset_date":today})

def _stats_text():
    _maybe_reset_daily()
    s = STATE["stats"]; total = s["wins"] + s["losses"]; wr = (s["wins"]/total*100) if total>0 else 0.0
    return (f"📊 Stats (today)\nWins: {s['wins']} | Losses: {s['losses']} | Skips: {s['skips']}\n"
            f"Win rate: {wr:.1f}%\nStreaks → Wins: {s['consec_wins']} | Losses: {s['consec_losses']}\n"
            f"Auto-stop after {STATE['loss_streak_stop']} consecutive losses")

def _record_result(result: str, chat_id=None):
    _maybe_reset_daily(); s = STATE["stats"]
    if result == "win":
        s["wins"] += 1; s["consec_wins"] += 1; s["consec_losses"] = 0
    elif result == "loss":
        s["losses"] += 1; s["consec_losses"] += 1; s["consec_wins"] = 0
        if s["consec_losses"] >= STATE["loss_streak_stop"]:
            _stop_autopoll(chat_id, reason=f"⛔ Auto-paused: {s['consec_losses']} consecutive losses")
    else:
        s["skips"] += 1

def _signal_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Win", callback_data="sig_win"),
                                  InlineKeyboardButton("❌ Loss", callback_data="sig_loss"),
                                  InlineKeyboardButton("⏭️ Skip", callback_data="sig_skip")]])

def _send_signal(chat_id, text, pair):
    msg = updater.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN, reply_markup=_signal_keyboard())
    STATE["last_signal_message_ids"][pair] = msg.message_id
    STATE["last_signal_time"] = now_utc(); STATE["last_chat_id"] = chat_id

def on_signal_button(update, ctx: CallbackContext):
    q = update.callback_query
    if not q: return
    chat_id = q.message.chat_id
    if q.data == "sig_win":
        _record_result("win", chat_id); q.answer("Win recorded"); q.edit_message_reply_markup(reply_markup=None); q.message.reply_text("✅ Win noted.\n"+_stats_text())
    elif q.data == "sig_loss":
        _record_result("loss", chat_id); q.answer("Loss recorded"); q.edit_message_reply_markup(reply_markup=None); q.message.reply_text("❌ Loss noted.\n"+_stats_text())
    elif q.data == "sig_skip":
        _record_result("skip", chat_id); q.answer("Skipped"); q.edit_message_reply_markup(reply_markup=None); q.message.reply_text("⏭️ Skipped.\n"+_stats_text())

def _stop_autopoll(chat_id=None, reason=""):
    STATE["autopoll_running"] = False
    try: STOP_EVENT.set()
    except: pass
    if chat_id:
        try: updater.bot.send_message(chat_id, f"{reason}\nUse /autopoll to start again.")
        except: pass

# ---------- commands ----------
def cmd_start(update, ctx):
    update.message.reply_text(
        "Bot ready ✅ (Render webhook)\n\n"
        "/watchlist <5 OTC pairs>\n/otc  (strict mode)\n"
        "/autopoll <amount> <threshold%> <tf> <minutes>\n"
        "ex: /autopoll 5 78 5min 60\n"
        "/settings  /stats  /guardrail <N>  /stop"
    )

def cmd_help(update, ctx): cmd_start(update, ctx)

def cmd_watchlist(update, ctx):
    args = " ".join(ctx.args).strip()
    if args:
        pairs = [p.strip().upper().replace("/", "") for p in args.split(",") if p.strip()]
        if len(pairs) != 5: return update.message.reply_text("❌ Please provide exactly 5 OTC pairs (comma-separated).")
        if not all("-OTC" in p for p in pairs): return update.message.reply_text("❌ OTC focus: include -OTC in all 5 symbols.")
        STATE["watchlist"] = pairs
        update.message.reply_text(f"✅ Watchlist set (5): {', '.join(pairs)}")
    else:
        update.message.reply_text(f"📌 Current watchlist (5): {', '.join(STATE['watchlist'])}")

def cmd_settings(update, ctx):
    s=STATE
    update.message.reply_text(
        "Settings:\n"
        f"- timeframe: {s['tf']} (signals at M5 close)\n"
        f"- threshold: {int(s['threshold']*100)}%\n"
        f"- confluence votes: {s['require_votes']}\n"
        f"- ATR floor: {s['atr_floor']}\n"
        f"- cooldown/pair: {s['cooldown_min']}m | min gap: {s['min_signal_gap_min']}m\n"
        f"- API budget: {s['max_calls_per_hour']}/hr, {s['daily_call_cap']}/day\n"
        f"- loss-streak stop: {s['loss_streak_stop']}"
    )

def cmd_guardrail(update, ctx):
    try:
        n = int(ctx.args[0]); n = max(1, min(10, n)); STATE["loss_streak_stop"] = n
        update.message.reply_text(f"🛡️ Auto-stop after {n} consecutive losses.")
    except:
        update.message.reply_text(f"Usage: /guardrail <1-10> (current {STATE['loss_streak_stop']})")

def cmd_stats(update, ctx): update.message.reply_text(_stats_text())

def cmd_otc(update, ctx):
    STATE["threshold"] = 0.78; STATE["require_votes"] = 4; STATE["atr_floor"] = 0.0005
    STATE["cooldown_min"] = 5; STATE["min_signal_gap_min"] = 7
    update.message.reply_text("⚙️ OTC mode: threshold 78%, votes 4/4, ATR 0.0005, cooldown 5m, global gap 7m.")

def cmd_autopoll(update, ctx):
    if STATE["autopoll_running"]: return update.message.reply_text("ℹ️ Autopoll already running.")
    try:
        amount = float(ctx.args[0]) if len(ctx.args)>0 else STATE["amount"]
        thr    = float(ctx.args[1])/100.0 if len(ctx.args)>1 else STATE["threshold"]
        tf     = ctx.args[2] if len(ctx.args)>2 else STATE["tf"]
        mins   = int(ctx.args[3]) if len(ctx.args)>3 else STATE["duration_min"]
    except Exception:
        return update.message.reply_text("Usage: /autopoll <amount> <threshold%> <tf> <minutes>\nex: /autopoll 5 78 5min 60")

    STATE["amount"]=amount; STATE["threshold"]=max(0.60,min(0.90,thr)); STATE["tf"]=tf; STATE["duration_min"]=max(10,min(240,mins))
    STOP_EVENT.clear(); STATE["autopoll_running"]=True; STATE["last_signal_time"]=None; STATE["pair_last_signal_time"]={}; STATE["last_chat_id"]=update.effective_chat.id

    t = threading.Thread(target=autopoll_loop, args=(STATE["last_chat_id"],), daemon=True)
    STATE["autopoll_thread"]=t; t.start()
    update.message.reply_text(f"▶️ Autopoll started: ${amount}, threshold {int(STATE['threshold']*100)}%, tf {tf}, duration {STATE['duration_min']}m\nWatchlist: {', '.join(STATE['watchlist'])}")

def cmd_stop(update, ctx): _stop_autopoll(update.effective_chat.id, "⏹️ Stopped.")

# ---------- core loop ----------
def autopoll_loop(chat_id):
    try:
        end = now_utc() + timedelta(minutes=STATE["duration_min"])
        wait_until_next_m5_close()
        while now_utc() < end and not STOP_EVENT.is_set():
            any_signal = False
            for pair in STATE["watchlist"]:
                if STOP_EVENT.is_set(): break
                if not budget_ok(): 
                    updater.bot.send_message(chat_id, "⏳ API budget reached, pausing until next hour/day window.")
                    break
                bars = fetch_ohlcv(pair, "5min", 120)
                if not bars or len(bars)<60: continue

                should, side, conf, why = evaluate_pair_otc(pair, bars)

                # per-pair cooldown
                nowt = now_utc()
                lp = STATE["pair_last_signal_time"].get(pair)
                if lp and (nowt - lp).total_seconds() < STATE["cooldown_min"]*60: should=False
                # global min gap
                if should and STATE["last_signal_time"]:
                    if (nowt - STATE["last_signal_time"]).total_seconds() < STATE["min_signal_gap_min"]*60: should=False

                if should and conf >= STATE["threshold"]:
                    msg = (f"📈 *OTC Signal* — {pair}\n"
                           f"Action: *{side}*\n"
                           f"Confidence: *{int(conf*100)}%*\n"
                           f"TF: {STATE['tf']} (entry on M5 close)\n"
                           f"Amount: ${STATE['amount']}\n"
                           f"Why: `{why}`")
                    _send_signal(chat_id, msg, pair)
                    STATE["pair_last_signal_time"][pair] = nowt
                    any_signal = True

            wait_until_next_m5_close()
    except Exception as e:
        try: updater.bot.send_message(chat_id, f"❌ Autopoll crashed: {e}")
        except: pass
    finally:
        STATE["autopoll_running"] = False

# ---------- Telegram boot (webhook) ----------
updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start",     cmd_start))
dp.add_handler(CommandHandler("help",      cmd_help))
dp.add_handler(CommandHandler("watchlist", cmd_watchlist))
dp.add_handler(CommandHandler("settings",  cmd_settings))
dp.add_handler(CommandHandler("guardrail", cmd_guardrail))
dp.add_handler(CommandHandler("stats",     cmd_stats))
dp.add_handler(CommandHandler("otc",       cmd_otc))
dp.add_handler(CommandHandler("autopoll",  cmd_autopoll))
dp.add_handler(CommandHandler("stop",      cmd_stop))
dp.add_handler(CallbackQueryHandler(on_signal_button))

def on_shutdown(signum, frame):
    try: _stop_autopoll(STATE.get("last_chat_id"), "🛑 Shutting down.")
    except: pass
    try: updater.stop()
    except: pass

signal.signal(signal.SIGINT, on_shutdown)
signal.signal(signal.SIGTERM, on_shutdown)

if __name__ == "__main__":
    path = TELEGRAM_BOT_TOKEN
    updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=path)
    webhook_url = f"{PUBLIC_URL}/{path}"
    updater.bot.set_webhook(webhook_url)
    print(f"[boot] Webhook set: {webhook_url}")
    updater.idle()