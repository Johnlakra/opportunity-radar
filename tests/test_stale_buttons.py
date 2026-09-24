import pytest

from app.stale_buttons import is_stale_query


def test_telegrams_expired_button_error_is_recognised():
    err = Exception("Query is too old and response timeout expired or query id is invalid")
    assert is_stale_query(err)


def test_other_errors_are_not_swallowed():
    assert not is_stale_query(Exception("Message is not modified"))
    assert not is_stale_query(ValueError("boom"))


def test_answering_an_expired_button_does_not_stop_the_action():
    telegram = pytest.importorskip("telegram")
    import asyncio

    from app import stale_buttons

    async def expired(self, *args, **kwargs):
        raise telegram.error.BadRequest("Query is too old and response timeout expired or query id is invalid")

    original = telegram.CallbackQuery.answer
    try:
        telegram.CallbackQuery.answer = expired
        stale_buttons.install()
        query = telegram.CallbackQuery("1", telegram.User(1, "a", False), "inst")
        assert asyncio.run(query.answer()) is False
    finally:
        telegram.CallbackQuery.answer = original
