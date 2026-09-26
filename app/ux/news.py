"""The news half of the bot: what is worth your time, what you saved, and how it is doing.

Nothing here pushes a message on its own - everything still goes through the cream gate."""
import logging
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton

from .. import cream, learning, news_store, prefs, topics
from ..agents.news import agent_for_topic, item_buttons
from ..feedback import record_item_vote
from ..redis_client import r
from ..text import esc
from . import menu, news_cards
from .flows import keyboard, say

log = logging.getLogger(__name__)
TOP_PAGE = 3
REMIND_CHOICES = {"1h": ("in an hour", timedelta(hours=1)),
                  "3h": ("in three hours", timedelta(hours=3)),
                  "1d": ("tomorrow", timedelta(days=1))}
HEALTH_STALE_MIN = 180


# ---------------- 📰 Today's Best ----------------
TOPICS_PER_ROW = 3


def _topic_rows(active: str | None) -> list[list]:
    buttons = [InlineKeyboardButton(("• " if not active else "") + "Everything",
                                    callback_data="n:top::0")]
    for entry in topics.alerting_channels():
        mark = "• " if entry["channel"] == active else ""
        buttons.append(InlineKeyboardButton(mark + entry["label"][:18],
                                            callback_data=f"n:top:{entry['channel']}:0"))
    return [buttons[i:i + TOPICS_PER_ROW] for i in range(0, len(buttons), TOPICS_PER_ROW)]


async def show_today(update, channel: str | None = None, offset: int = 0):
    rows = news_store.top_recent(TOP_PAGE, channel or None, offset)
    where = topics.label_for_channel(channel) if channel else "everything"
    if not rows:
        text = (f"<b>📰 Today's best — {esc(where)}</b>\nNothing has cleared the bar recently. "
                "That is the filter doing its job.")
        return await say(update, text, keyboard(_topic_rows(channel)))
    await say(update, f"<b>📰 Today's best — {esc(where)}</b>\nTop {len(rows)} right now.")
    for alert in rows:
        await say(update, alert.text, keyboard(cream._rows(alert.buttons_json)))
    more = [InlineKeyboardButton(f"Show {TOP_PAGE} more", callback_data=f"n:top:{channel or ''}:{offset + TOP_PAGE}")]
    await say(update, "Pick a topic, or see more:", keyboard(_topic_rows(channel) + [more]))


async def cmd_today(update, ctx):
    await show_today(update)


# ---------------- 🗂 Saved & Deadlines ----------------
async def cmd_saved(update, ctx):
    rows = news_store.saved_and_deadlines()
    await say(update, news_cards.saved_list(rows))
    for row in rows[:6]:
        buttons = [[InlineKeyboardButton("🔗 Open", url=row.action_link or row.url),
                    InlineKeyboardButton("✅ Done", callback_data=f"n:done:{row.id}"),
                    InlineKeyboardButton("🗑 Remove", callback_data=f"n:drop:{row.id}")]]
        await say(update, news_cards.news_card(row, topics.label_for_channel(row.topic)),
                  keyboard(buttons))


# ---------------- 🩺 Bot Health ----------------
def _freshness(status: str) -> str:
    if not status:
        return "🟡 has not run yet"
    if "error" in status:
        return "🔴 " + status
    when = status.split(" UTC")[0]
    try:
        ran = datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return "🟢 " + status
    minutes = (datetime.now(timezone.utc) - ran).total_seconds() / 60
    ago = f"{minutes:.0f} min ago" if minutes < 120 else f"{minutes / 60:.0f} hours ago"
    return ("🟢 " if minutes < HEALTH_STALE_MIN else "🟡 ") + f"last run {ago}"


async def cmd_health(update, ctx):
    status = r.hgetall("agents:status") or {}
    lines = ["<b>🩺 Bot health</b>"]
    rows = []
    for entry in topics.channels():
        lines.append(f"· <b>{esc(entry['label'])}</b> — {esc(_freshness(status.get(entry['agent'], '')))}")
        broken = [name for name, fails in (r.hgetall(f"health:{entry['channel']}") or {}).items()
                  if str(fails) not in ("0", "")]
        if broken:
            lines.append(f"   ⚠️ feeds failing: {esc(', '.join(sorted(broken))[:120])}")
        rows.append([InlineKeyboardButton(f"▶️ Run {entry['label']}"[:28],
                                          callback_data=f"n:run:{entry['agent']}")])
    muted = prefs.muted_topics()
    if muted:
        lines.append("Muted: " + esc(", ".join(sorted(topics.label_for_channel(m) for m in muted))))
    rows.append([InlineKeyboardButton("📊 Today's stats", callback_data="n:stats")])
    await say(update, "\n".join(lines), keyboard(rows))


async def show_stats(update):
    from ..news_stats import today_text
    await say(update, today_text())


async def run_agent_now(update, agent_name: str):
    from ..orchestrator import build_agents, run_agent
    agents = build_agents()
    if agent_name not in agents:
        return await say(update, "I do not have an agent by that name any more.")
    await say(update, f"Running {esc(topics.label_for_channel(agent_name))} now…")
    status = await run_agent(agent_name, agents[agent_name][0])
    await say(update, f"Done: {esc(status)}")


# ---------------- item actions ----------------
async def save_item(update, item_id: int, saved: bool = True):
    row = news_store.set_saved(item_id, saved)
    if not row:
        return await update.callback_query.answer("That item is gone.")
    await update.callback_query.answer("⭐ Saved" if saved else "Removed from saved")
    try:
        await update.callback_query.edit_message_text(
            news_cards.news_card(row, topics.label_for_channel(row.topic)), parse_mode="HTML",
            disable_web_page_preview=True, reply_markup=keyboard(cream._rows(item_buttons(row))))
    except Exception:
        pass


async def ask_remind(update, item_id: int):
    row = news_store.get_item(item_id)
    if not row:
        return await update.callback_query.answer("That item is gone.")
    buttons = [[InlineKeyboardButton(label.capitalize(), callback_data=f"n:rem:{item_id}:{code}")]
               for code, (label, _) in REMIND_CHOICES.items()]
    if row.deadline_at:
        buttons.append([InlineKeyboardButton("The day before it closes", callback_data=f"n:rem:{item_id}:dl")])
    await update.callback_query.answer()
    await say(update, "When should I nudge you?", keyboard(buttons))


async def set_remind(update, item_id: int, code: str):
    row = news_store.get_item(item_id)
    if not row:
        return await update.callback_query.answer("That item is gone.")
    now = datetime.now(timezone.utc)
    if code == "dl" and row.deadline_at:
        when, label = row.deadline_at - timedelta(days=1), "the day before it closes"
    elif code in REMIND_CHOICES:
        label, delta = REMIND_CHOICES[code]
        when = now + delta
    else:
        return await update.callback_query.answer("I did not understand that choice.")
    if when <= now:
        when, label = now + timedelta(hours=1), "in an hour"
    news_store.set_reminder(item_id, when)
    await update.callback_query.answer(f"⏰ I will remind you {label}")


async def less_like_this(update, item_id: int):
    row = news_store.get_item(item_id)
    record_item_vote(item_id, "down")
    await update.callback_query.answer("Noted — fewer of these.")
    if row and row.category:
        buttons = [[InlineKeyboardButton(f"Yes, mute “{row.category[:20]}”", callback_data=f"n:mcat:{item_id}:y"),
                    InlineKeyboardButton("No, just this one", callback_data="n:mcat:0:n")]]
        await say(update, f"Should I stop sending <b>{esc(row.category)}</b> items altogether?",
                  keyboard(buttons))


async def mute_category(update, item_id: int, yes: bool):
    if not yes:
        return await update.callback_query.answer("Okay — only this one.")
    row = news_store.get_item(item_id)
    if row and row.category:
        prefs.set_category_muted(row.category, True)
        await update.callback_query.answer(f"Muted: {row.category[:30]}")
    else:
        await update.callback_query.answer()


async def tell_me_more(update, item_id: int):
    row = news_store.get_item(item_id)
    if not row:
        return await update.callback_query.answer("That item is gone.")
    await update.callback_query.answer("Looking it up…")
    label = topics.label_for_channel(row.topic)
    if row.researched:
        import json
        info = json.loads(row.research_json) if row.research_json else {}
        return await say(update, news_cards.news_card(row, label) + "\n" + news_cards.research_addition(info))
    agent = agent_for_topic(row.topic)
    if not agent:
        return await say(update, "I cannot look this one up — its topic is no longer configured.")
    import asyncio
    found, reason = await asyncio.to_thread(agent.research_one, row)
    if reason == "budget":
        return await say(update, "I have used today's free research budget. Try again tomorrow — "
                                 "the daily limit is what keeps this bot free.")
    if not found:
        return await say(update, "That lookup did not come back with anything. Try again later.")
    import json
    info = json.loads(found.research_json) if found.research_json else {}
    await say(update, news_cards.news_card(found, label) + "\n" + news_cards.research_addition(info),
              keyboard(cream._rows(item_buttons(found))))


async def show_search(update, query: str):
    rows = news_store.search(query)
    if not rows:
        return await say(update, f"Nothing I have seen matches <b>{esc(query)}</b>.\n"
                                 "I only search what already came through the filter.")
    await say(update, f"<b>🔎 {len(rows)} match(es) for “{esc(query)}”</b>")
    for row in rows[:5]:
        await say(update, news_cards.news_card(row, topics.label_for_channel(row.topic)),
                  keyboard(cream._rows(item_buttons(row))))


async def remind_last(update):
    """"remind me about the last one tomorrow" - the most recent thing you were shown."""
    rows = news_store.top_recent(1)
    item_id = None
    if rows and rows[0].key.startswith("news:"):
        item_id = int(rows[0].key.split(":")[1])
    if not item_id:
        return await say(update, "I am not sure which one you mean — open it and tap ⏰ Remind me.")
    news_store.set_reminder(item_id, datetime.now(timezone.utc) + timedelta(days=1))
    await say(update, "⏰ I will remind you about the last one tomorrow.")


# ---------------- 🧠 what I learned ----------------
def learning_message(review: dict) -> tuple[str, list]:
    label = review.get("label") or review["topic"]
    lines = [f"<b>🧠 What I learned about {esc(label)}</b>",
             f"From {review['votes']} 👍/👎 this week."]
    rows = []
    if review["lines"]:
        lines.append("I could add these notes to how I score it:")
        lines += [f"· {esc(line)}" for line in review["lines"]]
        rows.append([InlineKeyboardButton("Apply ✅", callback_data=f"n:lrn:{review['topic']}:y"),
                     InlineKeyboardButton("Skip", callback_data=f"n:lrn:{review['topic']}:n")])
    for index, name in enumerate(review.get("weak_sources", [])[:3]):
        lines.append(f"· <b>{esc(name)}</b> only ever gets 👎.")
        rows.append([InlineKeyboardButton(f"Turn off {name}"[:30],
                                          callback_data=f"n:src:{review['topic']}:{index}")])
    return "\n".join(lines), rows


async def show_learning(update, reviews: list[dict] | None = None):
    reviews = reviews if reviews is not None else learning.weekly_reviews()
    if not reviews:
        return await say(update, "<b>🧠 What I learned</b>\nNot enough 👍/👎 yet to spot a pattern. "
                                 "Keep tapping them on the cards.")
    for review in reviews:
        text, rows = learning_message(review)
        await say(update, text, keyboard(rows))


async def apply_learning(update, topic: str, yes: bool):
    if not yes:
        return await update.callback_query.answer("Left as it is.")
    applied, message = learning.apply(topic)
    await update.callback_query.answer("Updated" if applied else "Nothing to apply")
    await say(update, esc(message))


async def turn_source_off(update, topic: str, index: str):
    proposal = learning.load_proposal(topic) or {}
    weak = proposal.get("weak_sources") or []
    if not index.isdigit() or int(index) >= len(weak):
        return await update.callback_query.answer("That suggestion has expired.")
    await update.callback_query.answer("Switched off")
    await say(update, esc(learning.turn_source_off(topic, weak[int(index)])))


menu.register("today", "📰 Today's Best", cmd_today, order=20,
              command="today", description="What is worth your time")
menu.register("saved", "🗂 Saved & Deadlines", cmd_saved, order=45,
              command="saved", description="Saved items and deadlines")
menu.register("health", "🩺 Bot Health", cmd_health, order=80,
              command="health", description="Is everything running?")
