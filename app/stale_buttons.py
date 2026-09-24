"""A button tapped while the bot was asleep or restarting arrives after Telegram's answer window.
Answering it then raises "Query is too old", which used to abort the whole tap. The spinner has
long gone by then anyway, so skip the answer and let the action itself still run."""
import logging

log = logging.getLogger(__name__)

STALE_MARKERS = ("query is too old", "query id is invalid")


def is_stale_query(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in STALE_MARKERS)


def install():
    """Make every CallbackQuery.answer() in the bot tolerate an expired query. Call once at boot."""
    from telegram import CallbackQuery
    from telegram.error import BadRequest

    original = CallbackQuery.answer
    if getattr(original, "_tolerates_stale", False):
        return

    async def answer(self, *args, **kwargs):
        try:
            return await original(self, *args, **kwargs)
        except BadRequest as exc:
            if not is_stale_query(exc):
                raise
            log.info("button tap arrived too late to answer; running it anyway")
            return False

    answer._tolerates_stale = True
    CallbackQuery.answer = answer
