"""Arkesel SMS: what a message costs, what is sent, and how failures and the daily limit behave."""

import json
from datetime import date, datetime
from typing import Any

import httpx
import pytest

from app.config import get_settings
from app.services import notifications, sms
from app.services.citizen_reports import NotificationChannel, NotificationEvent, NotificationStatus
from app.services.report_taxonomy import TOPICS, Category
from app.services.sms import ArkeselSms, DailyBudget, SmsError, SmsLimitReached, SmsNotConfigured
from app.services.sms_text import is_gsm7, pages, plain
from app.teams import RECIPIENT_NAMES, short_name
from app.teams import RECIPIENT_NAMES

SITE = "https://nokware.tstitagency.com"  # where Nokware will be deployed (PUBLIC_SITE_URL)
TODAY = date(2026, 9, 14)


def test_pages_follow_gsm7_and_typography_is_made_plain() -> None:
    assert pages("a" * 160) == 1 and pages("a" * 161) == 2 and pages("a" * 306) == 2 and pages("a" * 307) == 3
    assert pages("€" * 80) == 1 and pages("€" * 81) == 2  # an extended character takes two
    assert pages("We’ll" + "a" * 70) == 2  # one curly apostrophe: UCS-2, 70 a page
    assert plain("We’ll — see “it”…") == "We'll - see \"it\"..." and is_gsm7(plain("· ‘x’"))


def _cases() -> list[dict[str, Any]]:
    """A case for every topic citizens can get messages about, and one with the two longest office names."""
    longest = sorted(RECIPIENT_NAMES, key=lambda team: len(RECIPIENT_NAMES[team]))[-2:]
    everyday = [t for t in TOPICS if t.category != Category.PERSONAL_SAFETY]
    cases = [{"reference": "K7QM-4TXP", "category": t.category.value, "topic": t.id, "recipients": list(t.recipients)} for t in everyday]
    return [*cases, {"reference": "K7QM-4TXP", "category": "civic_service", "topic": "roads", "recipients": longest},
            {"reference": "K7QM-4TXP", "category": "public_safety", "topic": "public_crime", "recipients": longest},
            {"reference": "K7QM-4TXP", "category": "personal_safety", "topic": "abuse", "recipients": longest}]


def test_every_message_fits_one_plain_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notifications, "get_settings", lambda: get_settings().model_copy(update={"public_site_url": SITE}))
    for case in _cases():
        for event in NotificationEvent:
            for variant in (case, {**case, "escalatedAt": "2026-09-13T10:00:00+00:00"}):
                message = notifications.compose(event, variant)
                allowed = 2 if message.template == "submitted_emergency" else 1  # an emergency's numbers
                assert is_gsm7(message.body) and pages(message.body) <= allowed, (len(message.body), message.body)


def test_names_give_way_to_a_count_only_when_they_would_not_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notifications, "get_settings", lambda: get_settings().model_copy(update={"public_site_url": SITE}))
    works = notifications.compose(NotificationEvent.SUBMITTED, {"reference": "K7QM-4TXP", "recipients": ["dept-works"]})
    assert "is with Works Department." in works.body
    # A report goes to one office: with the deployed address, every office's full name fits one page beside the link.
    for team in RECIPIENT_NAMES:
        for event in (NotificationEvent.SUBMITTED, NotificationEvent.RESOLVED):
            body = notifications.compose(event, {"reference": "K7QM-4TXP", "recipients": [team]}).body
            assert short_name(team) in body and pages(body) == 1 and "nokware.tstitagency.com/report/status" in body, body
            assert "https://" not in body and "K7QM-4TXP/" not in body  # no scheme, and the reference never in the address
    crowded = {"reference": "K7QM-4TXP", "recipients": ["dept-social-welfare", "dept-disaster-management", "agency-gnfs"]}
    assert pages(notifications.compose(NotificationEvent.SUBMITTED, crowded).body) == 1  # the count stands in if ever needed


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _provider(handler: Any, sandbox: bool = True, limit: int = 50) -> ArkeselSms:
    return ArkeselSms(api_key="key-1", sender="Nokware", sandbox=sandbox, budget=DailyBudget(limit), client=_client(handler))


def test_a_message_goes_plain_to_one_recipient_with_the_key_in_the_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "success", "data": [{"recipient": "233241234567", "id": "m-1"}]})

    provider = _provider(handler)
    assert provider.send("+233241234567", "We’ll message you") == "m-1"
    request = seen[0]
    assert str(request.url) == sms.SEND_URL and request.headers["api-key"] == "key-1"
    assert json.loads(request.content) == {"sender": "Nokware", "message": "We'll message you", "recipients": ["233241234567"], "sandbox": True}
    assert provider.name == "arkesel-sandbox" and not provider.delivers


def test_either_response_shape_gives_the_message_id() -> None:
    single = _provider(lambda r: httpx.Response(200, json={"status": "success", "data": {"id": "m-2", "credits_used": 1}}))
    assert single.send("+233241234567", "Hello there") == "m-2"


@pytest.mark.parametrize("response", [
    httpx.Response(422, json={"status": "error", "message": "Invalid recipient 233241234567"}),
    httpx.Response(200, json={"status": "error", "message": "Insufficient balance"}),
    httpx.Response(502, text="Bad gateway"),
])
def test_a_refusal_raises_without_the_number_or_the_key(response: httpx.Response) -> None:
    with pytest.raises(SmsError) as refused:
        _provider(lambda r: response).send("+233241234567", "Hello there")
    assert "233241234567" not in str(refused.value) and "key-1" not in str(refused.value)


def test_an_unreachable_gateway_raises_a_readable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(SmsError, match="couldn't be reached"):
        _provider(handler).send("+233241234567", "Hello there")


def test_the_daily_limit_counts_pages_and_only_outside_the_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sms, "utc_now", lambda: datetime(2026, 9, 14, 9, 0))

    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success", "data": [{"id": "m"}]})

    live = _provider(ok, sandbox=False, limit=3)
    live.send("+233241234567", "a" * 200)  # two pages
    with pytest.raises(SmsLimitReached):
        live.send("+233241234567", "a" * 200)
    live.send("+233241234567", "short")  # the third page still fits
    sandbox = _provider(ok, sandbox=True, limit=1)
    for _ in range(3):
        sandbox.send("+233241234567", "a" * 200)


def test_a_failed_send_gives_its_pages_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sms, "utc_now", lambda: datetime(2026, 9, 14, 9, 0))
    budget = DailyBudget(2)
    failing = ArkeselSms("key-1", "Nokware", sandbox=False, budget=budget, client=_client(lambda r: httpx.Response(500, json={})))
    for _ in range(3):
        with pytest.raises(SmsError):
            failing.send("+233241234567", "Hello there")
    budget.take(2, TODAY)  # nothing was spent


def test_arkesel_needs_its_key_and_a_sender_id_of_at_most_eleven_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    def configured(**update: Any) -> None:
        sms.arkesel.cache_clear()
        monkeypatch.setattr(sms, "get_settings", lambda: get_settings().model_copy(update=update))

    configured(arkesel_api_key="", arkesel_sender_id="Nokware")
    with pytest.raises(SmsNotConfigured):
        sms.arkesel()
    configured(arkesel_api_key="k", arkesel_sender_id="NokwareAccra1")
    with pytest.raises(SmsNotConfigured):
        sms.arkesel()
    configured(arkesel_api_key="k", arkesel_sender_id="Nokware", arkesel_sandbox=True)
    assert sms.arkesel().sandbox
    sms.arkesel.cache_clear()


def test_a_sandbox_send_is_recorded_as_not_delivered() -> None:
    provider = _provider(lambda r: httpx.Response(200, json={"status": "success", "data": [{"id": "m-3"}]}))
    outcome = notifications._deliver(provider, "+233241234567", notifications.Message("submitted", "Hello there"))
    assert outcome["status"] == NotificationStatus.SENT.value and outcome["provider"] == "arkesel-sandbox"
    note = notifications._history_note(NotificationEvent.SUBMITTED, NotificationChannel.SMS, outcome, provider)
    assert note == "Submission SMS accepted by the provider's sandbox, not delivered."


def test_an_emergencys_received_message_carries_numbers_to_try_but_personal_safety_never_does() -> None:
    fire = notifications.compose(NotificationEvent.SUBMITTED, {"reference": "K7QM-4TXP", "category": "public_safety",
                                                                "topic": "fire", "recipients": ["agency-gnfs"]})
    assert "Fire: 112, 192. Ambulance: 193, 0501 614 877." in fire.body and "/contacts" in fire.body
    private = notifications.compose(NotificationEvent.SUBMITTED, {"reference": "M3RD-8WQA", "category": "personal_safety",
                                                                   "topic": "abuse", "recipients": ["agency-police"]})
    assert private.body == "Nokware: reference M3RD-8WQA received."
