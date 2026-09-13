"""The portal's rules: who may do what to a Ledger document, and what changes.

Pure functions over a document record and a Principal, with no Appwrite calls,
so every rule is unit-tested and the routes cannot drift from each other.

Lifecycle:
  department upload  -> published
  contributor upload -> held; the owning department has 72h to review it
    department accepts -> published
    department disputes -> disputed (the clock stops; disputes wait for the contributor)
      contributor accepts the dispute -> withdrawn
      contributor resubmits (once) -> held, with a fresh 72h clock
      contributor escalates -> still disputed, and the MCE has 72h to rule
        MCE upholds the dispute -> withdrawn
        MCE overrules it -> published
  a clock that runs out publishes the document (held, or escalated and disputed)

Once a clock has run out, the document is publishing: no one can act on it.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from app.services.auth import Principal, Role
from app.services.document_history import HistoryAction
from app.services.ledger_documents import LedgerStatus, Origin, SourceType, parse_datetime
from app.teams import DEPARTMENT_TEAMS

REVIEW_WINDOW = timedelta(hours=72)  # the department's time to review a held document
MCE_WINDOW = timedelta(hours=72)  # the MCE's time to rule on an escalated dispute
MAX_RESUBMISSIONS = 1


class Action(StrEnum):
    ACCEPT = "accept"
    DISPUTE = "dispute"
    ACCEPT_DISPUTE = "accept-dispute"
    RESUBMIT = "resubmit"
    ESCALATE = "escalate"
    UPHOLD = "uphold"
    OVERRULE = "overrule"


class WorkflowError(Exception):
    status_code = 400


class NotAllowed(WorkflowError):
    status_code = 403


class WrongState(WorkflowError):
    status_code = 409


class MissingInput(WorkflowError):
    status_code = 422


@dataclass(frozen=True)
class Rule:
    role: Role
    status: LedgerStatus  # the status the document must be in
    escalated: bool  # whether it must be escalated to the MCE
    history: HistoryAction
    needs_note: bool = False


RULES = {
    Action.ACCEPT: Rule(Role.DEPARTMENT, LedgerStatus.HELD, False, HistoryAction.ACCEPTED),
    Action.DISPUTE: Rule(Role.DEPARTMENT, LedgerStatus.HELD, False, HistoryAction.DISPUTED, needs_note=True),
    Action.ACCEPT_DISPUTE: Rule(Role.CONTRIBUTOR, LedgerStatus.DISPUTED, False, HistoryAction.DISPUTE_ACCEPTED),
    Action.RESUBMIT: Rule(Role.CONTRIBUTOR, LedgerStatus.DISPUTED, False, HistoryAction.RESUBMITTED),
    Action.ESCALATE: Rule(Role.CONTRIBUTOR, LedgerStatus.DISPUTED, False, HistoryAction.ESCALATED, needs_note=True),
    Action.UPHOLD: Rule(Role.MCE, LedgerStatus.DISPUTED, True, HistoryAction.UPHELD),
    Action.OVERRULE: Rule(Role.MCE, LedgerStatus.DISPUTED, True, HistoryAction.OVERRULED),
}
_NOTE_NAMES = {Action.DISPUTE: "a reason for the dispute", Action.ESCALATE: "a response for the MCE"}


@dataclass(frozen=True)
class Transition:
    history: HistoryAction
    from_status: LedgerStatus
    changes: dict[str, Any]  # attributes to write to the document

    @property
    def publishes(self) -> bool:
        return self.changes.get("status") == LedgerStatus.PUBLISHED


def owns(principal: Principal, document: dict[str, Any]) -> bool:
    """Whether the document is the principal's to act on in their role."""
    if principal.role == Role.DEPARTMENT:
        return document.get("department") == principal.department
    if principal.role == Role.CONTRIBUTOR:
        return document.get("uploadedBy") == principal.user_id
    return principal.role == Role.MCE


def can_view(principal: Principal, document: dict[str, Any]) -> bool:
    return document.get("status") == LedgerStatus.PUBLISHED or owns(principal, document)


def clock_expired(document: dict[str, Any], now: datetime) -> bool:
    deadline = parse_datetime(document.get("heldUntil"))
    return deadline is not None and deadline <= now


def check(action: Action, document: dict[str, Any], principal: Principal, now: datetime) -> Rule:
    """The action's rule if the principal may take it now; raises WorkflowError otherwise."""
    rule = RULES[action]
    if principal.role != rule.role or not owns(principal, document):
        raise NotAllowed("You can't take this action on this document.")
    if document.get("status") != rule.status or bool(document.get("escalatedToMce")) != rule.escalated:
        raise WrongState(f"This document is {describe(document)}, so it can't be changed that way.")
    if clock_expired(document, now):
        raise WrongState("The review window has closed; this document is being published automatically.")
    if action == Action.RESUBMIT and (document.get("resubmissionCount") or 0) >= MAX_RESUBMISSIONS:
        raise WrongState("A document can be resubmitted only once. You can escalate the dispute to the MCE instead.")
    return rule


def allowed_actions(document: dict[str, Any], principal: Principal, now: datetime) -> list[Action]:
    allowed = []
    for action in Action:
        try:
            check(action, document, principal, now)
        except WorkflowError:
            continue
        allowed.append(action)
    return allowed


def describe(document: dict[str, Any]) -> str:
    status = document.get("status")
    if status == LedgerStatus.DISPUTED and document.get("escalatedToMce"):
        return "disputed and escalated to the MCE"
    return str(status)


def transition(
    action: Action,
    document: dict[str, Any],
    principal: Principal,
    now: datetime,
    note: str | None = None,
    file_id: str | None = None,
) -> Transition:
    """What taking the action changes. Raises WorkflowError if it isn't allowed."""
    rule = check(action, document, principal, now)
    if rule.needs_note and not note:
        raise MissingInput(f"Give {_NOTE_NAMES[action]}.")
    if action == Action.RESUBMIT and not file_id:
        raise MissingInput("Attach the revised PDF.")
    changes = _changes(action, document, principal, now, note, file_id)
    return Transition(history=rule.history, from_status=LedgerStatus(document["status"]), changes=changes)


def _publish(now: datetime) -> dict[str, Any]:
    return {"status": LedgerStatus.PUBLISHED.value, "publishedAt": now.isoformat(), "heldUntil": None}


def _withdraw() -> dict[str, Any]:
    return {"status": LedgerStatus.WITHDRAWN.value, "heldUntil": None}


def _changes(
    action: Action, document: dict[str, Any], principal: Principal, now: datetime, note: str | None, file_id: str | None
) -> dict[str, Any]:
    if action in (Action.ACCEPT, Action.OVERRULE):
        return _publish(now)
    if action in (Action.ACCEPT_DISPUTE, Action.UPHOLD):
        return _withdraw()
    if action == Action.DISPUTE:
        return {
            "status": LedgerStatus.DISPUTED.value,
            "disputeReason": note,
            "disputedBy": principal.user_id,
            "disputedAt": now.isoformat(),
            "heldUntil": None,  # disputes wait for the contributor, with no clock
        }
    if action == Action.ESCALATE:
        return {"escalatedToMce": True, "contributorResponse": note, "heldUntil": (now + MCE_WINDOW).isoformat()}
    # Resubmit: the new file goes back to the department on a fresh clock. The
    # earlier dispute stays on the record so the department can see it.
    return {
        "status": LedgerStatus.HELD.value,
        "fileId": file_id,
        "contributorResponse": note,
        "resubmissionCount": (document.get("resubmissionCount") or 0) + 1,
        "heldUntil": (now + REVIEW_WINDOW).isoformat(),
    }


def expiry(document: dict[str, Any], now: datetime) -> Transition | None:
    """The automatic publication due for a document whose clock ran out, if any."""
    status = document.get("status")
    on_clock = status == LedgerStatus.HELD or (status == LedgerStatus.DISPUTED and document.get("escalatedToMce"))
    if not on_clock or not clock_expired(document, now):
        return None
    return Transition(history=HistoryAction.AUTO_PUBLISHED, from_status=LedgerStatus(status), changes=_publish(now))


@dataclass(frozen=True)
class Submission:
    """The caller-supplied fields of a new document, already validated for shape."""

    title: str
    category: str
    document_year: int | None
    department: str | None
    source_url: str | None


def new_document(principal: Principal, submission: Submission, file_id: str, now: datetime) -> dict[str, Any]:
    """The attributes of a new upload. Raises WorkflowError if the role can't upload it."""
    common = {
        "title": submission.title,
        "category": submission.category,
        "documentYear": submission.document_year,
        "fileId": file_id,
        "uploadedBy": principal.user_id,
        "origin": Origin.PORTAL.value,
    }
    if principal.role == Role.DEPARTMENT:
        return {**common, **_agency_fields(principal, submission, now)}
    if principal.role == Role.CONTRIBUTOR:
        return {**common, **_contributor_fields(submission, now)}
    raise NotAllowed("Only departments and contributors upload documents to the Ledger.")


def _agency_fields(principal: Principal, submission: Submission, now: datetime) -> dict[str, Any]:
    if submission.department not in (None, principal.department):
        raise NotAllowed("Departments publish only under their own name.")
    return {
        "department": principal.department,
        "sourceType": SourceType.AGENCY.value,
        "sourceUrl": submission.source_url,
        **_publish(now),
    }


def _contributor_fields(submission: Submission, now: datetime) -> dict[str, Any]:
    if submission.department not in DEPARTMENT_TEAMS:
        raise MissingInput("Choose the department this document belongs to.")
    if not submission.source_url:
        raise MissingInput("Give the public web address where this document came from.")
    return {
        "department": submission.department,
        "sourceType": SourceType.CONTRIBUTOR.value,
        "sourceUrl": submission.source_url,
        "status": LedgerStatus.HELD.value,
        "heldUntil": (now + REVIEW_WINDOW).isoformat(),
        "resubmissionCount": 0,
        "escalatedToMce": False,
    }
