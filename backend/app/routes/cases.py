"""Citizen reports as staff work them. Signed in; each route checks the caller's role and view.

    GET  /api/cases/queue                     a department's or agency's cases, most urgent first
    GET  /api/cases/oversight                 every case, for the MCE (personal safety in outline)
    GET  /api/cases/{id}                      one case, as the caller may see it
    POST /api/cases/{id}/acknowledge          a recipient starts work
    POST /api/cases/{id}/resolve              a recipient finishes its part (note required)
    POST /api/cases/{id}/reassign             the MCE moves a recipient's part (reason required)
    POST /api/cases/{id}/reopen               the MCE sends an escalated case back (note required)
    POST /api/cases/{id}/confirm-resolution   the MCE upholds an escalated case's resolution (note required)
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends

from app.dependencies import require_roles
from app.routes.case_presenters import detail, summary
from app.schemas.cases import CaseDetail, CaseOversight, CaseQueue, NoteRequest, OversightStats, ReassignRequest
from app.schemas.documents import Option
from app.services import case_actions, case_queries
from app.services.auth import Principal, Role
from app.services.case_actions import Outcome
from app.services.case_workflow import CaseView, Reassignment, case_view
from app.services.citizen_reports import NotificationEvent
from app.services.ledger_documents import utc_now
from app.services.notifications import notify_quietly
from app.services.report_followups import CaseNotFound
from app.teams import RECIPIENT_NAMES

router = APIRouter(prefix="/api/cases", tags=["cases"])

Recipient = Annotated[Principal, Depends(require_roles(Role.DEPARTMENT, Role.AGENCY))]
Mce = Annotated[Principal, Depends(require_roles(Role.MCE))]
Staff = Annotated[Principal, Depends(require_roles(Role.DEPARTMENT, Role.AGENCY, Role.MCE))]


@router.get("/queue", response_model=CaseQueue)
def queue(principal: Recipient) -> CaseQueue:
    pairs = case_queries.queue(principal.recipient or "", utc_now())
    return CaseQueue(cases=[summary(principal, case, [mine]) for case, mine in pairs])


@router.get("/oversight", response_model=CaseOversight)
def oversight(principal: Mce) -> CaseOversight:
    cases = case_queries.all_cases()
    return CaseOversight(
        cases=[summary(principal, case, []) for case in cases],
        stats=OversightStats(**case_queries.oversight_stats(cases, utc_now())),
        recipients=[Option(id=team, name=name) for team, name in RECIPIENT_NAMES.items()],
    )


def _visible(principal: Principal, case_id: str) -> CaseDetail:
    """The case as the caller may see it; 404 (not 403) for anyone with no view, so its existence isn't revealed."""
    found = case_queries.load(case_id)
    if found is None or case_view(principal, found[0]) == CaseView.NONE:
        raise CaseNotFound(case_id)
    return detail(principal, *found)


@router.get("/{case_id}", response_model=CaseDetail)
def case(principal: Staff, case_id: str) -> CaseDetail:
    return _visible(principal, case_id)


def _after(principal: Principal, outcome: Outcome, tasks: BackgroundTasks) -> CaseDetail:
    if outcome.resolved:
        tasks.add_task(notify_quietly, outcome.case, NotificationEvent.RESOLVED)
    return _visible(principal, outcome.case["$id"])


@router.post("/{case_id}/acknowledge", response_model=CaseDetail)
def acknowledge(principal: Recipient, case_id: str, tasks: BackgroundTasks) -> CaseDetail:
    return _after(principal, case_actions.acknowledge(principal, case_id, utc_now()), tasks)


@router.post("/{case_id}/resolve", response_model=CaseDetail)
def resolve(principal: Recipient, case_id: str, request: NoteRequest, tasks: BackgroundTasks) -> CaseDetail:
    return _after(principal, case_actions.resolve(principal, case_id, request.note.strip() or None, utc_now()), tasks)


@router.post("/{case_id}/reassign", response_model=CaseDetail)
def reassign(principal: Mce, case_id: str, request: ReassignRequest, tasks: BackgroundTasks) -> CaseDetail:
    move = Reassignment(request.from_recipient, request.to_recipient)
    return _after(principal, case_actions.reassign(principal, case_id, move, request.reason.strip() or None, utc_now()), tasks)


@router.post("/{case_id}/reopen", response_model=CaseDetail)
def reopen(principal: Mce, case_id: str, request: NoteRequest, tasks: BackgroundTasks) -> CaseDetail:
    return _after(principal, case_actions.reopen(principal, case_id, request.note.strip() or None, utc_now()), tasks)


@router.post("/{case_id}/confirm-resolution", response_model=CaseDetail)
def confirm_resolution(principal: Mce, case_id: str, request: NoteRequest, tasks: BackgroundTasks) -> CaseDetail:
    outcome = case_actions.confirm_resolution(principal, case_id, request.note.strip() or None, utc_now())
    return _after(principal, outcome, tasks)
