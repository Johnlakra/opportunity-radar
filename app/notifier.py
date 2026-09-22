import html
import logging
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from .config import settings

log = logging.getLogger(__name__)


def esc(s) -> str:
    return html.escape(str(s)) if s not in (None, "") else ""


def btn(text, url=None, data=None):
    if url:
        if not str(url).startswith(("http://", "https://")):
            return None
        return InlineKeyboardButton(text, url=url)
    return InlineKeyboardButton(text, callback_data=data)


async def send(text: str, rows: list[list] | None = None):
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log.info("[telegram disabled] %s", text[:200])
        return
    markup = None
    if rows:
        rows = [[b for b in row if b] for row in rows]
        markup = InlineKeyboardMarkup([row for row in rows if row])
    async with Bot(settings.telegram_bot_token) as bot:
        await bot.send_message(chat_id=settings.telegram_chat_id, text=text[:4000],
                               parse_mode="HTML", reply_markup=markup,
                               disable_web_page_preview=True)
