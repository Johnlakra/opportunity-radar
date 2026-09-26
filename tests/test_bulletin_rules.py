from types import SimpleNamespace as NS

from app import bulletin_rules as br
from app.ux import news_cards


def alert(topic, priority):
    return NS(topic=topic, priority=priority)


def test_active_hours_are_start_inclusive_end_exclusive():
    assert br.is_active(7, 7, 23) and br.is_active(22, 7, 23)
    assert not br.is_active(23, 7, 23) and not br.is_active(6, 7, 23)


def test_day_fraction_is_clamped():
    assert br.day_fraction(7, 0, 7, 23) == br.MIN_DAY_FRACTION
    assert br.day_fraction(15, 0, 7, 23) == 0.5
    assert br.day_fraction(23, 30, 7, 23) == 1.0


def test_the_bar_rises_when_the_day_runs_ahead_of_target():
    assert br.bar(65, sent_today=30, target_per_day=30, fraction=0.5) > 65


def test_the_bar_eases_when_quiet_but_never_below_the_floor():
    assert br.bar(70, sent_today=0, target_per_day=30, fraction=0.5) == 70 - br.LOOSEN_BY
    assert br.bar(65, sent_today=0, target_per_day=30, fraction=0.5) == br.FLOOR
    assert br.bar(br.FLOOR, sent_today=0, target_per_day=30, fraction=0.5) == br.FLOOR


def test_the_bar_holds_when_on_pace_and_caps_its_raise():
    assert br.bar(65, sent_today=15, target_per_day=30, fraction=0.5) == 65
    assert br.bar(65, sent_today=999, target_per_day=30, fraction=0.5) == 65 + br.MAX_RAISE


def test_pick_takes_the_best_per_topic_above_the_bar():
    alerts = [alert("ai", 90), alert("ai", 80), alert("ai", 70), alert("crypto_news", 64), alert("ai", 60)]
    picks = br.pick(alerts, per_topic=2, min_priority=65)
    assert [a.priority for a in picks["ai"]] == [90, 80]
    assert "crypto_news" not in picks


def row(n, **extra):
    base = dict(id=n, title=f"Story <{n}>", url=f"https://e.x/{n}", why="It matters", source="Src",
                action_link=None, also_sources="")
    return NS(**{**base, **extra})


def test_bulletin_numbers_stories_escapes_titles_and_names_other_outlets():
    text = news_cards.bulletin("AI", "ai", [row(1, also_sources="Decrypt,The Block"), row(2)], bar=66)
    assert "1. <b>Story &lt;1&gt;</b>" in text and "2. <b>Story &lt;2&gt;</b>" in text
    assert "+2 more sources: Decrypt, The Block" in text
    assert 'href="https://e.x/1"' in text and "66/100" in text


def test_bulletin_prefers_the_official_link_found_by_research():
    text = news_cards.bulletin("AI", "ai", [row(1, action_link="https://official.example/join")])
    assert 'href="https://official.example/join"' in text


def test_also_line_is_empty_without_other_sources():
    assert news_cards.also_line("") == ""
    assert news_cards.also_line("Decrypt") == " <i>(+1 more source: Decrypt)</i>"


def test_stats_show_modes_bar_and_budgets():
    text = news_cards.stats_card({"urgent": 1, "bulletin": 7, "dropped": 20}, 68, 30,
                        {"scoring": (120, 300), "research": (45, 40)})
    assert "1 pinged now" in text and "7 in bulletins" in text and "20 filtered out" in text
    assert "68/100" in text and "120/300" in text and "40/40" in text


def test_stats_on_an_empty_day():
    assert "Nothing yet today." in news_cards.stats_card({}, None, None, {})
