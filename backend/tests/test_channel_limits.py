"""The per-number caps that guard SMS credits: what is counted, and what the number that refuses comes from."""

from types import SimpleNamespace

import fakeredis
import pytest

from app.config import get_settings
from app.services import channel_limits, notifications

PHONE = "+233507387216"
NOON = 1757937600.0  # a fixed second, so every call in a test falls in the same day's window


@pytest.fixture
def counts(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    server = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(channel_limits, "get_redis", lambda: server)
    return server


def _charged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_limits, "sms_is_charged", lambda: True)


def _limit(monkeypatch: pytest.MonkeyPatch, answers: int) -> None:
    settings = get_settings().model_copy(update={"sms_answer_daily_limit": answers})
    monkeypatch.setattr(channel_limits, "get_settings", lambda: settings)


def test_an_answer_the_log_provider_never_sent_leaves_the_cap_untouched(counts: fakeredis.FakeRedis) -> None:
    """SMS_PROVIDER=log, as the test settings and a test pass both set it: nothing is handed to anyone, so a
    resident who dials all afternoon is never refused and no count is kept to refuse them tomorrow."""
    for _ in range(channel_limits.SMS_ANSWERS.allowed + 3):
        assert channel_limits.SMS_ANSWERS.allow(PHONE, NOON)
    assert counts.keys("nokware:limit:sms-answers:*") == []


def test_the_answer_cap_is_read_from_the_setting(counts: fakeredis.FakeRedis, monkeypatch: pytest.MonkeyPatch) -> None:
    """And raising it for a test pass takes effect on the next question, with nothing cleared away first."""
    assert channel_limits.SMS_ANSWERS.allowed == get_settings().sms_answer_daily_limit
    _charged(monkeypatch)
    _limit(monkeypatch, 2)
    assert [channel_limits.SMS_ANSWERS.allow(PHONE, NOON) for _ in range(3)] == [True, True, False]
    _limit(monkeypatch, 4)
    assert channel_limits.SMS_ANSWERS.allow(PHONE, NOON)
    assert counts.keys("nokware:limit:sms-answers:*")  # the same day's count, kept and counted on from


def test_only_a_provider_that_delivers_is_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not notifications.sms_is_charged()  # SMS_PROVIDER=log
    for delivers in (False, True):  # Arkesel's sandbox accepts without delivering or charging; BMS always charges
        monkeypatch.setattr(notifications, "provider_for", lambda channel, d=delivers: SimpleNamespace(name="p", delivers=d))
        assert notifications.sms_is_charged() is delivers
