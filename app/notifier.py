import html
import logging
import re

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from .config import settings
from .text import esc                      # re-exported: callers still do `from .notifier import esc`

log = logging.getLogger(__name__)
MAX_TEXT = 4000
_TAG = re.compile(r"<[^>]+>")
# What Telegram's refusals mean in practice - so the log says what to fix, not just "Forbidden".
HINTS = {"forbidden": "that person must open the bot and press Start (or add the bot to the group)",
         "chat not found": "the chat id is wrong - send /start to the bot from that chat to see its id",
         "can't parse entities": "sent again as plain text"}

__all__ = ["esc", "btn", "send"]


def btn(text, url=None, data=None):
    if url:
        if not str(url).startswith(("http://", "https://")):
            return None
        return InlineKeyboardButton(text, url=url)
    return InlineKeyboardButton(text, callback_data=data)


async def send(text: str, rows: list[list] | None = None, chat_ids: list[str] | None = None):
    """One message, to whoever it is for. chat_ids=None means the people with full access,
    which is what every existing caller wants. One blocked chat never stops the others."""
    targets = chat_ids if chat_ids is not None else settings.chat_ids
    if not settings.telegram_bot_token or not targets:
        log.info("[telegram disabled] %s", text[:200])
        return
    markup = None
    if rows:
        rows = [[b for b in row if b] for row in rows]
        markup = InlineKeyboardMarkup([row for row in rows if row])
    async with Bot(settings.telegram_bot_token) as bot:
        for chat_id in targets:
            try:
                await bot.send_message(chat_id=chat_id, text=text[:MAX_TEXT], parse_mode="HTML",
                                       reply_markup=markup, disable_web_page_preview=True)
            except Exception as exc:
                log.warning("could not reach chat %s: %s%s", chat_id, exc, hint(exc))
                if "can't parse entities" in str(exc).lower():
                    await _send_plain(bot, chat_id, text, markup)


def hint(exc: BaseException) -> str:
    text = str(exc).lower()
    return next((f" ({advice})" for marker, advice in HINTS.items() if marker in text), "")


async def _send_plain(bot, chat_id, text: str, markup):
    """A cut-off or odd tag must not cost you the message: strip the formatting and send it."""
    try:
        await bot.send_message(chat_id=chat_id, text=html.unescape(_TAG.sub("", text))[:MAX_TEXT],
                               reply_markup=markup, disable_web_page_preview=True)
    except Exception as exc:
        log.warning("plain-text retry to chat %s failed too: %s", chat_id, exc)
