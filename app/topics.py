"""What the bot can alert you about, in words instead of internal names.

An agent's "channel" is the key it submits alerts under - that is what muting acts on.
News agents submit under their topic folder ("ai"), everything else under its own name."""
from pathlib import Path

import yaml

CONFIG = Path("config/agents.yaml")
FALLBACK_LABELS = {
    "regime": "Market mood alerts",
    "guardian": "Holdings protection",
    "majors": "Discounted big coins",
    "token_scout": "New coin finds",
    "curator": "Daily summary",
    "bulletin": "Hourly bulletin",
    "reminders": "Reminders",
}
# The curator and bulletin do not submit to the cream gate - they ARE the delivery - so muting or filtering
# by it would do nothing. Keep it out of the buttons that imply otherwise.
NEVER_SUBMITS = {"curator", "bulletin"}
ALWAYS_ON = {"guardian"}            # protects money you hold; muting it would be a foot-gun


def load_agents() -> dict:
    if not CONFIG.exists():
        return {}
    return (yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}).get("agents") or {}


def channel_of(agent_name: str, cfg: dict) -> str:
    return cfg.get("topic", agent_name) if cfg.get("type") == "news" else agent_name


def label_of(agent_name: str, cfg: dict) -> str:
    return cfg.get("label") or FALLBACK_LABELS.get(cfg.get("type") or agent_name, agent_name)


def channels(agents: dict | None = None) -> list[dict]:
    """[{agent, channel, label, type, muteable}] for every enabled agent."""
    out = []
    for name, cfg in (agents if agents is not None else load_agents()).items():
        if not cfg.get("enabled", True):
            continue
        kind = cfg.get("type", name)
        out.append({"agent": name, "channel": channel_of(name, cfg), "label": label_of(name, cfg),
                    "type": kind, "muteable": kind not in ALWAYS_ON,
                    "alerts": kind not in NEVER_SUBMITS})
    return out


def alerting_channels(agents: dict | None = None) -> list[dict]:
    """Only the agents that actually send you things."""
    return [c for c in channels(agents) if c["alerts"]]


def news_channels(agents: dict | None = None) -> list[dict]:
    return [c for c in channels(agents) if c["type"] == "news"]


def label_for_channel(channel: str, agents: dict | None = None) -> str:
    for entry in channels(agents):
        if entry["channel"] == channel:
            return entry["label"]
    return channel
