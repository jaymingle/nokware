"""Petitions in Appwrite: publishing one, editing it, closing it, and the clocks.

Every change re-reads the petition under a per-record lock and leaves an entry in petition_history, the audit
trail. Collections are server-only.

Nobody approves a petition. It is published by the person who wrote it, the moment their words pass the screen, and
it stays up until it closes or a verified contributor removes it on a named ground.

The creator is known only by a keyed hash of their verified number (creatorKey). The number itself is kept only
for updates about their petition, and deleted 30 days after it closes. A name is shown publicly only if the creator
chose to show it.
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
from app.services import channel_limits, issue_voices, ledger_documents, petition_versions
from app.services.appwrite_client import DATABASE_ID, as_record, every_record, get_databases
from app.services.auth import Principal
from app.services.ledger_documents import LedgerStatus
from app.services.locks import record_lock
from app.services.petition_rules import (
    Draft,
    InvalidPetition,
    PetitionAction,
    PetitionStatus,
    Scope,
    WrongState,
    check_editable,
    check_withdraw,
    clean_draft,
    clean_name,
    draft_fields,
    edit_action,
    edit_fields,
    is_public,
    new_code,
    normalise_code,
    publish_fields,
    threshold_for,
    version_of,
)
from app.services.phone_proof import Proof, phone_key
from app.services.test_fixtures import TEST_PREFIX
from app.services.workflow import WrongState as ClosedIssue
from app.wards import wards

logger = logging.getLogger(__name__)

PETITIONS_COLLECTION = "petitions"
HISTORY_COLLECTION = "petition_history"
RETENTION = timedelta(days=30)
CODE_ATTEMPTS = 5
PUBLIC_FIELDS = ["code", "title", "topic", "recipients", "scope", "wardLocation", "subMetro", "status", "publishedAt",
                 "closesAt", "closedAt", "threshold", "signatureCount", "creatorName", "thresholdReachedAt",
                 "responseDue", "respondedAt", "responseKind", "noResponseAt", "version", "versionedAt", "removalCount"]


class PetitionNotFound(Exception):
    """No petition has that number, or it isn't one the caller may see."""


@dataclass(frozen=True)
class Actor:
    id: str
    name: str
    role: str  # "creator", "contributor", "mce" or "system"


CREATOR = Actor("creator", "", "creator")
SYSTEM = Actor("system", "Automatic", "system")
ACTOR_ROLES = ("creator", "contributor", "mce", "department", "system")  # everyone a line of the trail can name


def mce_actor(principal: Principal) -> Actor:
    return Actor(principal.user_id, principal.name, "mce")


def contributor_actor(principal: Principal) -> Actor:
    return Actor(principal.user_id, principal.name, "contributor")


def department_actor(principal: Principal) -> Actor:
    """A department acts as itself: the trail keeps the name of the officer who wrote, the page shows neither."""
    return Actor(principal.user_id, principal.name, "department")


def list_petitions(queries: list[str]) -> tuple[list[dict[str, Any]], int]:
    listing = get_databases().list_documents(DATABASE_ID, PETITIONS_COLLECTION, queries=queries)
    return [as_record(d) for d in listing.documents], int(listing.total)


def find(code: str) -> dict[str, Any]:
    normal = normalise_code(code)
    found, _ = list_petitions([Query.equal("code", normal), Query.limit(1)]) if normal else ([], 0)
    if not found:
        raise PetitionNotFound(code)
    return found[0]


def by_ids(petition_ids: list[str]) -> dict[str, dict[str, Any]]:
    """The petitions behind a list of rows — reports, shares — read in one call rather than one call each."""
    ids = list(dict.fromkeys(petition_ids))
    if not ids:
        return {}
    found, _ = list_petitions([Query.equal("$id", ids), Query.limit(len(ids))])
    return {petition["$id"]: petition for petition in found}


def public(code: str) -> dict[str, Any]:
    """A removed petition is not found here, by design: everything that reads a petition for the public reads it
    through this function, so nothing of a removed one can reach a reader by an oversight elsewhere."""
    petition = find(code)
    if not is_public(petition):
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


def _location(draft: Draft) -> dict[str, Any]:
    return {"subMetro": wards()[draft.ward].sub_metro if draft.ward else None}


def threshold_of(scope: Scope) -> int:
    """Fixed on the petition when it opens, so a later change to the setting never moves a live goal."""
    settings = get_settings()
    return threshold_for(scope, settings.petition_threshold_area, settings.petition_threshold_metro)


def submit(proof: Proof, draft: Draft, show_name: bool, name: str | None, now: datetime) -> dict[str, Any]:
    """It is published here, not sent anywhere for a decision. The words were screened before this was called."""
    draft, shown_name = clean_draft(draft), clean_name(show_name, name)
    _check_links(draft)
    if not channel_limits.PETITIONS.allow(proof.number, now.timestamp()):
        raise WrongState("You've started as many petitions as can be started in a day. Try again tomorrow.")
    fields = {**draft_fields(draft), **_location(draft), **publish_fields(now, threshold_of(draft.scope)),
              "signatureCount": 0, "creatorKey": phone_key(proof.number), "creatorPhone": proof.number,
              "creatorChannel": proof.channel.value, "creatorName": shown_name, "createdAt": now.isoformat()}
    petition = _create(fields)
    petition_versions.record_version(petition["$id"], fields, version_of(petition), now)
    record_history(petition, PetitionAction.PUBLISHED, CREATOR, None)
    return petition


def owned(code: str, proof: Proof) -> dict[str, Any]:
    """Anyone else's petition is simply not found."""
    petition = find(code)
    if petition.get("creatorKey") != phone_key(proof.number):
        raise PetitionNotFound(code)
    return petition


def edit(code: str, proof: Proof, draft: Draft, now: datetime) -> dict[str, Any]:
    """A new version of the words, kept beside the ones people have already signed."""
    draft = clean_draft(draft)
    _check_links(draft)
    petition = owned(code, proof)
    with record_lock(petition["$id"]):
        petition = owned(code, proof)
        check_editable(petition)
        changes = {**edit_fields(draft, petition, now), **_location(draft)}
        updated = update_petition(petition["$id"], changes)
        petition_versions.record_version(petition["$id"], changes, version_of(updated), now)
        record_history(updated, edit_action(petition), CREATOR, petition["status"])
    return updated


def finish_fields(status: PetitionStatus, now: datetime) -> dict[str, Any]:
    return {"status": status.value, "closedAt": now.isoformat(), "purgeAt": (now + RETENTION).isoformat()}


def withdraw(code: str, proof: Proof, now: datetime) -> dict[str, Any]:
    """The creator closes their own petition. It stays public and closed, with its signatures: people signed it."""
    petition = owned(code, proof)
    with record_lock(petition["$id"]):
        petition = owned(code, proof)
        check_withdraw(petition)
        updated = update_petition(petition["$id"], finish_fields(PetitionStatus.CLOSED, now))
        record_history(updated, PetitionAction.WITHDRAWN, CREATOR, petition["status"])
    return updated


def make_anonymous(code: str, proof: Proof) -> dict[str, Any]:
    """The name can't be put back: that would need a new choice at the start."""
    petition = owned(code, proof)
    if not petition.get("creatorName"):
        return petition
    with record_lock(petition["$id"]):
        updated = update_petition(petition["$id"], {"creatorName": None})
        record_history(updated, PetitionAction.MADE_ANONYMOUS, CREATOR, petition["status"])
    return updated


def mine(proof: Proof) -> list[dict[str, Any]]:
    return every_record(PETITIONS_COLLECTION, [Query.equal("creatorKey", phone_key(proof.number)), Query.order_desc("createdAt")])


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


# A petition titled "[TEST] …" is a fixture: filed and signed for real, and never listed or counted in public. Its
# title shows on a card, but its signatures and its place in every count don't.
NOT_TEST = Query.not_starts_with("title", TEST_PREFIX)
# What every public reading of the collection is narrowed to first: a petition residents were shown, not a fixture.
PUBLISHED = [Query.is_not_null("publishedAt"), NOT_TEST]


def test_petition_ids() -> set[str]:
    return {row["$id"] for row in every_record(PETITIONS_COLLECTION, [Query.starts_with("title", TEST_PREFIX), Query.select(["$id"])])}


def list_public(statuses: list[PetitionStatus], topic: str | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    signing = PetitionStatus.OPEN in statuses or PetitionStatus.AWAITING_RESPONSE in statuses
    latest = "respondedAt" if PetitionStatus.RESPONDED in statuses else "closedAt"
    order = [Query.order_desc("signatureCount"), Query.order_desc("publishedAt")] if signing else [Query.order_desc(latest)]
    return list_petitions([
        Query.equal("status", [s.value for s in statuses]), *PUBLISHED,
        *([Query.equal("topic", topic)] if topic else []),
        Query.select(PUBLIC_FIELDS), *order, Query.limit(limit), Query.offset(offset),
    ])


def awaiting_response() -> list[dict[str, Any]]:
    return every_record(PETITIONS_COLLECTION, [Query.equal("status", PetitionStatus.AWAITING_RESPONSE.value),
                                               Query.order_asc("responseDue")])


# The four groups a published petition can be listed in, and the statuses each one gathers. The route names them in
# its URL; the counts below use the same map, so a tab can never say a number the list underneath won't show. A
# removed petition is in none of them: nothing here lists one, because nothing here may read one. It is counted
# under REMOVED_GROUP and listed, as tombstones, from the removal records.
PUBLIC_GROUPS: dict[str, list[PetitionStatus]] = {
    "open": [PetitionStatus.OPEN],
    "awaiting": [PetitionStatus.AWAITING_RESPONSE],
    "responded": [PetitionStatus.RESPONDED],
    "closed": [PetitionStatus.CLOSED],
}
REMOVED_GROUP = "removed"


def public_counts() -> dict[str, int]:
    """How many petitions stand in each group, and how many have been taken down. One read of their statuses
    rather than a count each, which on a public page would be five round trips for five small numbers."""
    rows = every_record(PETITIONS_COLLECTION, [*PUBLISHED, Query.select(["status"])])
    standing = Counter(str(row.get("status")) for row in rows)
    counted = {group: sum(standing[status.value] for status in statuses) for group, statuses in PUBLIC_GROUPS.items()}
    return {**counted, REMOVED_GROUP: standing[PetitionStatus.REMOVED.value]}


def removed_ids() -> set[str]:
    """The petitions that stand removed, by id alone. Nothing of such a petition is read here — not its title, not
    its status date — because the list that uses these ids is built from the removal records, not from them."""
    return {row["$id"] for row in every_record(PETITIONS_COLLECTION, [
        Query.equal("status", PetitionStatus.REMOVED.value), *PUBLISHED, Query.select(["$id"])])}
