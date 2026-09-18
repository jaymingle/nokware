"""The messages a resident agreed to and never got, on the channel they never got them on.

A case reaches four moments a resident is told about: it was received, a recipient started work on it, it was
resolved, and — if they escalated it — the escalation was received. Each one answers 201 or 200 and hands the
message to a background task. If the process restarts or dies in that moment the task goes with it: nothing is sent,
and — because the outbox row is written by the send itself — nothing anywhere records that a message was owed. This
sweep looks for that gap and sends the message the ordinary way, so the outbox row, the case-history line and the
daily SMS budget all behave as they do on the ordinary path. The start of work, the resolution and the escalation
are the moments a resident has been waiting for, so they are repaired exactly as the receipt is.

What is repaired is one message on one channel, never the case as a whole. A resident who agreed to both SMS and
WhatsApp and got only the SMS is owed the WhatsApp message and nothing else: repairing the case would either send
the SMS a second time or — as this sweep first did — leave the WhatsApp message unsent for ever. The same holds
between moments: a resident who got the receipt and not the resolution is owed the resolution alone.

A channel is owed a moment's message when every outbox row that answers for it says so, and a row says so in these
ways only:
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

from app.services import case_history
from app.services.appwrite_client import DATABASE_ID, as_record, every_record, get_databases
from app.services.case_history import CaseHistoryAction
from app.services.case_workflow import CaseStatus, has_started
from app.services.citizen_reports import (
    ASSIGNMENTS_COLLECTION,
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

# An old message is worse than none: by then the resident has drawn their own conclusion, and a message out of
# nowhere reads as a system talking to itself. The window is measured from the moment the message became owed — when
# the report was filed, resolved or escalated — not from when the case was filed: a case filed in March and resolved
# yesterday owes yesterday's message.
WINDOW = timedelta(days=7)
# These are real messages and real credits, so one run repairs a little at a time, oldest first. A case counts once
# however many of its moments and channels are repaired: the cap is there to keep a run small, and a case has at
# most four moments on at most two channels.
PER_RUN = 20
# How many recent cases each of the three scans looks at. The gap is rare, so this bounds the work, not the repair:
# a case further back than this is picked up by a later run, for as long as it stays inside the window.
SCAN_LIMIT = 200
BATCH = 25  # case IDs per lookup of contacts, of history and of outbox rows
# How long a row may sit at `queued` before the sweep stops believing a send is still in flight. On the ordinary
# path the row is written, the provider is called and the row is updated within seconds: the provider call is capped
# at sms.TIMEOUT_SECONDS (10s) and the Appwrite update at appwrite_client.TIMEOUT (5s + 25s). Fifteen minutes is far
# past any of that, so a slow provider, a retry or a few minutes of clock skew between this process and Appwrite is
# never mistaken for a death — and a resident whose message really is stuck still hears within the hour.
QUEUED_GRACE = timedelta(minutes=15)
# How far before a moment an outbox row may be written and still be that moment's own. The row is written by the
# send, moments after the case changed and by this same process, so this only covers the clocks of two machines.
EARLIER_GRACE = timedelta(minutes=5)

# When each moment happened, in the case's own history, for a case whose stored timestamp is missing. The latest
# `resolved` or `escalation_confirmed` entry is when the case itself became resolved: earlier ones are single
# recipients finishing their own part, which is not a moment the resident is written to about.
RESOLUTION_ACTIONS = (CaseHistoryAction.RESOLVED, CaseHistoryAction.ESCALATION_CONFIRMED)
ESCALATION_ACTIONS = (CaseHistoryAction.ESCALATED,)
HISTORY_ACTIONS = [action.value for action in (*RESOLUTION_ACTIONS, *ESCALATION_ACTIONS)]
# The fields a case's own moments are read from, and so the scans that find a case with a recent one. The start of
# work isn't among them: it is stamped on the assignment, not the case, and is scanned for there.
DATED_BY = ("createdAt", "resolvedAt", "escalatedAt")
STARTED_BY = "acknowledgedAt"  # on the assignment: when that recipient started work

NOTHING_RECORDED = "nothing was ever written to the outbox"
BUDGET = "our own daily SMS budget refused it, so nothing was sent to anyone"
NOT_ATTEMPTED = "our own side stopped before the provider was asked, so nothing was sent to anyone"
UNANSWERED = "the provider never answered, so nobody can ever learn whether it went"
STALE = "an outbox row was left queued: the send never finished"
NO_PROVIDER_THEN = "it was recorded but never sent, for want of a provider, and there is one now"

CLOSED_STALE = "the send never finished, so the sweep sent the message again"
CLOSED_REPAIRED = "the sweep sent this message again"

CHANNELS = {channel.value: channel for channel in NotificationChannel}


def _scan(collection: str, field: str, since: str) -> list[dict[str, Any]]:
    listing = get_databases().list_documents(
        DATABASE_ID,
        collection,
        queries=[
            Query.greater_than_equal(field, since),
            Query.order_asc(field),
            Query.limit(SCAN_LIMIT),
        ],
    )
    return [as_record(document) for document in listing.documents]


def _started_lately(since: str, already: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The cases a recipient started work on lately, apart from the ones the scans above have already found.

    A fourth scan, and over the assignments rather than the cases, for the same reason there are three: a case filed
    in March and picked up yesterday owes yesterday's message, and no scan by when it was filed would reach it.
    """
    started = {record["caseId"] for record in _scan(ASSIGNMENTS_COLLECTION, STARTED_BY, since)}
    case_ids = sorted(started - set(already))
    if not case_ids:
        return []
    listing = get_databases().list_documents(
        DATABASE_ID, REPORTS_COLLECTION, queries=[Query.equal("$id", case_ids), Query.limit(len(case_ids))]
    )
    return [as_record(document) for document in listing.documents]


def _recent_cases(now: datetime) -> list[dict[str, Any]]:
    """Every case that reached one of its moments lately: filed, started, resolved, or escalated.

    Four scans rather than one, because a case filed months ago and resolved yesterday owes yesterday's message and
    would never be found by when it was filed. A case found by two of them is looked at once.
    """
    since = (now - WINDOW).isoformat()
    found: dict[str, dict[str, Any]] = {}
    for field in DATED_BY:
        for case in _scan(REPORTS_COLLECTION, field, since):
            found.setdefault(case["$id"], case)
    for case in _started_lately(since, found):
        found.setdefault(case["$id"], case)
    return sorted(found.values(), key=lambda case: str(case.get("createdAt") or ""))


def _records_by_case(collection: str, case_ids: list[str], *narrower: str) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    queries = [Query.equal("caseId", case_ids), *narrower]
    for record in every_record(collection, queries) if case_ids else []:
        found.setdefault(record["caseId"], []).append(record)
    return found


def _agreed(cases: list[dict[str, Any]]) -> dict[str, list[NotificationChannel]]:
    """The channels each resident agreed to, by the one consent rule the ordinary path uses. A case whose resident
    agreed to none isn't here at all."""
    contacts = _records_by_case(CONTACTS_COLLECTION, [case["$id"] for case in cases])  # one per case, by its unique index
    agreed = {case_id: [channel for channel, _ in channels_for(found[0])] for case_id, found in contacts.items()}
    return {case_id: channels for case_id, channels in agreed.items() if channels}


def _at(stamp: Any) -> datetime | None:
    try:
        moment = datetime.fromisoformat(stamp) if isinstance(stamp, str) and stamp else None
    except ValueError:
        return None
    return moment.replace(tzinfo=UTC) if moment is not None and moment.tzinfo is None else moment


def _written_at(row: dict[str, Any]) -> datetime | None:
    return _at(row.get("createdAt") or row.get("$createdAt"))


def _last_entry(history: list[dict[str, Any]], actions: tuple[CaseHistoryAction, ...]) -> datetime | None:
    stamps = [when for entry in history if entry.get("action") in actions and (when := _at(entry.get("timestamp")))]
    return max(stamps, default=None)


@dataclass(frozen=True)
class Moment:
    """One message a case has reached, and when it became owed."""

    event: NotificationEvent
    at: datetime


def _first_start(assignments: list[dict[str, Any]]) -> tuple[bool, datetime | None]:
    """Whether work has started on this case, and when it first did — the earliest recipient's, because the citizen
    is written to when the first one starts and not when the second does. None means it started and nothing stored
    says when: an assignment that is in progress with no readable `acknowledgedAt`."""
    started = [assignment for assignment in assignments if has_started(assignment)]
    stamps = [at for assignment in started if (at := _at(assignment.get(STARTED_BY)))]
    return bool(started), min(stamps, default=None)


def _reached(case: dict[str, Any], history: list[dict[str, Any]],
             assignments: list[dict[str, Any]]) -> dict[NotificationEvent, datetime | None]:
    """Which messages this case has reached, and when each became owed. A value of None means the case reached that
    moment and nothing stored says when.

    Received: every case has one, when it was filed.
    Work started: once any recipient has acknowledged its own assignment, dated from the earliest of them. A case
      reopened by the MCE has its acknowledgements cleared, so work starting on it again is a moment of its own.
    Resolved: while the case IS resolved, which is the one state that message describes. A case resolved and then
      escalated is not owed it any more: after an escalation that message reads "reviewed and resolved", which is
      not what happened, and telling a resident something untrue is a worse harm than a message they never got. A
      case resolved twice — resolved, escalated, then the MCE's ruling — is owed it again, at the second resolution.
    Escalation received: once the citizen has escalated, and still owed after the MCE has ruled, because "we have
      your escalation" stays true. Late is not wrong; it can only be overtaken.
    """
    reached: dict[NotificationEvent, datetime | None] = {NotificationEvent.SUBMITTED: _at(case.get("createdAt"))}
    started, started_at = _first_start(assignments)
    if started:
        reached[NotificationEvent.STARTED] = started_at
    if case.get("status") == CaseStatus.RESOLVED:
        reached[NotificationEvent.RESOLVED] = _at(case.get("resolvedAt")) or _last_entry(history, RESOLUTION_ACTIONS)
    escalated = _at(case.get("escalatedAt")) or _last_entry(history, ESCALATION_ACTIONS)
    if case.get("escalatedAt") or escalated:
        reached[NotificationEvent.ESCALATED] = escalated
    return reached


def _moments(case: dict[str, Any], history: list[dict[str, Any]], assignments: list[dict[str, Any]],
             now: datetime) -> list[Moment]:
    """The moments this case could still be owed a message about, oldest first, so a repair sends them in the order
    they happened. A moment nothing can date is said aloud and left alone: a guessed date would either resend for
    ever or bury a message the resident is owed somewhere in the past."""
    moments = []
    for event, at in _reached(case, history, assignments).items():
        if at is None:
            logger.warning(
                "Missed-message sweep can't date the %s message for case %s: nothing stored says when it happened, "
                "so it is left unsent", event.value, case["$id"]
            )
        elif now - at <= WINDOW:
            moments.append(Moment(event, at))
    return sorted(moments, key=lambda moment: moment.at)


def _answers(row: dict[str, Any], moment: Moment) -> bool:
    """Whether this outbox row is about this moment's message.

    A row for the same event written clearly before the moment is about an earlier one of the same kind: a case
    resolved, escalated and then resolved again by the MCE owes a second resolution message, and the first
    resolution's row must not settle it. A row whose time can't be read is taken as this moment's rather than an
    earlier one — the other way round, a `sent` row nothing can close would be sent again run after run.
    """
    written = _written_at(row)
    return row.get("event") == moment.event and (written is None or written >= moment.at - EARLIER_GRACE)


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
    event: NotificationEvent
    channel: NotificationChannel
    why: str
    rows: list[dict[str, Any]]  # this moment's rows on this channel, closed before the resend


@dataclass(frozen=True)
class Owed:
    case: dict[str, Any]
    repairs: list[Repair]
    rows: list[dict[str, Any]]  # every outbox row the case had before the repair

    @property
    def why(self) -> str:
        return "; ".join(f"{repair.event.value} by {repair.channel.value}: {repair.why}" for repair in self.repairs)


def _repairs(case: dict[str, Any], history: list[dict[str, Any]], assignments: list[dict[str, Any]],
             rows: list[dict[str, Any]], channels: list[NotificationChannel], now: datetime) -> list[Repair]:
    """Every message this case still owes, oldest moment first."""
    repairs: list[Repair] = []
    for moment in _moments(case, history, assignments, now):
        answering = [row for row in rows if _answers(row, moment)]
        for channel, these in _rows_by_channel(channels, answering).items():
            if why := _reason(these, now):
                repairs.append(Repair(moment.event, channel, why, these))
    return repairs


def _owed(cases: list[dict[str, Any]], now: datetime) -> list[Owed]:
    """Of these cases, the ones with a moment and a channel whose resident agreed to it and got no message on it."""
    agreed = _agreed(cases)
    case_ids = list(agreed)
    rows = _records_by_case(NOTIFICATIONS_COLLECTION, case_ids)
    history = _records_by_case(case_history.COLLECTION_ID, case_ids, Query.equal("action", HISTORY_ACTIONS))
    assignments = _records_by_case(ASSIGNMENTS_COLLECTION, case_ids)
    owed: list[Owed] = []
    for case in cases:
        channels = agreed.get(case["$id"])
        if not channels:
            continue
        found = rows.get(case["$id"], [])
        if repairs := _repairs(case, history.get(case["$id"], []), assignments.get(case["$id"], []), found, channels, now):
            owed.append(Owed(case, repairs, found))
    return owed


def _close(repair: Repair, now: datetime) -> None:
    """Closes the rows this repair answers, so this message is never swept a second time.

    The judgement call, stated plainly: the provider may in fact have received one of these, so the resend risks a
    second message. A duplicate that carries nothing but a reference is a smaller harm than a resident who filed a
    report and heard nothing at all — but it is a real cost, so it is paid exactly once. The rows are closed BEFORE
    the send: if this process dies in between, the resident is left with the same silence they already had, whereas
    closing them afterwards would let that same death resend a third and fourth time.

    Rows our own side never attempted — the daily budget, or the counter behind it — are left open on purpose:
    nothing reached anyone, so tomorrow's send is this message arriving late and has no duplicate to pay for.
    """
    for row in repair.rows:
        if _stale_queued(row, now):
            mark_stale_queued(row["$id"], CLOSED_STALE)
        elif provider_unreachable(row) or _no_provider_then(row):
            mark_repaired(row["$id"], CLOSED_REPAIRED, was=str(row.get("error") or "")[:200])


def _send(owed: Owed, now: datetime) -> bool:
    """Sends one case's missed messages, on the unresolved moments and channels only. False means the run should stop."""
    case_id = owed.case["$id"]
    before = {row["$id"] for row in owed.rows}
    for repair in owed.repairs:
        _close(repair, now)
        notify_channel(owed.case, repair.event, repair.channel)
    fresh = [row for row in _records_by_case(NOTIFICATIONS_COLLECTION, [case_id]).get(case_id, []) if row["$id"] not in before]
    if fresh and all(row["status"] == NotificationStatus.FAILED for row in fresh):
        # Nothing this case could be sent on worked, and a row the provider refused is never retried, so every
        # further case risks being written off the same way. The run stops here and leaves the rest to a later one.
        logger.warning("Missed-message sweep stopped at case %s: the message failed to send", case_id)
        return False
    logger.info("Missed-message sweep sent the messages case %s was owed (%s)", case_id, owed.why)
    return True


def run_sweep(now: datetime) -> list[str]:
    """Sends the messages residents were owed and never got. Returns the case IDs it handled."""
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
