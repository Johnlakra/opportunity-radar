"""Cheap, LLM-free checks that run before any Gemini call. Pure - no network, Redis or database.

  prefilter  drop hype/spam and stale items so the scorer never pays for them
  cluster    the same story from five sites becomes one item that names the other four
  keyword    a rough score for when the AI scorer is out of budget or down
"""
import re
from datetime import datetime, timezone

DEFAULT_MAX_AGE_HOURS = 24
DUP_JACCARD = 0.5                # share of title words two headlines need to be "the same story"
MIN_TOKENS_TO_CLUSTER = 3        # "Bitcoin rises" vs "Bitcoin falls" is not enough to call it one story
FALLBACK_BASE = 5
FALLBACK_MAX = 6                 # a keyword guess can reach the digest, never an instant ping

_STOP = set("the a an of to in on for and or with is are was be by at from as new how why what this that its "
            "it you your will can now just says said after over into more has have had not but about".split())
SPAM = re.compile(r"(?i)(price prediction|sponsored (article|post|content|story)|paid (post|content)|press release|giveaway|to the moon|\b100x\b|\b1000x\b|"
                  r"buy now|presale|top \d+ (coins|tokens|altcoins)|could (soar|explode)|next (bitcoin|solana))")
_AI = re.compile(r"(?i)\b(ai|a\.i\.|llm|models?|gpt|gemini|claude|llama|agents?|openai|anthropic|deepmind|"
                 r"mistral|nvidia|hugging ?face|dataset|benchmark|inference|robot\w*|waitlist|beta)\b")
_CRYPTO = re.compile(r"(?i)\b(bitcoin|btc|ethereum|eth|solana|sol|crypto\w*|stablecoins?|etf|sec|defi|tokens?|"
                     r"exchange|binance|coinbase|airdrops?|on-?chain|blockchain|wallets?|hack\w*|exploit\w*)\b")
LANE_WORDS = {"ai": _AI, "crypto_news": _CRYPTO, "airdrops": _CRYPTO}
_STRONG = re.compile(r"(?i)\b(launch\w*|releases?d?|waitlist|early access|open(s|ed)? (to|for)|free credits|"
                     r"hack\w*|exploit\w*|drained|etf|approv\w*|list(s|ing)|delist\w*|airdrop|claim|snapshot|"
                     r"acquir\w*|raises?|funding|ban\w*|regulat\w*)\b")


def tokens(title: str) -> frozenset:
    return frozenset(w for w in re.findall(r"[a-z0-9]+", (title or "").lower()) if w not in _STOP and len(w) > 2)


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / max(1, len(a | b))


def same_story(a: frozenset, b: frozenset, threshold: float = DUP_JACCARD) -> bool:
    if min(len(a), len(b)) < MIN_TOKENS_TO_CLUSTER:
        return False
    return jaccard(a, b) >= threshold


def is_spam(title: str, summary: str = "") -> bool:
    return bool(SPAM.search(f"{title} {summary}"))


def is_stale(published: datetime | None, max_age_hours: float, now: datetime | None = None) -> bool:
    """No date means we cannot tell - keep it; the URL/title dedupe still stops repeats."""
    if published is None:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - published).total_seconds() / 3600 > max_age_hours


def prefilter(items: list[dict], max_age_hours: float, now: datetime | None = None) -> tuple[list, list]:
    """-> (kept, dropped as (item, reason)). Never mutates the input dicts."""
    kept, dropped = [], []
    for it in items:
        if is_spam(it.get("title", ""), it.get("summary", "")):
            dropped.append((it, "spam/hype"))
        elif is_stale(it.get("published"), max_age_hours, now):
            dropped.append((it, "stale"))
        else:
            kept.append(it)
    return kept, dropped


def cluster(items: list[dict], recent_titles: list[str], threshold: float = DUP_JACCARD) -> tuple[list, list]:
    """Group one run's items into stories.

    recent_titles: headlines already stored in the last day or two - a match means "already covered".
    -> (stories, merged). Each story is a copy of its first item plus "also": the other sources
    that ran it. merged is [(item, reason)] for everything folded away."""
    recent = [tokens(t) for t in recent_titles]
    stories, story_tokens, merged = [], [], []
    for it in items:
        tok = tokens(it.get("title", ""))
        if any(same_story(tok, old, threshold) for old in recent):
            merged.append((it, "already covered"))
            continue
        match = next((i for i, st in enumerate(story_tokens) if same_story(tok, st, threshold)), None)
        if match is None:
            stories.append({**it, "also": []})
            story_tokens.append(tok)
            continue
        rep = stories[match]
        source = it.get("source") or ""
        if source and source != rep.get("source") and source not in rep["also"]:
            stories[match] = {**rep, "also": [*rep["also"], source]}
        merged.append((it, "same story"))
    return stories, merged


def keyword_score(topic: str, title: str, summary: str = "") -> int:
    """0 when it is off-topic for the lane, else 5-6. Used only when Gemini cannot score."""
    text = f"{title} {summary}"
    lane = LANE_WORDS.get(topic)
    if lane is not None and not lane.search(text):
        return 0
    return min(FALLBACK_MAX, FALLBACK_BASE + (1 if _STRONG.search(text) else 0))
