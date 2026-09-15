"""BMS Africa SMS: what is sent, how failures and the limit behave, delivery by polling, and a key kept out of sight.

Every BMS call here is mocked: BMS has no sandbox, so a real call is a charged message."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from app.config import get_settings
from app.services import bms_deliveries, notifications, phone_proof, sms_bms
from app.services.citizen_reports import NotificationChannel
from app.services.sms import DailyBudget, SmsError, SmsLimitReached, SmsNotConfigured
from app.services.sms_bms import BmsSms

KEY = "bms-key-8f3a"
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
SENT = {"status": "success", "code": "2000", "message": "messages sent successfully",
        "summary": {"_id": "A59CCB70-662D", "type": "API QUICK SMS", "total_sent": 1, "contacts": 1, "total_rejected": 0,
                    "numbers_sent": ["0241234567"], "credit_used": 1, "credit_left": 1483}}


def _provider(handler: Any, limit: int = 50) -> BmsSms:
    return BmsSms(KEY, "Nokware", DailyBudget(limit), client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_a_message_goes_plain_to_one_local_number_with_the_key_as_bms_asks() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=SENT)

    provider = _provider(handler)
    assert provider.send("+233241234567", "We’ll message you") == "A59CCB70-662D"
    request = seen[0]
    assert request.url.path == "/api/sms/quick" and request.url.params["key"] == KEY
    assert json.loads(request.content) == {"recipient": ["0241234567"], "sender": "Nokware", "message": "We'll message you",
                                           "is_schedule": False, "schedule_date": ""}
    assert provider.name == "bms" and provider.delivers  # no sandbox: accepted means sent


@pytest.mark.parametrize("response", [
    httpx.Response(401, json={"status": "error", "message": f"Invalid API key {KEY} for https://api.mnotify.com/api/sms/quick?key={KEY}"}),
    httpx.Response(200, json={"status": "error", "code": "1005", "message": "Insufficient balance for 233241234567"}),
    httpx.Response(200, json={**SENT, "summary": {**SENT["summary"], "total_sent": 0, "total_rejected": 1}}),
    httpx.Response(502, text="Bad gateway"),
])
def test_a_refusal_raises_without_the_key_or_the_number_and_gives_the_page_back(response: httpx.Response) -> None:
    provider = _provider(lambda r: response, limit=1)
    with pytest.raises(SmsError) as refused:
        provider.send("+233241234567", "Hello there")
    assert KEY not in str(refused.value) and "233241234567" not in str(refused.value)
    provider.budget.take(1, NOW.date())  # the page came back


def test_an_unreachable_gateway_names_the_error_type_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout(f"timed out reaching {request.url}", request=request)

    with pytest.raises(SmsError, match=r"^BMS couldn't be reached \(ConnectTimeout\)\.$") as failed:
        _provider(handler).send("+233241234567", "Hello there")
    assert KEY not in str(failed.value)


def test_the_daily_limit_holds_on_bms_too() -> None:
    provider = _provider(lambda r: httpx.Response(200, json=SENT), limit=2)
    provider.send("+233241234567", "a" * 200)  # two pages
    with pytest.raises(SmsLimitReached):
        provider.send("+233241234567", "short")


def test_httpx_request_log_carries_no_key(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="httpx")
    _provider(lambda r: httpx.Response(200, json=SENT)).send("+233241234567", "Hello there")
    assert "api.mnotify.com" in caplog.text and "key=[redacted]" in caplog.text and KEY not in caplog.text


def test_the_outbox_never_holds_the_key() -> None:
    provider = _provider(lambda r: httpx.Response(401, json={"status": "error", "message": f"bad key {KEY}"}))
    outcome = notifications._deliver(provider, "+233241234567", notifications.Message("submitted", "Hello there"))
    assert outcome["provider"] == "bms" and KEY not in json.dumps(outcome)


def test_delivery_status_reads_bms_report() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/campaign/A59CCB70-662D" and request.url.params["key"] == KEY
        return httpx.Response(200, json={"status": "success", "report": [{"_id": 60711577, "status": "DELIVERED"}]})

    assert _provider(handler).delivery_status("A59CCB70-662D") == "DELIVERED"
    assert _provider(lambda r: httpx.Response(200, json={"status": "success", "report": []})).delivery_status("x") is None


def test_the_poll_records_what_bms_says_and_skips_what_is_settled(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"$id": "o1", "providerMessageId": "c1"}, {"$id": "o2", "providerMessageId": "c2", "deliveryStatus": "SUBMITTED"},
            {"$id": "o3", "providerMessageId": "c3"}]
    answers = {"c1": "DELIVERED", "c2": "SUBMITTED", "c3": SmsError("BMS couldn't be reached (ReadTimeout).")}

    class Fake:
        def delivery_status(self, campaign_id: str) -> str:
            answer = answers[campaign_id]
            if isinstance(answer, Exception):
                raise answer
            return answer

    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(bms_deliveries, "unsettled", lambda now: rows)
    monkeypatch.setattr(bms_deliveries, "bms", lambda: Fake())
    monkeypatch.setattr(bms_deliveries.notifications, "record_delivery", lambda mid, status, now: recorded.append((mid, status)) or True)
    assert bms_deliveries.poll(NOW) == 1 and recorded == [("c1", "DELIVERED")]  # c2 unchanged, c3 waits for the next run


def test_only_unsettled_messages_in_the_window_are_asked_about(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[list[str]] = []

    class Listing:
        documents = [type("Row", (), {"id": i, "data": {"deliveryStatus": s}})() for i, s in (("a", None), ("b", "DELIVERED"), ("c", "SUBMITTED"))]

    class Db:
        def list_documents(self, database: str, collection: str, queries: list[str]) -> Listing:
            asked.append(queries)
            return Listing()

    monkeypatch.setattr(bms_deliveries, "get_databases", lambda: Db())
    assert [row["$id"] for row in bms_deliveries.unsettled(NOW)] == ["a", "c"]
    window = " ".join(asked[0])
    assert '"provider"' in window and (NOW - timedelta(days=2)).isoformat() in window and (NOW - timedelta(minutes=1)).isoformat() in window


def _configured(monkeypatch: pytest.MonkeyPatch, **update: Any) -> None:
    sms_bms.bms.cache_clear()
    sms_bms.bms_codes.cache_clear()
    settings = get_settings().model_copy(update=update)
    for module in (sms_bms, notifications, phone_proof):
        monkeypatch.setattr(module, "get_settings", lambda: settings)


def test_bms_needs_its_key_and_a_short_sender_and_serves_reports_and_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    _configured(monkeypatch, sms_provider="bms", bms_api_key="", bms_sender_id="Nokware")
    with pytest.raises(SmsNotConfigured):
        notifications.provider_for(NotificationChannel.SMS)
    _configured(monkeypatch, sms_provider="bms", bms_api_key="k", bms_sender_id="NokwareAccra1")
    with pytest.raises(SmsNotConfigured):
        sms_bms.bms()
    _configured(monkeypatch, sms_provider="bms", bms_api_key="k", bms_sender_id="Nokware", redis_url="")
    assert isinstance(notifications.provider_for(NotificationChannel.SMS), BmsSms)
    assert phone_proof.CODE_SENDERS["bms"]() is not sms_bms.bms()  # codes on their own daily cap
    texted: list[str] = []
    monkeypatch.setitem(phone_proof.CODE_SENDERS, "bms", lambda: type("S", (), {"send": lambda self, to, body: texted.append(body)})())
    phone_proof._text_code("+233241234567", "123456")
    assert texted == ["Your Nokware code is 123456. It lasts 15 minutes. Don't share it."]
    sms_bms.bms.cache_clear()
    sms_bms.bms_codes.cache_clear()
