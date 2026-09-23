"""RemindersAgent: sends the reminders you set with the ⏰ button, once each.

Priority 95 so a reminder you asked for is never dropped, muted or held by quiet hours."""
import logging

from .. import cream, news_store
from ..notifier import esc
from ..ux import news_cards

log = logging.getLogger(__name__)
REMINDER_PRIORITY = 95


class RemindersAgent:
    kind = "reminders"

    def __init__(self, name, cfg):
        self.name = name
        self.max_per_run = int(cfg.get("max_per_run", 10))

    async def run(self):
        due = news_store.due_reminders(self.max_per_run)
        for row in due:
            news_store.mark_reminded(row.id)          # mark first: a crash must not re-ping you
            deadline = news_cards.when(row.deadline_at)
            head = "<b>⏰ You asked me to remind you</b>"
            if deadline:
                head += f" — this closes {esc(deadline)}"
            text = head + "\n\n" + news_cards.news_card(row, row.topic)
            from .news import item_buttons
            await cream.submit(f"remind:{row.id}:{row.remind_at:%Y%m%d%H%M}", "reminders",
                               REMINDER_PRIORITY, text, item_buttons(row))
        if due:
            log.info("[reminders] sent %d", len(due))
