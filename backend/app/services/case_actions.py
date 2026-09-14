"""Staff changes to a citizen report: a recipient acknowledges and resolves its part; the MCE
reassigns, reopens or confirms. Each re-reads the case under its lock, applies a rule from
case_workflow, writes the change and adds it to the audit trail.

A personal-safety case's trail never carries what anyone wrote about it (the
resolution note, the escalation): the MCE reads the trail but not the content.
The words stay on the case, for its recipients.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services import case_history, case_workflow, report_store
from app.services.auth import Principal
from app.services.case_history import CaseEntry, CaseHistoryAction, actor
from app.services.case_workflow import AssignmentStatus, CaseStatus, Reassignment
from app.services.locks import record_lock
from app.services.report_followups import CaseNotFound, sync_contact_retention
from app.services.workflow import NotAllowed, WrongState
from app.teams import RECIPIENT_NAMES


@dataclass(frozen=True)
class Outcome:
    case: dict[str, Any]
    resolved: bool  # the change resolved the case: the citizen gets the resolution message




def _load(case_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case = report_store.find_case(case_id)
    if case is None:
        raise CaseNotFound(case_id)
    return case, report_store.assignments_for(case_id)


def _named(recipient: str) -> str:
    return RECIPIENT_NAMES.get(recipient, recipient)


def _settle(case: dict[str, Any], assignments: list[dict[str, Any]], now: datetime) -> Outcome:
    """Write the case's status as its assignments now stand; keep the numbers' deletion date in step."""
    updated = report_store.update_case(case["$id"], case_workflow.after_assignments_change(case, assignments, now))
    resolved = updated["status"] == CaseStatus.RESOLVED and case["status"] != CaseStatus.RESOLVED
    if resolved:
        sync_contact_retention(updated)
    return Outcome(updated, resolved)


def _mine(principal: Principal, case: dict[str, Any], assignments: list[dict[str, Any]]) -> dict[str, Any]:
    mine = case_workflow.assignment_for(principal, assignments)
    if mine is None:
        raise NotAllowed("This case isn't assigned to you.")
    if case["status"] == CaseStatus.ESCALATED:
        raise WrongState("The citizen escalated this case; the MCE decides what happens next.")
    return mine


def _replace(assignments: list[dict[str, Any]], updated: dict[str, Any]) -> list[dict[str, Any]]:
    return [updated if a["$id"] == updated["$id"] else a for a in assignments]


def acknowledge(principal: Principal, case_id: str, now: datetime) -> Outcome:
    with record_lock(case_id):
        case, assignments = _load(case_id)
        mine = _mine(principal, case, assignments)
        updated = report_store.update_assignment(mine["$id"], case_workflow.acknowledge(principal, mine, now))
        outcome = _settle(case, _replace(assignments, updated), now)
        entry = CaseEntry(
            CaseHistoryAction.ACKNOWLEDGED,
            actor(principal),
            case["status"],
            outcome.case["status"],
            note=f"{_named(mine['recipient'])} started work.",
        )
        case_history.record(case_id, entry)
        return outcome


def resolve(principal: Principal, case_id: str, note: str | None, now: datetime) -> Outcome:
    with record_lock(case_id):
        case, assignments = _load(case_id)
        mine = _mine(principal, case, assignments)
        updated = report_store.update_assignment(mine["$id"], case_workflow.resolve(principal, mine, note, now))
        outcome = _settle(case, _replace(assignments, updated), now)
        said = f"Resolved by {_named(mine['recipient'])}."
        trail_note = said if case.get("isSensitive") else f"{said} {note}"
        entry = CaseEntry(
            CaseHistoryAction.RESOLVED, actor(principal), case["status"], outcome.case["status"], note=trail_note
        )
        case_history.record(case_id, entry)
        return outcome


def reassign(principal: Principal, case_id: str, move: Reassignment, reason: str | None, now: datetime) -> Outcome:
    """The MCE moves one recipient's part of the case to another. Written to the trail with the reason."""
    with record_lock(case_id):
        case, assignments = _load(case_id)
        case_workflow.check_reassign(principal, case, move, reason)
        leaving = next(a for a in assignments if a.get("active", True) and a["recipient"] == move.from_recipient)
        report_store.update_assignment(leaving["$id"], {"active": False})
        arriving = report_store.create_assignment(
            {
                "caseId": case_id,
                "recipient": move.to_recipient,
                "status": AssignmentStatus.ASSIGNED.value,
                "category": case["category"],
                "severity": case["severity"],
                "active": True,
                "assignedAt": now.isoformat(),
            }
        )
        recipients = [move.to_recipient if r == move.from_recipient else r for r in case["recipients"]]
        case = report_store.update_case(case_id, {"recipients": recipients})
        remaining = [a for a in assignments if a["$id"] != leaving["$id"]] + [arriving]
        outcome = _settle(case, remaining, now)
        entry = CaseEntry(
            CaseHistoryAction.REASSIGNED,
            actor(principal),
            case["status"],
            outcome.case["status"],
            from_recipient=move.from_recipient,
            to_recipient=move.to_recipient,
            note=f"Moved from {_named(move.from_recipient)} to {_named(move.to_recipient)}: {reason}",
        )
        case_history.record(case_id, entry)
        return outcome


def reopen(principal: Principal, case_id: str, note: str | None, now: datetime) -> Outcome:
    """The MCE sends an escalated case back to the same recipients to finish the work."""
    with record_lock(case_id):
        case, assignments = _load(case_id)
        case_workflow.reopen(principal, case, note)
        active = [a for a in assignments if a.get("active", True)]
        reopened = [report_store.update_assignment(a["$id"], case_workflow.reopened_assignment()) for a in active]
        outcome = _settle(case, reopened, now)
        names = " and ".join(_named(a["recipient"]) for a in active)
        entry = CaseEntry(
            CaseHistoryAction.REASSIGNED,
            actor(principal),
            case["status"],
            outcome.case["status"],
            note=f"Reopened for {names}: {note}",
        )
        case_history.record(case_id, entry)
        return outcome


def confirm_resolution(principal: Principal, case_id: str, note: str | None, now: datetime) -> Outcome:
    """The MCE upholds the resolution of an escalated case; the case closes."""
    with record_lock(case_id):
        case, _ = _load(case_id)
        updated = report_store.update_case(case_id, case_workflow.confirm_resolution(principal, case, note, now))
        sync_contact_retention(updated)
        entry = CaseEntry(
            CaseHistoryAction.ESCALATION_CONFIRMED,
            actor(principal),
            case["status"],
            updated["status"],
            note=f"The MCE confirmed the resolution: {note}",
        )
        case_history.record(case_id, entry)
        return Outcome(updated, resolved=True)
