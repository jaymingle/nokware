"""Cases as each caller may see them. The view (case_workflow.case_view) decides what is filled in."""

from typing import Any

from app.schemas.cases import CaseAssignment, CaseDetail, CaseEvent, CaseSummary, Contact
from app.services import case_history, case_timeline, issue_voices, report_locations
from app.services.auth import Principal
from app.services.case_history import CaseHistoryAction
from app.services.case_workflow import CaseView, allowed_case_actions, assignment_for, case_view, may_see_contact
from app.services.report_contacts import contact_for
from app.services.report_photos import photo_link
from app.services.report_rules import ClassificationMethod
from app.services.report_taxonomy import TOPICS_BY_ID, Category
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
        voices=(case.get("voiceCount") or 0) if case.get("category") == Category.CIVIC_SERVICE else 0,
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


def _event(entry: dict[str, Any], full: bool, private: bool) -> CaseEvent:
    """In an outline, the classification says only "personal safety", not which kind, and what staff wrote at a
    stage is left out: the MCE reads a personal-safety case's trail, not its content.

    Whether a step reaches the resident is answered here, by the module that decides it, so the portal can say
    "the resident reads this" without keeping its own copy of the rule to drift out of step."""
    note = entry.get("note")
    if not full and entry["action"] == CaseHistoryAction.CLASSIFIED:
        note = "Filed as personal safety."
    return CaseEvent(action=entry["action"], actor_name=entry["actorName"], actor_role=entry["actorRole"], note=note,
                     staff_note=entry.get("staffNote") if full else None, at=entry["timestamp"],
                     seen_by_the_resident=case_timeline.reaches_the_resident(entry["action"], private=private))


def _voice_names(principal: Principal, case: dict[str, Any], assignments: list[dict[str, Any]]) -> list[str] | None:
    """Names given with voices reach the department handling the issue, not the MCE or anyone else."""
    if case.get("category") != Category.CIVIC_SERVICE or assignment_for(principal, assignments) is None:
        return None
    return issue_voices.named_voices(case["$id"]) if case.get("voiceCount") else []


def _photos(case: dict[str, Any], stored_in: str, full: bool) -> list[str]:
    """The photos held under one attribute of the case, as links good for a few minutes. Which stage a photo
    belongs to is the attribute it is stored in — never its file name, which is meaningless on purpose."""
    return [photo_link(name) for name in case.get(stored_in) or []] if full else []


def detail(principal: Principal, case: dict[str, Any], assignments: list[dict[str, Any]]) -> CaseDetail:
    full = case_view(principal, case) == CaseView.FULL
    private = bool(case.get("isSensitive"))
    history = [_event(entry, full, private) for entry in case_history.entries_for(case["$id"])]
    return CaseDetail(
        **summary(principal, case, assignments).model_dump(),
        description=case["description"] if full else None,
        photos=_photos(case, "photoIds", full),
        escalation_photos=_photos(case, "escalationPhotoIds", full),
        escalation_note=case.get("escalationNote") if full else None,
        classification_note=case.get("classificationNote") if full else None,
        contact=_contact(principal, case) if full else None,
        assignments=[_assignment(a, full) for a in assignments],
        history=history,
        voice_names=_voice_names(principal, case, assignments),
        location_shared_at=report_locations.shared_at(principal, case, assignments) if full else None,
    )
