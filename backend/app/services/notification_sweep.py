"""The "received" message a resident agreed to and never got, on the channel they never got it on.

Filing a report answers 201 and hands the message to a background task. If the process restarts or dies in that
moment the task goes with it: nothing is sent, and — because the outbox row is written by the send itself — nothing
anywhere records that a message was owed. This sweep looks for that gap and sends the message the ordinary way, so
the outbox row, the case-history line and the daily SMS budget all behave as they do on the ordinary path.

What is repaired is one channel of one case, never the case as a whole. A resident who agreed to both SMS and
WhatsApp and got only the SMS is owed the WhatsApp message and nothing else: repairing the case would either send
the SMS a second time or — as this sweep first did — leave the WhatsApp message unsent for ever.

A channel is owed its message when every outbox row it has says so, and a row says so in these ways only:
  * there is no row at all — the task died before it wrote one;
  * our own side refused it before the provider was asked: the daily SMS budget, or the counter that budget needs.
    Nothing was sent to anyone, so a later send is the same message arriving late, not a second one;
  * the provider never answered: no message ID came back, so no delivery report and no poll can ever say whether
    the resident got it;
  * the row was left `queued` long past the moment the send should have finished — the process died between writing
    the row and updating it;
  * the row says `not_sent` because no provider was configured then, and one is configured now. That row is a
    message a resident never received, and configuring a provider is what happens at deployment.

Everything else settles the channel: a `sent` row is done; a row the provider refused with an answer may have been
delivered anyway; and a row this sweep has already repaired is never repaired again, which is what keeps the one
duplicate this sweep is willing to pay from becoming a stream of them.
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
    NotificationChannel,
    NotificationEvent,
    NotificationStatus,
)
from app.services.notifications import (
    budget_refused,
    channels_for,
    mark_repaired,
    mark_stale_queued,
    nothing_was_sent,
    notify_channel,
    provider_for,
    provider_unreachable,
    repaired,
)

logger = logging.getLogger(__name__)

# An old "we received your report" is worse than none: by then the resident has drawn their own conclusion, and a
# message out of nowhere reads as a system talking to itself. Anything filed longer ago than this is left unsent.
WINDOW = timedelta(days=7)
# These are real messages and real credits, so one run repairs a little at a time, oldest first. A case counts once
# however many of its channels are repaired: the cap is there to keep a run small, and a case has at most two.
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
NOT_ATTEMPTED = "our own side stopped before the provider was asked, so nothing was sent to anyone"
UNANSWERED = "the provider never answered, so nobody can ever learn whether it went"
STALE = "an outbox row was left queued: the send never finished"
NO_PROVIDER_THEN = "it was recorded but never sent, for want of a provider, and there is one now"

CLOSED_STALE = "the send never finished, so the sweep sent the message again"
CLOSED_REPAIRED = "the sweep sent this message again"

CHANNELS = {channel.value: channel for channel in NotificationChannel}


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


def _agreed(cases: list[dict[str, Any]]) -> dict[str, list[NotificationChannel]]:
    """The channels each resident agreed to, by the one consent rule the ordinary path uses. A case whose resident
    agreed to none isn't here at all."""
    contacts = _records_by_case(CONTACTS_COLLECTION, [case["$id"] for case in cases])  # one per case, by its unique index
    agreed = {case_id: [channel for channel, _ in channels_for(found[0])] for case_id, found in contacts.items()}
    return {case_id: channels for case_id, channels in agreed.items() if channels}


def _submitted_rows(case_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """The outbox rows for the submitted message, by case, whatever status they ended in."""
    rows = _records_by_case(NOTIFICATIONS_COLLECTION, case_ids)
    return {case_id: [row for row in found if row["event"] == NotificationEvent.SUBMITTED] for case_id, found in rows.items()}


def _written_at(row: dict[str, Any]) -> datetime | None:
    stamp = row.get("createdAt") or row.get("$createdAt")
    try:
        written = datetime.fromisoformat(stamp) if stamp else None
    except ValueError:
        return None
    return written.replace(tzinfo=UTC) if written and written.tzinfo is None else written


def _stale_queued(row: dict[str, Any], now: datetime) -> bool:
    if row.get("status") != NotificationStatus.QUEUED:
        return False
    written = _written_at(row)
    # A queued row whose time can't be read is taken as old rather than left alone for ever. The harm chosen: at
    # worst one duplicate reference, against a resident who never hears anything because a stamp was unreadable.
    return written is None or now - written > QUEUED_GRACE


def _no_provider_then(row: dict[str, Any]) -> bool:
    """A `not_sent` row is a message a resident never received, and at deployment a provider appears. The provider
    asked about is the row's own channel — the one that had none — so a repair that itself lands on a channel still
    without a provider writes a `not_sent` row that stays put instead of being swept again, run after run."""
    channel = CHANNELS.get(str(row.get("channel")))
    return row.get("status") == NotificationStatus.NOT_SENT and channel is not None and provider_for(channel) is not None


def _retriable(row: dict[str, Any], now: datetime) -> str:
    """Why this row leaves the message still owed, or "" if it settles it."""
    if repaired(row):  # this row's one duplicate has already been paid
        return ""
    if nothing_was_sent(row):
        return BUDGET if budget_refused(row) else NOT_ATTEMPTED
    if provider_unreachable(row):
        return UNANSWERED
    if _stale_queued(row, now):
        return STALE
    return NO_PROVIDER_THEN if _no_provider_then(row) else ""


def _reason(rows: list[dict[str, Any]], now: datetime) -> str:
    """Why this channel's message is still owed, or "" if any row settles it.

    Every row has to be retriable. One `sent` row, one the provider refused with an answer, or one this sweep has
    already repaired settles the channel: a repair is a whole message, so it can't be aimed at part of one.
    """
    if not rows:
        return NOTHING_RECORDED
    reasons = [_retriable(row, now) for row in rows]
    return "; ".join(dict.fromkeys(reasons)) if all(reasons) else ""


def _rows_by_channel(agreed: list[NotificationChannel], rows: list[dict[str, Any]]) -> dict[NotificationChannel, list[dict[str, Any]]]:
    """Which agreed channel each outbox row answers for.

    A row recorded on a channel the resident did not agree to is a stand-in: when a resident gave only a WhatsApp
    number and WhatsApp's 24-hour window is closed, the ordinary path sends by SMS to that same number and records
    the row on the SMS channel. That row IS the WhatsApp message, so it settles the WhatsApp channel and is never
    repaired a second time. A repair goes back through notify_channel, which reads the window again as it sends, so
    a repair of the WhatsApp channel may itself go out by SMS — which is what a first send would have done too.
    """
    found: dict[NotificationChannel, list[dict[str, Any]]] = {channel: [] for channel in agreed}
    for row in rows:
        channel = CHANNELS.get(str(row.get("channel")))
        if channel not in found and NotificationChannel.WHATSAPP in found:
            channel = NotificationChannel.WHATSAPP  # the stand-in above
        if channel in found:
            found[channel].append(row)
        # A row on a channel the resident no longer has (they changed their contact details) answers for none of the
        # channels they agreed to now, and those are the ones this sweep owes them.
    return found


@dataclass(frozen=True)
class Repair:
    channel: NotificationChannel
    why: str
    rows: list[dict[str, Any]]  # this channel's rows, closed before the resend


@dataclass(frozen=True)
class Owed:
    case: dict[str, Any]
    repairs: list[Repair]
    rows: list[dict[str, Any]]  # every submitted row the case had before the repair

    @property
    def why(self) -> str:
        return "; ".join(f"{repair.channel.value}: {repair.why}" for repair in self.repairs)


def _owed(cases: list[dict[str, Any]], now: datetime) -> list[Owed]:
    """Of these cases, the ones with a channel whose resident agreed to it and never got the message on it."""
    agreed = _agreed(cases)
    rows = _submitted_rows(list(agreed))
    owed: list[Owed] = []
    for case in cases:
        channels = agreed.get(case["$id"])
        if not channels:
            continue
        found = rows.get(case["$id"], [])
        by_channel = _rows_by_channel(channels, found)
        repairs = [Repair(channel, why, these) for channel, these in by_channel.items() if (why := _reason(these, now))]
        if repairs:
            owed.append(Owed(case, repairs, found))
    return owed


def _close(repair: Repair, now: datetime) -> None:
    """Closes the rows this repair answers, so this channel is never swept a second time.

    The judgement call, stated plainly: the provider may in fact have received one of these, so the resend risks a
    second "we received your report". A duplicate that carries nothing but a reference is a smaller harm than a
    resident who filed a report and heard nothing at all — but it is a real cost, so it is paid exactly once. The
    rows are closed BEFORE the send: if this process dies in between, the resident is left with the same silence
    they already had, whereas closing them afterwards would let that same death resend a third and fourth time.

    Rows our own side never attempted — the daily budget, or the counter behind it — are left open on purpose:
    nothing reached anyone, so tomorrow's send is this message arriving late and has no duplicate to pay for.
    """
    for row in repair.rows:
        if _stale_queued(row, now):
            mark_stale_queued(row["$id"], CLOSED_STALE)
        elif provider_unreachable(row) or _no_provider_then(row):
            mark_repaired(row["$id"], CLOSED_REPAIRED, was=str(row.get("error") or "")[:200])


def _send(owed: Owed, now: datetime) -> bool:
    """Sends one case's missed messages, on the unresolved channels only. False means the run should stop."""
    case_id = owed.case["$id"]
    before = {row["$id"] for row in owed.rows}
    for repair in owed.repairs:
        _close(repair, now)
        notify_channel(owed.case, NotificationEvent.SUBMITTED, repair.channel)
    fresh = [row for row in _submitted_rows([case_id]).get(case_id, []) if row["$id"] not in before]
    if fresh and all(row["status"] == NotificationStatus.FAILED for row in fresh):
        # Nothing this case could be sent on worked, and a row the provider refused is never retried, so every
        # further case risks being written off the same way. The run stops here and leaves the rest to a later one.
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
