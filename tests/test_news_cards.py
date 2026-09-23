import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.ux import news_cards

NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)


def item(**kw):
    base = dict(id=1, topic="ai", title="OpenAI opens a free tier", why="It runs on your stack",
                action="Join the waitlist", score=9, category="free credits", urgency="high",
                source="OpenAI", personal=True, saved=False, researched=True, research_json=None,
                deadline_at=None, india_ok=None, cost=None, url="https://x.io", action_link=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_the_card_leads_with_why_it_matters_and_what_to_do():
    text = news_cards.news_card(item(), "AI")
    assert "🤖 AI · ⭐ touches your setup" in text
    assert "Why it matters to you: It runs on your stack" in text
    assert "What to do: Join the waitlist" in text
    assert "Source: OpenAI" in text


def test_research_facts_appear_in_one_readable_line():
    row = item(deadline_at=NOW + timedelta(days=5), india_ok="available", cost="free")
    text = news_cards.news_card(row, "AI", NOW)
    assert "⏰ Closes in 5 days" in text and "Usable from India: yes" in text and "Cost: free" in text


def test_a_deadline_tomorrow_says_tomorrow():
    assert news_cards.when(NOW + timedelta(days=1), NOW) == "tomorrow"
    assert news_cards.when(NOW, NOW) == "today"
    assert news_cards.when(NOW - timedelta(days=2), NOW) == "closed"
    assert news_cards.when(None, NOW) == ""


def test_an_unconfirmed_item_says_so():
    row = item(research_json=json.dumps({"legitimacy": "unconfirmed", "evidence": "only a tweet"}))
    assert "Not confirmed yet" in news_cards.news_card(row, "AI")


def test_red_flags_are_never_hidden():
    row = item(research_json=json.dumps({"red_flags": ["Asks for your seed phrase"]}))
    assert "Asks for your seed phrase" in news_cards.news_card(row, "Airdrops")


def test_corrupt_research_does_not_break_the_card():
    assert "OpenAI opens a free tier" in news_cards.news_card(item(research_json="{broken"), "AI")


def test_titles_are_escaped_not_rendered():
    row = item(title="<b>not bold</b> & co")
    assert "&lt;b&gt;not bold&lt;/b&gt; &amp; co" in news_cards.news_card(row, "AI")


def test_deadlines_are_read_from_ordinary_english():
    assert news_cards.parse_deadline("2026-09-30", NOW).day == 30
    assert news_cards.parse_deadline("Sep 30", NOW).month == 9
    assert news_cards.parse_deadline("30 September 2026", NOW).year == 2026
    assert news_cards.parse_deadline("Jan 5", NOW).year == 2027        # already past -> next year
    assert news_cards.parse_deadline("rolling", NOW) is None
    assert news_cards.parse_deadline("Feb 30", NOW) is None


def test_the_digest_header_counts_what_is_inside():
    header = news_cards.digest_header({"AI": 2, "Crypto": 1, "Airdrops": 0})
    assert "3 things worth your time" in header and "2 AI, 1 Crypto" in header
    assert "Airdrops" not in header


def test_one_item_reads_as_one_thing():
    assert "1 thing worth your time" in news_cards.digest_header({"AI": 1})


def test_a_quiet_day_says_so_plainly():
    assert "Quiet day" in news_cards.digest_header({})


def test_the_saved_list_shows_deadlines_first():
    rows = [item(title="no deadline"), item(title="closing", deadline_at=NOW + timedelta(days=2))]
    text = news_cards.saved_list(rows, NOW)
    assert "closing" in text and "in 2 days" in text


def test_an_empty_saved_list_explains_the_button():
    assert "Tap <b>⭐ Save</b>" in news_cards.saved_list([])


def test_the_first_line_of_a_card_is_stripped_of_tags():
    assert news_cards.esc_first_line("<b>Hello</b> world\nsecond") == "Hello world"
