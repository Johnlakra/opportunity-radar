"""Create a new news topic from chat, the same way the topic-creator build agent does it.

Everything written here is generated from a validated slug and plain strings. Nothing from a
model is ever executed, imported or used as a path - it only becomes a quoted YAML value."""
import json
import re
from pathlib import Path

import yaml

SLUG = re.compile(r"^[a-z0-9_]{2,30}$")
TOPICS_DIR = Path("topics")
AGENTS_FILE = Path("config/agents.yaml")
MAX_QUERIES = 5
RESERVED = {"token_scout"}

PROFILE = """# {label} — scoring profile
For one person (a developer in India). Only things they can personally act on matter.

Score 8–10: a concrete, legitimate, time-sensitive opportunity in {label} they could take today —
open applications, free access, a deadline that is still ahead.
Score 5–7: useful {label} news with no time pressure.
Score 0–4: opinion, funding news, drama, anything with no action for an individual, anything
unavailable in India.

Never score above 4 anything that asks for a seed phrase, a private key, or a payment up front.
"""


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (text or "").strip().lower()).strip("_")[:30]


def label_of(slug: str) -> str:
    return slug.replace("_", " ").title()


def suggest_queries(slug: str) -> list[str]:
    """A deterministic starting point, used when the model is unavailable or unhelpful."""
    subject = slug.replace("_", " ")
    return [f"{subject} open applications", f"{subject} deadline apply",
            f"{subject} free for developers"]


def validate(slug: str, root: Path = TOPICS_DIR) -> tuple[bool, str]:
    if not SLUG.match(slug or ""):
        return False, "A topic name can only use lowercase letters, numbers and underscores."
    if slug in RESERVED:
        return False, "That name is taken by one of the built-in agents."
    if (root / slug).exists():
        return False, "You are already watching that."
    return True, ""


def clean_queries(queries) -> list[str]:
    out = []
    for query in queries or []:
        text = " ".join(str(query).split())[:120]
        if text and text not in out:
            out.append(text)
    return out[:MAX_QUERIES]


def agent_entry(slug: str, label: str, every_min: int = 90, threshold: int = 7) -> str:
    return (f"  news_{slug}:\n"
            f"    type: news\n"
            f"    topic: {slug}\n"
            f"    label: {json.dumps(label, ensure_ascii=False)}\n"   # JSON strings are valid YAML

            f"    every_min: {every_min}\n"
            f"    score_threshold: {threshold}\n")


def create_topic(slug: str, queries: list[str], root: Path = TOPICS_DIR,
                 config: Path = AGENTS_FILE) -> tuple[bool, str]:
    ok, why = validate(slug, root)
    if not ok:
        return False, why
    queries = clean_queries(queries) or suggest_queries(slug)
    label = label_of(slug)

    before = config.read_text(encoding="utf-8") if config.exists() else ""
    entry = agent_entry(slug, label)
    after = before.rstrip("\n") + "\n" + entry
    try:
        parsed = yaml.safe_load(after) or {}
        if f"news_{slug}" not in (parsed.get("agents") or {}):
            raise ValueError("entry did not land under agents:")
    except Exception as exc:
        return False, f"I could not add that safely to the config ({exc}). Nothing was changed."

    folder = root / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "profile.md").write_text(PROFILE.format(label=label), encoding="utf-8")
    (folder / "sources.yaml").write_text(
        yaml.safe_dump({"google_news": [{"name": q[:40], "q": q} for q in queries]},
                       sort_keys=False, allow_unicode=True), encoding="utf-8")
    config.write_text(after, encoding="utf-8")
    return True, label
