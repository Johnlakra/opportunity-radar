"""The /alerts and /levels screens.

Deliberately does not import app.bot (that would be circular): the owner check is two lines,
and the message helpers come from notifier and cream, which app.bot uses too."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from . import cream, level_store, levels, levels_data
from .config import settings
from .crypto.chains import CHAINS, coin_key, is_address, norm
from .crypto.http import CG, client, get_json
from .crypto.regime import CGB, _headers
from .redis_client import r
from .text import esc
from .ux import level_cards

log = logging.getLogger(__name__)
PAUSED_KEY = "lv:paused"
SEARCH_URL = f"{CGB}/search"
MAX_MATCHES = 4
PERIOD_BUTTONS = ("W", "M", "Q", "Y")


def mine(update: Update) -> bool:
    return str(update.effective_chat.id) == str(settings.telegram_chat_id)


def keyboard(rows) -> InlineKeyboardMarkup | None:
    rows = [[b for b in row if b] for row in rows]
    rows = [row for row in rows if row]
    return InlineKeyboardMarkup(rows) if rows else None


async def say(update: Update, text: str, markup=None):
    await update.effective_message.reply_html(text[:4000], reply_markup=markup,
                                              disable_web_page_preview=True)


async def redraw(update: Update, text: str, markup=None):
    """Edit the message the button is on, so the chat never fills up with menus."""
    query = update.callback_query
    try:
        await query.edit_message_text(text[:4000], parse_mode="HTML",
                                      disable_web_page_preview=True, reply_markup=markup)
    except Exception:                       # "message is not modified", or it is too old to edit
        await say(update, text, markup)


# ---------------- the menu ----------------
def menu_markup(subs) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(
        f"{level_cards.icon_for(s.asset_key, s.source)} {s.label}"[:24], callback_data=f"lv:a:{s.id}")
        for s in subs]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    paused = bool(r.exists(PAUSED_KEY))
    rows.append([InlineKeyboardButton("📒 Turn on all journal coins", callback_data="lv:j")])
    rows.append([InlineKeyboardButton("▶️ Resume all" if paused else "⏸ Pause all",
                                      callback_data="lv:p")])
    return keyboard(rows)


async def show_menu(update: Update, edit: bool = False):
    subs = level_store.all_subs()
    rows = [level_cards.menu_row(s, "".join(level_store.periods_of(s))) for s in subs]
    text = level_cards.menu_text(rows, bool(r.exists(PAUSED_KEY)))
    markup = menu_markup(subs)
    await (redraw if edit else say)(update, text, markup)


# ---------------- one asset ----------------
def panel_markup(sub) -> InlineKeyboardMarkup:
    on = set(level_store.periods_of(sub))
    period_row = [InlineKeyboardButton(f"{p} {'✅' if p in on else '❌'}",
                                       callback_data=f"lv:t:{sub.id}:{p}") for p in PERIOD_BUTTONS]
    return keyboard([
        period_row,
        [InlineKeyboardButton(f"↑ Above high {'✅' if sub.up else '❌'}", callback_data=f"lv:t:{sub.id}:U"),
         InlineKeyboardButton(f"↓ Below low {'✅' if sub.down else '❌'}", callback_data=f"lv:t:{sub.id}:D")],
        [InlineKeyboardButton("🔔 On" if sub.active else "🔕 Off", callback_data=f"lv:t:{sub.id}:A"),
         InlineKeyboardButton("📊 Show levels", callback_data=f"lv:s:{sub.id}")],
        [InlineKeyboardButton("🗑 Remove", callback_data=f"lv:r:{sub.id}"),
         InlineKeyboardButton("« Back", callback_data="lv:m")],
    ])


async def show_panel(update: Update, sub_id: int, edit: bool = True):
    sub = level_store.get_sub(sub_id)
    if not sub:
        return await show_menu(update, edit)
    price, found, _missing = await read_levels(sub)
    text = level_cards.panel_text(sub, "".join(level_store.periods_of(sub)), found, price,
                                  premium())
    await (redraw if edit else say)(update, text, panel_markup(sub))


# ---------------- reading the numbers ----------------
def _cfg() -> dict:
    from .orchestrator import load_config
    return load_config().get("level_watch") or {}


def premium() -> float:
    return float(_cfg().get("inr_premium_pct", 0) or 0)


async def read_levels(sub) -> tuple[float | None, dict, list[str]]:
    """(price, {period: (high, low)}, periods we cannot answer yet)."""
    today = level_store.local_today()
    price, bars = None, []
    async with client() as c:
        try:
            if sub.asset_key.startswith("metal:"):
                quote = await levels_data.metal_quote(c)
                if quote:
                    usd = (quote["gold_usd_oz"] if sub.asset_key == levels_data.GOLD
                           else quote["silver_usd_oz"])
                    price = levels.inr_per_gram(usd, quote["usd_inr"]) if usd else None
                # bootstrap here too, so /levels works before the agent's first run
                bars = await levels_data.metal_history(
                    c, sub.asset_key, bool(_cfg().get("bootstrap_silver_from_yahoo", True)))
            elif sub.asset_key.startswith("cg:"):
                coin_id = sub.asset_key.split(":", 1)[1]
                live = await levels_data.cg_prices(c, [coin_id])
                quote = live.get(coin_id) or {}
                price = quote.get("price")
                bars, _ = await levels_data.cg_history(c, coin_id, quote.get("symbol") or sub.label)
            else:
                ref = sub.asset_key.split(":", 1)[1]
                quote = (await levels_data.dex_quotes(c, [ref])).get(ref) or {}
                price = quote.get("price")
                bars = await levels_data.dex_history(c, ref, quote.get("pool", ""))
        except Exception as exc:
            log.warning("[levels] could not read %s: %s", sub.asset_key, exc)
    found, missing = {}, []
    for period in level_store.periods_of(sub):
        hl = levels.prev_period_hl(bars, period, today)
        (found.__setitem__(period, hl) if hl else missing.append(period))
    return price, found, missing


# ---------------- commands ----------------
def find_sub(name: str):
    wanted = (name or "").strip().lower()
    for sub in level_store.all_subs():
        if wanted in (sub.label.lower(), sub.asset_key.lower()) or \
                sub.asset_key.lower().endswith(":" + wanted):
            return sub
    return None


async def cmd_alerts(update: Update, ctx):
    if not mine(update):
        return
    args = list(getattr(ctx, "args", []) or [])
    if not args:
        return await show_menu(update)
    if args[0].lower() == "add":
        return await add_asset(update, args[1:])
    sub = find_sub(" ".join(args))
    if sub:
        return await show_panel(update, sub.id, edit=False)
    await say(update, f"I am not watching <b>{esc(' '.join(args))}</b>.\n"
                      f"Add it with <code>/alerts add {esc(' '.join(args))}</code>.")


async def cmd_levels(update: Update, ctx):
    if not mine(update):
        return
    args = list(getattr(ctx, "args", []) or [])
    if not args:
        return await say(update, "Usage: <code>/levels gold</code> — or open 🔔 /alerts.")
    sub = find_sub(" ".join(args))
    if not sub:
        return await say(update, f"I am not watching <b>{esc(' '.join(args))}</b> yet.")
    await send_levels(update, sub)


async def send_levels(update: Update, sub, edit: bool = False):
    price, found, missing = await read_levels(sub)
    text = level_cards.levels_table(sub.label, sub.asset_key, price, found, missing,
                                    premium(), sub.source)
    await (redraw if edit else say)(update, text, panel_markup(sub) if edit else None)


# ---------------- adding something new ----------------
async def add_asset(update: Update, args: list[str]):
    if not args:
        return await say(update, "Usage: <code>/alerts add bitcoin</code> or "
                                 "<code>/alerts add solana &lt;address&gt;</code>")
    if len(args) >= 2 and args[0] in CHAINS and is_address(args[1]):
        key = coin_key(args[0], norm(args[0], args[1]))
        sub = level_store.upsert(f"dex:{key}", args[1][:8], journal_periods())
        return await show_panel(update, sub.id, edit=False)
    matches = await search_coins(" ".join(args))
    if not matches:
        return await say(update, f"No coin called <b>{esc(' '.join(args))}</b> on CoinGecko.")
    if len(matches) == 1:
        sub = level_store.upsert(f"cg:{matches[0]['id']}", matches[0]["symbol"], journal_periods())
        return await show_panel(update, sub.id, edit=False)
    rows = [[InlineKeyboardButton(f"{m['symbol']} — {m['name']}"[:40], callback_data=f"lv:n:{m['id']}")]
            for m in matches[:MAX_MATCHES]]
    await say(update, "Which one did you mean?", keyboard(rows))


def journal_periods() -> str:
    return _cfg().get("journal_periods", "MQY")


async def search_coins(query: str) -> list[dict]:
    try:
        async with client() as c:
            found = await get_json(c, SEARCH_URL, CG, headers=_headers(), params={"query": query[:40]})
    except Exception as exc:
        log.warning("[levels] coin search failed: %s", exc)
        return []
    out = []
    for coin in (found or {}).get("coins") or []:
        if coin.get("id"):
            out.append({"id": coin["id"], "symbol": (coin.get("symbol") or "").upper(),
                        "name": coin.get("name") or coin["id"]})
    return out[:MAX_MATCHES]


# ---------------- buttons ----------------
async def on_button(update: Update, ctx):
    query = update.callback_query
    if not mine(update):
        return await query.answer()
    parts = (query.data or "").split(":")
    action = parts[1] if len(parts) > 1 else "m"
    arg = parts[2] if len(parts) > 2 else ""
    extra = parts[3] if len(parts) > 3 else ""

    if action == "m":
        await query.answer()
        return await show_menu(update, edit=True)
    if action == "p":
        paused = bool(r.exists(PAUSED_KEY))
        r.delete(PAUSED_KEY) if paused else r.set(PAUSED_KEY, 1)
        await query.answer("Alerts resumed" if paused else "All alerts paused")
        return await show_menu(update, edit=True)
    if action == "j":
        added, _ = level_store.sync_journal(journal_periods())
        await query.answer(f"{added} added from your journal" if added else "Already watching them")
        return await show_menu(update, edit=True)
    if action == "n" and arg:
        sub = level_store.upsert(f"cg:{arg}", arg.upper(), journal_periods())
        await query.answer(f"Watching {sub.label}")
        return await show_panel(update, sub.id)

    sub = level_store.get_sub(int(arg)) if arg.isdigit() else None
    if not sub:
        await query.answer("That one is gone.")
        return await show_menu(update, edit=True)
    if action == "a":
        await query.answer()
        return await show_panel(update, sub.id)
    if action == "s":
        await query.answer()
        return await send_levels(update, sub, edit=True)
    if action == "r":
        level_store.remove(sub.id)
        await query.answer(f"{sub.label} removed")
        return await show_menu(update, edit=True)
    if action == "t":
        await toggle(update, sub, extra)
        return
    await query.answer()


async def toggle(update: Update, sub, what: str):
    """Every toggle marks the row manual, so the journal sync stops managing it."""
    query = update.callback_query
    if what in PERIOD_BUTTONS:
        level_store.update(sub.id, periods=levels.toggle_period(sub.periods, what))
        await query.answer(f"{what} {'off' if what in level_store.periods_of(sub) else 'on'}")
    elif what == "U":
        level_store.update(sub.id, up=not sub.up)
        await query.answer("Above-high alerts " + ("off" if sub.up else "on"))
    elif what == "D":
        level_store.update(sub.id, down=not sub.down)
        await query.answer("Below-low alerts " + ("off" if sub.down else "on"))
    elif what == "A":
        level_store.update(sub.id, active=not sub.active)
        await query.answer("Alerts off" if sub.active else "Alerts on")
    else:
        return await query.answer()
    await show_panel(update, sub.id)
