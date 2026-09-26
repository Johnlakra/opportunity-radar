"""Routes every `n:` button. One place, so the news screens stay readable.

Returns False for anything it does not own, so the crypto router and the original
👍/👎 handler keep working untouched."""
import logging

from . import news, settings, topic_wizard

log = logging.getLogger(__name__)
PREFIX = "n"


def _int(value: str) -> int | None:
    return int(value) if value.isdigit() else None


async def route(update, ctx) -> bool:
    """True = handled here."""
    parts = (update.callback_query.data or "").split(":")
    if parts[0] != PREFIX or len(parts) < 2:
        return False
    query = update.callback_query
    action = parts[1]
    arg = parts[2] if len(parts) > 2 else ""
    extra = parts[3] if len(parts) > 3 else ""
    item_id = _int(arg)

    # ---- what is worth my time ----
    if action == "top":
        await query.answer()
        await news.show_today(update, arg or None, _int(extra) or 0)
    # ---- one item ----
    elif action == "save" and item_id:
        await news.save_item(update, item_id, True)
    elif action in ("done", "drop") and item_id:
        await news.save_item(update, item_id, False)
    elif action == "rem" and item_id:
        await (news.set_remind(update, item_id, extra) if extra else news.ask_remind(update, item_id))
    elif action == "less" and item_id:
        await news.less_like_this(update, item_id)
    elif action == "mcat":
        await news.mute_category(update, item_id or 0, extra == "y")
    elif action == "tell" and item_id:
        await news.tell_me_more(update, item_id)
    elif action == "stats":
        await query.answer()
        await news.show_stats(update)
    elif action == "run" and arg:
        await query.answer()
        await news.run_agent_now(update, arg)
    # ---- settings ----
    elif action == "set":
        await query.answer()
        await settings.cmd_settings(update, ctx)
    elif action == "tog":
        await (settings.toggle_topic(update, arg) if arg else _screen(query, settings.show_topics, update))
    elif action == "pk":
        if arg and extra:
            await settings.set_pickiness(update, arg, extra)
        else:
            await _screen(query, settings.show_pickiness, update, arg or None)
    elif action in ("cap", "hour"):
        if arg:
            await settings.set_simple(update, action, arg)
        else:
            await _screen(query, settings.show_cap if action == "cap" else settings.show_hour, update)
    elif action == "quiet":
        await (settings.set_quiet(update, arg) if arg else _screen(query, settings.show_quiet, update))
    elif action == "qday":
        await settings.toggle_quiet_day(update)
    elif action == "me":
        await _screen(query, settings.show_me, update, arg or None)
    elif action == "mead" and arg:
        await query.answer()
        await settings.ask_me_value(update, arg)
    elif action == "merm" and arg:
        await settings.remove_me_value(update, arg, extra)
    elif action == "metick":
        await settings.tickers_from_journal(update)
    elif action == "filt":
        await query.answer()
        await settings.show_filtered(update)
    elif action == "resc" and arg:
        await settings.rescue(update, arg)
    # ---- what I learned ----
    elif action == "lrn" and arg:
        await news.apply_learning(update, arg, extra == "y")
    elif action == "src" and arg:
        await news.turn_source_off(update, arg, extra)
    # ---- adding a whole new topic ----
    elif action == "tq":
        await topic_wizard.toggle(update, arg)
    elif action == "tok":
        await topic_wizard.create(update)
    elif action == "tno":
        await topic_wizard.cancel(update)
    else:
        await query.answer()
    return True


async def _screen(query, fn, *args):
    await query.answer()
    await fn(*args)
