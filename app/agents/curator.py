"""CuratorAgent: the daily digest. Picks the top alerts across ALL agents (AI + crypto),
max N per topic, then drops the rest. This is the 'only the cream' guarantee."""
from .. import cream
from ..config import settings
from ..crypto import regime
from ..notifier import send


class CuratorAgent:
    kind = "curator"

    def __init__(self, name, cfg):
        self.name = name
        self.total = cfg.get("total", settings.digest_total)
        self.per_topic = cfg.get("per_topic", settings.digest_per_topic)
        self.min_priority = cfg.get("min_priority", 60)

    async def run(self):
        picks = cream.pick_digest(self.total, self.per_topic, self.min_priority)
        header = "<b>☀️ Daily radar</b>"
        try:
            header += "\n\n" + regime.format_regime(await regime.current())
        except Exception:
            pass
        header += f"\n\n{len(picks)} item(s) worth your attention today." if picks else "\n\nNothing worth your time today. 👍"
        await send(header)
        for a in picks:
            await send(a.text, cream._rows(a.buttons_json))
            cream._mark(a.id, "digest")
        cream.close_out_queue()
