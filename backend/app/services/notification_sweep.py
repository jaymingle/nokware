"""The "received" message a resident agreed to but never got at all.

Filing a report answers 201 and hands the message to a background task. If the process restarts or dies in that
moment the task goes with it: nothing is sent, and — because the outbox row is written by the send itself — nothing
anywhere records that a message was owed. This sweep looks for that gap and sends the message the ordinary way, so
the outbox row, the case-history line and the daily SMS budget all behave as they do on the ordinary path.

A recorded failure is a different case and is left alone: a failed row means the provider was asked, and it may have
delivered anyway, so a second "we received your report" would be a duplicate.
"""

import logging
from datetime import datetime, timedelta
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
from app.services.notifications import channels_for, notify

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


def _submitted_statuses(case_ids: list[str]) -> dict[str, list[str]]:
    """The outbox rows for the submitted message, by case, whatever status they ended in."""
    rows = _records_by_case(NOTIFICATIONS_COLLECTION, case_ids)
    statuses = {case_id: [row["status"] for row in found if row["event"] == NotificationEvent.SUBMITTED] for case_id, found in rows.items()}
    return {case_id: found for case_id, found in statuses.items() if found}


def _owed(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Of these cases, the ones whose resident agreed to messages and whose submitted message never reached the outbox."""
    consenting = _consenting(cases)
    recorded = _submitted_statuses([case["$id"] for case in consenting])
    return [case for case in consenting if case["$id"] not in recorded]


def _send(case: dict[str, Any]) -> bool:
    """Sends one missed message the ordinary way. False means the run should stop."""
    case_id = case["$id"]
    notify(case, NotificationEvent.SUBMITTED)
    statuses = _submitted_statuses([case_id]).get(case_id, [])
    if statuses and all(status == NotificationStatus.FAILED for status in statuses):
        # Today's SMS budget is spent, or the provider is down. Every further case would be written off as a failure
        # this sweep never retries, so the run stops here and leaves them to a later one.
        logger.warning("Missed-message sweep stopped at case %s: the message failed to send", case_id)
        return False
    logger.info("Missed-message sweep sent the received message for case %s (%s)", case_id, ", ".join(statuses) or "no channel left")
    return True


def run_sweep(now: datetime) -> list[str]:
    """Sends the received message to residents who were owed one and got nothing. Returns the case IDs it handled."""
    cases = _recent_cases(now)
    sent: list[str] = []
    for start in range(0, len(cases), BATCH):
        for case in _owed(cases[start : start + BATCH]):
            if len(sent) >= PER_RUN:
                logger.info("Missed-message sweep: %d handled, the cap for one run; any others wait for the next", len(sent))
                return sent
            if not _send(case):
                return sent
            sent.append(case["$id"])
    return sent
