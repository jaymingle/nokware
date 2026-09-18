"""The "received" message a resident agreed to but never got at all.

Filing a report answers 201 and hands the message to a background task. If the process restarts or dies in that
moment the task goes with it: nothing is sent, and — because the outbox row is written by the send itself — nothing
anywhere records that a message was owed. This sweep looks for that gap and sends the message the ordinary way, so
the outbox row, the case-history line and the daily SMS budget all behave as they do on the ordinary path.

Three silences count as owed, and only these three:
  * no outbox row at all — the task died before it wrote one;
  * every row refused by our own daily SMS budget — nothing left this process, so tomorrow's send is the same
    message arriving late, not a second one;
  * every row left `queued` long past the moment the send should have finished — the process died between writing
    the row and updating it.

Everything else is left alone. A `sent` row is done; a `not_sent` row had no provider to reach; a provider failure
means the provider was asked and may have delivered anyway, so a second "we received your report" would be a
duplicate.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from appwrite.query import Query

from app.services.appwrite_client import DATABASE_ID, as_record, every_record, get_databases
from app.services.citizen_reports import (
    CONTACTS_COLLECTION,
    NOTIFICATIONS_COLLECTION,
    REPORTS_COLLECTION,
    NotificationEvent,
    NotificationStatus,
)
from app.services.notifications import budget_refused, channels_for, mark_stale_queued, notify

logger = logging.getLogger(__name__)

# An old "we received your report" is worse than none: by then the resident has drawn their own conclusion, and a
# message out of nowhere reads as a system talking to itself. Anything filed longer ago than this is left unsent.
WINDOW = timedelta(days=7)
# These are real messages and real credits, so one run repairs a little at a time, oldest first.
PER_RUN = 20
# How many recent cases a run looks at. The gap is rare, so this bounds the work, not the repair: a case further
# back than this is picked up by a later run, for as long as it stays inside the window.
SCAN_LIMIT = 200
BATCH = 25  # case IDs per lookup of contacts and of outbox rows
# How long a row may sit at `queued` before the sweep stops believing a send is still in flight. On the ordinary
# path the row is written, the provider is called and the row is updated within seconds: the provider call is capped
# at sms.TIMEOUT_SECONDS (10s) and the Appwrite update at appwrite_client.TIMEOUT (5s + 25s). Fifteen minutes is far
# past any of that, so a slow provider, a retry or a few minutes of clock skew between this process and Appwrite is
# never mistaken for a death — and a resident whose message really is stuck still hears within the hour.
QUEUED_GRACE = timedelta(minutes=15)

NOTHING_RECORDED = "nothing was ever written to the outbox"
BUDGET = "our own daily SMS budget refused it, so nothing was sent to anyone"
STALE = "an outbox row was left queued: the send never finished"


def _recent_cases(now: datetime) -> list[dict[str, Any]]:
    listing = get_databases().list_documents(
        DATABASE_ID,
        REPORTS_COLLECTION,
        queries=[
            Query.greater_than_equal("createdAt", (now - WINDOW).isoformat()),
            Query.order_asc("createdAt"),
            Query.limit(SCAN_LIMIT),
        ],
    )
    return [as_record(document) for document in listing.documents]


def _records_by_case(collection: str, case_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    for record in every_record(collection, [Query.equal("caseId", case_ids)]) if case_ids else []:
        found.setdefault(record["caseId"], []).append(record)
    return found


def _consenting(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only the residents who agreed to messages, by the one consent rule the ordinary path uses."""
    contacts = _records_by_case(CONTACTS_COLLECTION, [case["$id"] for case in cases])  # one per case, by its unique index
    agreed = {case_id for case_id, found in contacts.items() if channels_for(found[0])}
    return [case for case in cases if case["$id"] in agreed]


def _submitted_rows(case_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """The outbox rows for the submitted message, by case, whatever status they ended in."""
    rows = _records_by_case(NOTIFICATIONS_COLLECTION, case_ids)
    return {case_id: [row for row in found if row["event"] == NotificationEvent.SUBMITTED] for case_id, found in rows.items()}


def _written_at(row: dict[str, Any]) -> datetime | None:
    stamp = row.get("createdAt") or row.get("$createdAt")
    try:
        written = datetime.fromisoformat(stamp) if stamp else None
    except ValueError:
        return None  # an unreadable stamp must never make a row look old enough to resend
    return written.replace(tzinfo=UTC) if written and written.tzinfo is None else written


def _stale_queued(row: dict[str, Any], now: datetime) -> bool:
    if row.get("status") != NotificationStatus.QUEUED:
        return False
    written = _written_at(row)
    return written is not None and now - written > QUEUED_GRACE


def _retriable(row: dict[str, Any], now: datetime) -> str:
    """Why this row leaves the message still owed, or "" if it settles it."""
    if budget_refused(row):
        return BUDGET
    if _stale_queued(row, now):
        return STALE
    return ""


def _why_owed(rows: list[dict[str, Any]], now: datetime) -> str:
    """Why this case's resident is still owed the message, or "" if any row settles it.

    Every row has to be retriable. One `sent`, `not_sent` or provider-failed row among them settles the whole case:
    a resend goes out on every channel the resident agreed to, so it can't be aimed at the unresolved row alone.
    """
    if not rows:
        return NOTHING_RECORDED
    reasons = [_retriable(row, now) for row in rows]
    return "; ".join(dict.fromkeys(reasons)) if all(reasons) else ""


@dataclass(frozen=True)
class Owed:
    case: dict[str, Any]
    why: str
    rows: list[dict[str, Any]]


def _owed(cases: list[dict[str, Any]], now: datetime) -> list[Owed]:
    """Of these cases, the ones whose resident agreed to messages and never got the one they were owed."""
    consenting = _consenting(cases)
    rows = _submitted_rows([case["$id"] for case in consenting])
    found = [(case, rows.get(case["$id"], [])) for case in consenting]
    return [Owed(case, why, these) for case, these in found if (why := _why_owed(these, now))]


def _settle_stale(owed: Owed, now: datetime) -> None:
    """Closes the rows left mid-send, so this case is never swept a second time.

    The judgement call, stated plainly: the provider may in fact have received one of these, so the resend risks a
    second "we received your report". A duplicate that carries nothing but a reference is a smaller harm than a
    resident who filed a report and heard nothing at all — but it is a real cost, so it is paid exactly once. The
    rows are closed BEFORE the send: if this process dies in between, the resident is left with the same silence
    they already had, whereas closing them afterwards would let that same death resend a third and fourth time.
    """
    for row in owed.rows:
        if _stale_queued(row, now):
            mark_stale_queued(row["$id"], "the send never finished, so the sweep sent the message again")


def _send(owed: Owed, now: datetime) -> bool:
    """Sends one missed message the ordinary way. False means the run should stop."""
    case_id = owed.case["$id"]
    _settle_stale(owed, now)
    notify(owed.case, NotificationEvent.SUBMITTED)
    statuses = [row["status"] for row in _submitted_rows([case_id]).get(case_id, [])]
    if statuses and all(status == NotificationStatus.FAILED for status in statuses):
        # Nothing this case could be sent on worked, and a provider failure is never retried, so every further case
        # risks being written off the same way. The run stops here and leaves the rest to a later one.
        logger.warning("Missed-message sweep stopped at case %s: the message failed to send", case_id)
        return False
    logger.info("Missed-message sweep sent the received message for case %s (%s)", case_id, owed.why)
    return True


def run_sweep(now: datetime) -> list[str]:
    """Sends the received message to residents who were owed one and got nothing. Returns the case IDs it handled."""
    cases = _recent_cases(now)
    sent: list[str] = []
    for start in range(0, len(cases), BATCH):
        for owed in _owed(cases[start : start + BATCH], now):
            if len(sent) >= PER_RUN:
                logger.info("Missed-message sweep: %d handled, the cap for one run; any others wait for the next", len(sent))
                return sent
            if not _send(owed, now):
                return sent
            sent.append(owed.case["$id"])
    return sent
