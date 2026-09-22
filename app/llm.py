"""Thin Gemini wrapper: batched scoring + grounded (web-search) research."""
import json
import logging
import re
import time

from google import genai
from google.genai import types

from .config import settings

log = logging.getLogger(__name__)
_client = None


def _c():
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def extract_json(text):
    """Pull the first JSON object/array out of a model reply."""
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", text).strip()
    starts = [i for i in (t.find("["), t.find("{")) if i != -1]
    if not starts:
        return None
    s = min(starts)
    closer = "]" if t[s] == "[" else "}"
    e = t.rfind(closer)
    if e <= s:
        return None
    try:
        return json.loads(t[s:e + 1])
    except json.JSONDecodeError:
        return None


def _generate(model, contents, config, retries=2):
    for attempt in range(retries + 1):
        try:
            return _c().models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:  # 429 / transient
            if attempt == retries:
                raise
            log.warning("Gemini error (%s), retrying in 30s", exc)
            time.sleep(30)


def score_batch(label: str, profile: str, fewshot: str, items: list[dict], me: str = "") -> list[dict]:
    numbered = "\n".join(
        f'{i}. TITLE: {it["title"]}\n   SOURCE: {it["source"]}\n   SUMMARY: {it.get("summary", "")[:300]}'
        for i, it in enumerate(items))
    prompt = f"""You filter "{label}" news for ONE specific person. Be strict: most items should score below 5.

PERSON PROFILE AND RULES:
{profile}

MY SETUP (exchanges, wallets/chains, holdings, interests):
{me or "(not set)"}

RECENT FEEDBACK FROM THE PERSON (learn from it):
{fewshot}

For EACH numbered item return one element of a JSON array:
{{"idx": <int>, "score": <0-10>, "category": "<short label>",
 "action": "<concrete action the person can take, or 'none'>",
 "urgency": "<high|medium|low>", "why": "<one line: why it matters to THIS person>",
 "personal": <true if it directly affects something in MY SETUP, else false>}}
Score 7+ ONLY when there is a concrete, legitimate, time-relevant action for this person.
Paid promotions, price predictions, "X will 100x", unverified rumours and influencer shilling score 0-3.

ITEMS:
{numbered}"""
    resp = _generate(settings.gemini_score_model, prompt,
                     types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"))
    data = extract_json(resp.text)
    return data if isinstance(data, list) else []


def research(prompt: str) -> dict:
    """One grounded call with Google Search. Returns parsed JSON + source URLs."""
    tool = types.Tool(google_search=types.GoogleSearch())
    resp = _generate(settings.gemini_research_model, prompt,
                     types.GenerateContentConfig(tools=[tool], temperature=0.2))
    data = extract_json(resp.text)
    if not isinstance(data, dict):
        data = {"what_to_do": (resp.text or "")[:500], "legitimacy": "unconfirmed"}
    sources = []
    try:
        meta = resp.candidates[0].grounding_metadata
        for ch in (meta.grounding_chunks or []):
            if getattr(ch, "web", None) and ch.web.uri:
                sources.append(ch.web.uri)
    except Exception:
        pass
    data["_sources"] = sources[:5]
    return data
