"""The MCE shares a petition with a department, and the department answers on the petition's own page.

The MCE decides which department a petition belongs to and shares it; the department is then the one that writes,
under its own name, where everyone reading the petition can see it. The MCE cannot write that note, and cannot
change it afterwards, so "referred to the Works Department" can be checked against what Works itself said.

A department writes one note per petition. A note is published as given, as the MCE's response is: a second one
is refused rather than allowed to replace the first, because a page where an answer can be quietly rewritten is
worth nothing to the person who was answered. The MCE can share the same petition with more than one department —
a drain is often two departments' work — and each writes its own note.

The note is screened as a staff note on a case is: personal data by pattern, and the model's reading that it names
a private person. Either refuses it with the reason; nothing is quietly mended.

Every read here goes through petitions.public(), the door the tombstone closed: a removed petition cannot be
shared, cannot be noted, and its notes are not read anywhere — they come back with it, as its comments do.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from appwrite.id import ID
from appwrite.query import Query

from app.services import petitions
from app.services.appwrite_client import DATABASE_ID, as_record, every_record, get_databases
from app.services.auth import Principal
from app.services.locks import record_lock
from app.services.petition_rules import (
    DEPARTMENT_NOTE_MAX,
    NotAllowed,
    PetitionAction,
    WrongState,
    check_department,
    is_public,
)
from app.services.petition_screen import Refusals, screened
from app.services.phrases import phrase

SHARES_COLLECTION = "petition_shares"
REFUSALS = Refusals(empty="petition.note.empty", too_long="petition.note.too_long",
                    personal_data="petition.note.personal_data", private_individual="petition.note.private_individual")


@dataclass(frozen=True)
class Shared:
    """A petition as the department it was shared with meets it: the petition, and that department's own row."""

    petition: dict[str, Any]
    share: dict[str, Any]


def clean_note(text: str) -> str:
    """The note as it will be stored, or a refusal saying why it can't be, in the words a department reads."""
    return screened(text, DEPARTMENT_NOTE_MAX, REFUSALS)


def shares_on(petition_id: str) -> list[dict[str, Any]]:
    """Oldest first: the departments in the order the MCE sent the petition to them."""
    return every_record(SHARES_COLLECTION, [Query.equal("petitionId", petition_id), Query.order_asc("sharedAt")])


def _share_with(petition_id: str, department: str) -> dict[str, Any] | None:
    found = every_record(SHARES_COLLECTION, [Query.equal("petitionId", petition_id),
                                             Query.equal("department", department), Query.limit(1)])
    return found[0] if found else None


def _record_share(petition: dict[str, Any], principal: Principal, department: str, now: datetime) -> dict[str, Any]:
    return as_record(get_databases().create_document(DATABASE_ID, SHARES_COLLECTION, ID.unique(), {
        "petitionId": petition["$id"], "code": petition["code"], "department": department,
        "sharedById": principal.user_id, "sharedByName": principal.name, "sharedAt": now.isoformat(),
    }))


def share(principal: Principal, code: str, department: str, now: datetime) -> dict[str, Any]:
    """The petition as it now stands, so the page that asked can show who it sits with."""
    check_department(department)
    petition = petitions.public(code)
    with record_lock(petition["$id"]):
        petition = petitions.public(code)
        if _share_with(petition["$id"], department):
            raise WrongState(phrase("petition.share.already_shared"))
        _record_share(petition, principal, department, now)
        # The status doesn't move: sharing asks a department to answer, it doesn't put the petition anywhere new.
        petitions.record_history(petition, PetitionAction.SHARED, petitions.mce_actor(principal),
                                 petition["status"], reason=department)
    return petition


def _own_department(principal: Principal) -> str:
    """The caller's department, which the role check has already established; never a department they name."""
    if not principal.department:
        raise NotAllowed(phrase("petition.note.not_shared"))
    return principal.department


def add_note(principal: Principal, code: str, text: str, now: datetime) -> Shared:
    """The one note this department writes on this petition, published under the department's name."""
    said = clean_note(text)
    department = _own_department(principal)
    petition = petitions.public(code)
    with record_lock(petition["$id"]):
        standing = _share_with(petition["$id"], department)
        if standing is None:
            raise NotAllowed(phrase("petition.note.not_shared"))
        if standing.get("note"):
            raise WrongState(phrase("petition.note.already_written"))
        written = as_record(get_databases().update_document(DATABASE_ID, SHARES_COLLECTION, standing["$id"], {
            "note": said, "noteAt": now.isoformat(),
            "notedById": principal.user_id, "notedByName": principal.name,
        }))
        petitions.record_history(petition, PetitionAction.DEPARTMENT_NOTE, petitions.department_actor(principal),
                                 petition["status"], reason=department)
    return Shared(petition, written)


def shared_with(principal: Principal) -> list[Shared]:
    """What one department has been asked to answer, newest first.

    A removed petition is left out: a department answers what the public can read, and a note written against a
    tombstone would appear the moment the creator published the petition again.
    """
    rows = every_record(SHARES_COLLECTION, [Query.equal("department", _own_department(principal)),
                                            Query.order_desc("sharedAt")])
    standing = petitions.by_ids([str(row["petitionId"]) for row in rows])
    return [Shared(found, row) for row in rows
            if (found := standing.get(str(row["petitionId"]))) is not None and is_public(found)]
