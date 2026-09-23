"""CuratorAgent: the daily summary. The top alerts across ALL agents, max N per topic,
then the rest are dropped. This is the 'only the cream' guarantee.
On Sundays it also tells you what it learned from your 👍/👎 that week."""
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .. import cream, learning, prefs, topics
from ..config import settings
from ..crypto import regime
from ..notifier import send
from ..ux import news_cards

SUNDAY = 6


def footer_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑 What got filtered", callback_data="n:filt"),
        InlineKeyboardButton("🕘 Change this time", callback_data="n:hour"),
    ]])


class CuratorAgent:
    kind = "curator"

    def __init__(self, name, cfg):
        self.name = name
        self.total = cfg.get("total", settings.digest_total)
        self.per_topic = cfg.get("per_topic", settings.digest_per_topic)
        self.min_priority = cfg.get("min_priority", 60)

    async def run(self):
        picks = cream.pick_digest(self.total, self.per_topic, self.min_priority)
        if not picks and not prefs.tell_me_on_quiet_days():
            cream.close_out_queue()                 # stay silent, as you asked
            return await self.weekly_learning()
        counts = {}
        for alert in picks:
            label = topics.label_for_channel(alert.topic)
            counts[label] = counts.get(label, 0) + 1
        header = news_cards.digest_header(counts)
        try:
            header += "\n\n" + regime.format_regime(await regime.current())
        except Exception:
            pass
        await send(header)
        for alert in picks:
            await send(alert.text, cream._rows(alert.buttons_json))
            cream._mark(alert.id, "digest")
        cream.close_out_queue()
        if picks:
            await send("That is everything worth your time today.", footer_buttons().inline_keyboard)
        await self.weekly_learning()

    async def weekly_learning(self):
        """Once a week: what your 👍/👎 taught the bot, with a one-tap way to apply it."""
        if datetime.now(timezone.utc).weekday() != SUNDAY:
            return
        from ..ux.news import learning_message
        for review in learning.weekly_reviews():
            text, rows = learning_message(review)
            await send(text, rows)
