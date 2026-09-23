"""Add a whole new topic from chat: "watch hackathons".

The model only ever suggests search phrases. The slug, the folder, the profile and the config
entry are all built by app/topic_builder.py from a validated name - nothing is executed."""
import asyncio
import logging

from telegram import InlineKeyboardButton

from .. import topic_builder
from ..text import esc
from .flows import clear_state, get_state, keyboard, say, set_state

log = logging.getLogger(__name__)


async def start(update, raw_name: str):
    slug = topic_builder.slugify(raw_name)
    ok, why = topic_builder.validate(slug)
    if not ok:
        return await say(update, esc(why))
    await say(update, f"Setting up <b>{esc(topic_builder.label_of(slug))}</b> — finding good "
                      "searches for it…")
    queries = await _suggest(slug)
    set_state(update.effective_chat.id, mode="topic", slug=slug, queries=queries,
              kept=list(range(len(queries))))
    await _show(update)


async def _suggest(slug: str) -> list[str]:
    from ..llm import topic_queries
    try:
        suggested = await asyncio.to_thread(topic_queries, slug.replace("_", " "))
    except Exception:
        suggested = []
    return topic_builder.clean_queries(suggested) or topic_builder.suggest_queries(slug)


async def _show(update):
    state = get_state(update.effective_chat.id)
    queries, kept = state.get("queries", []), set(state.get("kept", []))
    rows = [[InlineKeyboardButton(("✅ " if i in kept else "⬜️ ") + query[:40],
                                  callback_data=f"n:tq:{i}")]
            for i, query in enumerate(queries)]
    rows.append([InlineKeyboardButton("Start watching", callback_data="n:tok"),
                 InlineKeyboardButton("Cancel", callback_data="n:tno")])
    await say(update, f"<b>{esc(topic_builder.label_of(state.get('slug', '')))}</b>\n"
                      "I will watch these searches. Tap any you do not want.", keyboard(rows))


async def toggle(update, index: str):
    state = get_state(update.effective_chat.id)
    if state.get("mode") != "topic" or not index.isdigit():
        return await update.callback_query.answer("That setup has expired.")
    kept = set(state.get("kept", []))
    kept.symmetric_difference_update({int(index)})
    set_state(update.effective_chat.id, **{**state, "kept": sorted(kept)})
    await update.callback_query.answer()
    await _show(update)


async def create(update):
    state = get_state(update.effective_chat.id)
    if state.get("mode") != "topic":
        return await update.callback_query.answer("That setup has expired.")
    queries = [q for i, q in enumerate(state.get("queries", [])) if i in set(state.get("kept", []))]
    if not queries:
        return await update.callback_query.answer("Keep at least one search.")
    ok, result = await asyncio.to_thread(topic_builder.create_topic, state["slug"], queries)
    clear_state(update.effective_chat.id)
    await update.callback_query.answer()
    if not ok:
        return await say(update, esc(result))
    await say(update, f"✅ Now watching <b>{esc(result)}</b>.\nIt joins the next scheduled run, and "
                      "its items go through the same filter as everything else.\n"
                      "<i>Restart the worker to pick up the new schedule.</i>")


async def cancel(update):
    clear_state(update.effective_chat.id)
    await update.callback_query.answer("Cancelled")
