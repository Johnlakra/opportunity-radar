"""Routes every new-style button press. Returns False for the old buttons so the bot's
original handler (👍/👎 votes, w:/x: watch and ignore) keeps working untouched."""
import logging
from io import BytesIO

from telegram import InlineKeyboardButton

from ..journal import get_holding, remove_holding, set_status
from ..text import esc
from ..redis_client import r
from . import flows, glossary, menu, news_router, portfolio, tokens

log = logging.getLogger(__name__)
NEW_ACTIONS = {"m", "g", "chk", "wl", "wx", "jw", "sl", "slq", "mt"}
EXPIRED = "That button is older than a week — please search for the coin again."


async def _menu(update, target: str) -> None:
    handler = menu.handler(target)
    if handler:
        return await handler(update, None)
    if target == "csv":
        rows = await portfolio.rows()
        if not rows:
            return await flows.say(update, "Nothing to export yet.")
        doc = BytesIO(portfolio.csv_bytes(rows))
        doc.name = "journal.csv"
        return await update.effective_message.reply_document(document=doc, filename="journal.csv",
                                                             caption="Your journal, for any spreadsheet.")
    await flows.say(update, menu.menu_text(), menu.main_menu())


async def route(update, ctx) -> bool:
    """True = handled here."""
    if await news_router.route(update, ctx):
        return True
    query = update.callback_query
    action, _, arg = (query.data or "").partition(":")
    if action not in NEW_ACTIONS:
        return False
    if action == "m":
        await query.answer()
        await _menu(update, arg)
        return True
    if action == "g":
        text = glossary.lookup(arg)
        await query.answer()
        await flows.say(update, text or "No entry for that word yet.")
        return True
    if action == "slq":                     # removing is not undoable, so name it first
        holding = get_holding(int(arg)) if arg.isdigit() else None
        await query.answer()
        if not holding:
            await flows.say(update, "That holding is already gone.")
        else:
            await flows.say(update, f"Remove <b>{esc(holding.symbol)}</b> (${holding.usd:,.0f} in) "
                                    "from the journal?",
                            flows.keyboard([[InlineKeyboardButton("Yes, remove",
                                                                  callback_data=f"sl:{holding.id}"),
                                             InlineKeyboardButton("Cancel",
                                                                  callback_data="m:journal")]]))
        return True
    if action == "sl":
        gone = remove_holding(int(arg)) if arg.isdigit() else False
        await query.answer("Removed from the journal" if gone else "Already gone")
        await flows.cmd_journal(update, ctx)          # renumbered straight away
        return True
    if action == "mt":
        if r.sismember("muted", arg):
            r.srem("muted", arg)
            await query.answer(f"{arg}: alerts on")
        else:
            r.sadd("muted", arg)
            await query.answer(f"{arg}: muted")
        await flows.cmd_settings(update, None)
        return True

    key = tokens.get(arg)                       # coin actions: the address lives in Redis, not the button
    if not key:
        await query.answer()
        await flows.say(update, EXPIRED)
        return True
    if action == "chk":
        await query.answer()
        await flows.check(update, key)
    elif action == "wl":
        set_status(key, "watch")
        await query.answer("⭐ Watching — the scout re-checks it every run")
    elif action == "wx":
        set_status(key, "ignore")
        await query.answer("🚫 Ignored")
    elif action == "jw":
        await query.answer()
        await flows.ask_amount(update, key)
    return True
