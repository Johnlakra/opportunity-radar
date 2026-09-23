"""What the bot noticed about your taste, and what it proposes to do about it.

Proposals are plain sentences appended to a topic's profile.md - only ever appended, never
rewritten, so the safety language in every profile stays exactly where it is. Nothing is
applied without you tapping Apply."""
import json
import logging
from pathlib import Path

from . import prefs, topics
from .redis_client import r

log = logging.getLogger(__name__)
TOPICS_DIR = Path("topics")
MIN_VOTES = 3                    # one bad day is not a pattern
MAX_PROPOSALS = 3
MAX_PROFILE_LINES = 60
PROPOSAL_KEY = "learn:proposal:{}"
PROPOSAL_TTL = 8 * 86400


def _sorted_by(counts: dict, index: int) -> list[tuple[str, list]]:
    return sorted(counts.items(), key=lambda kv: -kv[1][index])


def propose(tally: dict) -> list[str]:
    """Plain-English profile lines, each backed by at least MIN_VOTES consistent votes."""
    out = []
    for name, (up, down) in _sorted_by(tally.get("categories", {}), 0):
        if up >= MIN_VOTES and down == 0:
            out.append(f"Score higher: {name} items — I keep saying yes to these.")
    for name, (up, down) in _sorted_by(tally.get("categories", {}), 1):
        if down >= MIN_VOTES and up == 0:
            out.append(f"Score lower: {name} items — I keep saying no to these.")
    return out[:MAX_PROPOSALS]


def weak_sources(tally: dict) -> list[str]:
    return [name for name, (up, down) in tally.get("sources", {}).items()
            if down >= MIN_VOTES and up == 0]


def review(topic: str, days: int = 7) -> dict:
    from . import feedback          # imported here so the analysis above stays database-free
    tally = feedback.tally(topic, days)
    return {"topic": topic, "votes": tally["total"], "lines": propose(tally),
            "weak_sources": weak_sources(tally)}


def store_proposal(review_data: dict) -> None:
    r.set(PROPOSAL_KEY.format(review_data["topic"]), json.dumps(review_data), ex=PROPOSAL_TTL)


def load_proposal(topic: str) -> dict | None:
    raw = r.get(PROPOSAL_KEY.format(topic))
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return None


def profile_path(topic: str) -> Path:
    return TOPICS_DIR / topic / "profile.md"


def apply(topic: str) -> tuple[bool, str]:
    """Append the stored lines to the topic profile, after keeping a backup."""
    proposal = load_proposal(topic)
    if not proposal or not proposal.get("lines"):
        return False, "There is nothing waiting to be applied."
    path = profile_path(topic)
    if not path.exists():
        return False, "That topic no longer has a profile file."
    current = path.read_text(encoding="utf-8")
    lines = [line for line in proposal["lines"] if line not in current]
    if not lines:
        return False, "Those notes are already in the profile."
    if len(current.splitlines()) + len(lines) + 2 > MAX_PROFILE_LINES:
        return False, "That profile is already long — tidy it by hand first."
    path.with_suffix(".md.bak").write_text(current, encoding="utf-8")
    path.write_text(current.rstrip() + "\n\n## Learned from your feedback\n"
                    + "\n".join(f"- {line}" for line in lines) + "\n", encoding="utf-8")
    r.delete(PROPOSAL_KEY.format(topic))
    return True, f"Applied {len(lines)} note(s) to the {topic} profile. The old one is kept as a backup."


def weekly_reviews(days: int = 7) -> list[dict]:
    out = []
    for entry in topics.news_channels():
        data = review(entry["channel"], days)
        data["label"] = entry["label"]
        if data["lines"] or data["weak_sources"]:
            store_proposal(data)
            out.append(data)
    return out


def turn_source_off(topic: str, name: str) -> str:
    prefs.set_source_off(topic, name, True)
    return f"{name} is switched off for {topic}. It stays in sources.yaml, so you can turn it back on."
