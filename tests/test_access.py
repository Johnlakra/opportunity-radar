"""Who the bot answers. Getting this wrong either locks you out or lets strangers in."""
import pytest

from app.config import Settings


def settings_with(chat_id: str, metals: str = "") -> Settings:
    return Settings(telegram_chat_id=chat_id, telegram_metals_chat_id=metals, _env_file=None)


def test_one_id_still_works_exactly_as_before():
    s = settings_with("123456789")
    assert s.chat_ids == ["123456789"]
    assert s.may_use("123456789") and s.may_use(123456789)


def test_two_people_can_both_use_it():
    s = settings_with("111,222")
    assert s.chat_ids == ["111", "222"]
    assert s.may_use(111) and s.may_use("222")


def test_spaces_around_the_comma_are_forgiven():
    assert settings_with(" 111 , 222 ,").chat_ids == ["111", "222"]


def test_everyone_else_is_refused():
    s = settings_with("111,222")
    for stranger in ("333", 333, "", "11", "1110", None):
        assert not s.may_use(stranger)


def test_no_chat_id_configured_means_nobody():
    s = settings_with("")
    assert s.chat_ids == [] and not s.may_use("111")


def test_a_near_miss_is_not_a_match():
    """String containment would let 11 in on a list of 111 - it must be an exact id."""
    assert not settings_with("111").may_use("1")
    assert not settings_with("111,222").may_use("11")


@pytest.mark.parametrize("raw,expected", [("111", 1), ("111,222", 2), ("111,222,333", 3)])
def test_the_list_grows_with_the_commas(raw, expected):
    assert len(settings_with(raw).chat_ids) == expected


# ---------------- the metals-only guest ----------------
def test_a_metals_guest_gets_alerts_but_not_the_bot():
    s = settings_with("111", metals="222")
    assert s.may_use("111") and s.may_see_metals("111")       # you get everything
    assert s.may_see_metals("222") and not s.may_use("222")   # he gets gold and silver only


def test_the_level_audience_is_both_of_you():
    assert settings_with("111", metals="222").level_chat_ids == ["111", "222"]


def test_several_guests_are_fine():
    s = settings_with("111", metals="222, 333")
    assert s.metals_chat_ids == ["222", "333"]
    assert all(s.may_see_metals(c) and not s.may_use(c) for c in ("222", "333"))


def test_listing_yourself_as_a_guest_does_not_demote_you():
    """A copy-paste mistake must not quietly cut your own access down to metals."""
    s = settings_with("111", metals="111,222")
    assert s.metals_chat_ids == ["222"] and s.may_use("111")
    assert s.level_chat_ids.count("111") == 1                 # and you are not alerted twice


def test_no_guest_configured_changes_nothing():
    s = settings_with("111")
    assert s.metals_chat_ids == [] and s.level_chat_ids == ["111"]
    assert not s.may_see_metals("222")


def test_a_stranger_is_refused_by_both_doors():
    s = settings_with("111", metals="222")
    assert not s.may_use("333") and not s.may_see_metals("333")
