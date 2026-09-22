"""Generic LLM-filtered news topic. Any topic = a folder with profile.md + sources.yaml."""
import asyncio
import json
from datetime import datetime, timezone
import logging
from pathlib import Path

import httpx
import yaml
from sqlmodel import select

from ..collectors.hackernews import fetch_hn
from ..collectors.rss import fetch_rss, google_news_url
from ..config import settings
from ..db import session
from ..dedupe import is_new
from ..feedback import build_fewshot
from ..llm import research, score_batch
from ..models import Item
from ..notifier import esc
from ..redis_client import r
from .. import cream, safety
from ..me import me_text

log = logging.getLogger(__name__)
TOPICS_DIR = Path("topics")

DEFAULT_RESEARCH = """Topic: {label}
Item: "{title}"  ({url})

Use web search. Prefer OFFICIAL sources (the project's own site, blog, docs or verified account).
Return ONLY a JSON object:
{{"official_site": "<official homepage or null>",
 "action_link": "<signup / waitlist / claim / docs link on the OFFICIAL domain, or null>",
 "what_to_do": "<the single next step for the person>",
 "cost": "<free / paid / credits, or null>",
 "deadline": "<date or null>",
 "india_availability": "<available / restricted / unknown>",
 "legitimacy": "<confirmed | unconfirmed | suspicious>",
 "evidence": "<one line: which source confirmed it>",
 "red_flags": ["..."]}}
Never invent links. Use null when unknown."""


class NewsAgent:
    """Collect -> dedupe -> batch-score -> research the top few -> submit to the cream gate."""
    kind = "news"

    def __init__(self, name: str, cfg: dict):
        self.agent_name = name
        name = cfg.get("topic", name)          # topic folder under topics/
        self.name = name
        self.dir = TOPICS_DIR / name
        self.label = cfg.get("label", name)
        self.threshold = int(cfg.get("score_threshold", 7))
        self.batch = int(cfg.get("batch_size", 15))
        self.max_research = int(cfg.get("max_research_per_run", 5))
        self.weight = int(cfg.get("priority_boost", 0))   # topic-level bias, e.g. airdrops +5

    # ---- files -------------------------------------------------------------
    def profile(self) -> str:
        return (self.dir / "profile.md").read_text(encoding="utf-8")

    def research_template(self) -> str:
        p = self.dir / "research.md"
        return p.read_text(encoding="utf-8") if p.exists() else DEFAULT_RESEARCH

    def sources(self) -> dict:
        return yaml.safe_load((self.dir / "sources.yaml").read_text(encoding="utf-8")) or {}

    # ---- stages ------------------------------------------------------------
    async def collect(self) -> list[dict]:
        src = self.sources()
        async with httpx.AsyncClient() as c:
            tasks, names = [], []
            for s in src.get("rss", []):
                tasks.append(fetch_rss(c, s["url"], s["name"])); names.append(s["name"])
            for s in src.get("google_news", []):
                tasks.append(fetch_rss(c, google_news_url(s["q"]), s.get("name", "GoogleNews")))
                names.append(s.get("name", s["q"]))
            for s in src.get("hackernews", []):
                tasks.append(fetch_hn(c, s.get("tags", "story"), s.get("min_points", 5)))
                names.append(f"HN/{s.get('tags')}")
            results = await asyncio.gather(*tasks, return_exceptions=True)
        items = []
        for name, res in zip(names, results):
            if isinstance(res, Exception):
                log.warning("[%s] source %s failed: %s", self.name, name, res)
                r.hincrby(f"health:{self.name}", name, 1)
                continue
            r.hset(f"health:{self.name}", name, 0)
            items.extend(res)
        return [i for i in items if is_new(self.name, i["url"], i["title"])]

    def _score(self, rows: list[Item]):
        profile, fewshot = self.profile(), build_fewshot(self.name)
        for i in range(0, len(rows), self.batch):
            chunk = rows[i:i + self.batch]
            try:
                results = score_batch(self.label, profile, fewshot,
                                      [{"title": x.title, "source": x.source, "summary": x.summary} for x in chunk],
                                      me=me_text())
            except Exception as exc:
                log.error("[%s] scoring failed: %s", self.name, exc)
                continue
            with session() as s:
                for res in results:
                    idx = res.get("idx")
                    if not isinstance(idx, int) or idx >= len(chunk):
                        continue
                    row = s.get(Item, chunk[idx].id)
                    row.score = int(res.get("score") or 0)
                    row.category = res.get("category")
                    row.action = res.get("action")
                    row.urgency = (res.get("urgency") or "low").lower()
                    row.why = res.get("why")
                    row.personal = bool(res.get("personal"))
                    s.add(row)
                s.commit()

    def _research(self):
        with session() as s:
            hot = s.exec(select(Item).where(Item.topic == self.name, Item.score >= self.threshold,
                                            Item.researched == False)  # noqa: E712
                         .order_by(Item.score.desc()).limit(self.max_research)).all()
        done = []
        budget_key = "research:" + datetime.now(timezone.utc).strftime("%Y%m%d")
        for row in hot:
            if r.incr(budget_key) > settings.research_daily_cap:   # shared Gemini budget, all agents
                r.expire(budget_key, 2 * 86400)
                log.info("[%s] daily research budget used up", self.name)
                break
            r.expire(budget_key, 2 * 86400)
            prompt = self.research_template().format(label=self.label, title=row.title, url=row.url)
            try:
                info = research(prompt)
            except Exception as exc:
                log.error("[%s] research failed: %s", self.name, exc)
                continue
            flags = safety.check(info)
            info["red_flags"] = flags
            with session() as s:
                db = s.get(Item, row.id)
                db.researched = True
                db.research_json = json.dumps(info)
                db.flagged = bool(flags)
                db.action_link = None if flags else (info.get("action_link") or None)
                s.add(db); s.commit(); s.refresh(db)
                done.append(db)
        return done

    async def run(self):
        fresh = await self.collect()
        log.info("[%s] %d new items", self.name, len(fresh))
        if not fresh:
            return
        with session() as s:
            rows = []
            for it in fresh:
                row = Item(topic=self.name, url=it["url"], title=it["title"][:500],
                           source=it["source"], summary=it.get("summary", ""))
                s.add(row); rows.append(row)
            s.commit()
            for row in rows:
                s.refresh(row)
        await asyncio.to_thread(self._score, rows)
        researched = await asyncio.to_thread(self._research)
        for row in researched:
            await self.submit(row)

    def priority(self, row: Item) -> int:
        """Score 0-10 -> 0-100, with boosts. Only confirmed + unflagged items can reach the top."""
        if row.flagged:
            return 0
        info = json.loads(row.research_json) if row.research_json else {}
        p = (row.score or 0) * 9 + self.weight
        if row.personal:
            p += 12
        if row.urgency == "high":
            p += 6
        if str(info.get("legitimacy", "")).lower() != "confirmed":
            p = min(p, 70)          # unconfirmed never becomes urgent
        return p

    async def submit(self, row: Item):
        await cream.submit(f"news:{row.id}", self.name, self.priority(row),
                           format_item(row, self.label), item_buttons(row))


def format_item(row: Item, label: str) -> str:
    info = json.loads(row.research_json) if row.research_json else {}
    tag = "⭐ " if row.personal else ""
    lines = [f"<b>{tag}[{esc(label)}] {esc(row.title)}</b>"]
    if row.why:
        lines.append(f"<i>{esc(row.why)}</i>")
    lines.append(f"Score {row.score} · {esc(row.category)} · urgency {esc(row.urgency)}")
    step = info.get("what_to_do") or row.action
    if step and step != "none":
        lines.append(f"➡️ {esc(step)}")
    meta = []
    if info.get("cost"): meta.append(f"💰 {esc(info['cost'])}")
    if info.get("deadline"): meta.append(f"⏰ {esc(info['deadline'])}")
    if info.get("india_availability"): meta.append(f"🇮🇳 {esc(info['india_availability'])}")
    if meta:
        lines.append(" | ".join(meta))
    if info.get("legitimacy"):
        lines.append(f"Legitimacy: {esc(info['legitimacy'])} — {esc(info.get('evidence'))}")
    for f in info.get("red_flags") or []:
        lines.append(f"⚠️ {esc(f)}")
    return "\n".join(lines)


def item_buttons(row: Item) -> str:
    first = [("🔗 Official link", row.action_link, None)] if row.action_link else []
    first.append(("📰 Source", row.url, None))
    return cream.buttons(first, [("👍", None, f"v:up:{row.id}"), ("👎", None, f"v:dn:{row.id}")])
