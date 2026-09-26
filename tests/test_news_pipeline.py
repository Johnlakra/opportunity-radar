"""The news run end to end on SQLite, with Redis and Gemini faked:
research or scoring failing must never cost you the story, and the bulletin must pick it up."""
import asyncio
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("sqlmodel")
pytest.importorskip("telegram")

from app import cream, prefs                                       # noqa: E402
from app.agents import bulletin, news                               # noqa: E402
from app.config import settings                                     # noqa: E402
from app.db import init_db, session                                 # noqa: E402
from app.models import Alert, Item                                  # noqa: E402
from sqlmodel import select                                          # noqa: E402


class FakeRedis:
    def __init__(self):
        self.kv, self.hashes, self.sets = {}, defaultdict(dict), defaultdict(set)

    def get(self, k): return self.kv.get(k)
    def set(self, k, v, ex=None, nx=False):
        if nx and k in self.kv:
            return False
        self.kv[k] = v
        return True
    def incr(self, k): return self.incrby(k, 1)
    def incrby(self, k, n):
        self.kv[k] = int(self.kv.get(k, 0)) + n
        return self.kv[k]
    def expire(self, k, s): return True
    def delete(self, *ks): return sum(self.kv.pop(k, None) is not None for k in ks)
    def mget(self, ks): return [self.kv.get(k) for k in ks]
    def pipeline(self): return self
    def execute(self): return []
    def hget(self, h, f): return self.hashes[h].get(f)
    def hset(self, h, f=None, v=None, mapping=None):
        self.hashes[h].update(mapping or {f: v})
    def hincrby(self, h, f, n): self.hashes[h][f] = int(self.hashes[h].get(f, 0)) + n
    def hgetall(self, h): return dict(self.hashes[h])
    def sismember(self, s, v): return v in self.sets[s]
    def smembers(self, s): return set(self.sets[s])


STORIES = [
    {"url": "https://a.example/1", "title": "OpenAI opens waitlist for new agent platform", "source": "OpenAI",
     "summary": "", "published": None},
    {"url": "https://b.example/1", "title": "OpenAI opens waitlist for its new agent platform", "source": "Verge",
     "summary": "", "published": None},
    {"url": "https://c.example/1", "title": "Mistral releases small open model for phones", "source": "HF",
     "summary": "", "published": None},
]


@pytest.fixture
def world(monkeypatch):
    init_db()
    with session() as s:                    # each test starts from an empty news side
        for model in (Alert, Item):
            for row in s.exec(select(model)).all():
                s.delete(row)
        s.commit()
    fake, sent = FakeRedis(), []
    for module in (news, cream, prefs, bulletin):
        monkeypatch.setattr(module, "r", fake)
    monkeypatch.setattr("app.dedupe.r", fake)

    async def fake_send(text, rows=None, chat_ids=None):
        sent.append(text)
    monkeypatch.setattr(cream, "send", fake_send)
    monkeypatch.setattr(bulletin, "send", fake_send)
    monkeypatch.setattr(news, "build_fewshot", lambda topic: "")
    monkeypatch.setattr(news, "me_text", lambda: "")
    return fake, sent


def agent(monkeypatch, stories=STORIES):
    """A real NewsAgent whose one feed returns `stories` - collect() runs for real."""
    a = news.NewsAgent("news_ai", {"topic": "ai", "label": "AI", "score_threshold": 7})

    async def feed(client, url, name):
        return stories
    monkeypatch.setattr(news, "fetch_rss", feed)
    monkeypatch.setattr(a, "sources", lambda: {"rss": [{"name": "feed", "url": "https://feed.example"}]})
    monkeypatch.setattr(a, "profile", lambda: "")
    return a


def rows(model):
    with session() as s:
        return list(s.exec(select(model)).all())


def test_research_failing_still_delivers_the_story_unconfirmed(world, monkeypatch):
    fake, sent = world
    a = agent(monkeypatch)
    monkeypatch.setattr(news, "score_batch", lambda *args, **kw: [
        {"idx": 0, "score": 8, "why": "Open now"}, {"idx": 1, "score": 6}])
    monkeypatch.setattr(news, "research", lambda prompt: (_ for _ in ()).throw(RuntimeError("429 per day")))
    asyncio.run(a.run())
    items = {i.title: i for i in rows(Item)}
    alerts = rows(Alert)
    waitlist = items["OpenAI opens waitlist for new agent platform"]
    assert waitlist.also_sources == "Verge"                 # two outlets, one story
    assert len(items) == 2
    assert [a_.key for a_ in alerts] == [f"news:{waitlist.id}"]
    assert alerts[0].priority == 70                         # unconfirmed: capped, never a ping
    assert sent == []


def test_scoring_down_falls_back_to_keywords(world, monkeypatch):
    a = agent(monkeypatch)
    monkeypatch.setattr(news, "score_batch", lambda *args, **kw: (_ for _ in ()).throw(RuntimeError("down")))
    asyncio.run(a.run())
    items, alerts = rows(Item), rows(Alert)
    assert {i.category for i in items} == {news.KEYWORD_CATEGORY}
    assert alerts and all(al.priority == news.KEYWORD_PRIORITY for al in alerts)


def test_scoring_budget_spent_skips_gemini(world, monkeypatch):
    fake, _ = world
    a = agent(monkeypatch)
    calls = []
    monkeypatch.setattr(news, "score_batch", lambda *args, **kw: calls.append(1) or [])
    monkeypatch.setattr(settings, "score_daily_cap", 0)
    asyncio.run(a.run())
    assert calls == []


def test_the_bulletin_sends_waiting_news_once(world, monkeypatch):
    fake, sent = world
    a = agent(monkeypatch)
    monkeypatch.setattr(news, "score_batch", lambda *args, **kw: [
        {"idx": 0, "score": 8, "why": "Open now"}, {"idx": 1, "score": 8, "why": "Small model"}])
    monkeypatch.setattr(news, "research", lambda prompt: {"legitimacy": "unconfirmed"})
    asyncio.run(a.run())

    noon = datetime(2026, 9, 26, 12, tzinfo=ZoneInfo(settings.timezone))
    monkeypatch.setattr(bulletin, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: noon)}))
    b = bulletin.BulletinAgent("bulletin", {"active_hours": [7, 23], "per_topic": 5, "min_priority": 65})
    asyncio.run(b.run())
    assert len(sent) == 1 and "this hour" in sent[0] and "+1 more source: Verge" in sent[0]
    assert {al.sent_mode for al in rows(Alert)} == {"bulletin"}
    asyncio.run(b.run())
    assert len(sent) == 1                                   # nothing is sent twice


def test_the_bulletin_waits_outside_active_hours(world, monkeypatch):
    _, sent = world
    night = datetime(2026, 9, 26, 2, tzinfo=ZoneInfo(settings.timezone))
    monkeypatch.setattr(bulletin, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: night)}))
    asyncio.run(bulletin.BulletinAgent("bulletin", {}).run())
    assert sent == []
