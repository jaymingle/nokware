"""What residents say under a petition: writing a comment, reading them, reporting one and taking one down.

Whoever can sign a petition can comment on it, by the same confirmed number, proved the same way. The number is
never stored: a comment holds a keyed hash of the number and the petition together, as a signature does, so the
same person cannot be followed from one petition's comments to another's. What stands over the words is the
display name they chose, or "Resident".

The words are screened before they are stored, by the screen a petition's own words pass: personal data by
pattern, and the model's reading that they name a private person. Either refuses the comment with the reason, and
nothing is quietly mended — the person who wrote it is the one who decides how to say it instead.

Comments are read through petitions.public(), the same door the tombstone closed: a removed petition has no
comments to read, and the moment its creator publishes it again they are all back. Nothing is hidden and nothing
is deleted, so no filter here can be forgotten. A comment a contributor removes keeps its place in the page, with
the ground standing where its words were.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from appwrite.id import ID
from appwrite.query import Query

from app.services import petitions
from app.services.appwrite_client import DATABASE_ID, as_record, every_record, get_databases
from app.services.auth import Principal
from app.services.locks import record_lock
from app.services.petition_grounds import Dismissal, Ground, in_plain_words
from app.services.petition_reports import ReportNotFound, ReportState
from app.services.petition_reports import clean_note as clean_report_note
from app.services.petition_rules import PetitionError, WrongState, clean_signer_name
from app.services.petition_screen import Refusals, screened
from app.services.phone_proof import Proof, keyed_hash
from app.services.phrases import Language, phrase

COMMENTS_COLLECTION = "petition_comments"
COMMENT_REPORTS_COLLECTION = "petition_comment_reports"
COMMENT_MAX = 500
PAGE_MAX = 50
REFUSALS = Refusals(empty="petition.comment.empty", too_long="petition.comment.too_long",
                    personal_data="petition.comment.personal_data", private_individual="petition.comment.private_individual")


class CommentNotFound(PetitionError):
    """No comment of that petition has that id. A comment of a removed petition is not found either: the petition
    it stands under isn't."""

    status_code = 404


@dataclass(frozen=True)
class Seen:
    """One comment as a reader meets it: what somebody wrote, or — where a contributor removed it — the notice
    that stands in its place. No phone number, because a comment holds none."""

    id: str
    name: str | None  # None on a removed comment: the notice is nobody's words
    text: str
    at: str
    removed: bool


@dataclass(frozen=True)
class ReportedComment:
    """One open report, with the comment it is about and how many others stand against that same comment."""

    report: dict[str, Any]
    comment: Seen
    reports_on_this_comment: int


def commenter_key(petition_id: str, number: str) -> str:
    """The same number under another petition gives an unrelated key, as a signature's does."""
    return keyed_hash(f"comment:{petition_id}:{number}")


def display_name(chosen: str | None) -> str:
    """The name to stand over the words: the one they chose, or "Resident" for whoever gives none. It keeps the
    letters-only rule a signer's name keeps, so the field can't carry a number or a message."""
    return clean_signer_name(bool((chosen or "").strip()), chosen) or phrase("petition.comment.default_name")


def clean_comment(text: str) -> str:
    """The comment as it will be stored, or a refusal saying why it can't be, in the words a commenter reads."""
    return screened(text, COMMENT_MAX, REFUSALS)


def removal_words(ground: Ground, language: Language = Language.ENGLISH) -> str:
    """What stands where a removed comment's words were: the ground, in the words every screen names it by."""
    return phrase("petition.comment.removed", language).format(ground=in_plain_words(ground, language))


def report_received() -> str:
    """What whoever reported a comment is told. It says the comment stays up, because it does."""
    return phrase("petition.comment.report_received")


def as_seen(row: dict[str, Any], language: Language = Language.ENGLISH) -> Seen:
    """A removed comment is built from its ground and its date alone. Its words are not read here, the way a
    tombstone is built from the removal record and never from the petition."""
    ground = row.get("removalGround")
    if ground in set(Ground):
        return Seen(id=str(row["$id"]), name=None, text=removal_words(Ground(ground), language),
                    at=str(row["createdAt"]), removed=True)
    return Seen(id=str(row["$id"]), name=str(row["name"]), text=str(row["text"]), at=str(row["createdAt"]), removed=False)


def add(code: str, proof: Proof, name: str | None, text: str, now: datetime) -> Seen:
    """Published as written, by whoever holds the number: a comment waits for nobody's leave, as the petition it
    stands under doesn't. A petition that has closed still takes comments; a removed one is not found at all."""
    said, shown = clean_comment(text), display_name(name)
    petition = petitions.public(code)
    return as_seen(as_record(get_databases().create_document(DATABASE_ID, COMMENTS_COLLECTION, ID.unique(), {
        "petitionId": petition["$id"], "commenterKey": commenter_key(petition["$id"], proof.number),
        "name": shown, "text": said, "createdAt": now.isoformat(),
    })))


def on_petition(code: str, limit: int, offset: int) -> tuple[list[Seen], int]:
    """Newest first, a page at a time. Read through petitions.public(): a removed petition has no comments to
    read, and a republished one has them all again, by the same door rather than by a filter."""
    petition = petitions.public(code)
    listing = get_databases().list_documents(DATABASE_ID, COMMENTS_COLLECTION, queries=[
        Query.equal("petitionId", petition["$id"]), Query.order_desc("createdAt"),
        Query.limit(min(limit, PAGE_MAX)), Query.offset(offset)])
    return [as_seen(as_record(document)) for document in listing.documents], int(listing.total)


def count_on(petition: dict[str, Any]) -> int:
    """How many comments stand under a petition, for a page or a channel that says so. The caller passes the
    petition it already read publicly, so a removed one is never counted. A removed comment is counted: its
    notice is still a line on the page, and the count must be the length of what a reader is shown."""
    listing = get_databases().list_documents(DATABASE_ID, COMMENTS_COLLECTION, queries=[
        Query.equal("petitionId", petition["$id"]), Query.limit(1)])
    return int(listing.total)


def _under_petition(code: str, comment_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """One comment with the petition it stands under, found only while that petition is public."""
    petition = petitions.public(code)
    found = every_record(COMMENTS_COLLECTION, [Query.equal("$id", comment_id),
                                               Query.equal("petitionId", petition["$id"]), Query.limit(1)])
    if not found:
        raise CommentNotFound(comment_id)
    return found[0], petition


def file_report(code: str, comment_id: str, ground: Ground, note: str | None, now: datetime) -> dict[str, Any]:
    """Anyone reading, without signing in, on the same four grounds a petition is reported on. A report hides
    nothing here either: the comment stays exactly as it is while a contributor reads it. A duplicate names no
    other petition — a comment repeats what is on its own page, and nothing is built from the answer."""
    note = clean_report_note(note)
    comment, petition = _under_petition(code, comment_id)
    return as_record(get_databases().create_document(DATABASE_ID, COMMENT_REPORTS_COLLECTION, ID.unique(), {
        "petitionId": petition["$id"], "code": petition["code"], "commentId": comment["$id"], "ground": ground.value,
        "note": note, "state": ReportState.OPEN.value, "createdAt": now.isoformat(),
    }))


def open_reports() -> list[dict[str, Any]]:
    """Newest first: a contributor reads what has just come in."""
    return every_record(COMMENT_REPORTS_COLLECTION, [Query.equal("state", ReportState.OPEN.value),
                                                     Query.order_desc("createdAt")])


def _comments_by_id(comment_ids: list[str]) -> dict[str, dict[str, Any]]:
    ids = list(dict.fromkeys(comment_ids))
    if not ids:
        return {}
    found = every_record(COMMENTS_COLLECTION, [Query.equal("$id", ids), Query.limit(len(ids))])
    return {comment["$id"]: comment for comment in found}


def queue() -> list[ReportedComment]:
    """The reported comments, for the same screen the reported petitions are read on."""
    reports = open_reports()
    standing = _comments_by_id([str(report["commentId"]) for report in reports])
    against = Counter(str(report["commentId"]) for report in reports)
    return [ReportedComment(report, as_seen(standing[comment_id]), against[comment_id])
            for report in reports if (comment_id := str(report["commentId"])) in standing]


def find_open(report_id: str) -> dict[str, Any]:
    reports = every_record(COMMENT_REPORTS_COLLECTION, [Query.equal("$id", report_id), Query.limit(1)])
    if not reports or reports[0].get("state") != ReportState.OPEN:
        raise ReportNotFound(report_id)
    return reports[0]


def _settle(report_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    return as_record(get_databases().update_document(DATABASE_ID, COMMENT_REPORTS_COLLECTION, report_id, changes))


def dismiss(principal: Principal, report_id: str, reason: Dismissal, now: datetime) -> dict[str, Any]:
    """The report is settled with one of the two fixed reasons; the comment is untouched."""
    report = find_open(report_id)
    return _settle(report["$id"], {"state": ReportState.DISMISSED.value, "dismissedReason": reason.value,
                                   "settledById": principal.user_id, "settledByName": principal.name,
                                   "settledAt": now.isoformat()})


def _close_open_reports(comment_id: str, now: datetime) -> int:
    """Called when a comment is removed: every open report on it has been answered by that."""
    reports = every_record(COMMENT_REPORTS_COLLECTION, [Query.equal("commentId", comment_id),
                                                        Query.equal("state", ReportState.OPEN.value), Query.select(["$id"])])
    for report in reports:
        _settle(report["$id"], {"state": ReportState.ACTED_ON.value, "settledAt": now.isoformat()})
    return len(reports)


def remove(principal: Principal, code: str, comment_id: str, ground: Ground, now: datetime) -> Seen:
    """A verified contributor takes one comment down on a named ground.

    The petition itself is untouched, and so is every other comment: it was this comment that was judged. No
    confirmed number is asked of the contributor, as it is for a petition's removal, because there is nothing
    here for it to answer — a petition's removal asks it to prove they neither started nor signed the petition
    they are judging, and removing one's own comment is not a judgement on anybody.
    """
    comment, _ = _under_petition(code, comment_id)
    with record_lock(comment["$id"]):
        comment, _ = _under_petition(code, comment_id)
        if comment.get("removalGround") in set(Ground):
            raise WrongState(phrase("petition.comment.already_removed"))
        removed = as_record(get_databases().update_document(DATABASE_ID, COMMENTS_COLLECTION, comment["$id"], {
            "removalGround": ground.value, "removedAt": now.isoformat(),
            "removedById": principal.user_id, "removedByName": principal.name,
        }))
    _close_open_reports(comment["$id"], now)
    return as_seen(removed)
