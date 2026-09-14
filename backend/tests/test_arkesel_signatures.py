"""Arkesel's signed delivery reports: verified exactly as its guide specifies, and recorded on the outbox."""

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.routes import channels
from app.services import notifications, sms
from app.services.arkesel_signatures import canonical_json, extract_signatures, verify_webhook

SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
OLD_SECRET = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
NOW = 1783425600


def sign(params: dict[str, Any], timestamp: int = NOW, secret: str = SECRET) -> str:
    message = f"{timestamp}.{canonical_json(params)}".encode()
    return "v1=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def test_the_canonical_string_is_the_guides_own_example() -> None:
    assert f"{NOW}.{canonical_json({'status': 'DELIVERED', 'sms_id': 'abc123'})}" == '1783425600.{"sms_id":"abc123","status":"DELIVERED"}'


def test_canonical_json_sorts_every_level_keeps_lists_and_escapes_like_php() -> None:
    payload = {"b": {"z": 1, "a": [3, 1, {"y": 2, "x": 1}]}, "a": "https://x.org/p", "n": "Ésa 😀"}
    assert canonical_json(payload) == (
        '{"a":"https://x.org/p","b":{"a":[3,1,{"x":1,"y":2}],"z":1},"n":"\\u00c9sa \\ud83d\\ude00"}'
    )


def test_a_valid_signature_is_accepted_and_anything_changed_is_refused() -> None:
    params = {"sms_id": "abc123", "status": "DELIVERED"}
    header = sign(params)
    assert verify_webhook(params, str(NOW), header, SECRET, now=NOW)
    assert not verify_webhook({**params, "status": "FAILED"}, str(NOW), header, SECRET, now=NOW)
    assert not verify_webhook(params, str(NOW + 1), header, SECRET, now=NOW)  # the timestamp is signed too
    assert not verify_webhook(params, str(NOW), sign(params, secret="another"), SECRET, now=NOW)
    assert not verify_webhook(params, str(NOW), header.replace("v1=", "v2="), SECRET, now=NOW)
    assert not verify_webhook(params, str(NOW), "", SECRET, now=NOW)


def test_during_rotation_either_signature_may_match() -> None:
    params = {"sms_id": "abc123", "status": "DELIVERED"}
    both = f"{sign(params, secret=OLD_SECRET)}, {sign(params)}"
    assert extract_signatures(both)[0] != extract_signatures(both)[1]
    assert verify_webhook(params, str(NOW), both, SECRET, now=NOW)  # the current secret is the second value
    assert verify_webhook(params, str(NOW), both, OLD_SECRET, now=NOW)


@pytest.mark.parametrize("timestamp", ["1783425299", "1783425901", "", "17834x5600", "１７８３"])
def test_a_timestamp_more_than_five_minutes_off_or_not_a_number_is_refused(timestamp: str) -> None:
    params = {"sms_id": "abc123"}
    header = sign(params, int(timestamp)) if timestamp.isascii() and timestamp.isdigit() else sign(params)
    assert not verify_webhook(params, timestamp, header, SECRET, now=NOW)


def test_without_a_secret_nothing_is_trusted() -> None:
    params = {"sms_id": "abc123"}
    assert not verify_webhook(params, str(NOW), sign(params, secret=""), "", now=NOW)


def _configured(monkeypatch: pytest.MonkeyPatch, **update: Any) -> None:
    settings = get_settings().model_copy(update=update)
    monkeypatch.setattr(channels, "get_settings", lambda: settings)
    monkeypatch.setattr(sms, "get_settings", lambda: settings)


def test_the_route_records_a_signed_report_and_refuses_the_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    _configured(monkeypatch, arkesel_webhook_secret=SECRET)
    monkeypatch.setattr(channels, "verify_webhook", lambda *args: verify_webhook(*args, now=NOW))
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(notifications, "record_delivery", lambda sms_id, status, now: recorded.append((sms_id, status)) or True)
    client = TestClient(app)
    params = {"sms_id": "e886136c", "status": "DELIVERED"}
    headers = {"X-Arkesel-Webhook-Timestamp": str(NOW), "X-Arkesel-Webhook-Signature": sign(params), "X-Arkesel-Webhook-Id": "w-1"}
    assert client.get("/api/channels/sms/delivery", params=params, headers=headers).json() == {"recorded": True}
    assert client.get("/api/channels/sms/delivery", params={**params, "status": "FAILED"}, headers=headers).status_code == 401
    assert client.get("/api/channels/sms/delivery", params=params).status_code == 401
    assert recorded == [("e886136c", "DELIVERED")]


def test_a_report_sets_the_outbox_rows_delivery_status(monkeypatch: pytest.MonkeyPatch) -> None:
    class Row:
        id = "n1"

    class Listing:
        def __init__(self, documents: list[Row]) -> None:
            self.documents = documents

    updates: list[dict[str, Any]] = []
    db = notifications.get_databases()
    monkeypatch.setattr(db, "list_documents", lambda *args, queries: Listing([Row()] if '"m-1"' in str(queries) else []))
    monkeypatch.setattr(db, "update_document", lambda *args: updates.append(args[3]))
    at = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    assert notifications.record_delivery("m-1", "delivered", at)
    assert notifications.record_delivery("m-1", "<b>Failed</b>", at)  # only letters survive
    assert updates == [{"deliveryStatus": "DELIVERED", "deliveredAt": at.isoformat()}, {"deliveryStatus": "BFAILEDB"}]
    assert not notifications.record_delivery("m-2", "DELIVERED", at)


def test_delivery_reports_are_asked_for_only_when_they_can_arrive_and_be_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    _configured(monkeypatch, public_api_url="https://api.example.org/", arkesel_webhook_secret=SECRET)
    assert sms.delivery_report_url() == "https://api.example.org/api/channels/sms/delivery"
    _configured(monkeypatch, public_api_url="https://api.example.org", arkesel_webhook_secret="")
    assert sms.delivery_report_url() is None
