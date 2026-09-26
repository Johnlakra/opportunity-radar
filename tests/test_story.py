from datetime import datetime, timedelta, timezone

from app import story

NOW = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)


def item(title, source="A", hours_old=None, summary=""):
    published = NOW - timedelta(hours=hours_old) if hours_old is not None else None
    return {"title": title, "source": source, "summary": summary, "url": f"https://x/{title}",
            "published": published}


def test_hype_and_price_predictions_are_dropped_before_scoring():
    kept, dropped = story.prefilter([item("XRP price prediction for 2027"), item("OpenAI ships GPT-6")], 24, NOW)
    assert [i["title"] for i in kept] == ["OpenAI ships GPT-6"]
    assert dropped[0][1] == "spam/hype"


def test_stale_items_are_dropped_but_undated_ones_are_kept():
    kept, dropped = story.prefilter([item("Old news about Claude models", hours_old=30),
                                     item("Undated Claude news story")], 24, NOW)
    assert [i["title"] for i in kept] == ["Undated Claude news story"]
    assert dropped[0][1] == "stale"


def test_the_same_story_from_three_outlets_becomes_one_with_the_others_named():
    items = [item("SEC approves spot Solana ETF applications", "CoinDesk"),
             item("SEC approves spot Solana ETF applications today", "Decrypt"),
             item("Spot Solana ETF applications approved by SEC", "The Block"),
             item("Coinbase launches new wallet for developers", "CoinDesk")]
    stories, merged = story.cluster(items, [])
    assert len(stories) == 2
    assert stories[0]["source"] == "CoinDesk" and stories[0]["also"] == ["Decrypt", "The Block"]
    assert len(merged) == 2


def test_clustering_does_not_mutate_the_input():
    items = [item("SEC approves spot Solana ETF applications", "CoinDesk"),
             item("SEC approves spot Solana ETF applications today", "Decrypt")]
    story.cluster(items, [])
    assert "also" not in items[0]


def test_a_story_already_covered_in_the_last_days_is_folded_away():
    stories, merged = story.cluster([item("Anthropic releases Claude 6 with longer context")],
                                    ["Anthropic releases Claude 6 with longer context window"])
    assert stories == [] and merged[0][1] == "already covered"


def test_short_headlines_are_never_merged_on_two_shared_words():
    stories, _ = story.cluster([item("Bitcoin rises"), item("Bitcoin falls")], [])
    assert len(stories) == 2


def test_keyword_fallback_is_zero_off_topic_and_never_reaches_a_ping():
    assert story.keyword_score("ai", "Local bakery opens second shop") == 0
    assert story.keyword_score("ai", "OpenAI launches a new model") == story.FALLBACK_MAX
    assert story.keyword_score("crypto_news", "Bitcoin steady on quiet day") == story.FALLBACK_BASE
    assert story.keyword_score("unknown_topic", "Anything at all") == story.FALLBACK_BASE
