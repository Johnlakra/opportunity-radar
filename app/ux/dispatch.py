"""One door for plain text: work out what you meant, then hand it to the right screen.

Keyword routing first (free and predictable). Only when that finds nothing does one small
Gemini call get a say, and if that fails too you get the menu - never an error message."""
import logging

from .. import prefs, topics
from ..text import esc
from . import text_router

log = logging.getLogger(__name__)
LLM_INTENTS = ["today", "search", "coin", "mute", "unmute", "saved", "health", "settings", "menu"]


async def handle_text(update, text: str) -> None:
    channels = topics.channels()
    decision = text_router.classify(text, channels)
    if not await _dispatch(update, decision, channels):
        await _fallback(update, text, channels)


async def _dispatch(update, decision: dict, channels: list[dict]) -> bool:
    """False means "I could not do anything useful with this"."""
    from . import flows, news, settings, topic_wizard
    intent, arg = decision.get("intent"), decision.get("arg") or ""

    if intent == "coin":
        await flows.search(update, arg[:100])
    elif intent == "today":
        await news.show_today(update, arg or None)
    elif intent == "search":
        return await news.show_search(update, arg)
    elif intent in ("mute", "unmute"):
        prefs.set_topic_muted(arg, intent == "mute")
        state = "off" if intent == "mute" else "on"
        await flows.say(update, f"🔔 <b>{esc(topics.label_for_channel(arg))}</b> is now {state}.")
        await settings.show_topics(update)
    elif intent == "picky":
        prefs.set_pickiness(arg, decision.get("level", "normal"))
        await flows.say(update, f"🎚 I will be {esc(decision.get('level'))} about "
                                f"<b>{esc(topics.label_for_channel(arg))}</b> from the next run.")
    elif intent == "remind_last":
        await news.remind_last(update)
    elif intent == "saved":
        await news.cmd_saved(update, None)
    elif intent == "health":
        await news.cmd_health(update, None)
    elif intent == "settings":
        await settings.cmd_settings(update, None)
    elif intent == "filtered":
        await settings.show_filtered(update)
    elif intent == "mood":
        await flows.cmd_mood(update, None)
    elif intent == "new_topic":
        await topic_wizard.start(update, arg)
    else:
        return False
    return True


async def _fallback(update, text: str, channels: list[dict]) -> None:
    from . import flows, menu
    from ..llm import intent as ask_llm
    import asyncio
    guess = None
    try:
        guess = await asyncio.to_thread(ask_llm, text, LLM_INTENTS, [c["channel"] for c in channels])
    except Exception:                       # the menu is always a safe answer
        guess = None
    if guess and guess.get("intent") != "menu" and await _dispatch(update, guess, channels):
        return
    await flows.say(update, "I am not sure what you meant. Here is everything I can do:",
                    menu.main_menu())
