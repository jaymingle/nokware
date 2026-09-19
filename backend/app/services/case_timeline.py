"""A case's whole trail, as the resident who filed it may read it.

Two rules hold everywhere in here.

Departments only, never a person. The audit trail keeps the name of whoever acted, because an Assembly has to be
able to say who did what; a resident is owed the office, not the civil servant. Nothing this module returns is read
from `actorName`, and nothing in it names an individual.

A personal-safety case is a trail of fixed neutral lines and nothing else. Whoever holds the reference may not be
the person who filed it — a phone gets shared, and a household gets searched — so the timeline says how far along
the case is and no more: no department, no category, no photo, and none of the words staff wrote. Those lines come
from the phrase catalogue, beside the rest of Nokware's fixed text.

Times go out as they were stored, in UTC and in ISO 8601. The web renders them in Africa/Accra.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from app.services.case_history import CaseHistoryAction
from app.services.case_workflow import CaseStatus, closes_at
from app.services.ledger_documents import parse_datetime
from app.services.phrases import Language, phrase
from app.teams import RECIPIENT_NAMES

# The steps a resident is shown, in the order the case took them. Everything else in the trail — the messages
# Nokware sent, the numbers it deleted, a location opened, a classification reconsidered — is the Assembly's own
# record-keeping and says nothing to the person waiting.
SHOWN = {
    CaseHistoryAction.SUBMITTED.value: "filed",
    CaseHistoryAction.ASSIGNED.value: "routed",
    CaseHistoryAction.ACKNOWLEDGED.value: "started",
    CaseHistoryAction.REASSIGNED.value: "reassigned",
    CaseHistoryAction.RESOLVED.value: "resolved",
    CaseHistoryAction.ESCALATED.value: "escalated",
    CaseHistoryAction.ESCALATION_CONFIRMED.value: "mce_response",
    CaseHistoryAction.REOPENED.value: "reopened",
}
SAFETY_LINES = {
    "filed": "case.safety.received",
    "started": "case.safety.in_progress",
    "closed": "case.safety.closed",
}


@dataclass(frozen=True)
class Event:
    action: str  # one of SHOWN's values, or "closed"
    at: str  # ISO 8601, UTC, as stored
    description: str  # the resident's own sentence about this step; an office is named, a person never is
    note: str | None = None  # what staff wrote at this step, when they wrote anything


def reaches_the_resident(action: str, *, private: bool) -> bool:
    """Whether a step of the trail appears on the resident's own status page.

    A personal-safety case shows three fixed lines built from its dates — filed, started, closed — so the trail
    entries behind them are the submission, the first acknowledgement and the resolution. Asked here rather than
    worked out again in the portal, where a second copy of the rule would drift."""
    if private:
        return action in {CaseHistoryAction.SUBMITTED.value, CaseHistoryAction.ACKNOWLEDGED.value,
                          CaseHistoryAction.RESOLVED.value}
    return action in SHOWN


def _named(team: str | None) -> str:
    return RECIPIENT_NAMES.get(team or "", team or "the Assembly")


def _routed(entry: dict[str, Any]) -> str:
    names = [_named(team) for team in str(entry.get("toDept") or "").split(",") if team]
    return f"Routed to {' and '.join(names)}." if names else "Routed to the Assembly."


def _reassigned(entry: dict[str, Any]) -> str:
    return f"Moved from {_named(entry.get('fromDept'))} to {_named(entry.get('toDept'))}."


def _description(action: str, entry: dict[str, Any]) -> str:
    if action == "routed":
        return _routed(entry)
    if action == "reassigned":
        return _reassigned(entry)
    return {
        "filed": "You filed this report.",
        "started": "Work started.",
        "resolved": "Marked resolved.",
        "escalated": "You escalated this report to the MCE's office.",
        "mce_response": "The MCE's office reviewed the escalation and confirmed the resolution.",
        "reopened": "The MCE's office sent it back to be finished.",
        "closed": "This report is closed.",
    }[action]


def _closing(case: dict[str, Any], now: datetime) -> datetime | None:
    """A case closes when nothing more can happen to it, which is a date and not an entry in the trail."""
    closed = closes_at(case)
    return closed if closed is not None and closed <= now else None


def _everyday(case: dict[str, Any], history: list[dict[str, Any]], now: datetime) -> list[Event]:
    events = []
    for entry in history:
        action = SHOWN.get(str(entry.get("action")))
        if action is None or not entry.get("timestamp"):
            continue
        events.append(Event(action, entry["timestamp"], _description(action, entry), entry.get("staffNote") or None))
    closed = _closing(case, now)
    if closed is not None:
        events.append(Event("closed", closed.isoformat(), _description("closed", {})))
    return events


def _started_at(assignments: list[dict[str, Any]]) -> str | None:
    stamps = sorted(a["acknowledgedAt"] for a in assignments if a.get("acknowledgedAt"))
    return stamps[0] if stamps else None


def _safety(case: dict[str, Any], assignments: list[dict[str, Any]], now: datetime,
            language: Language) -> list[Event]:
    """Three fixed lines at most, built from the case's own dates. No entry of the trail is read at all, so no
    department, category or note can reach this list by an oversight somewhere else."""
    steps = [("filed", case.get("createdAt")), ("started", _started_at(assignments))]
    if case.get("status") == CaseStatus.RESOLVED:
        closed = _closing(case, now)
        steps.append(("closed", closed.isoformat() if closed else case.get("resolvedAt")))
    return [
        Event(action, at, phrase(SAFETY_LINES[action], language))
        for action, at in steps
        if at
    ]


def for_resident(case: dict[str, Any], assignments: list[dict[str, Any]], history: list[dict[str, Any]],
                 now: datetime, language: Language = Language.ENGLISH) -> list[dict[str, Any]]:
    """The whole trail, oldest first."""
    private = bool(case.get("isSensitive"))
    events = _safety(case, assignments, now, language) if private else _everyday(case, history, now)
    return [asdict(event) for event in sorted(events, key=lambda event: parse_datetime(event.at) or now)]


def latest(timeline: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The step a phone screen has room for: the last thing that happened."""
    return timeline[-1] if timeline else None
