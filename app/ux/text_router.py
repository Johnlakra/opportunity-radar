"""Understands what you typed, without you having to learn any commands.

A deterministic keyword pass first - it is free, instant and predictable. Only if that finds
nothing does the caller fall back to a single tiny LLM call, and if that fails too the bot
shows the menu instead of an error."""
import re

from ..crypto.chains import find_address

COIN_HOSTS = ("dexscreener", "birdeye", "pump.fun", "jup.ag", "solscan", "etherscan", "geckoterminal",
              "tonviewer", "tonscan", "suiscan", "tronscan", "basescan", "bscscan", "arbiscan",
              "dextools", "coingecko")
NEWS_WORDS = ("news", "anything new", "what's new", "whats new", "latest", "update on", "updates on",
              "happening", "worth my time", "today's best", "todays best")
SEARCH_PREFIXES = ("find ", "search ", "search for ", "look up ", "show me ")
STOP_WORDS = {"on", "about", "in", "the", "a", "any", "new", "me", "my", "for", "with", "of", "to",
              "is", "there", "anything", "what", "whats", "s", "please"}
MAX_COIN_WORDS = 2
MAX_COIN_CHARS = 14
NEW_TOPIC_SLUG = re.compile(r"^[a-z0-9_]{2,30}$")


def _channel_in(text: str, channels: list[dict]) -> str | None:
    """Which topic the sentence is about, by its plain-English label or its internal name."""
    for entry in sorted(channels, key=lambda e: -len(e["label"])):
        words = [entry["channel"].lower(), entry["label"].lower()]
        words += [w for w in re.split(r"[_\s]+", entry["channel"].lower()) if len(w) > 2]
        if any(re.search(rf"\b{re.escape(w)}\b", text) for w in words):
            return entry["channel"]
    return None


def _looks_like_a_coin(text: str) -> bool:
    words = text.split()
    return 0 < len(words) <= MAX_COIN_WORDS and len(text) <= MAX_COIN_CHARS


def _strip(text: str) -> str:
    return " ".join(w for w in text.split() if w not in STOP_WORDS).strip(" ?!.,")


def classify(raw: str, channels: list[dict] | None = None) -> dict:
    """-> {"intent": ..., "arg": ...}. Pure: no network, no Redis, no Telegram."""
    channels = channels or []
    text = (raw or "").strip()
    low = text.lower()
    if not low:
        return {"intent": "menu", "arg": ""}

    # 1. anything that is unmistakably a token belongs to the crypto side
    if find_address(text) or any(host in low for host in COIN_HOSTS):
        return {"intent": "coin", "arg": text}

    # 2. turning topics off and on
    if re.search(r"\b(unmute|resume|enable|turn on)\b|\bback on\b", low):
        channel = _channel_in(low, channels)
        if channel:
            return {"intent": "unmute", "arg": channel}
    if re.search(r"\b(mute|turn off|stop sending|stop|silence|disable)\b", low):
        channel = _channel_in(low, channels)
        if channel:
            return {"intent": "mute", "arg": channel}

    # 3. how picky to be
    picky = None
    if re.search(r"\b(strict|stricter|pickier|fewer|less noise)\b", low):
        picky = "strict"
    elif re.search(r"\b(relaxed|looser|less strict)\b|\b(more of|send me more|more)\s", low):
        picky = "relaxed"
    if picky:
        channel = _channel_in(low, channels)
        if channel:
            return {"intent": "picky", "arg": channel, "level": picky}

    # 4. reminders about the thing I just showed you
    if "remind" in low and re.search(r"\b(last|previous|that one|it)\b", low):
        return {"intent": "remind_last", "arg": ""}

    # 5. the screens, by name
    if re.search(r"\b(saved|deadline|deadlines|bookmarks)\b", low):
        return {"intent": "saved", "arg": ""}
    if re.search(r"\b(health|healthy|status|working|running|broken)\b", low):
        return {"intent": "health", "arg": ""}
    if re.search(r"\b(settings|alerts|preferences|quiet hours|my setup)\b", low):
        return {"intent": "settings", "arg": ""}
    if re.search(r"\b(market mood|how'?s the market|should i buy)\b", low):
        return {"intent": "mood", "arg": ""}
    if re.search(r"\b(filtered|what did you drop|rejected)\b", low):
        return {"intent": "filtered", "arg": ""}

    # 6. watch a brand-new topic
    watch = re.match(r"^(?:watch|track|follow)\s+([a-z0-9_ ]{2,30})$", low)
    if watch:
        wanted = watch.group(1).strip().replace(" ", "_")
        if not _channel_in(wanted, channels) and NEW_TOPIC_SLUG.match(wanted):
            return {"intent": "new_topic", "arg": wanted}

    # 7. "anything new on AI?"
    if any(word in low for word in NEWS_WORDS):
        return {"intent": "today", "arg": _channel_in(low, channels) or ""}

    # 8. an explicit search
    for prefix in SEARCH_PREFIXES:
        if low.startswith(prefix):
            # "find claude" means "did anything about Claude come through?" - a bare word on its
            # own still goes to the coin search, which is what people type for tokens.
            return {"intent": "search", "arg": text[len(prefix):].strip()}

    # 9. just the name of a topic
    bare = _strip(low)
    channel = _channel_in(low, channels)
    if channel and len(bare.split()) <= 2:
        return {"intent": "today", "arg": channel}

    # 10. short and coin-shaped goes to the coin search, as it always has
    if _looks_like_a_coin(text):
        return {"intent": "coin", "arg": text}
    return {"intent": "search", "arg": text}
