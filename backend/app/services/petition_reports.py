"""Reporting a petition, and the queue of what has been reported.

Anyone reading a petition can report it, without signing in, on one of the same four grounds a contributor can
remove it on. A report hides nothing: the petition stays exactly as it was, signable and countable, while a
contributor reads it. Hiding on report would hand anyone with a browser a veto over everyone else's words, which is
the thing the MCE's review gate was taken out to prevent.

What a contributor does with a report is remove the petition on a ground, or dismiss the report with one of two
fixed reasons. Removing settles every open report on that petition at once: they were all about the same page.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from appwrite.id import ID
from appwrite.query import Query

from app.services import petitions
from app.services.appwrite_client import DATABASE_ID, as_record, every_record, get_databases
from app.services.auth import Principal
from app.services.petition_grounds import Dismissal, Ground, needs_another_petition
from app.services.petition_rules import REPORT_NOTE_MAX, InvalidPetition, PetitionError, WrongState
from app.services.petition_screen import personal_data
from app.services.phrases import phrase

REPORTS_COLLECTION = "petition_reports"


class ReportState(StrEnum):
    OPEN = "open"
    DISMISSED = "dismissed"  # a contributor read it and left the petition standing
    ACTED_ON = "acted_on"  # the petition was removed, on this ground or another


@dataclass(frozen=True)
class Reported:
    """One open report, with the petition it is about and how many others stand against the same petition."""

    report: dict[str, Any]
    petition: dict[str, Any]
    reports_on_this_petition: int


class ReportNotFound(PetitionError):
    """No open report has that id: another contributor settled it a moment ago, or it never existed."""

    status_code = 404


def clean_note(note: str | None) -> str | None:
    """What the reader adds, in their own words. Screened like any note that other people will read: a report is
    read by contributors, and personal data doesn't belong in one any more than in the petition."""
    text = (note or "").strip()
    if not text:
        return None
    if len(text) > REPORT_NOTE_MAX:
        raise InvalidPetition(phrase("petition.report.note_too_long"))
    if personal_data(text):
        raise InvalidPetition(phrase("petition.report.note_personal_data"))
    return text


def _duplicate_code(ground: Ground, typed: str | None) -> str | None:
    if not needs_another_petition(ground):
        return None
    if not (typed or "").strip():
        raise InvalidPetition(phrase("petition.removal.duplicate_needs_code"))
    try:
        return str(petitions.public(typed or "")["code"])
    except petitions.PetitionNotFound:
        raise InvalidPetition(phrase("petition.removal.duplicate_not_found")) from None


def file_report(code: str, ground: Ground, duplicate_of: str | None, note: str | None, now: datetime) -> dict[str, Any]:
    """The petition is not touched, read for its identity and nothing else."""
    note = clean_note(note)
    duplicate = _duplicate_code(ground, duplicate_of)
    try:
        petition = petitions.public(code)
    except petitions.PetitionNotFound:
        raise WrongState(phrase("petition.report.already_removed")) from None
    return as_record(get_databases().create_document(DATABASE_ID, REPORTS_COLLECTION, ID.unique(), {
        "petitionId": petition["$id"], "code": petition["code"], "ground": ground.value, "duplicateOf": duplicate,
        "note": note, "state": ReportState.OPEN.value, "createdAt": now.isoformat(),
    }))


def open_reports() -> list[dict[str, Any]]:
    """Newest first: a contributor reads what has just come in."""
    return every_record(REPORTS_COLLECTION, [Query.equal("state", ReportState.OPEN.value), Query.order_desc("createdAt")])


def queue() -> list[Reported]:
    reports = open_reports()
    standing = petitions.by_ids([str(report["petitionId"]) for report in reports])
    against = Counter(str(report["petitionId"]) for report in reports)
    return [Reported(report, standing[petition_id], against[petition_id])
            for report in reports if (petition_id := str(report["petitionId"])) in standing]


def find_open(report_id: str) -> dict[str, Any]:
    reports = every_record(REPORTS_COLLECTION, [Query.equal("$id", report_id), Query.limit(1)])
    if not reports or reports[0].get("state") != ReportState.OPEN:
        raise ReportNotFound(report_id)
    return reports[0]


def _settle(report_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    return as_record(get_databases().update_document(DATABASE_ID, REPORTS_COLLECTION, report_id, changes))


def dismiss(principal: Principal, report_id: str, reason: Dismissal, now: datetime) -> dict[str, Any]:
    report = find_open(report_id)
    return _settle(report["$id"], {"state": ReportState.DISMISSED.value, "dismissedReason": reason.value,
                                  "settledById": principal.user_id, "settledByName": principal.name,
                                  "settledAt": now.isoformat()})


def close_open_reports(petition_id: str, now: datetime) -> int:
    """Called when a petition is removed: every open report on it has been answered by that."""
    reports = every_record(REPORTS_COLLECTION, [Query.equal("petitionId", petition_id),
                                                Query.equal("state", ReportState.OPEN.value), Query.select(["$id"])])
    for report in reports:
        _settle(report["$id"], {"state": ReportState.ACTED_ON.value, "settledAt": now.isoformat()})
    return len(reports)
