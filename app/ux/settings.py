"""🎛 Alerts & Topics — every setting as a button, in plain English.

Everything is stored in Redis (app/prefs.py). config/me.yaml and config/agents.yaml are
never rewritten, so what you typed by hand stays exactly as you typed it."""
from telegram import InlineKeyboardButton

from .. import me as me_module
from .. import news_store, prefs, topics
from ..config import settings as env
from ..text import esc
from . import menu, news_cards
from .flows import keyboard, say, set_state

# The vocabulary of the settings lives in app/prefs.py, next to what each one does.
PICKY_WORDS, QUIET_CHOICES = prefs.PICKY_WORDS, prefs.QUIET_CHOICES
ME_FIELDS, HOURS = prefs.ME_FIELDS, prefs.DIGEST_HOURS


# ---------------- main screen ----------------
async def cmd_settings(update, ctx):
    window = prefs.quiet_hours()
    quiet = f"{window[0]}:00 – {window[1]}:00" if window else "off"
    lines = ["<b>🎛 Alerts &amp; topics</b>",
             f"Instant pings: up to {prefs.urgent_cap(env.urgent_daily_cap)} a day",
             f"Daily summary: {prefs.digest_hour(env.digest_hour)}:00",
             f"Quiet hours: {esc(quiet)}",
             f"On quiet days: {'tell me' if prefs.tell_me_on_quiet_days() else 'stay silent'}"]
    muted = prefs.muted_topics()
    if muted:
        lines.append("Off right now: " + esc(", ".join(sorted(topics.label_for_channel(m) for m in muted))))
    if prefs.muted_categories():
        lines.append("Muted kinds: " + esc(", ".join(sorted(prefs.muted_categories()))[:120]))
    rows = [[InlineKeyboardButton("🔔 Topics on/off", callback_data="n:tog"),
             InlineKeyboardButton("🎚 How picky?", callback_data="n:pk")],
            [InlineKeyboardButton("📣 Pings per day", callback_data="n:cap"),
             InlineKeyboardButton("🕘 Summary time", callback_data="n:hour")],
            [InlineKeyboardButton("🌙 Quiet hours", callback_data="n:quiet"),
             InlineKeyboardButton("🙋 My setup", callback_data="n:me")],
            [InlineKeyboardButton("🗑 What got filtered", callback_data="n:filt")]]
    await say(update, "\n".join(lines), keyboard(rows))


# ---------------- topics on/off ----------------
async def show_topics(update):
    rows = []
    for entry in topics.alerting_channels():
        if not entry["muteable"]:
            continue
        on = not prefs.is_topic_muted(entry["channel"])
        rows.append([InlineKeyboardButton(("🔔 " if on else "🔇 ") + entry["label"],
                                          callback_data=f"n:tog:{entry['channel']}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="n:set")])
    await say(update, "<b>🔔 Topics</b>\nTap to turn a topic off or on.\n"
                      "<i>Alerts that protect coins you hold always come through.</i>", keyboard(rows))


async def toggle_topic(update, channel: str):
    muted = prefs.is_topic_muted(channel)
    prefs.set_topic_muted(channel, not muted)
    await update.callback_query.answer(
        f"{topics.label_for_channel(channel)}: {'on' if muted else 'off'}")
    await show_topics(update)


# ---------------- how picky ----------------
async def show_pickiness(update, topic: str | None = None):
    if not topic:
        rows = [[InlineKeyboardButton(f"{e['label']} — {PICKY_WORDS[prefs.pickiness(e['channel'])]}"[:40],
                                      callback_data=f"n:pk:{e['channel']}")]
                for e in topics.news_channels()]
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="n:set")])
        return await say(update, "<b>🎚 How picky should I be?</b>\nPick a topic to change it.",
                         keyboard(rows))
    rows = [[InlineKeyboardButton(("• " if prefs.pickiness(topic) == level else "") + words,
                                  callback_data=f"n:pk:{topic}:{level}")]
            for level, words in PICKY_WORDS.items()]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="n:pk")])
    await say(update, f"<b>{esc(topics.label_for_channel(topic))}</b>\n"
                      "Strict means fewer, better items. Relaxed means more of them.", keyboard(rows))


async def set_pickiness(update, topic: str, level: str):
    try:
        prefs.set_pickiness(topic, level)
    except ValueError:
        return await update.callback_query.answer("Unknown setting.")
    await update.callback_query.answer(f"{topics.label_for_channel(topic)}: {level}")
    await show_pickiness(update, topic)


# ---------------- pings, summary time, quiet hours ----------------
async def show_cap(update):
    current = prefs.urgent_cap(env.urgent_daily_cap)
    rows = [[InlineKeyboardButton(("• " if n == current else "") + (f"{n} a day" if n else "none"),
                                  callback_data=f"n:cap:{n}")]
            for n in range(0, prefs.MAX_URGENT_PER_DAY + 1)]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="n:set")])
    await say(update, "<b>📣 Instant pings</b>\nHow many times a day may I interrupt you?\n"
                      "<i>Everything else waits for the daily summary. Alerts about coins you "
                      "hold always come through.</i>", keyboard(rows))


async def show_hour(update):
    current = prefs.digest_hour(env.digest_hour)
    rows = [[InlineKeyboardButton(("• " if h == current else "") + f"{h}:00", callback_data=f"n:hour:{h}")]
            for h in HOURS]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="n:set")])
    await say(update, "<b>🕘 Daily summary</b>\nWhen should it arrive? "
                      f"<i>({esc(env.timezone)})</i>", keyboard(rows))


async def show_quiet(update):
    window = prefs.quiet_hours()
    current = "off"
    for code, (_, hours) in QUIET_CHOICES.items():
        if hours and window == hours:
            current = code
    rows = [[InlineKeyboardButton(("• " if code == current else "") + words,
                                  callback_data=f"n:quiet:{code}")]
            for code, (words, _) in QUIET_CHOICES.items()]
    rows.append([InlineKeyboardButton(
        ("🔔 " if prefs.tell_me_on_quiet_days() else "🔕 ") + "Tell me on quiet days",
        callback_data="n:qday")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="n:set")])
    await say(update, "<b>🌙 Quiet hours</b>\nPings wait until morning during these hours.\n"
                      "<i>Alerts about coins you hold still come through.</i>", keyboard(rows))


async def set_simple(update, field: str, raw: str):
    """One of the number settings: pings per day or summary hour."""
    if not raw.isdigit():
        return await update.callback_query.answer("Unknown setting.")
    if field == "cap":
        prefs.put("urgent_cap", int(raw))
        await update.callback_query.answer(f"Up to {prefs.urgent_cap(env.urgent_daily_cap)} a day")
        return await show_cap(update)
    prefs.put("digest_hour", int(raw))
    await update.callback_query.answer(f"Summary at {prefs.digest_hour(env.digest_hour)}:00")
    await show_hour(update)


async def set_quiet(update, code: str):
    choice = QUIET_CHOICES.get(code)
    if not choice:
        return await update.callback_query.answer("Unknown setting.")
    prefs.set_quiet_hours(*(choice[1] or (None,)))
    await update.callback_query.answer(f"Quiet hours: {choice[0]}")
    await show_quiet(update)


async def toggle_quiet_day(update):
    prefs.set_quiet_day_notice(not prefs.tell_me_on_quiet_days())
    await update.callback_query.answer("On quiet days: "
                                       + ("tell me" if prefs.tell_me_on_quiet_days() else "stay silent"))
    await show_quiet(update)


# ---------------- my setup ----------------
async def show_me(update, field: str | None = None):
    me = me_module.load_me()
    if not field:
        lines = ["<b>🙋 My setup</b>", "The scorer uses this to decide what matters to you."]
        rows = []
        for key, label in ME_FIELDS:
            values = me.get(key) or []
            lines.append(f"· <b>{esc(label)}</b>: {esc(', '.join(map(str, values))[:80]) or '—'}")
            rows.append([InlineKeyboardButton(f"✏️ {label}", callback_data=f"n:me:{key}")])
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="n:set")])
        return await say(update, "\n".join(lines), keyboard(rows))
    label = dict(ME_FIELDS).get(field, field)
    values = list(me.get(field) or [])
    rows = [[InlineKeyboardButton(f"🗑 {value}"[:40], callback_data=f"n:merm:{field}:{i}")]
            for i, value in enumerate(values[:10])]
    rows.append([InlineKeyboardButton("➕ Add", callback_data=f"n:mead:{field}")])
    if field == "holding_tickers":
        rows.append([InlineKeyboardButton("📒 Use the coins in my journal", callback_data="n:metick")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="n:me")])
    await say(update, f"<b>{esc(label)}</b>\nTap one to remove it, or add another.", keyboard(rows))


async def ask_me_value(update, field: str):
    set_state(update.effective_chat.id, mode=f"me:{field}")
    label = dict(ME_FIELDS).get(field, field)
    await say(update, f"Type what you want to add to <b>{esc(label)}</b>, or /menu to stop.")


async def save_me_value(update, field: str, value: str):
    me_module.add_to_field(field, value[:60])
    await say(update, f"Added <b>{esc(value[:60])}</b>.")
    await show_me(update, field)


async def remove_me_value(update, field: str, index: str):
    values = list(me_module.load_me().get(field) or [])
    if index.isdigit() and int(index) < len(values):
        me_module.remove_from_field(field, values[int(index)])
        await update.callback_query.answer("Removed")
    else:
        await update.callback_query.answer()
    await show_me(update, field)


async def tickers_from_journal(update):
    from ..journal import holdings_symbols
    symbols = holdings_symbols()
    if not symbols:
        return await update.callback_query.answer("Your journal is empty.")
    me_module.set_field("holding_tickers", symbols)
    await update.callback_query.answer(f"Using {len(symbols)} from your journal")
    await show_me(update, "holding_tickers")


# ---------------- what got filtered ----------------
async def show_filtered(update):
    rows = news_store.dropped()
    if not rows:
        return await say(update, "Nothing has been filtered out recently.",
                         keyboard([[InlineKeyboardButton("⬅️ Back", callback_data="n:set")]]))
    await say(update, "<b>🗑 What got filtered</b>\nBelow the bar, or from a topic you muted. "
                      "Tap 👍 on anything I should have sent.")
    for alert in rows:
        first = news_cards.esc_first_line(alert.text)
        await say(update, f"[{alert.priority}] {first}",
                  keyboard([[InlineKeyboardButton("👍 Rescue this", callback_data=f"n:resc:{alert.id}")]]))


async def rescue(update, alert_id: str):
    alert = news_store.get_alert(int(alert_id)) if alert_id.isdigit() else None
    if not alert:
        return await update.callback_query.answer("That one is gone.")
    if alert.key.startswith("news:"):
        from ..feedback import record_item_vote
        record_item_vote(int(alert.key.split(":")[1]), "up")
    await update.callback_query.answer("Sending it — and I will remember you liked it.")
    from .. import cream
    await say(update, alert.text, keyboard(cream._rows(alert.buttons_json)))


menu.register("set", "🎛 Alerts & Topics", cmd_settings, order=70,
              command="settings", description="Alerts, topics and your setup")
