"""The main menu: one registry both halves of the bot add their buttons to.

Crypto entries are registered by app/ux/flows.py, news entries by app/ux/news.py.
Nothing here knows what those buttons do - it only knows how to show them."""
import logging

from telegram import BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonCommands

from ..config import settings

log = logging.getLogger(__name__)
BUTTONS_PER_ROW = 2
_REGISTRY: dict[str, dict] = {}


def register(key: str, label: str, handler, order: int = 50,
             command: str | None = None, description: str | None = None) -> None:
    """One main-menu button. `key` is the callback id ("m:<key>") and must stay short."""
    if key in _REGISTRY:
        raise ValueError(f"menu key already registered: {key}")
    _REGISTRY[key] = {"key": key, "label": label, "handler": handler, "order": order,
                      "command": command, "description": description}


def entries() -> list[dict]:
    return sorted(_REGISTRY.values(), key=lambda e: (e["order"], e["label"]))


def handler(key: str):
    entry = _REGISTRY.get(key)
    return entry["handler"] if entry else None


def main_menu() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(e["label"], callback_data=f"m:{e['key']}") for e in entries()]
    rows = [buttons[i:i + BUTTONS_PER_ROW] for i in range(0, len(buttons), BUTTONS_PER_ROW)]
    return InlineKeyboardMarkup(rows)


def commands() -> list[tuple[str, str]]:
    """The short visible command list. Old commands still work, they are just not advertised."""
    out = [("menu", "Open the main menu")]
    for entry in entries():
        if entry["command"] and entry["command"] != "menu":
            out.append((entry["command"], entry["description"] or entry["label"]))
    return out


# A gold-and-silver-only chat sees just what answers it - the full list would all be silent there.
METALS_COMMANDS = [("start", "Your gold and silver alerts"),
                   ("alerts", "Gold and silver level alerts"),
                   ("levels", "Previous week/month/quarter/year high and low, e.g. /levels gold"),
                   ("chatid", "Show this chat's id")]


def _chat_number(chat_id: str) -> int | None:
    try:
        return int(chat_id)
    except ValueError:
        log.warning("a chat id setting has a non-numeric entry: %r", chat_id)
        return None


async def _setup_metals_chats(app) -> None:
    commands_list = [BotCommand(name, desc) for name, desc in METALS_COMMANDS]
    for chat in filter(None, map(_chat_number, settings.metals_chat_ids)):
        try:
            await app.bot.set_my_commands(commands_list, scope=BotCommandScopeChat(chat))
            await app.bot.set_chat_menu_button(chat_id=chat, menu_button=MenuButtonCommands())
        except Exception as exc:            # usually: that person has not pressed Start yet
            log.warning("could not set the menu for metals chat %s: %s", chat, exc)


def menu_text() -> str:
    return ("<b>Opportunity Radar</b>\n"
            "Tap a button, or just tell me what you want in your own words.\n"
            "<i>I only ever read public data. I never trade, sign or hold keys.</i>")


async def setup(app) -> None:
    """Register the menu so it sits next to the text box. Never fatal if Telegram is unhappy."""
    try:
        commands_list = [BotCommand(name, desc[:256]) for name, desc in commands()]
        await app.bot.set_my_commands(commands_list)
        for chat_id in settings.chat_ids:
            try:
                chat = int(chat_id)
            except ValueError:
                log.warning("TELEGRAM_CHAT_ID has a non-numeric entry: %r", chat_id)
                continue
            await app.bot.set_my_commands(commands_list, scope=BotCommandScopeChat(chat))
            await app.bot.set_chat_menu_button(chat_id=chat, menu_button=MenuButtonCommands())
        await _setup_metals_chats(app)
    except Exception:                       # a menu that failed to register must not stop the bot
        log.warning("could not register the Telegram menu", exc_info=True)
