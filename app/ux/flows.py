"""Button and free-text flows: the address-free way to use the radar.

Type a coin name, tap the one you meant, get a plain-English scorecard, and add it to the
watchlist or the journal with one tap. Nothing here trades, signs or stores a key."""
import json
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..agents.token_scout import TokenScoutAgent
from ..crypto import dexscreener as dx, fng, regime, resolve
from ..crypto.chains import CHAINS, has_security
from ..crypto.http import client
from ..journal import add_dex_holding, watchlist
from ..redis_client import r
from ..text import esc, money, price
from . import cards, glossary, menu, portfolio, tokens

log = logging.getLogger(__name__)
STATE = "ux:state:{}"
STATE_TTL = 900
MAX_USD = 10_000_000


# ---------------- tiny conversation state (Redis, expires by itself) ----------------
def set_state(chat_id, **data) -> None:
    r.set(STATE.format(chat_id), json.dumps(data), ex=STATE_TTL)


def get_state(chat_id) -> dict:
    raw = r.get(STATE.format(chat_id))
    return json.loads(raw) if raw else {}


def clear_state(chat_id) -> None:
    r.delete(STATE.format(chat_id))


# ---------------- replying ----------------
async def say(update, text: str, markup=None):
    await update.effective_message.reply_html(text[:4000], reply_markup=markup,
                                              disable_web_page_preview=True)


def keyboard(rows) -> InlineKeyboardMarkup | None:
    rows = [[b for b in row if b] for row in rows]
    rows = [row for row in rows if row]
    return InlineKeyboardMarkup(rows) if rows else None


def url_button(text, url):
    return InlineKeyboardButton(text, url=url) if str(url or "").startswith("http") else None


def security_url(chain: str, address: str) -> str:
    """Empty string when no free report covers the chain - the button is then dropped."""
    cfg = CHAINS.get(chain) or {}
    if cfg.get("security") == "rugcheck":
        return f"https://rugcheck.xyz/tokens/{address}"
    if cfg.get("security") == "goplus":
        return f"https://gopluslabs.io/token-security/{cfg['goplus']}/{address}"
    return ""


def coin_keyboard(key: str, pair_url: str = "") -> InlineKeyboardMarkup:
    chain, _, address = key.partition(":")
    return keyboard([
        [url_button("📊 Chart", pair_url), url_button("🛡 Safety report", security_url(chain, address))],
        [InlineKeyboardButton("⭐ Watch", callback_data=tokens.cb("wl", key)),
         InlineKeyboardButton("📒 Journal", callback_data=tokens.cb("jw", key)),
         InlineKeyboardButton("🚫 Ignore", callback_data=tokens.cb("wx", key))],
        [InlineKeyboardButton("❓ What do these words mean?", callback_data="m:help")],
    ])


# ---------------- menu entries ----------------
async def cmd_menu(update, ctx):
    await say(update, menu.menu_text(), menu.main_menu())


async def cmd_mood(update, ctx):
    reg = await regime.current()
    async with client() as c:
        mood = await fng.current(c)
    await say(update, cards.mood_card(reg, mood),
              keyboard([[InlineKeyboardButton("❓ What does this mean?", callback_data="g:regime"),
                         InlineKeyboardButton("🔄 Refresh", callback_data="m:mood")]]))


async def cmd_find(update, ctx):
    query = " ".join(getattr(ctx, "args", []) or []).strip()
    if query:
        return await search(update, query)
    set_state(update.effective_chat.id, mode="find")
    await say(update, "Type a coin name (like <b>bonk</b>), or paste any link or address.\n"
                      "<i>I will find it for you — you never need to copy an address.</i>")


async def cmd_journal(update, ctx):
    rows = await portfolio.rows()
    await say(update, cards.portfolio_card(rows),
              keyboard([[InlineKeyboardButton("➕ Add a coin", callback_data="m:find"),
                         InlineKeyboardButton("⬇️ Export CSV", callback_data="m:csv")]]
                       + [[InlineKeyboardButton(f"🗑 Remove #{row['n']} {row['symbol']}"[:60],
                                                callback_data=f"slq:{row['id']}")] for row in rows[:8]]))


async def cmd_watchlist(update, ctx):
    coins = watchlist()
    if not coins:
        return await say(update, "⭐ Your watchlist is empty.\nCheck a coin and tap <b>⭐ Watch</b> to follow it.",
                         keyboard([[InlineKeyboardButton("🔎 Check a Coin", callback_data="m:find")]]))
    shown = coins[:10]
    try:
        async with client() as c:
            quotes = await portfolio.dex_quotes(c, [coin.key for coin in shown])
    except Exception:                       # a quote outage must not hide the watchlist
        log.warning("watchlist quotes unavailable", exc_info=True)
        quotes = {}
    lines = ["<b>⭐ Watchlist</b>", "The scout re-checks these on every run."]
    rows = []
    for coin in shown:
        quote = quotes.get(coin.key) or {}
        live = ""
        if quote.get("price"):
            live += f" · {price(quote['price'])}"
        if quote.get("mcap") or coin.mcap:
            live += f" · MC {money(quote.get('mcap') or coin.mcap)}"
        lines.append(f"· <b>{esc(coin.symbol or coin.address[:6])}</b>{live} · "
                     f"{esc(coin.stage)} · score {coin.score}")
        rows.append([InlineKeyboardButton(f"🔎 {coin.symbol or 'check'}"[:24],
                                          callback_data=tokens.cb("chk", coin.key)),
                     InlineKeyboardButton("🚫 Drop", callback_data=tokens.cb("wx", coin.key))])
    await say(update, "\n".join(lines), keyboard(rows))


async def cmd_settings(update, ctx):
    """Settings live on the news side now - one screen for everything."""
    from . import settings as settings_ux
    await settings_ux.cmd_settings(update, ctx)


async def cmd_picks(update, ctx):
    """🧭 Daily Picks: send today's digest now."""
    from ..agents.curator import CuratorAgent
    await say(update, "🧭 Putting today's picks together…")
    await CuratorAgent("curator", {}).run()


async def cmd_glossary(update, ctx):
    rows, current = [], []
    for key, (title, _) in glossary.TERMS.items():
        current.append(InlineKeyboardButton(title[:24], callback_data=f"g:{key}"))
        if len(current) == 2:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    await say(update, glossary.index(), keyboard(rows))


# ---------------- search -> pick -> scorecard ----------------
async def search(update, query: str):
    clear_state(update.effective_chat.id)
    async with client() as c:
        found = await resolve.resolve(c, query)
    rows = [[InlineKeyboardButton(cards.candidate_label(cand)[:64], callback_data=tokens.cb("chk", cand.key))]
            for cand in found]
    await say(update, cards.candidates_card(query, found), keyboard(rows))


async def show_details(update, key: str):
    """Lookup-only chains: real numbers, and an honest note about the checks we cannot run."""
    chain, _, address = key.partition(":")
    async with client() as c:
        found = await resolve.one(c, chain, address)
    if not found:
        return await say(update, "That token has no tradeable pair I can read right now.")
    await say(update, cards.details_card(found, chain), coin_keyboard(key, found.pair_url))


async def check(update, key: str):
    chain, _, address = key.partition(":")
    if chain not in CHAINS or not address:
        return await say(update, "I lost track of that coin — please search for it again.")
    if not has_security(chain):
        return await show_details(update, key)
    await say(update, "Checking safety, holders, price location and socials… about 30 seconds.")
    snap, verdict, rules = await TokenScoutAgent("token_scout", {}).analyse(chain, address)
    if snap is None:
        return await say(update, "That token has no tradeable pair I can read right now.")
    await say(update, cards.scorecard(snap, verdict, rules), coin_keyboard(key, snap.pair_url))


# ---------------- journal wizard ----------------
async def ask_amount(update, key: str):
    set_state(update.effective_chat.id, mode="amount", key=key)
    await say(update, "How many dollars did you put in? Just type the number, e.g. <b>50</b>.\n"
                      "<i>I record the market cap you entered at, so I can show your multiple later.</i>")


async def save_amount(update, text: str):
    chat_id = update.effective_chat.id
    state = get_state(chat_id)
    try:
        usd = float(text.replace("$", "").replace(",", "").strip())
    except ValueError:
        return await say(update, "That didn't look like a number. Try just <b>50</b>, or /menu to stop.")
    if not 0 < usd <= MAX_USD:
        return await say(update, "Enter an amount between 1 and 10,000,000.")
    chain, _, address = state.get("key", "").partition(":")
    if chain not in CHAINS or not address:
        clear_state(chat_id)
        return await say(update, "I lost track of that coin — please search for it again.")
    async with client() as c:
        pair = dx.best_pairs(chain, await dx.pairs_for(c, chain, [address])).get(address)
    if not pair:
        clear_state(chat_id)
        return await say(update, "That token has no tradeable pair right now, so I can't record an entry.")
    basics = dx.basics(pair)
    holding = add_dex_holding(state["key"], basics["symbol"], basics["mcap"] or 0, usd,
                              basics["price"])
    clear_state(chat_id)
    entry_price = f" (one coin cost {price(basics['price'])})" if basics.get("price") else ""
    await say(update, f"📒 Saved #{holding.id} <b>{esc(holding.symbol)}</b> — ${usd:,.0f} in at a market cap of "
                      f"{money(holding.entry_value)}{entry_price}.\nI will tell you when it doubles, and if the "
                      "community goes quiet.",
              keyboard([[InlineKeyboardButton("📒 See journal", callback_data="m:journal")]]))


async def on_text(update, ctx):
    """Free text: whatever a wizard is waiting for, otherwise work out what you meant."""
    text = (update.effective_message.text or "").strip()
    if not text:
        return
    chat_id = update.effective_chat.id
    mode = get_state(chat_id).get("mode", "")
    if mode == "amount":
        return await save_amount(update, text)
    if mode == "find":                                  # you just tapped 🔎 Check a Coin
        return await search(update, text[:100])
    if mode.startswith("me:"):
        from . import settings as settings_ux
        clear_state(chat_id)
        return await settings_ux.save_me_value(update, mode[3:], text)
    from .dispatch import handle_text
    await handle_text(update, text[:200])


menu.register("mood", "🌡 Market Mood", cmd_mood, order=10,
              command="mood", description="Is it a good time to buy?")
menu.register("find", "🔎 Check a Coin", cmd_find, order=15,
              command="find", description="Check any coin by name")
menu.register("picks", "🧭 Daily Picks", cmd_picks, order=30)
menu.register("watch", "⭐ Watchlist", cmd_watchlist, order=35,
              command="watchlist", description="Coins you are following")
menu.register("journal", "📒 Journal", cmd_journal, order=40,
              command="journal", description="Your coins, live profit")
menu.register("help", "❓ Help", cmd_glossary, order=95,
              command="help", description="Plain English help")
