"""Messenger agent: Telegram commands + button callbacks. Only answers YOUR chat id."""
import logging
import re

from sqlmodel import select
from telegram import Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from . import cream
from .agents.curator import CuratorAgent
from .agents.token_scout import TokenScoutAgent
from .config import settings
from .crypto import coingecko, dexscreener as dx, regime
from .crypto.chains import CHAINS, LOOKUP_ONLY, SCOUT_CHAINS, coin_key, has_security, is_address, norm
from .crypto.http import client
from .db import init_db, session
from .feedback import record_item_vote
from .journal import holding_at, holdings_in_order, set_status
from .models import Alert, Holding
from .notifier import esc
from .text import price as fmt_price
from .orchestrator import build_agents, run_agent
from .redis_client import r
from .ux import flows, menu, news, router, settings as settings_ux  # noqa: F401 (menu registration)

logging.basicConfig(level=logging.INFO)
HELP = """<b>Opportunity Radar</b>
<b>Easiest way:</b> /menu, or just type a coin name — I find the address for you.
/mood – is this a good time to buy? · /find &lt;name&gt; – check any coin
/journal – your coins, live profit · /watchlist – coins you follow

<b>Everything else still works:</b>
/digest – send today's cream now
/regime – BTC regime (cheat sheet)
/check &lt;chain&gt; &lt;address&gt; – run the course checklist on a token
/watch &lt;chain&gt; &lt;address&gt; – add to scout watchlist
/hold cg &lt;coingecko-id&gt; &lt;usd&gt; – journal a listed coin (e.g. /hold cg solana 100)
/hold &lt;chain&gt; &lt;address&gt; &lt;usd&gt; – journal a DEX token
/holdings · /sell &lt;id&gt;
/mute &lt;topic&gt; · /unmute &lt;topic&gt; · /more · /agents
Chains I can check fully: """ + ", ".join(SCOUT_CHAINS) + f"""
Chains I can look up (price, journal, alerts - no safety report yet): {", ".join(LOOKUP_ONLY)}"""


def mine(update: Update) -> bool:
    return str(update.effective_chat.id) == str(settings.telegram_chat_id)


async def reply(update: Update, text: str, buttons_json: str = "[]"):
    from telegram import InlineKeyboardMarkup
    rows = [[b for b in row if b] for row in cream._rows(buttons_json)]
    markup = InlineKeyboardMarkup([row for row in rows if row]) if any(rows) else None
    await update.effective_message.reply_html(text[:4000], reply_markup=markup, disable_web_page_preview=True)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if mine(update):
        await reply(update, HELP)


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """The 7-button menu - the front door for everything below."""
    if mine(update):
        await flows.cmd_menu(update, ctx)


async def cmd_regime(update, ctx):
    if mine(update):
        await reply(update, regime.format_regime(await regime.compute()))


async def cmd_digest(update, ctx):
    if mine(update):
        await CuratorAgent("curator", {}).run()


def _chain_addr(args):
    if len(args) < 2 or args[0] not in CHAINS or not is_address(args[1]):
        return None, None
    return args[0], norm(args[0], args[1])


async def cmd_check(update, ctx):
    if not mine(update):
        return
    chain, addr = _chain_addr(ctx.args)
    if not chain:
        return await reply(update, "Usage: /check &lt;chain&gt; &lt;address&gt;")
    if not has_security(chain):                  # TON, Sui, Aptos...: show the numbers, not a false verdict
        return await flows.show_details(update, coin_key(chain, addr))
    await reply(update, "Checking… (security, holders, range, socials — ~30s)")
    text, btns = await TokenScoutAgent("token_scout", {}).check_one(chain, addr)
    await reply(update, text, btns)


async def cmd_watch(update, ctx):
    if not mine(update):
        return
    chain, addr = _chain_addr(ctx.args)
    if not chain:
        return await reply(update, "Usage: /watch &lt;chain&gt; &lt;address&gt;")
    set_status(coin_key(chain, addr), "watch")
    await reply(update, "👀 Added to watchlist; the scout re-checks it every run.")


async def cmd_hold(update, ctx):
    if not mine(update):
        return
    a = ctx.args
    entry_price = None
    try:
        if len(a) == 3 and a[0] == "cg":
            async with client() as c:
                m = await coingecko.markets(c, ids=[a[1]])
            if not m:
                return await reply(update, "Unknown CoinGecko id (see the coin's CoinGecko URL).")
            entry_price = m[0]["current_price"]
            h = Holding(kind="cg", ref=a[1], symbol=m[0]["symbol"].upper(),
                        entry_value=entry_price, entry_price=entry_price, usd=float(a[2]))
        elif len(a) == 3 and a[0] in CHAINS and is_address(a[1]):
            chain, addr = a[0], norm(a[0], a[1])
            async with client() as c:
                pair = dx.best_pairs(chain, await dx.pairs_for(c, chain, [addr])).get(addr)
            if not pair:
                return await reply(update, "No pair found for that token.")
            b = dx.basics(pair)
            entry_price = b["price"]
            h = Holding(kind="dex", ref=coin_key(chain, addr), symbol=b["symbol"],
                        entry_value=b["mcap"] or 0, entry_price=entry_price, usd=float(a[2]))
        else:
            return await reply(update, "Usage: /hold cg &lt;id&gt; &lt;usd&gt;  or  /hold &lt;chain&gt; &lt;address&gt; &lt;usd&gt;")
    except ValueError:
        return await reply(update, "USD amount must be a number.")
    with session() as s:
        s.add(h)
        s.commit()
        s.refresh(h)
    unit = "price" if h.kind == "cg" else "market cap"
    at_price = f" (one coin cost {fmt_price(entry_price)})" if h.kind != "cg" and entry_price else ""
    await reply(update, f"📝 Journaled #{h.id} {esc(h.symbol)}: ${h.usd:,.0f} at {unit} "
                        f"{h.entry_value:,.4g}{at_price}. "
                        "The guardian now watches take-profit levels and community health.")


async def cmd_holdings(update, ctx):
    if not mine(update):
        return
    rows = holdings_in_order()
    if not rows:
        return await reply(update, "No holdings journaled. Use /hold, or 📒 Journal in /menu.")
    lines = ["<b>📒 Journal</b>"]
    for position, h in enumerate(rows, start=1):
        entry = f"{fmt_price(h.entry_price)} · " if h.entry_price else ""
        unit = "price" if h.kind == "cg" else "market cap"
        lines.append(f"#{position} {esc(h.symbol)} · ${h.usd:,.0f} in · {entry}"
                     f"{unit} {h.entry_value:,.0f} · {h.added_at:%Y-%m-%d}")
    lines.append("<i>Live values and profit: 📒 Journal in /menu.</i>")
    await reply(update, "\n".join(lines))


async def cmd_sell(update, ctx):
    """/sell <n> - n is the number shown in the journal, which always counts from 1."""
    if not mine(update) or not ctx.args:
        return
    if not ctx.args[0].isdigit():
        return await reply(update, "Usage: /sell &lt;number from the journal&gt;")
    holding = holding_at(int(ctx.args[0]))
    if not holding:
        return await reply(update, "There is no holding with that number (see /journal).")
    await reply(update, f"Remove <b>{esc(holding.symbol)}</b> (${holding.usd:,.0f} in) from the journal?",
                cream.buttons([("Yes, remove", None, f"sl:{holding.id}"),
                               ("Cancel", None, "m:journal")]))


async def cmd_mute(update, ctx):
    if mine(update) and ctx.args:
        r.sadd("muted", ctx.args[0])
        await reply(update, f"🔇 Muted {esc(ctx.args[0])} (holding-protection alerts still come through).")


async def cmd_unmute(update, ctx):
    if mine(update) and ctx.args:
        r.srem("muted", ctx.args[0])
        await reply(update, f"🔔 Unmuted {esc(ctx.args[0])}.")


async def cmd_more(update, ctx):
    if not mine(update):
        return
    with session() as s:
        rows = s.exec(select(Alert).where(Alert.sent_mode == "dropped")
                      .order_by(Alert.created_at.desc()).limit(10)).all()
    if not rows:
        return await reply(update, "Nothing filtered out recently.")
    lines = ["<b>Filtered out (below the cream line):</b>"]
    for a in rows:
        first = re.sub("<[^>]+>", "", a.text.split("\n")[0])
        lines.append(f"· [{a.priority}] {esc(first)[:120]}")
    await reply(update, "\n".join(lines))


async def cmd_agents(update, ctx):
    if not mine(update):
        return
    status = r.hgetall("agents:status")
    lines = ["<b>Agents</b>"] + [f"· {esc(k)}: {esc(v)}" for k, v in sorted(status.items())]
    muted = r.smembers("muted")
    if muted:
        lines.append("Muted: " + ", ".join(sorted(muted)))
    await reply(update, "\n".join(lines) if status else "No agent has run yet.")


async def cmd_run(update, ctx):
    """/run <agent> - run one agent now (e.g. /run news_ai)."""
    if not mine(update) or not ctx.args:
        return
    agents = build_agents()
    if ctx.args[0] not in agents:
        return await reply(update, "Agents: " + ", ".join(agents))
    status = await run_agent(ctx.args[0], agents[ctx.args[0]][0])
    await reply(update, f"{esc(ctx.args[0])}: {esc(status)}")


def owner_only(fn):
    """Wrap a flow handler so it only ever answers YOUR chat id."""
    async def wrapped(update, ctx):
        if mine(update):
            await fn(update, ctx)
    return wrapped


async def on_button(update: Update, ctx):
    q = update.callback_query
    if not mine(update):
        return await q.answer()
    if await router.route(update, ctx):
        return
    data = q.data or ""
    if data.startswith("v:"):
        _, vote, item_id = data.split(":", 2)
        record_item_vote(int(item_id), "up" if vote == "up" else "down")
        await q.answer("Saved — the scorer learns from this.")
    elif data.startswith(("w:", "x:")):
        set_status(data[2:], "watch" if data[0] == "w" else "ignore")
        await q.answer("Watching" if data[0] == "w" else "Ignored")
    else:
        await q.answer()
    try:
        await q.edit_message_reply_markup(reply_markup=None) if data.startswith("v:") else None
    except Exception:
        pass


def main():
    init_db()
    app = Application.builder().token(settings.telegram_bot_token).post_init(menu.setup).build()
    for name, fn in [("start", cmd_menu), ("help", cmd_help), ("regime", cmd_regime), ("digest", cmd_digest),
                     ("check", cmd_check), ("watch", cmd_watch), ("hold", cmd_hold), ("holdings", cmd_holdings),
                     ("sell", cmd_sell), ("mute", cmd_mute), ("unmute", cmd_unmute), ("more", cmd_more),
                     ("agents", cmd_agents), ("run", cmd_run),
                     ("menu", cmd_menu), ("mood", owner_only(flows.cmd_mood)),
                     ("find", owner_only(flows.cmd_find)), ("journal", owner_only(flows.cmd_journal)),
                     ("watchlist", owner_only(flows.cmd_watchlist)),
                     ("settings", owner_only(settings_ux.cmd_settings)),
                     ("glossary", owner_only(flows.cmd_glossary)),
                     ("today", owner_only(news.cmd_today)), ("saved", owner_only(news.cmd_saved)),
                     ("health", owner_only(news.cmd_health))]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, owner_only(flows.on_text)))
    app.run_polling()


if __name__ == "__main__":
    main()
