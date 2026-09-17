"""Petitions in Appwrite: submitting, the MCE's decision, the creator's changes, and the clocks.

Every change re-reads the petition under a per-record lock and leaves an entry in petition_history, the audit
trail. Collections are server-only.

The creator is known only by a keyed hash of their verified number (creatorKey). The number itself is kept only
for updates about their petition, and deleted 30 days after it closes, is withdrawn, or is refused and not sent
back. A name is shown publicly only if the creator chose to show it.
"""

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from appwrite.exception import AppwriteException
from appwrite.id import ID
from appwrite.query import Query

from app.config import get_settings
from app.services import channel_limits, issue_voices, ledger_documents
from app.services.appwrite_client import DATABASE_ID, as_record, every_record, get_databases
from app.services.auth import Principal
from app.services.ledger_documents import LedgerStatus
from app.services.locks import record_lock
from app.services.petition_rules import (
    Draft,
    InvalidPetition,
    PetitionAction,
    PetitionStatus,
    PublishedBy,
    Scope,
    WrongState,
    check_resubmit,
    check_review,
    check_withdraw,
    clean_draft,
    clean_name,
    draft_fields,
    new_code,
    normalise_code,
    publish_fields,
    refusal_fields,
    review_fields,
    threshold_for,
    was_published,
)
from app.services.phone_proof import Proof, phone_key
from app.services.test_fixtures import TEST_PREFIX
from app.services.workflow import WrongState as ClosedIssue
from app.wards import wards

logger = logging.getLogger(__name__)

PETITIONS_COLLECTION = "petitions"
HISTORY_COLLECTION = "petition_history"
IN_REVIEW_PER_PHONE = 3
RETENTION = timedelta(days=30)
CODE_ATTEMPTS = 5
PUBLIC_FIELDS = ["code", "title", "topic", "recipients", "scope", "wardLocation", "subMetro", "status", "publishedAt",
                 "publishedBy", "closesAt", "closedAt", "threshold", "signatureCount", "creatorName", "thresholdReachedAt",
                 "responseDue", "respondedAt", "responseKind", "noResponseAt"]


class PetitionNotFound(Exception):
    """No petition has that number, or it isn't one the caller may see."""


@dataclass(frozen=True)
class Actor:
    id: str
    name: str
    role: str  # "creator", "mce" or "system"


CREATOR = Actor("creator", "", "creator")
SYSTEM = Actor("system", "Automatic", "system")


def mce_actor(principal: Principal) -> Actor:
    return Actor(principal.user_id, principal.name, "mce")


def list_petitions(queries: list[str]) -> tuple[list[dict[str, Any]], int]:
    listing = get_databases().list_documents(DATABASE_ID, PETITIONS_COLLECTION, queries=queries)
    return [as_record(d) for d in listing.documents], int(listing.total)


def find(code: str) -> dict[str, Any]:
    normal = normalise_code(code)
    found, _ = list_petitions([Query.equal("code", normal), Query.limit(1)]) if normal else ([], 0)
    if not found:
        raise PetitionNotFound(code)
    return found[0]


def public(code: str) -> dict[str, Any]:
    petition = find(code)
    if not was_published(petition):
        raise PetitionNotFound(code)
    return petition


def update_petition(petition_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Callers hold the petition's lock."""
    return as_record(get_databases().update_document(DATABASE_ID, PETITIONS_COLLECTION, petition_id, changes))


def record_history(petition: dict[str, Any], action: PetitionAction, actor: Actor, from_status: str | None,
                   reason: str | None = None, note: str | None = None) -> None:
    get_databases().create_document(DATABASE_ID, HISTORY_COLLECTION, ID.unique(), {
        "petitionId": petition["$id"], "action": action.value, "actorId": actor.id, "actorName": actor.name or None,
        "actorRole": actor.role, "fromStatus": from_status, "toStatus": petition["status"], "reason": reason,
        "note": note, "at": ledger_documents.now_iso(),
    })


def history(petition_id: str) -> list[dict[str, Any]]:
    return every_record(HISTORY_COLLECTION, [Query.equal("petitionId", petition_id), Query.order_asc("at")])


def _check_links(draft: Draft) -> None:
    if draft.issue:
        try:
            issue_voices.find_issue(draft.issue)
        except (issue_voices.IssueNotFound, ClosedIssue):
            raise InvalidPetition("The linked issue isn't an open issue any more. Remove it and try again.") from None
    check_documents(draft.documents)


def check_documents(document_ids: tuple[str, ...]) -> None:
    documents = ledger_documents.get_documents(document_ids)
    if any(documents.get(d, {}).get("status") != LedgerStatus.PUBLISHED for d in document_ids):
        raise InvalidPetition("A cited document isn't in the Ledger. Remove it and try again.")


def _create(fields: dict[str, Any]) -> dict[str, Any]:
    """The unique index on code says when a new number is already taken."""
    for _ in range(CODE_ATTEMPTS):
        try:
            return as_record(get_databases().create_document(
                DATABASE_ID, PETITIONS_COLLECTION, ID.unique(), {**fields, "code": new_code()}))
        except AppwriteException as exc:
            if exc.code != 409:
                raise
    raise RuntimeError("No free petition number; try again.")


def _in_review_by(key: str) -> int:
    _, total = list_petitions([Query.equal("creatorKey", key), Query.equal("status", PetitionStatus.IN_REVIEW.value), Query.limit(1)])
    return total


def _location(draft: Draft) -> dict[str, Any]:
    return {"subMetro": wards()[draft.ward].sub_metro if draft.ward else None}


def submit(proof: Proof, draft: Draft, show_name: bool, name: str | None, now: datetime) -> dict[str, Any]:
    draft, shown_name = clean_draft(draft), clean_name(show_name, name)
    _check_links(draft)
    key = phone_key(proof.number)
    if _in_review_by(key) >= IN_REVIEW_PER_PHONE:
        raise WrongState(f"You have {IN_REVIEW_PER_PHONE} petitions waiting for review. Wait for a decision on one first.")
    if not channel_limits.PETITIONS.allow(proof.number, now.timestamp()):
        raise WrongState("You've started as many petitions as can be started in a day. Try again tomorrow.")
    petition = _create({
        **draft_fields(draft), **_location(draft), **review_fields(now), "resubmissions": 0, "signatureCount": 0,
        "creatorKey": key, "creatorPhone": proof.number, "creatorChannel": proof.channel.value,
        "creatorName": shown_name, "createdAt": now.isoformat(),
    })
    record_history(petition, PetitionAction.SUBMITTED, CREATOR, None)
    return petition


def _owned(code: str, proof: Proof) -> dict[str, Any]:
    """Anyone else's petition is simply not found."""
    petition = find(code)
    if petition.get("creatorKey") != phone_key(proof.number):
        raise PetitionNotFound(code)
    return petition


def resubmit(code: str, proof: Proof, draft: Draft, now: datetime) -> dict[str, Any]:
    draft = clean_draft(draft)
    _check_links(draft)
    petition = _owned(code, proof)
    with record_lock(petition["$id"]):
        petition = _owned(code, proof)
        check_resubmit(petition)
        changes = {**draft_fields(draft), **_location(draft), **review_fields(now),
                   "resubmissions": (petition.get("resubmissions") or 0) + 1, "purgeAt": None}
        updated = update_petition(petition["$id"], changes)
        record_history(updated, PetitionAction.RESUBMITTED, CREATOR, petition["status"])
    return updated


def finish_fields(status: PetitionStatus, now: datetime) -> dict[str, Any]:
    return {"status": status.value, "closedAt": now.isoformat(), "purgeAt": (now + RETENTION).isoformat()}


def withdraw(code: str, proof: Proof, now: datetime) -> dict[str, Any]:
    petition = _owned(code, proof)
    with record_lock(petition["$id"]):
        petition = _owned(code, proof)
        check_withdraw(petition)
        updated = update_petition(petition["$id"], finish_fields(PetitionStatus.WITHDRAWN, now))
        record_history(updated, PetitionAction.WITHDRAWN, CREATOR, petition["status"])
    return updated


def make_anonymous(code: str, proof: Proof) -> dict[str, Any]:
    """The name can't be put back: that would need a new choice at the start."""
    petition = _owned(code, proof)
    if not petition.get("creatorName"):
        return petition
    with record_lock(petition["$id"]):
        updated = update_petition(petition["$id"], {"creatorName": None})
        record_history(updated, PetitionAction.MADE_ANONYMOUS, CREATOR, petition["status"])
    return updated


def mine(proof: Proof) -> list[dict[str, Any]]:
    return every_record(PETITIONS_COLLECTION, [Query.equal("creatorKey", phone_key(proof.number)), Query.order_desc("createdAt")])


def review_queue() -> list[dict[str, Any]]:
    return every_record(PETITIONS_COLLECTION, [Query.equal("status", PetitionStatus.IN_REVIEW.value), Query.order_asc("reviewDeadline")])


def threshold_of(petition: dict[str, Any]) -> int:
    """Fixed on the petition when it opens."""
    settings = get_settings()
    return threshold_for(Scope(petition["scope"]), settings.petition_threshold_area, settings.petition_threshold_metro)


def _open_duplicate(typed: str | None, petition: dict[str, Any]) -> str:
    try:
        other = find(typed or "")
    except PetitionNotFound:
        raise InvalidPetition("No petition has that number.") from None
    if other["status"] != PetitionStatus.OPEN or other["$id"] == petition["$id"]:
        raise InvalidPetition("A petition can only be refused as a duplicate of another petition that is open.")
    return other["code"]


def _decision(petition: dict[str, Any], publish: bool, reason: str, note: str | None, duplicate_of: str | None,
              now: datetime) -> tuple[dict[str, Any], PetitionAction]:
    if publish:
        return publish_fields(petition, PublishedBy.MCE, now, threshold_of(petition)), PetitionAction.PUBLISHED
    duplicate = _open_duplicate(duplicate_of, petition) if reason == "duplicate" else None
    changes = {**refusal_fields(reason, note, duplicate), "purgeAt": (now + RETENTION).isoformat()}
    return changes, PetitionAction.REFUSED


def decide(principal: Principal, code: str, publish: bool, reason: str | None, note: str | None,
           duplicate_of: str | None, now: datetime) -> dict[str, Any]:
    petition = find(code)
    with record_lock(petition["$id"]):
        petition = find(code)
        check_review(petition, now)
        changes, action = _decision(petition, publish, reason or "", note, duplicate_of, now)
        updated = update_petition(petition["$id"], changes)
        record_history(updated, action, mce_actor(principal), petition["status"], changes.get("refusalReason"), changes.get("refusalNote"))
    return updated


def purge_creator_numbers(now: datetime) -> int:
    """The keyed hash stays, so creators can still find their petition by confirming their number again."""
    rows = every_record(PETITIONS_COLLECTION, [Query.is_not_null("purgeAt"), Query.less_than_equal("purgeAt", now.isoformat()),
                                               Query.select(["code"])])
    for row in rows:
        get_databases().update_document(DATABASE_ID, PETITIONS_COLLECTION, row["$id"],
                                        {"creatorPhone": None, "creatorChannel": None, "purgeAt": None})
    if rows:
        logger.info("Deleted the creator's number from %d closed petition(s)", len(rows))
    return len(rows)


# A petition titled "[TEST] …" is a fixture: filed, moderated and signed for real, and never listed or counted in
# public. Its title shows on a card, but its signatures, the MCE's decision on it and its place in every count don't.
NOT_TEST = Query.not_starts_with("title", TEST_PREFIX)


def test_petition_ids() -> set[str]:
    return {row["$id"] for row in every_record(PETITIONS_COLLECTION, [Query.starts_with("title", TEST_PREFIX), Query.select(["$id"])])}


def list_public(statuses: list[PetitionStatus], topic: str | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    signing = PetitionStatus.OPEN in statuses or PetitionStatus.AWAITING_RESPONSE in statuses
    latest = "respondedAt" if PetitionStatus.RESPONDED in statuses else "closedAt"
    order = [Query.order_desc("signatureCount"), Query.order_desc("publishedAt")] if signing else [Query.order_desc(latest)]
    return list_petitions([
        Query.equal("status", [s.value for s in statuses]), Query.is_not_null("publishedAt"), NOT_TEST,
        *([Query.equal("topic", topic)] if topic else []),
        Query.select(PUBLIC_FIELDS), *order, Query.limit(limit), Query.offset(offset),
    ])


def awaiting_response() -> list[dict[str, Any]]:
    return every_record(PETITIONS_COLLECTION, [Query.equal("status", PetitionStatus.AWAITING_RESPONSE.value),
                                               Query.order_asc("responseDue")])


def _count(queries: list[str]) -> int:
    _, total = list_petitions([*queries, NOT_TEST, Query.limit(1)])
    return total


def moderation_counts() -> dict[str, Any]:
    tests = test_petition_ids()
    refusals = [row for row in every_record(HISTORY_COLLECTION, [Query.equal("action", PetitionAction.REFUSED.value),
                                                                  Query.select(["reason", "petitionId"])])
                if row.get("petitionId") not in tests]
    return {
        "awaiting": _count([Query.equal("status", PetitionStatus.IN_REVIEW.value)]),
        "published_by_mce": _count([Query.equal("publishedBy", PublishedBy.MCE.value)]),
        "published_automatically": _count([Query.equal("publishedBy", PublishedBy.AUTOMATIC.value)]),
        "refusals": Counter(row.get("reason") for row in refusals if row.get("reason")),
    }
