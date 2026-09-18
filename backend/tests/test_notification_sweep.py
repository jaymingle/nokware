"""The sweep for a "received" message a resident never got on a channel they agreed to.

Storage is an in-memory fake that reads the real Appwrite queries, so the window and the "no row in any status" rule
are the ones the sweep actually sends with. Sending is faked too: no test ever reaches a provider.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services import appwrite_client, notification_sweep, notifications
from app.services.appwrite_client import DATABASE_ID
from app.services.citizen_reports import (
    CONTACTS_COLLECTION,
    NOTIFICATIONS_COLLECTION,
    REPORTS_COLLECTION,
    NotificationChannel,
    NotificationEvent,
    NotificationStatus,
)

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
CONSENTED = {"notify": True, "phone": "+233241234567", "whatsapp": None}
BOTH = {"notify": True, "phone": "+233241234567", "whatsapp": "+233241234567"}
WHATSAPP_ONLY = {"notify": True, "phone": None, "whatsapp": "+233241234567"}
SMS, WHATSAPP = NotificationChannel.SMS, NotificationChannel.WHATSAPP


def case(case_id: str, filed: datetime) -> dict[str, Any]:
    return {"$id": case_id, "caseId": case_id, "reference": f"K7QM-{case_id.upper()}", "category": "civic_service",
            "topic": "drainage", "recipients": ["dept-works"], "createdAt": filed.isoformat()}


def outbox(case_id: str, status: NotificationStatus, event: NotificationEvent = NotificationEvent.SUBMITTED,
           written: datetime | str | None = NOW, error: str | None = None, oid: str = "",
           channel: NotificationChannel = NotificationChannel.SMS) -> dict[str, Any]:
    row = {"$id": oid or f"n-{case_id}-{event.value}-{channel.value}-{status.value}", "caseId": case_id,
           "event": event.value, "channel": channel.value, "status": status.value,
           "createdAt": written.isoformat() if isinstance(written, datetime) else written}
    return {**row, "error": error} if error is not None else row


def budget_refused(case_id: str, channel: NotificationChannel = NotificationChannel.SMS) -> dict[str, Any]:
    """What notifications._deliver writes when our own daily budget, not the provider, refused the message."""
    return outbox(case_id, NotificationStatus.FAILED, channel=channel,
                  error=f"{notifications.BUDGET_REFUSED}Today's limit of 200 SMS pages is reached.")


class Listing:
    def __init__(self, documents: list[Any]) -> None:
        self.documents = documents


class Document:
    def __init__(self, record: dict[str, Any]) -> None:
        self.id = record["$id"]
        self.data = {key: value for key, value in record.items() if not key.startswith("$")}
        self.createdat = record.get("createdAt")
        self.updatedat = record.get("createdAt")


class FakeDatabases:
    """Enough of Appwrite's listing to answer the sweep's own queries."""

    def __init__(self, collections: dict[str, list[dict[str, Any]]]) -> None:
        self.collections = collections

    def list_documents(self, database: str, collection: str, queries: list[str]) -> Listing:
        assert database == DATABASE_ID
        rows, limit = list(self.collections.get(collection, [])), 100
        for query in queries:
            parsed = json.loads(query)
            method, attribute, values = parsed["method"], parsed.get("attribute"), parsed.get("values", [])
            if method == "equal":
                rows = [row for row in rows if row.get(attribute) in values]
            elif method == "greaterThanEqual":
                rows = [row for row in rows if row.get(attribute) >= values[0]]
            elif method == "orderAsc":
                rows = sorted(rows, key=lambda row: row[attribute])
            elif method == "limit":
                limit = values[0]
            else:
                raise AssertionError(f"the sweep sent a query the fake doesn't know: {query}")
        return Listing([Document(row) for row in rows[:limit]])

    def update_document(self, database: str, collection: str, document_id: str, data: dict[str, Any]) -> None:
        assert database == DATABASE_ID
        row = next(row for row in self.collections[collection] if row["$id"] == document_id)
        row.update(data)


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, Any]]]:
    collections: dict[str, list[dict[str, Any]]] = {REPORTS_COLLECTION: [], CONTACTS_COLLECTION: [], NOTIFICATIONS_COLLECTION: []}
    fake = FakeDatabases(collections)
    monkeypatch.setattr(notification_sweep, "get_databases", lambda: fake)
    monkeypatch.setattr(appwrite_client, "get_databases", lambda: fake)  # every_record reads its own client
    monkeypatch.setattr(notifications, "get_databases", lambda: fake)  # marking a stale row writes through this one
    return collections


@pytest.fixture
def sent(storage: dict[str, list[dict[str, Any]]], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Sending the ordinary way writes the outbox row, so the fake does the same. Each entry is "case/channel": the
    channel is the point, because the sweep repairs the channels a resident is owed on and no others."""
    done: list[str] = []

    def fake_notify_channel(case: dict[str, Any], event: NotificationEvent, channel: NotificationChannel) -> None:
        done.append(f"{case['$id']}/{channel.value}")
        storage[NOTIFICATIONS_COLLECTION].append(
            outbox(case["$id"], NotificationStatus.SENT, event, channel=channel, oid=f"resend-{case['$id']}-{channel.value}")
        )

    monkeypatch.setattr(notification_sweep, "notify_channel", fake_notify_channel)
    return done


@pytest.fixture
def sms_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """What deployment does: a real SMS provider exists. WhatsApp still has none."""
    monkeypatch.setattr(notification_sweep, "provider_for", lambda channel: object() if channel == SMS else None)


def test_a_resident_who_agreed_and_got_nothing_is_sent_exactly_one_message(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/sms"]  # the row it wrote stops the next run


@pytest.mark.parametrize("status", list(NotificationStatus))
def test_a_case_whose_message_is_already_recorded_is_left_alone(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], status: NotificationStatus
) -> None:
    """A failed row means the provider was asked and may have delivered: a second message would be the duplicate.

    The queued row here was written a moment ago, so a send is still plausibly in flight and nothing is resent, and
    the `not_sent` row has no provider to send it with even now (SMS_PROVIDER=log), so it waits for one.
    """
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", status))

    assert notification_sweep.run_sweep(NOW) == [] and sent == []


def test_a_message_our_own_budget_refused_is_sent_again_and_then_only_once(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """Our daily limit means nothing reached anyone, so tomorrow's send is the same message late, not a second one."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(budget_refused("c1"))

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/sms"]  # the sent row it wrote settles the channel
    assert "+233" not in caplog.text


def test_a_message_the_provider_refused_is_never_sent_again(storage: dict[str, list[dict[str, Any]]], sent: list[str]) -> None:
    """The provider was asked and may have delivered anyway; only our own budget is safe to retry."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.FAILED, error="Arkesel refused the request (400): invalid"))

    assert notification_sweep.run_sweep(NOW) == [] and sent == []


def test_a_budget_refusal_beside_a_settled_row_leaves_the_case_alone(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """A resend is a whole message, so one settled row on the same channel holds that channel back."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(budget_refused("c1"))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT))

    assert notification_sweep.run_sweep(NOW) == [] and sent == []


def test_a_row_left_queued_past_the_grace_is_sent_once_and_the_row_is_closed(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """The process died between writing the row and updating it: nobody would ever learn whether it went."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    stuck = outbox("c1", NotificationStatus.QUEUED, written=NOW - notification_sweep.QUEUED_GRACE - timedelta(minutes=1))
    storage[NOTIFICATIONS_COLLECTION].append(stuck)

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/sms"]
    assert stuck["status"] == NotificationStatus.FAILED.value and stuck["error"].startswith(notifications.STALE_QUEUED)
    assert "+233" not in stuck["error"] and "+233" not in caplog.text
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/sms"]


def test_a_stale_row_is_retried_once_even_when_the_resend_sticks_too(
    storage: dict[str, list[dict[str, Any]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise every run would resend: one duplicate is the price, an endless stream of them is not."""
    tried: list[str] = []

    def sticking_notify(case: dict[str, Any], event: NotificationEvent, channel: NotificationChannel) -> None:
        tried.append(case["$id"])
        storage[NOTIFICATIONS_COLLECTION].append(outbox(case["$id"], NotificationStatus.QUEUED, event, oid="n-resend"))

    monkeypatch.setattr(notification_sweep, "notify_channel", sticking_notify)
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.QUEUED, written=NOW - timedelta(hours=1)))

    assert notification_sweep.run_sweep(NOW) == ["c1"] and tried == ["c1"]
    later = NOW + notification_sweep.QUEUED_GRACE + timedelta(minutes=1)  # the resend's own row is stale by now
    assert notification_sweep.run_sweep(later) == [] and tried == ["c1"]


def test_a_message_about_another_moment_is_not_the_one_that_is_owed(storage: dict[str, list[dict[str, Any]]], sent: list[str]) -> None:
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, NotificationEvent.RESOLVED))

    assert notification_sweep.run_sweep(NOW) == ["c1"]


@pytest.mark.parametrize("contact", [None, {"notify": False, "phone": "+233241234567"}, {"notify": True, "phone": None, "whatsapp": None}])
def test_without_the_resident_s_agreement_nothing_is_sent(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], contact: dict[str, Any] | None
) -> None:
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    if contact is not None:
        storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **contact})

    assert notification_sweep.run_sweep(NOW) == [] and sent == []


def test_a_report_older_than_the_window_is_left_unsent(storage: dict[str, list[dict[str, Any]]], sent: list[str]) -> None:
    """A "we received your report" a week and a half late is worse than none at all."""
    storage[REPORTS_COLLECTION].append(case("old", NOW - notification_sweep.WINDOW - timedelta(hours=1)))
    storage[REPORTS_COLLECTION].append(case("new", NOW - notification_sweep.WINDOW + timedelta(hours=1)))
    for case_id in ("old", "new"):
        storage[CONTACTS_COLLECTION].append({"$id": case_id, "caseId": case_id, **CONSENTED})

    assert notification_sweep.run_sweep(NOW) == ["new"] and sent == ["new/sms"]


def test_one_run_sends_at_most_its_cap_oldest_first(storage: dict[str, list[dict[str, Any]]], sent: list[str]) -> None:
    owed = notification_sweep.PER_RUN + 5
    for number in range(owed):
        case_id = f"c{number:02d}"
        storage[REPORTS_COLLECTION].append(case(case_id, NOW - timedelta(days=1, minutes=owed - number)))
        storage[CONTACTS_COLLECTION].append({"$id": case_id, "caseId": case_id, **CONSENTED})

    first = notification_sweep.run_sweep(NOW)
    assert first == [f"c{number:02d}" for number in range(notification_sweep.PER_RUN)]  # oldest first
    assert notification_sweep.run_sweep(NOW) == [f"c{number:02d}" for number in range(notification_sweep.PER_RUN, owed)]


def test_a_failed_send_stops_the_run_rather_than_writing_off_the_rest(
    storage: dict[str, list[dict[str, Any]]], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The daily SMS budget is recorded as a failure, and a failed row is never retried: stop while the rest can wait."""
    tried: list[str] = []

    def failing_notify(case: dict[str, Any], event: NotificationEvent, channel: NotificationChannel) -> None:
        tried.append(case["$id"])
        storage[NOTIFICATIONS_COLLECTION].append(outbox(case["$id"], NotificationStatus.FAILED, event))

    monkeypatch.setattr(notification_sweep, "notify_channel", failing_notify)
    for case_id in ("c1", "c2"):
        storage[REPORTS_COLLECTION].append(case(case_id, NOW - timedelta(hours=2)))
        storage[CONTACTS_COLLECTION].append({"$id": case_id, "caseId": case_id, **CONSENTED})

    assert notification_sweep.run_sweep(NOW) == [] and tried == ["c1"]
    assert "stopped at case c1" in caplog.text and "+233" not in caplog.text


def test_only_the_channel_the_resident_is_still_owed_on_is_sent_on(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """The SMS arrived; the WhatsApp message our own budget refused did not. Repairing the case would duplicate the
    SMS, and this sweep once did nothing at all rather than risk that."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **BOTH})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, channel=SMS))
    storage[NOTIFICATIONS_COLLECTION].append(budget_refused("c1", channel=WHATSAPP))

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/whatsapp"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/whatsapp"]


def test_each_channel_is_repaired_when_both_are_owed(storage: dict[str, list[dict[str, Any]]], sent: list[str]) -> None:
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **BOTH})

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/sms", "c1/whatsapp"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/sms", "c1/whatsapp"]


def test_a_whatsapp_message_that_went_by_sms_settles_the_whatsapp_channel(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """The resident gave a WhatsApp number only; the window was closed, so the ordinary path sent an SMS to that same
    number and recorded it on the SMS channel. That row is the WhatsApp message, and nothing more is owed."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **WHATSAPP_ONLY})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, channel=SMS))

    assert notification_sweep.run_sweep(NOW) == [] and sent == []


def test_a_row_recorded_with_no_provider_is_sent_once_one_exists_and_never_twice(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], sms_configured: None, caplog: pytest.LogCaptureFixture
) -> None:
    """A `not_sent` row is a message a resident never received. Deployment configures a provider; this sends them."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    recorded = outbox("c1", NotificationStatus.NOT_SENT)
    storage[NOTIFICATIONS_COLLECTION].append(recorded)

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/sms"]
    assert recorded["status"] == NotificationStatus.NOT_SENT.value  # what happened to this row is still what it says
    assert notifications.repaired(recorded) and "+233" not in recorded["error"] and "+233" not in caplog.text
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/sms"]


def test_a_row_recorded_with_no_provider_waits_while_its_own_channel_still_has_none(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], sms_configured: None
) -> None:
    """SMS has a provider now and WhatsApp has none: sending the WhatsApp row would only record it unsent again."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **WHATSAPP_ONLY})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.NOT_SENT, channel=WHATSAPP))

    assert notification_sweep.run_sweep(NOW) == [] and sent == []


@pytest.mark.parametrize("stamp", [None, "", "the fifteenth"])
def test_a_queued_row_whose_time_cannot_be_read_is_repaired_rather_than_left_for_ever(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], stamp: str | None
) -> None:
    """The harm chosen: one duplicate reference, against a resident who never hears because a stamp was unreadable."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    stuck = outbox("c1", NotificationStatus.QUEUED, written=stamp)
    storage[NOTIFICATIONS_COLLECTION].append(stuck)

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/sms"]
    assert stuck["error"].startswith(notifications.STALE_QUEUED)
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/sms"]


def test_a_send_the_provider_never_answered_is_made_once_more_and_only_once(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """No message ID came back, so no delivery report and no poll can ever say whether the resident got it."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    unanswered = outbox("c1", NotificationStatus.FAILED, error=f"{notifications.UNREACHABLE}Arkesel couldn't be reached (ReadTimeout).")
    storage[NOTIFICATIONS_COLLECTION].append(unanswered)

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/sms"]
    assert notifications.repaired(unanswered) and "ReadTimeout" in unanswered["error"]  # why it was repaired is kept
    assert "+233" not in unanswered["error"] and "+233" not in caplog.text
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/sms"]


def test_a_send_our_own_side_never_attempted_is_sent_again(storage: dict[str, list[dict[str, Any]]], sent: list[str]) -> None:
    """The counter the daily budget needs couldn't be reached, so nothing was handed to any provider."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(
        outbox("c1", NotificationStatus.FAILED, error=f"{notifications.NOTHING_SENT}The SMS limit can't be checked (RedisUnavailable).")
    )

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/sms"]


def test_no_stored_field_and_no_log_line_ever_holds_a_number(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], sms_configured: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Every repair the sweep can make, in one run, against the numbers the contacts hold."""
    for case_id, contact in (("c1", CONSENTED), ("c2", BOTH), ("c3", WHATSAPP_ONLY)):
        storage[REPORTS_COLLECTION].append(case(case_id, NOW - timedelta(hours=2)))
        storage[CONTACTS_COLLECTION].append({"$id": case_id, "caseId": case_id, **contact})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.NOT_SENT))
    storage[NOTIFICATIONS_COLLECTION].append(budget_refused("c2", channel=WHATSAPP))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c3", NotificationStatus.QUEUED, written=NOW - timedelta(hours=1), channel=WHATSAPP))

    assert notification_sweep.run_sweep(NOW) == ["c1", "c2", "c3"]
    written = " ".join(str(value) for row in storage[NOTIFICATIONS_COLLECTION] for value in row.values())
    assert "+233" not in written and "241234567" not in written
    assert "+233" not in caplog.text and "241234567" not in caplog.text
