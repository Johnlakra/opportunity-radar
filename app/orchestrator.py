"""The orchestrator: builds agents from config/agents.yaml and runs each one on its own
schedule, with its own lock and error isolation (one failing agent never blocks the others)."""
import asyncio
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .agents.curator import CuratorAgent
from .agents.guardian import GuardianAgent
from .agents.majors import MajorsAgent
from .agents.news import NewsAgent
from .agents.regime_agent import RegimeAgent
from .agents.reminders import RemindersAgent
from .agents.token_scout import TokenScoutAgent
from .db import init_db
from .redis_client import r

log = logging.getLogger(__name__)
TYPES = {"news": NewsAgent, "regime": RegimeAgent, "token_scout": TokenScoutAgent,
         "majors": MajorsAgent, "guardian": GuardianAgent, "curator": CuratorAgent,
         "reminders": RemindersAgent}


def load_config() -> dict:
    return yaml.safe_load(Path("config/agents.yaml").read_text(encoding="utf-8"))["agents"]


def build_agents() -> dict:
    agents = {}
    for name, cfg in load_config().items():
        if cfg.get("enabled", True):
            agents[name] = (TYPES[cfg["type"]](name, cfg), cfg)
    return agents


async def run_agent(name: str, agent) -> str:
    lock = f"lock:agent:{name}"
    if not r.set(lock, 1, nx=True, ex=3 * 3600):
        return "skipped (already running)"
    started = datetime.now(timezone.utc)
    try:
        await agent.run()
        status = "ok"
    except Exception as exc:
        log.error("agent %s failed:\n%s", name, traceback.format_exc())
        status = f"error: {exc}"[:200]
    finally:
        r.delete(lock)
    secs = (datetime.now(timezone.utc) - started).total_seconds()
    r.hset("agents:status", name, f"{started:%Y-%m-%d %H:%M} UTC · {status} · {secs:.0f}s")
    return status


def run_sync(name: str, agent):
    init_db()
    asyncio.run(run_agent(name, agent))
