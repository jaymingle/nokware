"""Cases as each caller may see them. The view (case_workflow.case_view) decides what is filled in."""

from typing import Any

from app.schemas.cases import CaseAssignment, CaseDetail, CaseEvent, CaseSummary, Contact
from app.services import case_history
from app.services.case_history import CaseHistoryAction
from app.services.auth import Principal
from app.services.case_workflow import CaseView, allowed_case_actions, assignment_for, case_view, may_see_contact
from app.services.report_contacts import contact_for
from app.services.report_photos import photo_link
from app.services.report_rules import ClassificationMethod
from app.services.report_taxonomy import TOPICS_BY_ID
from app.teams import RECIPIENT_NAMES
from app.wards import sub_metros, wards

EXCERPT_LENGTH = 160
OUTLINE_TOPIC = "Personal safety"


def _place(case: dict[str, Any]) -> str | None:
    ward, sub_metro = wards().get(case.get("wardLocation") or ""), sub_metros().get(case.get("subMetro") or "")
    names = [place.name for place in (ward, sub_metro) if place]
    return ", ".join(names) or None


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= EXCERPT_LENGTH else flat[: EXCERPT_LENGTH - 1].rstrip() + "…"


def summary(principal: Principal, case: dict[str, Any], assignments: list[dict[str, Any]]) -> CaseSummary:
    full = case_view(principal, case) == CaseView.FULL
    mine = assignment_for(principal, assignments)
    return CaseSummary(
        case_id=case["$id"],
        reference=case["reference"],
        private=case["isSensitive"],
        view="full" if full else "oversight",
        topic=TOPICS_BY_ID[case["topic"]].label if full else OUTLINE_TOPIC,
        severity=case["severity"],
        status=case["status"],
        my_status=mine["status"] if mine else None,
        place=_place(case) if full else None,
        excerpt=_excerpt(case["description"]) if full else None,
        submitted_at=case["createdAt"],
        recipients=[RECIPIENT_NAMES.get(r, r) for r in case["recipients"]],
        escalated=bool(case.get("escalatedAt")),
        needs_routing=case.get("classifiedBy") == ClassificationMethod.TRIAGE,
        allowed_actions=allowed_case_actions(principal, case, assignments),
    )


def _assignment(a: dict[str, Any], full: bool) -> CaseAssignment:
    return CaseAssignment(
        recipient=a["recipient"],
        name=RECIPIENT_NAMES.get(a["recipient"], a["recipient"]),
        status=a["status"],
        active=a.get("active", True),
        acknowledged_at=a.get("acknowledgedAt"),
        resolved_at=a.get("resolvedAt"),
        resolution_note=a.get("resolutionNote") if full else None,
    )


def _contact(principal: Principal, case: dict[str, Any]) -> Contact | None:
    contact = contact_for(case["$id"])
    if not contact or not may_see_contact(principal, case, contact):
        return None
    return Contact(phone=contact.get("phone"), whatsapp=contact.get("whatsapp"))


def _event(entry: dict[str, Any], full: bool) -> CaseEvent:
    """An audit entry. In an outline, the classification says only "personal safety", not which kind."""
    note = entry.get("note")
    if not full and entry["action"] == CaseHistoryAction.CLASSIFIED:
        note = "Filed as personal safety."
    return CaseEvent(action=entry["action"], actor_name=entry["actorName"], actor_role=entry["actorRole"], note=note, at=entry["timestamp"])


def detail(principal: Principal, case: dict[str, Any], assignments: list[dict[str, Any]]) -> CaseDetail:
    full = case_view(principal, case) == CaseView.FULL
    history = [_event(entry, full) for entry in case_history.entries_for(case["$id"])]
    return CaseDetail(
        **summary(principal, case, assignments).model_dump(),
        description=case["description"] if full else None,
        photos=[photo_link(p) for p in case.get("photoIds") or []] if full else [],
        escalation_note=case.get("escalationNote") if full else None,
        classification_note=case.get("classificationNote") if full else None,
        contact=_contact(principal, case) if full else None,
        assignments=[_assignment(a, full) for a in assignments],
        history=history,
    )
