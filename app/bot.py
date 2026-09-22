"""Messenger agent: Telegram commands + button callbacks. Only answers YOUR chat id."""
import logging
import re

from sqlmodel import select
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from . import cream
from .agents.curator import CuratorAgent
from .agents.token_scout import TokenScoutAgent
from .config import settings
from .crypto import coingecko, dexscreener as dx, regime
from .crypto.chains import CHAINS, coin_key, norm
from .crypto.http import client
from .db import init_db, session
from .feedback import record_item_vote
from .models import Alert, Coin, Holding
from .notifier import esc
from .orchestrator import build_agents, run_agent
from .redis_client import r

logging.basicConfig(level=logging.INFO)
ADDR = re.compile(r"^(0x[a-fA-F0-9]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})$")
HELP = """<b>Opportunity Radar</b>
/digest – send today's cream now
/regime – BTC regime (cheat sheet)
/check &lt;chain&gt; &lt;address&gt; – run the course checklist on a token
/watch &lt;chain&gt; &lt;address&gt; – add to scout watchlist
/hold cg &lt;coingecko-id&gt; &lt;usd&gt; – journal a listed coin (e.g. /hold cg solana 100)
/hold &lt;chain&gt; &lt;address&gt; &lt;usd&gt; – journal a DEX token
/holdings · /sell &lt;id&gt;
/mute &lt;topic&gt; · /unmute &lt;topic&gt; · /more · /agents
Chains: """ + ", ".join(CHAINS)


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


async def cmd_regime(update, ctx):
    if mine(update):
        await reply(update, regime.format_regime(await regime.compute()))


async def cmd_digest(update, ctx):
    if mine(update):
        await CuratorAgent("curator", {}).run()


def _chain_addr(args):
    if len(args) < 2 or args[0] not in CHAINS or not ADDR.match(args[1]):
        return None, None
    return args[0], norm(args[0], args[1])


async def cmd_check(update, ctx):
    if not mine(update):
        return
    chain, addr = _chain_addr(ctx.args)
    if not chain:
        return await reply(update, "Usage: /check &lt;chain&gt; &lt;address&gt;")
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


def set_status(key: str, status: str):
    chain, addr = key.split(":", 1)
    with session() as s:
        coin = s.get(Coin, key) or Coin(key=key, chain=chain, address=addr)
        coin.user_status = status
        s.add(coin)
        s.commit()


async def cmd_hold(update, ctx):
    if not mine(update):
        return
    a = ctx.args
    try:
        if len(a) == 3 and a[0] == "cg":
            async with client() as c:
                m = await coingecko.markets(c, ids=[a[1]])
            if not m:
                return await reply(update, "Unknown CoinGecko id (see the coin's CoinGecko URL).")
            h = Holding(kind="cg", ref=a[1], symbol=m[0]["symbol"].upper(),
                        entry_value=m[0]["current_price"], usd=float(a[2]))
        elif len(a) == 3 and a[0] in CHAINS and ADDR.match(a[1]):
            chain, addr = a[0], norm(a[0], a[1])
            async with client() as c:
                pair = dx.best_pairs(chain, await dx.pairs_for(c, chain, [addr])).get(addr)
            if not pair:
                return await reply(update, "No pair found for that token.")
            b = dx.basics(pair)
            h = Holding(kind="dex", ref=coin_key(chain, addr), symbol=b["symbol"],
                        entry_value=b["mcap"] or 0, usd=float(a[2]))
        else:
            return await reply(update, "Usage: /hold cg &lt;id&gt; &lt;usd&gt;  or  /hold &lt;chain&gt; &lt;address&gt; &lt;usd&gt;")
    except ValueError:
        return await reply(update, "USD amount must be a number.")
    with session() as s:
        s.add(h)
        s.commit()
        s.refresh(h)
    unit = "price" if h.kind == "cg" else "market cap"
    await reply(update, f"📝 Journaled #{h.id} {esc(h.symbol)}: ${h.usd:,.0f} at {unit} {h.entry_value:,.4g}. "
                        "The guardian now watches take-profit levels and community health.")


async def cmd_holdings(update, ctx):
    if not mine(update):
        return
    with session() as s:
        rows = s.exec(select(Holding)).all()
    if not rows:
        return await reply(update, "No holdings journaled. Use /hold.")
    lines = ["<b>📒 Journal</b>"] + [f"#{h.id} {esc(h.symbol)} · ${h.usd:,.0f} · entry {h.entry_value:,.4g} · "
                                     f"{h.added_at:%Y-%m-%d}" for h in rows]
    await reply(update, "\n".join(lines))


async def cmd_sell(update, ctx):
    if not mine(update) or not ctx.args:
        return
    with session() as s:
        h = s.get(Holding, int(ctx.args[0])) if ctx.args[0].isdigit() else None
        if not h:
            return await reply(update, "Unknown holding id (see /holdings).")
        s.delete(h)
        s.commit()
    await reply(update, "Removed from journal.")


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


async def on_button(update: Update, ctx):
    q = update.callback_query
    if not mine(update):
        return await q.answer()
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
    app = Application.builder().token(settings.telegram_bot_token).build()
    for name, fn in [("start", cmd_help), ("help", cmd_help), ("regime", cmd_regime), ("digest", cmd_digest),
                     ("check", cmd_check), ("watch", cmd_watch), ("hold", cmd_hold), ("holdings", cmd_holdings),
                     ("sell", cmd_sell), ("mute", cmd_mute), ("unmute", cmd_unmute), ("more", cmd_more),
                     ("agents", cmd_agents), ("run", cmd_run)]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(on_button))
    app.run_polling()


if __name__ == "__main__":
    main()
