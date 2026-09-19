"""Taking a petition down, and the tombstone that stays in its place.

Only a verified contributor removes a petition, and only on one of the four grounds in petition_grounds. The MCE
cannot: the Assembly is usually what a petition is about, and a target with a delete button is not accountability.
A contributor cannot remove a petition they started or signed either — nobody judges their own side.

What is left behind is built here, from the removal record alone: the number, the ground in plain words, the date,
the duplicate's number where there is one, and how many times this petition had been removed before. The petition
itself is never read to build it, so no title, body, image, comment, signature count or answer can reach a reader
through the tombstone by an oversight somewhere else.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from appwrite.id import ID
from appwrite.query import Query

from app.services import petition_reports, petition_signatures, petitions
from app.services.appwrite_client import DATABASE_ID, as_record, every_record, get_databases
from app.services.auth import Principal
from app.services.locks import record_lock
from app.services.petition_grounds import Ground, in_plain_words, needs_another_petition
from app.services.petition_rules import (
    REMOVAL_NOTE_MAX,
    InvalidPetition,
    NotAllowed,
    PetitionAction,
    check_removable,
    removal_fields,
    removals_of,
)
from app.services.petition_screen import personal_data
from app.services.phone_proof import Proof, phone_key
from app.services.phrases import Language, phrase

REMOVALS_COLLECTION = "petition_removals"


@dataclass(frozen=True)
class Removed:
    """The removal as it was recorded, and the petition as it now stands. The tombstone is built from the record;
    the petition is here only so the creator can be told, on the number they confirmed."""

    record: dict[str, Any]
    petition: dict[str, Any]


@dataclass(frozen=True)
class Tombstone:
    """Everything a removed petition's page may say, and nothing else."""

    code: str
    ground: str
    ground_words: str
    removed_at: str
    duplicate_of: str | None
    previous_removals: int


def clean_note(note: str | None) -> str | None:
    """A contributor's note is for the record, not for the reader of the tombstone. It is still screened: the record
    is read by other people, and a phone number in it would outlive the petition it was taken from."""
    text = (note or "").strip()
    if not text:
        return None
    if len(text) > REMOVAL_NOTE_MAX:
        raise InvalidPetition(phrase("petition.removal.note_too_long"))
    if personal_data(text):
        raise InvalidPetition(phrase("petition.removal.note_personal_data"))
    return text


def duplicate_code(ground: Ground, typed: str | None, petition: dict[str, Any]) -> str | None:
    """A duplicate is the one ground that can't be judged alone: the other petition must exist and be public, and
    its number is kept so the tombstone can send the reader there."""
    if not needs_another_petition(ground):
        return None
    if not (typed or "").strip():
        raise InvalidPetition(phrase("petition.removal.duplicate_needs_code"))
    try:
        other = petitions.public(typed or "")
    except petitions.PetitionNotFound:
        raise InvalidPetition(phrase("petition.removal.duplicate_not_found")) from None
    if other["$id"] == petition["$id"]:
        raise InvalidPetition(phrase("petition.removal.duplicate_not_found"))
    return str(other["code"])


def _not_their_own(petition: dict[str, Any], proof: Proof) -> None:
    if petition.get("creatorKey") == phone_key(proof.number):
        raise NotAllowed(phrase("petition.removal.own_petition"))
    if petition_signatures.has_signed(petition["$id"], proof.number):
        raise NotAllowed(phrase("petition.removal.signed_petition"))


def _record_removal(petition: dict[str, Any], principal: Principal, ground: Ground, duplicate: str | None,
                    note: str | None, now: datetime) -> dict[str, Any]:
    return as_record(get_databases().create_document(DATABASE_ID, REMOVALS_COLLECTION, ID.unique(), {
        "petitionId": petition["$id"], "code": petition["code"], "ground": ground.value, "duplicateOf": duplicate,
        "note": note, "removedById": principal.user_id, "removedByName": principal.name,
        "previousRemovals": removals_of(petition), "at": now.isoformat(),
    }))


def remove(principal: Principal, proof: Proof, code: str, ground: Ground, duplicate_of: str | None,
           note: str | None, now: datetime) -> Removed:
    """The contributor proves the same phone number a resident does, which is the only way the server can tell
    whether they started or signed this petition."""
    note = clean_note(note)
    petition = petitions.find(code)
    duplicate = duplicate_code(ground, duplicate_of, petition)
    with record_lock(petition["$id"]):
        petition = petitions.find(code)
        check_removable(petition)
        _not_their_own(petition, proof)
        # The record is written from the petition as it stood, so previousRemovals counts the removals before
        # this one; the petition itself now carries the count including it.
        removal = _record_removal(petition, principal, ground, duplicate, note, now)
        updated = petitions.update_petition(petition["$id"], removal_fields(ground, duplicate, petition, now))
        petitions.record_history(updated, PetitionAction.REMOVED, petitions.contributor_actor(principal),
                                 petition["status"], ground.value, note)
    petition_reports.close_open_reports(petition["$id"], now)
    return Removed(removal, updated)


def latest_removal(petition_id: str) -> dict[str, Any] | None:
    listing = get_databases().list_documents(DATABASE_ID, REMOVALS_COLLECTION, queries=[
        Query.equal("petitionId", petition_id), Query.order_desc("at"), Query.limit(1)])
    return as_record(listing.documents[0]) if listing.documents else None


def tombstone(removal: dict[str, Any], language: Language = Language.ENGLISH) -> Tombstone:
    """Built from the removal record and nothing else."""
    ground = Ground(removal["ground"])
    return Tombstone(code=str(removal["code"]), ground=ground.value, ground_words=in_plain_words(ground, language),
                     removed_at=str(removal["at"]), duplicate_of=removal.get("duplicateOf"),
                     previous_removals=int(removal.get("previousRemovals") or 0))


def removals_by_ground() -> dict[str, int]:
    """How many petitions have been removed on each ground, for the public page. A fixture's removal isn't a
    resident's petition coming down, so it isn't counted."""
    tests = petitions.test_petition_ids()
    grounds = Counter(str(row.get("ground")) for row in every_record(REMOVALS_COLLECTION, [Query.select(["ground", "petitionId"])])
                      if row.get("petitionId") not in tests)
    return {ground.value: grounds.get(ground.value, 0) for ground in Ground}
