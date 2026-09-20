"""The sweep for a message a resident never got on a channel they agreed to: the receipt, the start of work, the
resolution, and the acknowledged escalation alike.

Storage is an in-memory fake that reads the real Appwrite queries, so the window and the "no row in any status" rule
are the ones the sweep actually sends with. Sending is faked too: no test ever reaches a provider.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services import appwrite_client, case_history, notification_sweep, notifications
from app.services.appwrite_client import DATABASE_ID
from app.services.case_history import CaseHistoryAction
from app.services.case_workflow import CaseStatus
from app.services.citizen_reports import (
    ASSIGNMENTS_COLLECTION,
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
SUBMITTED, RESOLVED, ESCALATED = NotificationEvent.SUBMITTED, NotificationEvent.RESOLVED, NotificationEvent.ESCALATED
STARTED = NotificationEvent.STARTED


def case(case_id: str, filed: datetime, **reached: str) -> dict[str, Any]:
    """`reached` carries the case's own record of what has happened to it since: status, resolvedAt, escalatedAt."""
    return {"$id": case_id, "caseId": case_id, "reference": f"K7QM-{case_id.upper()}", "category": "civic_service",
            "topic": "drainage", "recipients": ["dept-works"], "createdAt": filed.isoformat(), **reached}


def resolved_case(case_id: str, filed: datetime, at: datetime) -> dict[str, Any]:
    return case(case_id, filed, status=CaseStatus.RESOLVED.value, resolvedAt=at.isoformat())


def escalated_case(case_id: str, filed: datetime, at: datetime) -> dict[str, Any]:
    """As the lifecycle has it: resolved first, then escalated by the citizen within the fourteen days."""
    return case(case_id, filed, status=CaseStatus.ESCALATED.value,
                resolvedAt=(at - timedelta(days=1)).isoformat(), escalatedAt=at.isoformat())


def assignment(case_id: str, started: datetime | None, recipient: str = "dept-works",
               status: str = "in_progress") -> dict[str, Any]:
    """One recipient's part of a case. `started` is its acknowledgedAt: when that recipient began work."""
    return {"$id": f"a-{case_id}-{recipient}", "caseId": case_id, "recipient": recipient, "active": True,
            "status": status, "assignedAt": None, "acknowledgedAt": started.isoformat() if started else None}


def entry(case_id: str, action: CaseHistoryAction, when: datetime) -> dict[str, Any]:
    return {"$id": f"h-{case_id}-{action.value}", "caseId": case_id, "action": action.value, "timestamp": when.isoformat()}


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
            elif method == "greaterThanEqual":  # a row with nothing in that field is outside any range, as in Appwrite
                rows = [row for row in rows if row.get(attribute) is not None and row[attribute] >= values[0]]
            elif method == "orderAsc":
                rows = sorted(rows, key=lambda row: row.get(attribute) or "")
            elif method == "limit":
                limit = values[0]
            else:
                raise AssertionError(f"the sweep sent a query the fake doesn't know: {query}")
        return Listing([Document(row) for row in rows[:limit]])

    def update_document(self, database: str, collection: str, document_id: str, data: dict[str, Any]) -> None:
        assert database == DATABASE_ID
        row = next(row for row in self.collections[collection] if row["$id"] == document_id)
        row.update(data)

    def create_document(self, database: str, collection: str, document_id: str, data: dict[str, Any]) -> Document:
        """Appwrite's own `unique()` stands for "give it an ID", so the fake gives it one: rows the repair writes
        have to be told apart from each other, and from the ones the case already had."""
        assert database == DATABASE_ID
        rows = self.collections.setdefault(collection, [])
        row = {"$id": f"{collection}-{len(rows) + 1}" if document_id == "unique()" else document_id, **data}
        rows.append(row)
        return Document(row)


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, Any]]]:
    collections: dict[str, list[dict[str, Any]]] = {
        REPORTS_COLLECTION: [], CONTACTS_COLLECTION: [], NOTIFICATIONS_COLLECTION: [],
        ASSIGNMENTS_COLLECTION: [], case_history.COLLECTION_ID: []
    }
    fake = FakeDatabases(collections)
    monkeypatch.setattr(notification_sweep, "get_databases", lambda: fake)
    monkeypatch.setattr(appwrite_client, "get_databases", lambda: fake)  # every_record reads its own client
    monkeypatch.setattr(notifications, "get_databases", lambda: fake)  # marking a stale row writes through this one
    return collections


@pytest.fixture
def sent(storage: dict[str, list[dict[str, Any]]], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Sending the ordinary way writes the outbox row, so the fake does the same. Each entry is "case/event/channel":
    both are the point, because the sweep repairs the moments and channels a resident is owed on and no others."""
    done: list[str] = []

    def fake_notify_channel(case: dict[str, Any], event: NotificationEvent, channel: NotificationChannel) -> None:
        done.append(f"{case['$id']}/{event.value}/{channel.value}")
        storage[NOTIFICATIONS_COLLECTION].append(
            outbox(case["$id"], NotificationStatus.SENT, event, channel=channel,
                   oid=f"resend-{case['$id']}-{event.value}-{channel.value}")
        )

    monkeypatch.setattr(notification_sweep, "notify_channel", fake_notify_channel)
    return done


class FakeProvider:
    """Accepts whatever it is handed, so a message that reached a provider is visible as one that was sent."""

    delivers = True

    def __init__(self, channel: NotificationChannel, sent: list[tuple[str, str, str]]) -> None:
        self.name, self.channel, self.sent = f"fake-{channel.value}", channel, sent

    def send(self, to: str, body: str) -> str:
        self.sent.append((self.channel.value, to, body))
        return f"m-{len(self.sent)}"


@pytest.fixture
def delivered(storage: dict[str, list[dict[str, Any]]], monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """The repair as it really runs, with nothing of the sending faked out but the provider itself: the sweep's own
    notify_channel, its consent check, the message it composes, the outbox row and the case-history line.

    Each entry is (channel, number, body) as the provider was asked for it — the channel a message really went out
    on, which is the thing a per-channel repair has to get right and which faking notify_channel cannot show.
    """
    done: list[tuple[str, str, str]] = []
    monkeypatch.setattr(notifications, "provider_for", lambda channel: FakeProvider(channel, done))
    monkeypatch.setattr(notification_sweep, "provider_for", lambda channel: FakeProvider(channel, done))
    monkeypatch.setattr(case_history, "get_databases", lambda: FakeDatabases(storage))
    monkeypatch.setattr(
        notifications, "contact_for",
        lambda case_id: next((row for row in storage[CONTACTS_COLLECTION] if row["caseId"] == case_id), None),
    )
    return done


def history_notes(storage: dict[str, list[dict[str, Any]]]) -> list[str]:
    return [str(row.get("note") or "") for row in storage[case_history.COLLECTION_ID]]


@pytest.fixture
def sms_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """What deployment does: a real SMS provider exists. WhatsApp still has none."""
    monkeypatch.setattr(notification_sweep, "provider_for", lambda channel: object() if channel == SMS else None)


def test_a_resident_who_agreed_and_got_nothing_is_sent_exactly_one_message(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/submitted/sms"]  # the row it wrote stops the next run


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

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/submitted/sms"]  # the sent row it wrote settles the channel
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

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/sms"]
    assert stuck["status"] == NotificationStatus.FAILED.value and stuck["error"].startswith(notifications.STALE_QUEUED)
    assert "+233" not in stuck["error"] and "+233" not in caplog.text
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/submitted/sms"]


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

    assert notification_sweep.run_sweep(NOW) == ["new"] and sent == ["new/submitted/sms"]


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

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/whatsapp"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/submitted/whatsapp"]


@pytest.mark.parametrize("failed", [SMS, WHATSAPP])
def test_a_repair_reaches_the_provider_on_the_failed_channel_alone(
    storage: dict[str, list[dict[str, Any]]], delivered: list[tuple[str, str, str]], failed: NotificationChannel
) -> None:
    """End to end, through the real notify_channel: one channel's message went, the other's never got an answer out
    of the provider. Exactly one message leaves, on the channel that still owes one. A second message on the
    channel that worked would be a duplicate of one the resident already has — and this asserts on the channel the
    provider was really asked for, not on the one the sweep meant to ask for.
    """
    worked = WHATSAPP if failed == SMS else SMS
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **BOTH})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, channel=worked))
    storage[NOTIFICATIONS_COLLECTION].append(
        outbox("c1", NotificationStatus.FAILED, channel=failed, error=f"{notifications.UNREACHABLE}ReadTimeout")
    )

    assert notification_sweep.run_sweep(NOW) == ["c1"]
    assert [channel for channel, _, _ in delivered] == [failed.value]
    assert notification_sweep.run_sweep(NOW) == [] and len(delivered) == 1  # and never a second time


def test_a_repair_of_one_channel_leaves_the_other_moments_and_channels_alone(
    storage: dict[str, list[dict[str, Any]]], delivered: list[tuple[str, str, str]]
) -> None:
    """The resolution went by both; only the receipt's WhatsApp message never did. One message, on one channel."""
    filed, done = NOW - timedelta(days=2), NOW - timedelta(hours=2)
    storage[REPORTS_COLLECTION].append(resolved_case("c1", filed, done))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **BOTH})
    for channel in (SMS, WHATSAPP):
        storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, RESOLVED, written=done, channel=channel))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed, channel=SMS))

    assert notification_sweep.run_sweep(NOW) == ["c1"]
    assert [(channel, body) for channel, _, body in delivered] == [(WHATSAPP.value, "Nokware: report K7QM-C1 is with "
                                                                   "Works Department. We'll message you when it's "
                                                                   "resolved. Track it: localhost:3000/report/status")]


def test_a_safety_case_s_repair_carries_neither_its_category_nor_its_service_anywhere(
    storage: dict[str, list[dict[str, Any]]], delivered: list[tuple[str, str, str]]
) -> None:
    """The message a resident gets, the outbox row it is kept in and the line written into the case's own trail: a
    phone can be shared, and the trail is read in the portal, so none of the three names what the case is."""
    storage[REPORTS_COLLECTION].append({
        **case("c1", NOW - timedelta(hours=2)), "category": "personal_safety", "topic": "abuse",
        "recipients": ["agency-police", "dept-social-welfare"]})
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})

    assert notification_sweep.run_sweep(NOW) == ["c1"]
    assert delivered == [(SMS.value, "+233241234567", "Nokware: reference K7QM-C1 received.")]
    written = [row for row in storage[NOTIFICATIONS_COLLECTION] if row["status"] == NotificationStatus.SENT.value]
    said = " ".join([*history_notes(storage), *(str(row.get("body") or "") for row in written)]).lower()
    for giveaway in ("safety", "abuse", "police", "welfare", "report", "sensitive"):
        assert giveaway not in said
    assert written[0]["template"] == "private_submitted"


def test_each_channel_is_repaired_when_both_are_owed(storage: dict[str, list[dict[str, Any]]], sent: list[str]) -> None:
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **BOTH})

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/sms", "c1/submitted/whatsapp"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/submitted/sms", "c1/submitted/whatsapp"]


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

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/sms"]
    assert recorded["status"] == NotificationStatus.NOT_SENT.value  # what happened to this row is still what it says
    assert notifications.repaired(recorded) and "+233" not in recorded["error"] and "+233" not in caplog.text
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/submitted/sms"]


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

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/sms"]
    assert stuck["error"].startswith(notifications.STALE_QUEUED)
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/submitted/sms"]


def test_a_send_the_provider_never_answered_is_made_once_more_and_only_once(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """No message ID came back, so no delivery report and no poll can ever say whether the resident got it."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    unanswered = outbox("c1", NotificationStatus.FAILED, error=f"{notifications.UNREACHABLE}Arkesel couldn't be reached (ReadTimeout).")
    storage[NOTIFICATIONS_COLLECTION].append(unanswered)

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/sms"]
    assert notifications.repaired(unanswered) and "ReadTimeout" in unanswered["error"]  # why it was repaired is kept
    assert "+233" not in unanswered["error"] and "+233" not in caplog.text
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/submitted/sms"]


def test_a_send_our_own_side_never_attempted_is_sent_again(storage: dict[str, list[dict[str, Any]]], sent: list[str]) -> None:
    """The counter the daily budget needs couldn't be reached, so nothing was handed to any provider."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(
        outbox("c1", NotificationStatus.FAILED, error=f"{notifications.NOTHING_SENT}The SMS limit can't be checked (RedisUnavailable).")
    )

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/submitted/sms"]


def test_a_resolution_the_resident_never_heard_about_is_sent_once(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """The moment they have been waiting for. The receipt arrived; the resolution never reached the outbox at all."""
    filed = NOW - timedelta(days=2)
    storage[REPORTS_COLLECTION].append(resolved_case("c1", filed, NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed))

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/resolved/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/resolved/sms"]


def test_a_start_of_work_the_resident_never_heard_about_is_sent_once(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """Someone picked the report up the same day and the resident heard nothing: the silence this message is for."""
    filed = NOW - timedelta(days=1)
    storage[REPORTS_COLLECTION].append(case("c1", filed))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[ASSIGNMENTS_COLLECTION].append(assignment("c1", NOW - timedelta(hours=2)))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed))

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/started/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/started/sms"]  # the row it wrote settles it


def test_the_second_recipient_starting_owes_nothing_because_the_first_one_already_did(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """One message for the case, not one per office: the Police and Social Welfare each opening their own part is
    one piece of news. The row written when the first started answers for the case."""
    filed = NOW - timedelta(days=1)
    storage[REPORTS_COLLECTION].append(case("c1", filed))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    first = NOW - timedelta(hours=4)
    storage[ASSIGNMENTS_COLLECTION].append(assignment("c1", first, "agency-police"))
    storage[ASSIGNMENTS_COLLECTION].append(assignment("c1", NOW - timedelta(hours=1), "dept-social-welfare"))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, STARTED, written=first))

    assert notification_sweep.run_sweep(NOW) == [] and sent == []


def test_the_start_is_dated_from_the_first_recipient_so_a_late_second_one_revives_nothing(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """The message goes on the first start, so that is the moment it is owed from. A "work has started" a week and a
    half late is worse than none, and the second office starting doesn't make it new again."""
    filed = NOW - timedelta(days=30)
    storage[REPORTS_COLLECTION].append(case("c1", filed))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[ASSIGNMENTS_COLLECTION].append(
        assignment("c1", NOW - notification_sweep.WINDOW - timedelta(hours=1), "agency-police")
    )
    storage[ASSIGNMENTS_COLLECTION].append(assignment("c1", NOW - timedelta(hours=1), "dept-social-welfare"))

    assert notification_sweep.run_sweep(NOW) == [] and sent == []


def test_a_case_picked_up_long_after_it_was_filed_is_found_by_when_the_work_started(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """Only the assignment records when work started, so the case itself is found through it. Filed a month ago, it
    would never be reached by a scan over the case's own dates. The month-old receipt stays unsent."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(days=30)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[ASSIGNMENTS_COLLECTION].append(assignment("c1", NOW - timedelta(hours=2)))

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/started/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/started/sms"]


def test_a_start_nothing_can_date_is_said_aloud_rather_than_guessed_at(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """Work is in progress and no stamp says when it began: a guessed date would send it run after run."""
    filed = NOW - timedelta(hours=2)
    storage[REPORTS_COLLECTION].append(case("c1", filed))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[ASSIGNMENTS_COLLECTION].append(assignment("c1", None))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed))

    assert notification_sweep.run_sweep(NOW) == [] and sent == []
    assert "can't date the started message for case c1" in caplog.text and "+233" not in caplog.text


def test_an_assignment_resolved_without_ever_being_started_owes_no_start(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """A recipient may resolve a case outright, never acknowledging it. Nothing started, so nothing was owed: the
    resolution is the message, and it is the only one."""
    filed = NOW - timedelta(days=1)
    storage[REPORTS_COLLECTION].append(resolved_case("c1", filed, NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[ASSIGNMENTS_COLLECTION].append(assignment("c1", None, status="resolved"))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed))

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/resolved/sms"]


def test_an_escalation_is_sent_and_the_resolution_the_case_has_moved_past_is_not(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """The escalation acknowledgement is owed the same as any other message. The resolution message is not: after an
    escalation it reads "reviewed and resolved", which is not what happened, and an untruth is its own harm."""
    filed = NOW - timedelta(days=3)
    storage[REPORTS_COLLECTION].append(escalated_case("c1", filed, NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed))

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/escalated/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/escalated/sms"]


def test_a_case_whose_resolution_message_was_sent_is_left_alone(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    filed, resolved = NOW - timedelta(days=2), NOW - timedelta(hours=2)
    storage[REPORTS_COLLECTION].append(resolved_case("c1", filed, resolved))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, RESOLVED, written=resolved))

    assert notification_sweep.run_sweep(NOW) == [] and sent == []


def test_a_case_resolved_long_after_it_was_filed_is_found_by_when_it_was_resolved(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """A case filed a month ago and resolved this morning owes this morning's message, and no scan by when it was
    filed would ever reach it. The receipt, a month old, stays unsent: that one nobody wants now."""
    storage[REPORTS_COLLECTION].append(resolved_case("c1", NOW - timedelta(days=30), NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/resolved/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/resolved/sms"]


def test_a_resolution_older_than_the_window_is_left_unsent(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """A "your report was resolved" a week and a half late is worse than none, exactly as a late receipt is."""
    filed = NOW - timedelta(days=40)
    storage[REPORTS_COLLECTION].append(resolved_case("old", filed, NOW - notification_sweep.WINDOW - timedelta(hours=1)))
    storage[REPORTS_COLLECTION].append(resolved_case("new", filed, NOW - notification_sweep.WINDOW + timedelta(hours=1)))
    for case_id in ("old", "new"):
        storage[CONTACTS_COLLECTION].append({"$id": case_id, "caseId": case_id, **CONSENTED})

    assert notification_sweep.run_sweep(NOW) == ["new"] and sent == ["new/resolved/sms"]


def test_the_window_is_measured_from_each_moment_and_not_from_the_case(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """One case, three moments, one of them recent: the old receipt stays unsent and this morning's escalation goes."""
    storage[REPORTS_COLLECTION].append(escalated_case("c1", NOW - timedelta(days=30), NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/escalated/sms"]


def test_the_mce_s_ruling_is_owed_though_the_first_resolution_was_sent(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """Resolved, escalated, then resolved again by the MCE: two resolution messages, and the first one's outbox row
    was written days before the second moment, so it answers for the first and settles nothing here."""
    filed, first, escalation, ruling = (NOW - timedelta(days=5), NOW - timedelta(days=4),
                                        NOW - timedelta(days=3), NOW - timedelta(hours=2))
    storage[REPORTS_COLLECTION].append(
        case("c1", filed, status=CaseStatus.RESOLVED.value, resolvedAt=ruling.isoformat(), escalatedAt=escalation.isoformat())
    )
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, RESOLVED, written=first, oid="n-first"))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, ESCALATED, written=escalation))

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/resolved/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/resolved/sms"]


def test_every_moment_a_case_has_reached_is_repaired_in_the_order_it_happened(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """Nothing at all was ever written for this case: the resident hears the three things in the order they happened."""
    escalation, ruling = NOW - timedelta(days=2), NOW - timedelta(hours=1)
    storage[REPORTS_COLLECTION].append(
        case("c1", NOW - timedelta(days=3), status=CaseStatus.RESOLVED.value,
             resolvedAt=ruling.isoformat(), escalatedAt=escalation.isoformat())
    )
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})

    assert notification_sweep.run_sweep(NOW) == ["c1"]
    assert sent == ["c1/submitted/sms", "c1/escalated/sms", "c1/resolved/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and len(sent) == 3


def test_a_resolution_is_dated_by_the_case_s_own_history_when_the_case_itself_does_not_say(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """Nothing on this case says when it was resolved, so the trail it keeps of itself does — the latest of the
    entries that resolve a case, because an earlier one is a single recipient finishing its own part."""
    filed, first, ruling = NOW - timedelta(days=3), NOW - timedelta(days=2), NOW - timedelta(hours=2)
    storage[REPORTS_COLLECTION].append(case("c1", filed, status=CaseStatus.RESOLVED.value))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, RESOLVED, written=first))
    storage[case_history.COLLECTION_ID].append(entry("c1", CaseHistoryAction.RESOLVED, first))
    storage[case_history.COLLECTION_ID].append(entry("c1", CaseHistoryAction.ESCALATION_CONFIRMED, ruling))

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/resolved/sms"]
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/resolved/sms"]


def test_a_moment_nothing_can_date_is_said_aloud_rather_than_guessed_at(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """A guessed date would either send the message run after run or bury it somewhere outside the window."""
    filed = NOW - timedelta(days=2)
    storage[REPORTS_COLLECTION].append(case("c1", filed, status=CaseStatus.RESOLVED.value))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed))

    assert notification_sweep.run_sweep(NOW) == [] and sent == []
    assert "can't date the resolved message for case c1" in caplog.text and "+233" not in caplog.text


def test_a_whatsapp_message_that_never_left_is_repaired_and_one_twilio_answered_is_not(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """Twilio's failures are told apart now as Arkesel's already were: the send that never made a connection reached
    nobody, and the one Twilio answered — 63016 among them — may have been delivered, so it is left alone."""
    for case_id in ("c1", "c2"):
        storage[REPORTS_COLLECTION].append(case(case_id, NOW - timedelta(hours=2)))
        storage[CONTACTS_COLLECTION].append({"$id": case_id, "caseId": case_id, **WHATSAPP_ONLY})
    storage[NOTIFICATIONS_COLLECTION].append(outbox(
        "c1", NotificationStatus.FAILED, channel=WHATSAPP,
        error=f"{notifications.NOTHING_SENT}Twilio couldn't be reached (ConnectError).",
    ))
    storage[NOTIFICATIONS_COLLECTION].append(outbox(
        "c2", NotificationStatus.FAILED, channel=WHATSAPP,
        error="Twilio refused the message (400, code 63016): outside the 24-hour window",
    ))

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/whatsapp"]


def test_a_whatsapp_message_twilio_never_answered_is_sent_once_more_and_only_once(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """It may have been delivered: no SID came back, so no status callback can ever settle it. One duplicate, paid once."""
    storage[REPORTS_COLLECTION].append(case("c1", NOW - timedelta(hours=2)))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **WHATSAPP_ONLY})
    unanswered = outbox("c1", NotificationStatus.FAILED, channel=WHATSAPP,
                        error=f"{notifications.UNREACHABLE}Twilio couldn't be reached (ReadTimeout).")
    storage[NOTIFICATIONS_COLLECTION].append(unanswered)

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/whatsapp"]
    assert notifications.repaired(unanswered) and "ReadTimeout" in unanswered["error"]  # why it was repaired is kept
    assert "+233" not in unanswered["error"] and "+233" not in caplog.text
    assert notification_sweep.run_sweep(NOW) == [] and sent == ["c1/submitted/whatsapp"]


def test_no_stored_field_and_no_log_line_ever_holds_a_number(
    storage: dict[str, list[dict[str, Any]]], sent: list[str], sms_configured: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Every repair the sweep can make — every moment, every channel — in one run, against the contacts' own numbers."""
    filed = NOW - timedelta(days=2)
    records = (resolved_case("c1", filed, NOW - timedelta(hours=2)), escalated_case("c2", filed, NOW - timedelta(hours=3)),
               case("c3", NOW - timedelta(hours=2), status=CaseStatus.RESOLVED.value))
    for record, contact in zip(records, (CONSENTED, BOTH, WHATSAPP_ONLY)):
        storage[REPORTS_COLLECTION].append(record)
        storage[CONTACTS_COLLECTION].append({"$id": record["$id"], "caseId": record["$id"], **contact})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.NOT_SENT, RESOLVED))
    storage[NOTIFICATIONS_COLLECTION].append(budget_refused("c2", channel=WHATSAPP))
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c3", NotificationStatus.QUEUED, written=NOW - timedelta(hours=1), channel=WHATSAPP))

    with caplog.at_level(logging.INFO):
        assert notification_sweep.run_sweep(NOW) == ["c1", "c2", "c3"]
    written = " ".join(str(value) for row in storage[NOTIFICATIONS_COLLECTION] for value in row.values())
    assert "+233" not in written and "241234567" not in written
    assert "+233" not in caplog.text and "241234567" not in caplog.text
    assert "can't date the resolved message for case c3" in caplog.text  # and no number in that line either


def test_a_move_and_a_reopening_are_repaired_like_any_other_moment(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """Both are stamped on the case, so the sweep finds them by when they happened and composes the message from
    the case alone — the same words the first attempt would have carried."""
    filed, moved, reopened = NOW - timedelta(days=3), NOW - timedelta(hours=5), NOW - timedelta(hours=2)
    storage[REPORTS_COLLECTION].append(case(
        "c1", filed, status=CaseStatus.ASSIGNED.value, recipients=["dept-urban-roads"],
        reassignedAt=moved.isoformat(), reassignedFrom="dept-works", reassignedTo="dept-urban-roads",
        reopenedAt=reopened.isoformat()))
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})
    storage[NOTIFICATIONS_COLLECTION].append(outbox("c1", NotificationStatus.SENT, SUBMITTED, written=filed))

    assert notification_sweep.run_sweep(NOW) == ["c1"]
    assert sent == ["c1/reassigned/sms", "c1/reopened/sms"]  # oldest moment first
    assert notification_sweep.run_sweep(NOW) == [] and len(sent) == 2


def test_a_safety_case_is_never_sent_a_move_or_a_reopening_even_years_later(
    storage: dict[str, list[dict[str, Any]]], sent: list[str]
) -> None:
    """Which service holds it is the sensitive fact, so there is nothing to repair. The receipt still is."""
    filed, moved = NOW - timedelta(days=2), NOW - timedelta(hours=3)
    storage[REPORTS_COLLECTION].append({
        **case("c1", filed, status=CaseStatus.ASSIGNED.value, reassignedAt=moved.isoformat(),
               reassignedFrom="agency-police", reassignedTo="dept-social-welfare",
               reopenedAt=moved.isoformat()),
        "category": "personal_safety", "recipients": ["dept-social-welfare"]})
    storage[CONTACTS_COLLECTION].append({"$id": "c1", "caseId": "c1", **CONSENTED})

    assert notification_sweep.run_sweep(NOW) == ["c1"] and sent == ["c1/submitted/sms"]
