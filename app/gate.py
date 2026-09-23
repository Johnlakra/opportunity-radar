"""The cream gate's decision rule, on its own so it can be read and tested in isolation.

  urgent  -> ping you now (still subject to the daily ping budget)
  queued  -> compete for the daily digest
  dropped -> stored for "What got filtered", never pushed
Anything at ALWAYS_DELIVER or above is protecting money you already hold: no mute, no quiet
hours and no budget may hold it back."""
URGENT_MIN = 85
ALWAYS_DELIVER = 95


def decide(priority: int, topic_muted: bool, category_muted: bool, quiet: bool) -> str:
    if priority >= ALWAYS_DELIVER:
        return "urgent"
    if topic_muted or category_muted:
        return "dropped"
    if priority < URGENT_MIN or quiet:       # quiet hours delay a ping, they never drop it
        return "queued"
    return "urgent"
