"""Petitions as each audience sees them: the public, the creator, the contributor, the MCE.

The public never sees a phone number, a contributor's internal note, or the creator's name unless they chose to
show it. The public timeline says a petition was removed and on what ground, never by whom: a ground is a ground
whoever names it, and naming the contributor would turn moderation into a quarrel between two residents.

A department's note is public, under the department's name and never the officer's: the Assembly answers as the
Assembly. The petitioner's reply is public too, under whatever name their petition carries — none, if they started
it anonymously.

A removed petition is not presented here at all. Its page is the tombstone, which petition_removals builds from the
removal record, so nothing of the petition can reach a reader through this module by an oversight.
"""

from dataclasses import asdict
from typing import Any

from app.routes.issues import STAGES as ISSUE_STAGES
from app.schemas.petitions import (
    AwaitingResponse,
    DepartmentShare,
    DismissalOption,
    DocumentRef,
    GroundOption,
    LedgerMatch,
    LinkedIssue,
    MySignature,
    NamedSignature,
    OwnPetition,
    PetitionCard,
    PetitionDetail,
    PetitionReply,
    PetitionResponse,
    RemovalCount,
    RemovalNotice,
    Removals,
    ReportedPetition,
    SharedPetition,
    TimelineEntry,
    Tombstone,
    VersionEntry,
)
from app.services import (
    issue_voices,
    ledger_documents,
    petition_departments,
    petition_ledger,
    petition_signatures,
    petition_versions,
    petitions,
)
from app.services.case_workflow import CaseStatus
from app.services.petition_grounds import DISMISSALS, GROUNDS, Ground, dismissal_in_plain_words, in_plain_words
from app.services.petition_images import image_links
from app.services.petition_ledger import describe
from app.services.petition_removals import Tombstone as RemovalTombstone
from app.services.petition_reports import Reported
from app.services.petition_rules import (
    LEGACY_LABELS,
    LEGACY_STATUSES,
    RESPONSE_KINDS,
    STATUS_WORDS,
    PetitionAction,
    PetitionStatus,
    creator_actions,
    days_late,
    responded_late,
    version_of,
)
from app.services.phrases import phrase
from app.services.report_taxonomy import TOPICS_BY_ID
from app.teams import DEPARTMENT_NAMES, RECIPIENT_NAMES
from app.wards import sub_metros, wards

PUBLIC_ACTIONS = {a.value for a in PetitionAction} - {PetitionAction.MADE_ANONYMOUS.value, PetitionAction.CREATOR_NOTIFIED.value}


def _place(petition: dict[str, Any]) -> tuple[str | None, str | None]:
    ward, sub_metro = wards().get(petition.get("wardLocation") or ""), sub_metros().get(petition.get("subMetro") or "")
    return (ward.name if ward else None), (sub_metro.name if sub_metro else None)


def status_words(status: str) -> str:
    return phrase(STATUS_WORDS[PetitionStatus(status)])


def _card_fields(petition: dict[str, Any]) -> dict[str, Any]:
    area, sub_metro = _place(petition)
    return {
        "code": petition["code"], "title": petition["title"], "topic": TOPICS_BY_ID[petition["topic"]].label,
        "departments": [RECIPIENT_NAMES.get(r, r) for r in petition.get("recipients") or []], "scope": petition["scope"],
        "area": area, "sub_metro": sub_metro, "status": petition["status"],
        "status_label": status_words(str(petition["status"])), "published_at": petition.get("publishedAt"),
        "closes_at": petition.get("closesAt"), "closed_at": petition.get("closedAt"),
        "threshold": petition.get("threshold"), "signatures": petition.get("signatureCount") or 0,
        "started_by": petition.get("creatorName"),
        "threshold_reached_at": petition.get("thresholdReachedAt"), "response_due": petition.get("responseDue"),
        "responded_at": petition.get("respondedAt"), "unanswered_at": petition.get("noResponseAt"),
        "response_label": RESPONSE_KINDS[petition["responseKind"]].label if petition.get("responseKind") in RESPONSE_KINDS else None,
        "version": version_of(petition), "versioned_at": petition.get("versionedAt"),
        "removals": int(petition.get("removalCount") or 0),
    }


def card(petition: dict[str, Any]) -> PetitionCard:
    return PetitionCard(**_card_fields(petition))


def _reason_words(reason: str | None) -> str | None:
    """A removal's ground, or the department a petition was shared with."""
    if reason in set(Ground):
        return in_plain_words(Ground(reason))
    return DEPARTMENT_NAMES.get(reason or "")


# The one line scripts/migrate_petitions.py leaves on a petition that was already in the database when the review
# process was taken out: written by the system, with the status the row carried before as its reason. Nothing else
# records a status as a reason, which is what tells this line from a removal's or a share's.
MOVED_TO_NEW_PROCESS = "moved_to_new_process"
STATUS_BEFORE_THE_MOVE = {*LEGACY_STATUSES, *(status.value for status in PetitionStatus)}


def _moved_in_the_migration(entry: dict[str, Any]) -> bool:
    return entry.get("actorRole") == "system" and str(entry.get("reason") or "") in STATUS_BEFORE_THE_MOVE


def _moved_entry(entry: dict[str, Any]) -> TimelineEntry:
    """What the move did, said in words that are true of it: this petition came to the new process on this date.
    The old process's ending is named only where the move actually closed the petition — the same line on one the
    move published would read as a publication with a closing reason, which is nothing that happened."""
    closed = entry["action"] == PetitionAction.CLOSED.value
    return TimelineEntry(action=MOVED_TO_NEW_PROCESS, at=entry["at"],
                         reason=_ended_by_the_old_process(entry["reason"]) if closed else None)


def _ended_by_the_old_process(status_before: str) -> str | None:
    """How the old process ended a petition, where it did. A status it simply kept has nothing to say here."""
    return phrase(LEGACY_LABELS[status_before]) if status_before in LEGACY_LABELS else None


def _entry(entry: dict[str, Any]) -> TimelineEntry:
    return TimelineEntry(action=entry["action"], at=entry["at"], reason=_reason_words(entry.get("reason")))


def timeline(entries: list[dict[str, Any]]) -> list[TimelineEntry]:
    return [_moved_entry(e) if _moved_in_the_migration(e) else _entry(e)
            for e in entries if e["action"] in PUBLIC_ACTIONS]


def versions(petition_id: str) -> list[VersionEntry]:
    return [VersionEntry(version=int(v["version"]), at=v["at"], title=v["title"], changed=changed)
            for v, changed in petition_versions.history(petition_id)]


def linked_issue(public_id: str | None) -> LinkedIssue | None:
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


def reply(petition: dict[str, Any]) -> PetitionReply | None:
    """Read from the petition beside the response it answers, so it is never shown without one."""
    if not petition.get("replyAt") or not petition.get("replyText"):
        return None
    return PetitionReply(text=petition["replyText"], at=petition["replyAt"])


def share(row: dict[str, Any]) -> DepartmentShare:
    """A department stands under its own name here; the officer who wrote the note is named only in the trail."""
    department = str(row["department"])
    return DepartmentShare(department=DEPARTMENT_NAMES.get(department, department), shared_at=str(row["sharedAt"]),
                           note=row.get("note"), note_at=row.get("noteAt"))


def shares(rows: list[dict[str, Any]]) -> list[DepartmentShare]:
    return [share(row) for row in rows]


def shared(item: petition_departments.Shared) -> SharedPetition:
    """For the department's own queue: the petition it was asked about, and what it has said so far."""
    return SharedPetition(petition=card(item.petition), shared_at=str(item.share["sharedAt"]),
                          note=item.share.get("note"), note_at=item.share.get("noteAt"))


def response(petition: dict[str, Any]) -> PetitionResponse | None:
    kind = petition.get("responseKind")
    if kind not in RESPONSE_KINDS or not petition.get("respondedAt"):
        return None
    department = petition.get("responseDepartment")
    return PetitionResponse(kind=kind, label=RESPONSE_KINDS[kind].label, text=petition["responseText"],
                            department=RECIPIENT_NAMES.get(department, department) if department else None,
                            documents=cited(petition.get("responseDocumentIds")), responded_at=petition["respondedAt"],
                            late=responded_late(petition), days_late=days_late(petition), reply=reply(petition))


def detail(petition: dict[str, Any]) -> PetitionDetail:
    return PetitionDetail(**_card_fields(petition), body=petition["body"], images=image_links(petition.get("imageIds")),
                          timeline=timeline(petitions.history(petition["$id"])), versions=versions(petition["$id"]),
                          signatures_on_earlier_versions=petition_signatures.on_earlier_versions(petition),
                          issue=linked_issue(petition.get("issueId")), documents=cited(petition.get("documentIds")),
                          response=response(petition))


def tombstone(stone: RemovalTombstone) -> Tombstone:
    return Tombstone(**asdict(stone))


def ledger_matches(petition: dict[str, Any]) -> list[LedgerMatch]:
    query = petition_ledger.query_for(petition["title"], petition["body"], TOPICS_BY_ID[petition["topic"]].label)
    return [LedgerMatch(**asdict(match)) for match in petition_ledger.cached_search(query)]


def _removal_notice(petition: dict[str, Any]) -> RemovalNotice | None:
    ground = petition.get("removalGround")
    if ground not in set(Ground) or not petition.get("removedAt"):
        return None
    return RemovalNotice(ground=ground, label=in_plain_words(Ground(ground)), removed_at=petition["removedAt"],
                         duplicate_of=petition.get("removalDuplicateOf"))


def own(petition: dict[str, Any]) -> OwnPetition:
    return OwnPetition(
        **_card_fields(petition), body=petition["body"], images=image_links(petition.get("imageIds")),
        topic_id=petition["topic"], ward_id=petition.get("wardLocation"), issue_id=petition.get("issueId"),
        document_ids=petition.get("documentIds") or [], image_ids=petition.get("imageIds") or [],
        submitted_at=petition.get("submittedAt"), removal=_removal_notice(petition), actions=creator_actions(petition),
    )


def grounds() -> list[GroundOption]:
    return [GroundOption(id=ground.value, label=in_plain_words(ground), needs_petition_number=rule.names_another_petition)
            for ground, rule in GROUNDS.items()]


def dismissal_reasons() -> list[DismissalOption]:
    return [DismissalOption(id=reason.value, label=dismissal_in_plain_words(reason)) for reason in DISMISSALS]


def reported(item: Reported) -> ReportedPetition:
    ground = Ground(item.report["ground"])
    return ReportedPetition(
        id=item.report["$id"], reported_at=item.report["createdAt"], ground=ground.value,
        ground_words=in_plain_words(ground), duplicate_of=item.report.get("duplicateOf"),
        note=item.report.get("note"), reports_on_this_petition=item.reports_on_this_petition,
        petition=card(item.petition),
    )


def removals(by_ground: dict[str, int]) -> Removals:
    counts = [RemovalCount(ground=ground.value, label=in_plain_words(ground), count=by_ground.get(ground.value, 0))
              for ground in Ground]
    return Removals(total=sum(c.count for c in counts), grounds=counts)


def my_signature(signature: dict[str, Any] | None) -> MySignature:
    if not signature:
        return MySignature(signed=False, named=False, name=None, signed_at=None, version=None)
    return MySignature(signed=True, named=bool(signature.get("named")), name=signature.get("name"),
                       signed_at=signature.get("createdAt"), version=signature.get("version"))


def named_signature(row: dict[str, Any]) -> NamedSignature:
    return NamedSignature(name=row["name"], signed_at=row["createdAt"])


def awaiting(petition: dict[str, Any]) -> AwaitingResponse:
    fields = _card_fields(petition)
    return AwaitingResponse(
        code=fields["code"], title=fields["title"], topic=fields["topic"], departments=fields["departments"], scope=fields["scope"],
        area=fields["area"], sub_metro=fields["sub_metro"], signatures=fields["signatures"], threshold=petition["threshold"],
        threshold_reached_at=petition["thresholdReachedAt"], response_due=petition["responseDue"],
    )


def report_received() -> str:
    """What whoever reported a petition is told. It says the petition stays up, because it does."""
    return phrase("petition.report.received")


def status_catalogue() -> dict[str, str]:
    """One wording for each status, handed to the page so the portal and the public say the same word."""
    return {status.value: phrase(key) for status, key in STATUS_WORDS.items()}
