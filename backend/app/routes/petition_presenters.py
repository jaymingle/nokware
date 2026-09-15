"""Petitions as each audience sees them: the public, the creator, the MCE.

The public never sees a number, a refusal's note to the creator, a petition
that was never published, or the creator's name unless they chose to show it.
The public timeline says the MCE decided, never which person.
"""

from dataclasses import asdict
from typing import Any

from app.schemas.petitions import (
    DocumentRef,
    LedgerMatch,
    LinkedIssue,
    Moderation,
    OwnPetition,
    PetitionCard,
    PetitionDetail,
    Refusal,
    RefusalCount,
    RefusalReason,
    ReviewItem,
    TimelineEntry,
)
from app.services import issue_voices, ledger_documents, petition_ledger, petitions
from app.services.case_workflow import CaseStatus
from app.services.petition_ledger import describe
from app.services.petition_rules import MAX_RESUBMISSIONS, REFUSALS, PetitionAction, creator_actions
from app.services.report_taxonomy import TOPICS_BY_ID
from app.teams import RECIPIENT_NAMES
from app.wards import sub_metros, wards

PUBLIC_ACTIONS = {a.value for a in PetitionAction} - {PetitionAction.MADE_ANONYMOUS.value}
ISSUE_STAGES = {CaseStatus.SUBMITTED: "received", CaseStatus.ASSIGNED: "received", CaseStatus.IN_PROGRESS: "in_progress",
                CaseStatus.ESCALATED: "escalated"}


def _place(petition: dict[str, Any]) -> tuple[str | None, str | None]:
    ward, sub_metro = wards().get(petition.get("wardLocation") or ""), sub_metros().get(petition.get("subMetro") or "")
    return (ward.name if ward else None), (sub_metro.name if sub_metro else None)


def _card_fields(petition: dict[str, Any]) -> dict[str, Any]:
    area, sub_metro = _place(petition)
    return {
        "code": petition["code"], "title": petition["title"], "topic": TOPICS_BY_ID[petition["topic"]].label,
        "departments": [RECIPIENT_NAMES.get(r, r) for r in petition.get("recipients") or []], "scope": petition["scope"],
        "area": area, "sub_metro": sub_metro, "status": petition["status"], "published_at": petition.get("publishedAt"),
        "published_by": petition.get("publishedBy"), "closes_at": petition.get("closesAt"), "closed_at": petition.get("closedAt"),
        "threshold": petition.get("threshold"), "signatures": petition.get("signatureCount") or 0,
        "started_by": petition.get("creatorName"),
    }


def card(petition: dict[str, Any]) -> PetitionCard:
    return PetitionCard(**_card_fields(petition))


def timeline(entries: list[dict[str, Any]]) -> list[TimelineEntry]:
    return [TimelineEntry(action=e["action"], at=e["at"], reason=REFUSALS[e["reason"]].label if e.get("reason") in REFUSALS else None)
            for e in entries if e["action"] in PUBLIC_ACTIONS]


def linked_issue(public_id: str | None) -> LinkedIssue | None:
    """The civic issue a petition links to, as the issue list shows it; "resolved" once it has closed."""
    if not public_id:
        return None
    try:
        case = issue_voices.civic_issue(public_id)
    except issue_voices.IssueNotFound:
        return None
    ward = wards().get(case.get("wardLocation") or "")
    return LinkedIssue(public_id=public_id, topic=TOPICS_BY_ID[case["topic"]].label, ward=ward.name if ward else None,
                       stage=ISSUE_STAGES.get(CaseStatus(case["status"]), "resolved"), voices=case.get("voiceCount") or 0)


def cited(document_ids: list[str] | None) -> list[DocumentRef]:
    found = ledger_documents.get_documents(document_ids or [])
    return [DocumentRef(**describe(found[d])) for d in document_ids or [] if d in found]


def detail(petition: dict[str, Any]) -> PetitionDetail:
    return PetitionDetail(**_card_fields(petition), body=petition["body"], timeline=timeline(petitions.history(petition["$id"])),
                          issue=linked_issue(petition.get("issueId")), documents=cited(petition.get("documentIds")))


def ledger_matches(petition: dict[str, Any]) -> list[LedgerMatch]:
    query = petition_ledger.query_for(petition["title"], petition["body"], TOPICS_BY_ID[petition["topic"]].label)
    return [LedgerMatch(**asdict(match)) for match in petition_ledger.cached_search(query)]


def _refusal(reason: str | None, note: str | None, duplicate_of: str | None) -> Refusal | None:
    if reason not in REFUSALS:
        return None
    return Refusal(reason=reason, label=REFUSALS[reason].label, explanation=REFUSALS[reason].explanation, note=note,
                   duplicate_of=duplicate_of)


def own(petition: dict[str, Any]) -> OwnPetition:
    return OwnPetition(
        **_card_fields(petition), body=petition["body"], topic_id=petition["topic"], ward_id=petition.get("wardLocation"),
        issue_id=petition.get("issueId"), document_ids=petition.get("documentIds") or [],
        submitted_at=petition.get("submittedAt"), review_deadline=petition.get("reviewDeadline"),
        refusal=_refusal(petition.get("refusalReason"), petition.get("refusalNote"), petition.get("duplicateOf")),
        resubmissions_left=max(0, MAX_RESUBMISSIONS - (petition.get("resubmissions") or 0)), actions=creator_actions(petition),
    )


def review_item(petition: dict[str, Any]) -> ReviewItem:
    fields = _card_fields(petition)
    earlier = [_refusal(e.get("reason"), e.get("note"), None) for e in petitions.history(petition["$id"])
               if e["action"] == PetitionAction.REFUSED]
    return ReviewItem(
        code=fields["code"], title=fields["title"], body=petition["body"], topic=fields["topic"], departments=fields["departments"],
        scope=fields["scope"], area=fields["area"], sub_metro=fields["sub_metro"], started_by=fields["started_by"],
        submitted_at=petition["submittedAt"], review_deadline=petition["reviewDeadline"],
        resubmissions=petition.get("resubmissions") or 0, earlier_refusals=[r for r in earlier if r],
        issue=linked_issue(petition.get("issueId")), documents=cited(petition.get("documentIds")),
    )


def refusal_reasons() -> list[RefusalReason]:
    return [RefusalReason(id=key, label=r.label, explanation=r.explanation) for key, r in REFUSALS.items()]


def moderation(counts: dict[str, Any]) -> Moderation:
    refusals = [RefusalCount(reason=key, label=r.label, count=counts["refusals"].get(key, 0)) for key, r in REFUSALS.items()]
    return Moderation(awaiting=counts["awaiting"], published_by_mce=counts["published_by_mce"],
                      published_automatically=counts["published_automatically"], refusals=refusals,
                      refusals_total=sum(r.count for r in refusals))
