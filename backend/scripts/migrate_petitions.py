"""Move the petitions already in the database to Stage A, where nobody approves a petition.

docs/petition-migration.md holds the mapping this script follows and the record of what it did. In short:

    in_review           -> open, or closed if the draft-time screen now stops it
    open                -> open
    awaiting_response   -> awaiting_response (the 30-day response clock keeps running)
    responded           -> responded
    refused             -> closed, labelled "Refused under the earlier review process"
    withdrawn, closed   -> closed

Nothing is deleted. Every row keeps what it was in legacyStatus, and the trail gets a line saying what the move did
and why. A petition that was waiting for the MCE's review goes through the draft-time screen again, because Stage A
publishes without a reviewer: if its words no longer pass, it is closed with the reason rather than published to
nobody's decision. Existing signatures become signatures on version 1, and every petition gets a version 1 in
petition_versions so its edit history starts where its words did.

A row that fits no rule is left exactly as it is and listed at the end.

A dry run by default: it prints what it would do and writes nothing. --yes applies it. Run
scripts/create_petitions.py first: this script writes fields that script creates.

    backend/.venv/bin/python backend/scripts/migrate_petitions.py [--yes]
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from appwrite.query import Query

from app.services import petition_screen, petition_versions, petitions
from app.services.appwrite_client import DATABASE_ID, every_record, get_databases, quiet_sdk_deprecation_warnings
from app.services.ledger_documents import parse_datetime, utc_now
from app.services.petition_rules import (
    FIRST_VERSION,
    OPEN_FOR,
    PetitionAction,
    PetitionStatus,
    Scope,
)
from app.services.petition_signatures import SIGNATURES_COLLECTION
from app.services.phrases import phrase

KEPT = {status.value: status for status in (PetitionStatus.OPEN, PetitionStatus.AWAITING_RESPONSE, PetitionStatus.RESPONDED,
                                            PetitionStatus.CLOSED)}
ENDED_BY_THE_OLD_PROCESS = ("refused", "withdrawn")


@dataclass(frozen=True)
class Move:
    """Where one petition goes, and what a reader is told about how it got there."""

    status: PetitionStatus
    legacy_status: str
    label: str | None  # shown in the public trail, from the phrase catalogue
    note: str | None = None  # the whole reason, for the audit trail only


def move_for(status: str, screen_stop: str | None) -> Move | None:
    """The mapping, as a pure function. None means no rule fits this row, so nothing is written to it.

    screen_stop: what the draft-time screen now says about a petition that was waiting for review, or None when it
    passes or when the status makes the screen beside the point."""
    if status in KEPT:
        return Move(KEPT[status], status, None)
    if status in ENDED_BY_THE_OLD_PROCESS:
        return Move(PetitionStatus.CLOSED, status, phrase(f"petition.legacy.{status}"))
    if status == "in_review":
        if screen_stop:
            label = phrase("petition.legacy.closed_in_move")
            return Move(PetitionStatus.CLOSED, status, label, f"{label}: {screen_stop}")
        return Move(PetitionStatus.OPEN, status, None)
    return None


def screen_stop_for(petition: dict[str, Any]) -> str | None:
    """Only a petition that was waiting for the MCE is screened again: every other row was already public or
    already over, and re-screening those would take words down that nobody is about to publish."""
    if petition.get("status") != "in_review":
        return None
    return petition_screen.hard_stop(petition.get("title") or "", petition.get("body") or "")


def _published_at(petition: dict[str, Any], now: datetime) -> str:
    """A petition that was never published takes the date it was written, not today: it is the same petition."""
    return str(petition.get("publishedAt") or petition.get("submittedAt") or petition.get("createdAt") or now.isoformat())


def changes_for(petition: dict[str, Any], move: Move, now: datetime) -> dict[str, Any]:
    changes: dict[str, Any] = {"status": move.status.value, "legacyStatus": move.legacy_status,
                               "version": petition.get("version") or FIRST_VERSION,
                               "removalCount": petition.get("removalCount") or 0}
    published = _published_at(petition, now)
    changes["versionedAt"] = petition.get("versionedAt") or published
    if move.status == PetitionStatus.OPEN and not petition.get("publishedAt"):
        opened = parse_datetime(published) or now
        changes.update(publishedAt=published, closesAt=(opened + OPEN_FOR).isoformat(),
                       threshold=petition.get("threshold") or petitions.threshold_of(Scope(petition["scope"])))
    if move.status == PetitionStatus.CLOSED and not petition.get("closedAt"):
        changes["closedAt"] = now.isoformat()
    return changes


def action_for(move: Move) -> PetitionAction:
    return PetitionAction.PUBLISHED if move.status == PetitionStatus.OPEN else PetitionAction.CLOSED


def _stamp_signatures(petition_id: str) -> int:
    """Signatures given before versions were kept are signatures on version 1: they were given to those words."""
    unversioned = every_record(SIGNATURES_COLLECTION, [Query.equal("petitionId", petition_id), Query.is_null("version"),
                                                       Query.select(["$id"])])
    for signature in unversioned:
        get_databases().update_document(DATABASE_ID, SIGNATURES_COLLECTION, signature["$id"], {"version": FIRST_VERSION})
    return len(unversioned)


def _record_first_version(petition: dict[str, Any], at: str, now: datetime) -> bool:
    if petition_versions.versions_of(petition["$id"]):
        return False
    petition_versions.record_version(petition["$id"], petition, FIRST_VERSION, parse_datetime(at) or now)
    return True


def apply_move(petition: dict[str, Any], move: Move, now: datetime) -> dict[str, Any]:
    changes = changes_for(petition, move, now)
    updated = petitions.update_petition(petition["$id"], changes)
    _record_first_version(updated, changes["versionedAt"], now)
    _stamp_signatures(petition["$id"])
    petitions.record_history(updated, action_for(move), petitions.SYSTEM, str(petition.get("status")),
                             move.legacy_status, move.note or move.label)
    return updated


def every_petition() -> list[dict[str, Any]]:
    return every_record(petitions.PETITIONS_COLLECTION, [Query.order_asc("createdAt")])


def _describe(petition: dict[str, Any], move: Move | None) -> str:
    code, was = petition.get("code"), petition.get("status")
    if move is None:
        return f"untouched {code}: {was} fits no rule in the mapping"
    label = f' labelled "{move.label}"' if move.label else ""
    return f"{code}: {was} -> {move.status.value}, legacyStatus={move.legacy_status}{label}"


def run(apply_it: bool, now: datetime) -> int:
    moves = [(petition, move_for(str(petition.get("status")), screen_stop_for(petition))) for petition in every_petition()]
    for petition, move in moves:
        print(("" if apply_it else "[dry run] ") + _describe(petition, move))
        if apply_it and move is not None:
            apply_move(petition, move, now)
    untouched = sum(1 for _, move in moves if move is None)
    print(f"\n{len(moves)} petition(s) read, {len(moves) - untouched} {'moved' if apply_it else 'to move'}, {untouched} untouched")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="make the changes (default: a dry run)")
    parser.add_argument("--dry-run", action="store_true", help="print what would change and write nothing (the default)")
    args = parser.parse_args()
    quiet_sdk_deprecation_warnings()
    return run(args.yes and not args.dry_run, utc_now())


if __name__ == "__main__":
    sys.exit(main())
