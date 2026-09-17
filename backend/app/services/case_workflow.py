"""A citizen report's lifecycle, and who may see what.

A case has one assignment per recipient (two for some personal-safety cases).
Each recipient acknowledges and resolves its own assignment; the case is
resolved when every active assignment is.

    submitted -> assigned -> in_progress -> resolved
    resolved -> escalated (the citizen, once, within 14 days)
      escalated -> assigned (the MCE reassigns it, or reopens it with the same recipients)
      escalated -> resolved (the MCE confirms the resolution)

"submitted" lasts only while a report waits for a person to route it (triage).
Errors reuse the Ledger workflow's, so they map to the same HTTP statuses.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from app.services.auth import Principal, Role
from app.services.ledger_documents import parse_datetime
from app.services.report_taxonomy import POLICE, SOCIAL_WELFARE, Category
from app.services.workflow import MissingInput, NotAllowed, WrongState
from app.teams import RECIPIENT_NAMES

ESCALATION_WINDOW = timedelta(days=14)
CONTACT_RETENTION = timedelta(days=30)  # after the case closes, the citizen's numbers are deleted
SMALL_COUNT = 5  # counts below this are never shown as numbers
# Never a department that has no business with a personal-safety case.
SAFETY_RECIPIENTS = frozenset({POLICE, SOCIAL_WELFARE})


class CaseStatus(StrEnum):
    SUBMITTED = "submitted"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class AssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


def case_status(assignments: list[dict[str, Any]]) -> CaseStatus:
    statuses = {a["status"] for a in assignments if a.get("active", True)}
    if not statuses:
        return CaseStatus.SUBMITTED
    if statuses == {AssignmentStatus.RESOLVED}:
        return CaseStatus.RESOLVED
    if AssignmentStatus.IN_PROGRESS in statuses or AssignmentStatus.RESOLVED in statuses:
        return CaseStatus.IN_PROGRESS
    return CaseStatus.ASSIGNED


class CaseAction(StrEnum):
    ACKNOWLEDGE = "acknowledge"
    RESOLVE = "resolve"
    REASSIGN = "reassign"
    REOPEN = "reopen"
    CONFIRM_RESOLUTION = "confirm-resolution"


def assignment_for(principal: Principal, assignments: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (a for a in assignments if a.get("active", True) and principal.recipient and a["recipient"] == principal.recipient),
        None,
    )


def allowed_case_actions(principal: Principal, case: dict[str, Any], assignments: list[dict[str, Any]]) -> list[CaseAction]:
    """Exactly what the server would accept from the caller now."""
    status = case.get("status")
    if principal.role == Role.MCE:
        movable = status != CaseStatus.RESOLVED and bool(reassign_targets(case))
        actions = [CaseAction.REASSIGN] if movable else []
        return actions + ([CaseAction.REOPEN, CaseAction.CONFIRM_RESOLUTION] if status == CaseStatus.ESCALATED else [])
    mine = assignment_for(principal, assignments)
    if mine is None or status == CaseStatus.ESCALATED:  # an escalated case waits for the MCE
        return []
    actions = [CaseAction.ACKNOWLEDGE] if mine["status"] == AssignmentStatus.ASSIGNED else []
    return actions + ([CaseAction.RESOLVE] if mine["status"] != AssignmentStatus.RESOLVED else [])


def reassign_targets(case: dict[str, Any]) -> list[str]:
    """Only safety services for personal safety."""
    allowed = SAFETY_RECIPIENTS if case.get("category") == Category.PERSONAL_SAFETY else RECIPIENT_NAMES
    current = set(case.get("recipients") or [])
    return [recipient for recipient in allowed if recipient not in current]


def _own_assignment(principal: Principal, assignment: dict[str, Any]) -> None:
    if principal.role not in (Role.DEPARTMENT, Role.AGENCY) or assignment.get("recipient") != principal.recipient:
        raise NotAllowed("This case isn't assigned to you.")
    if not assignment.get("active", True):
        raise WrongState("This case has been moved to another department.")


def acknowledge(principal: Principal, assignment: dict[str, Any], now: datetime) -> dict[str, Any]:
    _own_assignment(principal, assignment)
    if assignment["status"] != AssignmentStatus.ASSIGNED:
        raise WrongState("Work on this case has already started.")
    return {"status": AssignmentStatus.IN_PROGRESS.value, "acknowledgedAt": now.isoformat()}


def resolve(principal: Principal, assignment: dict[str, Any], note: str | None, now: datetime) -> dict[str, Any]:
    _own_assignment(principal, assignment)
    if assignment["status"] == AssignmentStatus.RESOLVED:
        raise WrongState("This case is already resolved.")
    if not note:
        raise MissingInput("Say what was done, for the citizen and the record.")
    return {"status": AssignmentStatus.RESOLVED.value, "resolvedAt": now.isoformat(), "resolutionNote": note}


def after_assignments_change(case: dict[str, Any], assignments: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    status = case_status(assignments)
    changes: dict[str, Any] = {"status": status.value}
    if status == CaseStatus.RESOLVED and case.get("status") != CaseStatus.RESOLVED:
        changes["resolvedAt"] = now.isoformat()
    return changes


def escalation_open(case: dict[str, Any], now: datetime) -> bool:
    resolved_at = parse_datetime(case.get("resolvedAt"))
    return (
        case.get("status") == CaseStatus.RESOLVED
        and not case.get("escalatedAt")
        and resolved_at is not None
        and now < resolved_at + ESCALATION_WINDOW
    )


def escalate(case: dict[str, Any], note: str | None, now: datetime) -> dict[str, Any]:
    if case.get("escalatedAt"):
        raise WrongState("This case has already been escalated once.")
    if not escalation_open(case, now):
        raise WrongState("A case can be escalated only within 14 days of being resolved.")
    if not note:
        raise MissingInput("Say what is still wrong.")
    return {"status": CaseStatus.ESCALATED.value, "escalatedAt": now.isoformat(), "escalationNote": note}


def _mce(principal: Principal) -> None:
    if principal.role != Role.MCE:
        raise NotAllowed("Only the MCE can reassign cases or rule on escalations.")


@dataclass(frozen=True)
class Reassignment:
    from_recipient: str
    to_recipient: str


def check_reassign(principal: Principal, case: dict[str, Any], move: Reassignment, reason: str | None) -> None:
    _mce(principal)
    if case.get("status") == CaseStatus.RESOLVED:
        raise WrongState("A resolved case can't be reassigned; the citizen can escalate it.")
    recipients = set(case.get("recipients") or [])
    if move.from_recipient not in recipients:
        raise WrongState("The case isn't with that recipient.")
    if move.to_recipient not in RECIPIENT_NAMES or move.to_recipient in recipients:
        raise WrongState("Choose a recipient the case isn't already with.")
    if case.get("category") == Category.PERSONAL_SAFETY and move.to_recipient not in SAFETY_RECIPIENTS:
        raise WrongState("A personal-safety case can only move between Police and Social Welfare.")
    if not reason:
        raise MissingInput("Give a reason; it is written to the audit trail.")


def confirm_resolution(principal: Principal, case: dict[str, Any], note: str | None, now: datetime) -> dict[str, Any]:
    _mce(principal)
    if case.get("status") != CaseStatus.ESCALATED:
        raise WrongState("Only an escalated case can be confirmed as resolved.")
    if not note:
        raise MissingInput("Say why the resolution stands, for the citizen and the record.")
    return {"status": CaseStatus.RESOLVED.value, "resolvedAt": now.isoformat()}


def reopen(principal: Principal, case: dict[str, Any], note: str | None) -> None:
    _mce(principal)
    if case.get("status") != CaseStatus.ESCALATED:
        raise WrongState("Only an escalated case can be reopened.")
    if not note:
        raise MissingInput("Say what is still to be done; the recipients see it.")


def reopened_assignment() -> dict[str, Any]:
    """The earlier resolution stays in the audit trail."""
    return {"status": AssignmentStatus.ASSIGNED.value, "acknowledgedAt": None, "resolvedAt": None, "resolutionNote": None}


def closes_at(case: dict[str, Any]) -> datetime | None:
    """When nothing more can happen to a case: at a final resolution, or when the escalation window ends."""
    resolved_at = parse_datetime(case.get("resolvedAt"))
    if case.get("status") != CaseStatus.RESOLVED or resolved_at is None:
        return None
    return resolved_at if case.get("escalatedAt") else resolved_at + ESCALATION_WINDOW


def contact_purge_at(case: dict[str, Any]) -> datetime | None:
    closed = closes_at(case)
    return closed + CONTACT_RETENTION if closed else None


class CaseView(StrEnum):
    FULL = "full"  # everything, including the description and photos
    OVERSIGHT = "oversight"  # status, recipients, age and audit trail; no description or photos
    NONE = "none"


def case_view(principal: Principal, case: dict[str, Any]) -> CaseView:
    if principal.recipient is not None and principal.recipient in (case.get("recipients") or []):
        return CaseView.FULL
    if principal.role == Role.MCE:
        return CaseView.OVERSIGHT if case.get("category") == Category.PERSONAL_SAFETY else CaseView.FULL
    return CaseView.NONE


def may_see_contact(principal: Principal, case: dict[str, Any], contact: dict[str, Any]) -> bool:
    """A recipient sees the citizen's number only if the citizen allowed a call about this case."""
    return bool(contact.get("callbackConsent")) and case_view(principal, case) == CaseView.FULL and principal.role != Role.MCE


def shown_count(count: int) -> int | None:
    # Zero is hidden too, unlike stats.shown: a personal-safety count under 5 is never shown, not even as "none".
    return count if count >= SMALL_COUNT else None
