import pytest

from app import me, prefs


class FakeRedis:
    """Just the handful of Redis calls the settings store uses."""
    def __init__(self):
        self.h, self.sets, self.strings = {}, {}, {}

    def hget(self, key, field):
        return self.h.get(key, {}).get(field)

    def hset(self, key, field, value):
        self.h.setdefault(key, {})[field] = str(value)

    def hdel(self, key, *fields):
        for field in fields:
            self.h.get(key, {}).pop(field, None)

    def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)

    def srem(self, key, value):
        self.sets.setdefault(key, set()).discard(value)

    def sismember(self, key, value):
        return value in self.sets.get(key, set())

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def get(self, key):
        return self.strings.get(key)

    def set(self, key, value, ex=None):
        self.strings[key] = value


@pytest.fixture
def fake(monkeypatch):
    stub = FakeRedis()
    monkeypatch.setattr(prefs, "r", stub)
    return stub


def test_empty_settings_behave_exactly_like_the_config_file(fake):
    assert prefs.threshold_for("ai", 7) == 7
    assert prefs.urgent_cap(3) == 3 and prefs.digest_hour(9) == 9
    assert prefs.quiet_hours() is None and not prefs.is_quiet_now(2)


def test_pickiness_overrides_the_threshold(fake):
    prefs.set_pickiness("ai", "strict")
    assert prefs.threshold_for("ai", 7) == 8 and prefs.pickiness("ai") == "strict"
    prefs.set_pickiness("ai", "relaxed")
    assert prefs.threshold_for("ai", 7) == 6


def test_an_unknown_pickiness_is_refused(fake):
    with pytest.raises(ValueError):
        prefs.set_pickiness("ai", "whatever")


def test_caps_stay_inside_sane_bounds(fake):
    prefs.put("urgent_cap", 99)
    assert prefs.urgent_cap(3) == prefs.MAX_URGENT_PER_DAY
    prefs.put("digest_hour", "not a number")
    assert prefs.digest_hour(9) == 9


def test_quiet_hours_wrap_past_midnight():
    assert prefs.within_quiet_hours(23, 7, 2) and prefs.within_quiet_hours(23, 7, 23)
    assert not prefs.within_quiet_hours(23, 7, 9)
    assert prefs.within_quiet_hours(13, 17, 14) and not prefs.within_quiet_hours(13, 17, 18)
    assert not prefs.within_quiet_hours(7, 7, 7)


def test_quiet_hours_round_trip(fake):
    prefs.set_quiet_hours(23, 7)
    assert prefs.quiet_hours() == (23, 7) and prefs.is_quiet_now(1)
    prefs.set_quiet_hours(None)
    assert prefs.quiet_hours() is None


def test_muting_a_category_is_case_insensitive(fake):
    prefs.set_category_muted("Funding Round", True)
    assert prefs.is_category_muted("funding round")
    prefs.set_category_muted("FUNDING ROUND", False)
    assert not prefs.is_category_muted("Funding Round")


def test_the_overlay_wins_and_the_yaml_is_never_touched(fake, monkeypatch):
    monkeypatch.setattr(me, "base_me", lambda: {"country": "India", "exchanges": ["A"]})
    assert me.load_me()["exchanges"] == ["A"]
    me.add_to_field("exchanges", "CoinDCX")
    assert me.load_me()["exchanges"] == ["A", "CoinDCX"]
    assert me.load_me()["country"] == "India"          # untouched fields still come from the file
    me.remove_from_field("exchanges", "A")
    assert me.load_me()["exchanges"] == ["CoinDCX"]


def test_adding_the_same_thing_twice_does_nothing(fake, monkeypatch):
    monkeypatch.setattr(me, "base_me", lambda: {"chains": []})
    me.add_to_field("chains", "solana")
    me.add_to_field("chains", "solana")
    assert me.load_me()["chains"] == ["solana"]


def test_me_text_is_still_plain_yaml_for_the_scorer(fake, monkeypatch):
    monkeypatch.setattr(me, "base_me", lambda: {"country": "India"})
    assert "country: India" in me.me_text()


def test_a_corrupt_overlay_is_ignored_rather_than_crashing(fake):
    fake.strings[prefs.ME_OVERLAY] = "{not json"
    assert prefs.me_overlay() == {}
