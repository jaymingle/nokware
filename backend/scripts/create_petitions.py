"""Create the Appwrite structure for petitions.

- petitions: one row per petition. The creator is stored as a keyed hash of
  their confirmed number (creatorKey); the number itself (creatorPhone) is
  encrypted at rest and deleted 30 days after the petition closes, is
  withdrawn, or is refused and not sent back. A name only if they chose to
  show it.
- petition_history: the audit trail, one row per step.
- petition_signatures (P2): one row per signature. No phone number: a keyed
  hash of number and petition together, unique, so a number signs once and
  can't be matched across petitions. A name only if the signer chose to show
  it (public).
- P3 adds the MCE's response to petitions. The MCE's name is kept for the
  trail and never shown.
- Stage E adds what residents say under a petition: petition_comments (one
  row per comment, holding a keyed hash of the number and the petition
  together and never the number, plus what a contributor's removal leaves on
  it) and petition_comment_reports (what readers report about a comment,
  settled in the same queue as a report about a petition).
- Stage A takes the MCE's review gate out and adds what replaces it, all
  additively: petition_versions (every wording a petition has had),
  petition_removals (a contributor's removal, and the only thing a tombstone
  is built from) and petition_reports (what readers report, which hides
  nothing); on petitions, the version fields, the removal fields, imageIds and
  legacyStatus; on a signature, the version it was signed on.

The status and action lists are written with the statuses and steps that
existed before Stage A as well as today's, so a row the migration has not
moved yet is still a row the schema accepts. Nothing is renamed and nothing
is dropped: the attributes the gate used (reviewDeadline, refusalReason,
publishedBy and the rest) are simply no longer written.

All server-only: no client permissions. A dry run by default: it prints
what it would do. --yes applies it. It only adds; nothing is deleted. Safe to
re-run.

    backend/.venv/bin/python backend/scripts/create_petitions.py [--yes]
"""

import argparse
import sys

from appwrite.services.databases import Databases
from create_citizen_reports import ENCRYPTED_MIN, HASH, ID, KEY, TEAM, UNIQUE, Creator, ensure, ensure_indexes, values, wait_for_attributes

from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.petition_comments import COMMENT_MAX
from app.services.petition_comments import COMMENT_REPORTS_COLLECTION as COMMENT_REPORTS
from app.services.petition_comments import COMMENTS_COLLECTION as COMMENTS
from app.services.petition_grounds import Dismissal, Ground
from app.services.petition_removals import REMOVALS_COLLECTION as REMOVALS
from app.services.petition_reports import REPORTS_COLLECTION as REPORTS
from app.services.petition_reports import ReportState
from app.services.petition_rules import (
    BODY_MAX,
    CODE_DIGITS,
    LEGACY_ACTIONS,
    LEGACY_STATUSES,
    NAME_MAX,
    NOTE_MAX,
    REMOVAL_NOTE_MAX,
    REPORT_NOTE_MAX,
    RESPONSE_KINDS,
    RESPONSE_MAX,
    TITLE_MAX,
    PetitionAction,
    PetitionStatus,
    Scope,
)
from app.services.petition_signatures import SIGNATURES_COLLECTION as SIGNATURES
from app.services.petition_versions import VERSIONS_COLLECTION as VERSIONS
from app.services.petitions import HISTORY_COLLECTION as HISTORY
from app.services.petitions import PETITIONS_COLLECTION as PETITIONS
from app.services.phone_proof import Channel

TOPIC = 64
STATUS = 20
ISSUE_ID = 20
OBJECT_NAME = 256  # an image's name in MinIO: "petitions/<32 hex>/01-<12 hex>.jpg" is 55, with room to spare


def statuses() -> list[str]:
    """Today's statuses and the ones that came before Stage A, so a row the migration has yet to move still fits."""
    return [*values(PetitionStatus), *LEGACY_STATUSES]


def actions() -> list[str]:
    return [*values(PetitionAction), *LEGACY_ACTIONS]


def petition_text(db: Databases, c: tuple[str, str]) -> dict[str, Creator]:
    return {
        "code": lambda: db.create_string_attribute(*c, "code", CODE_DIGITS, True),
        "title": lambda: db.create_string_attribute(*c, "title", TITLE_MAX + 50, True),
        "body": lambda: db.create_string_attribute(*c, "body", BODY_MAX + 96, True),
        "topic": lambda: db.create_string_attribute(*c, "topic", TOPIC, True),
        "recipients": lambda: db.create_string_attribute(*c, "recipients", TEAM, True, array=True),
        "scope": lambda: db.create_enum_attribute(*c, "scope", values(Scope), True),
        "wardLocation": lambda: db.create_string_attribute(*c, "wardLocation", TOPIC, False),
        "subMetro": lambda: db.create_string_attribute(*c, "subMetro", TOPIC, False),
        "issueId": lambda: db.create_string_attribute(*c, "issueId", ISSUE_ID, False),
        "documentIds": lambda: db.create_string_attribute(*c, "documentIds", ID, False, array=True),
        "imageIds": lambda: db.create_string_attribute(*c, "imageIds", OBJECT_NAME, False, array=True),
    }


def petition_state(db: Databases, c: tuple[str, str]) -> dict[str, Creator]:
    return {
        "status": lambda: db.create_enum_attribute(*c, "status", statuses(), True),
        "submittedAt": lambda: db.create_datetime_attribute(*c, "submittedAt", True),
        "publishedAt": lambda: db.create_datetime_attribute(*c, "publishedAt", False),
        "closesAt": lambda: db.create_datetime_attribute(*c, "closesAt", False),
        "closedAt": lambda: db.create_datetime_attribute(*c, "closedAt", False),
        "threshold": lambda: db.create_integer_attribute(*c, "threshold", False, min=1),
        "signatureCount": lambda: db.create_integer_attribute(*c, "signatureCount", False, min=0, default=0),
        "createdAt": lambda: db.create_datetime_attribute(*c, "createdAt", True),
        "thresholdReachedAt": lambda: db.create_datetime_attribute(*c, "thresholdReachedAt", False),
        "responseDue": lambda: db.create_datetime_attribute(*c, "responseDue", False),
        # The words as they stand now; every wording it has had is in petition_versions.
        "version": lambda: db.create_integer_attribute(*c, "version", False, min=1, default=1),
        "versionedAt": lambda: db.create_datetime_attribute(*c, "versionedAt", False),
        # What a removal leaves on the petition. None of it is public: the tombstone is built from the removal
        # record. removedFromStatus is where a republication puts it back.
        "removedAt": lambda: db.create_datetime_attribute(*c, "removedAt", False),
        "removalGround": lambda: db.create_enum_attribute(*c, "removalGround", values(Ground), False),
        "removalDuplicateOf": lambda: db.create_string_attribute(*c, "removalDuplicateOf", CODE_DIGITS, False),
        "removedFromStatus": lambda: db.create_string_attribute(*c, "removedFromStatus", STATUS, False),
        "removalCount": lambda: db.create_integer_attribute(*c, "removalCount", False, min=0, default=0),
        # What this petition's status was under the MCE's review gate, kept for good by the migration.
        "legacyStatus": lambda: db.create_string_attribute(*c, "legacyStatus", STATUS, False),
    }


def petition_response(db: Databases, c: tuple[str, str]) -> dict[str, Creator]:
    return {
        "responseKind": lambda: db.create_enum_attribute(*c, "responseKind", list(RESPONSE_KINDS), False),
        "responseText": lambda: db.create_string_attribute(*c, "responseText", RESPONSE_MAX + 96, False),
        "responseDepartment": lambda: db.create_string_attribute(*c, "responseDepartment", TEAM, False),
        "responseDocumentIds": lambda: db.create_string_attribute(*c, "responseDocumentIds", ID, False, array=True),
        "respondedAt": lambda: db.create_datetime_attribute(*c, "respondedAt", False),
        "respondedByName": lambda: db.create_string_attribute(*c, "respondedByName", 256, False),
        "noResponseAt": lambda: db.create_datetime_attribute(*c, "noResponseAt", False),
    }


def petition_creator(db: Databases, c: tuple[str, str]) -> dict[str, Creator]:
    return {
        "creatorKey": lambda: db.create_string_attribute(*c, "creatorKey", HASH, True),
        "creatorPhone": lambda: db.create_string_attribute(*c, "creatorPhone", ENCRYPTED_MIN, False, encrypt=True),
        "creatorChannel": lambda: db.create_enum_attribute(*c, "creatorChannel", values(Channel), False),
        "creatorName": lambda: db.create_string_attribute(*c, "creatorName", NAME_MAX + 20, False),
        "purgeAt": lambda: db.create_datetime_attribute(*c, "purgeAt", False),
    }


def petition_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, PETITIONS)
    return {**petition_text(db, c), **petition_state(db, c), **petition_response(db, c), **petition_creator(db, c)}


def history_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, HISTORY)
    return {
        "petitionId": lambda: db.create_string_attribute(*c, "petitionId", ID, True),
        "action": lambda: db.create_enum_attribute(*c, "action", actions(), True),
        "actorId": lambda: db.create_string_attribute(*c, "actorId", ID, True),
        "actorName": lambda: db.create_string_attribute(*c, "actorName", 256, False),
        "actorRole": lambda: db.create_enum_attribute(*c, "actorRole", ["creator", "contributor", "mce", "system"], True),
        "fromStatus": lambda: db.create_string_attribute(*c, "fromStatus", STATUS, False),
        "toStatus": lambda: db.create_string_attribute(*c, "toStatus", STATUS, True),
        "reason": lambda: db.create_string_attribute(*c, "reason", TOPIC, False),
        "note": lambda: db.create_string_attribute(*c, "note", NOTE_MAX + 24, False),
        "at": lambda: db.create_datetime_attribute(*c, "at", True),
    }


def signature_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, SIGNATURES)
    return {
        "petitionId": lambda: db.create_string_attribute(*c, "petitionId", ID, True),
        "signerKey": lambda: db.create_string_attribute(*c, "signerKey", HASH, True),
        "named": lambda: db.create_boolean_attribute(*c, "named", True),
        "name": lambda: db.create_string_attribute(*c, "name", NAME_MAX + 20, False),
        "channel": lambda: db.create_enum_attribute(*c, "channel", values(Channel), True),
        # Which wording of the petition this signature stands on. A signature given before versions were kept has
        # none, and is counted against the first version.
        "version": lambda: db.create_integer_attribute(*c, "version", False, min=1),
        "createdAt": lambda: db.create_datetime_attribute(*c, "createdAt", True),
    }


def version_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, VERSIONS)
    return {
        "petitionId": lambda: db.create_string_attribute(*c, "petitionId", ID, True),
        "version": lambda: db.create_integer_attribute(*c, "version", True, min=1),
        "title": lambda: db.create_string_attribute(*c, "title", TITLE_MAX + 50, True),
        "body": lambda: db.create_string_attribute(*c, "body", BODY_MAX + 96, True),
        "topic": lambda: db.create_string_attribute(*c, "topic", TOPIC, True),
        "scope": lambda: db.create_enum_attribute(*c, "scope", values(Scope), True),
        "wardLocation": lambda: db.create_string_attribute(*c, "wardLocation", TOPIC, False),
        "imageIds": lambda: db.create_string_attribute(*c, "imageIds", OBJECT_NAME, False, array=True),
        "at": lambda: db.create_datetime_attribute(*c, "at", True),
    }


def removal_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, REMOVALS)
    return {
        "petitionId": lambda: db.create_string_attribute(*c, "petitionId", ID, True),
        "code": lambda: db.create_string_attribute(*c, "code", CODE_DIGITS, True),
        "ground": lambda: db.create_enum_attribute(*c, "ground", values(Ground), True),
        "duplicateOf": lambda: db.create_string_attribute(*c, "duplicateOf", CODE_DIGITS, False),
        # The contributor's note is internal: the audit trail reads it, no page does.
        "note": lambda: db.create_string_attribute(*c, "note", REMOVAL_NOTE_MAX + 24, False),
        "removedById": lambda: db.create_string_attribute(*c, "removedById", ID, True),
        "removedByName": lambda: db.create_string_attribute(*c, "removedByName", 256, False),
        "previousRemovals": lambda: db.create_integer_attribute(*c, "previousRemovals", False, min=0, default=0),
        "at": lambda: db.create_datetime_attribute(*c, "at", True),
    }


def report_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, REPORTS)
    return {
        "petitionId": lambda: db.create_string_attribute(*c, "petitionId", ID, True),
        "code": lambda: db.create_string_attribute(*c, "code", CODE_DIGITS, True),
        "ground": lambda: db.create_enum_attribute(*c, "ground", values(Ground), True),
        "duplicateOf": lambda: db.create_string_attribute(*c, "duplicateOf", CODE_DIGITS, False),
        "note": lambda: db.create_string_attribute(*c, "note", REPORT_NOTE_MAX + 24, False),
        "state": lambda: db.create_enum_attribute(*c, "state", values(ReportState), True),
        "dismissedReason": lambda: db.create_enum_attribute(*c, "dismissedReason", values(Dismissal), False),
        "settledById": lambda: db.create_string_attribute(*c, "settledById", ID, False),
        "settledByName": lambda: db.create_string_attribute(*c, "settledByName", 256, False),
        "settledAt": lambda: db.create_datetime_attribute(*c, "settledAt", False),
        "createdAt": lambda: db.create_datetime_attribute(*c, "createdAt", True),
    }


def comment_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, COMMENTS)
    return {
        "petitionId": lambda: db.create_string_attribute(*c, "petitionId", ID, True),
        # The commenter as stored: a keyed hash of their confirmed number and the petition together, as a
        # signature's is. No number, and nothing to match against another petition's comments.
        "commenterKey": lambda: db.create_string_attribute(*c, "commenterKey", HASH, True),
        "name": lambda: db.create_string_attribute(*c, "name", NAME_MAX + 20, True),
        "text": lambda: db.create_string_attribute(*c, "text", COMMENT_MAX + 24, True),
        "createdAt": lambda: db.create_datetime_attribute(*c, "createdAt", True),
        # What a contributor's removal leaves: the ground stands where the words were, and the words are no
        # longer read.
        "removalGround": lambda: db.create_enum_attribute(*c, "removalGround", values(Ground), False),
        "removedAt": lambda: db.create_datetime_attribute(*c, "removedAt", False),
        "removedById": lambda: db.create_string_attribute(*c, "removedById", ID, False),
        "removedByName": lambda: db.create_string_attribute(*c, "removedByName", 256, False),
    }


def comment_report_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, COMMENT_REPORTS)
    return {
        "petitionId": lambda: db.create_string_attribute(*c, "petitionId", ID, True),
        "code": lambda: db.create_string_attribute(*c, "code", CODE_DIGITS, True),
        "commentId": lambda: db.create_string_attribute(*c, "commentId", ID, True),
        # The same four grounds a petition is reported on. A duplicate names no other petition here: a comment
        # repeats what is on its own page.
        "ground": lambda: db.create_enum_attribute(*c, "ground", values(Ground), True),
        "note": lambda: db.create_string_attribute(*c, "note", REPORT_NOTE_MAX + 24, False),
        "state": lambda: db.create_enum_attribute(*c, "state", values(ReportState), True),
        "dismissedReason": lambda: db.create_enum_attribute(*c, "dismissedReason", values(Dismissal), False),
        "settledById": lambda: db.create_string_attribute(*c, "settledById", ID, False),
        "settledByName": lambda: db.create_string_attribute(*c, "settledByName", 256, False),
        "settledAt": lambda: db.create_datetime_attribute(*c, "settledAt", False),
        "createdAt": lambda: db.create_datetime_attribute(*c, "createdAt", True),
    }


def adjust_status_lists() -> None:
    """Re-derived every run: today's statuses and steps, plus the ones from before Stage A, which no code writes
    again but old rows still carry."""
    db = get_databases()
    db.update_enum_attribute(DATABASE_ID, PETITIONS, "status", statuses(), True, None)
    db.update_enum_attribute(DATABASE_ID, HISTORY, "action", actions(), True, None)
    print("updated   petitions.status and petition_history.action (Stage A's, and the ones they replaced)")


PETITION_INDEXES = {
    "uniq_code": (UNIQUE, ["code"]),
    "idx_status_closesAt": (KEY, ["status", "closesAt"]),
    "idx_status_publishedAt": (KEY, ["status", "publishedAt"]),
    "idx_creatorKey": (KEY, ["creatorKey"]),
    "idx_purgeAt": (KEY, ["purgeAt"]),
    "idx_status_responseDue": (KEY, ["status", "responseDue"]),
    "idx_status_signatures": (KEY, ["status", "signatureCount"]),
    "idx_status_respondedAt": (KEY, ["status", "respondedAt"]),
    "idx_legacyStatus": (KEY, ["legacyStatus"]),
}
HISTORY_INDEXES = {"idx_petition_at": (KEY, ["petitionId", "at"]), "idx_action": (KEY, ["action"])}
SIGNATURE_INDEXES = {
    "uniq_signerKey": (UNIQUE, ["signerKey"]),
    "idx_petition_named_created": (KEY, ["petitionId", "named", "createdAt"]),
    "idx_petition_version": (KEY, ["petitionId", "version"]),
}
VERSION_INDEXES = {"idx_petition_version": (KEY, ["petitionId", "version"])}
REMOVAL_INDEXES = {"idx_petition_at": (KEY, ["petitionId", "at"]), "idx_ground": (KEY, ["ground"])}
REPORT_INDEXES = {"idx_state_created": (KEY, ["state", "createdAt"]), "idx_petition_state": (KEY, ["petitionId", "state"])}
COMMENT_INDEXES = {"idx_petition_created": (KEY, ["petitionId", "createdAt"]), "idx_commenterKey": (KEY, ["commenterKey"])}
COMMENT_REPORT_INDEXES = {"idx_state_created": (KEY, ["state", "createdAt"]), "idx_comment_state": (KEY, ["commentId", "state"])}


def build_schema() -> None:
    db = get_databases()
    plan = ((PETITIONS, "Petitions", petition_attributes(), PETITION_INDEXES),
            (HISTORY, "Petition history", history_attributes(), HISTORY_INDEXES),
            (SIGNATURES, "Petition signatures", signature_attributes(), SIGNATURE_INDEXES),
            (VERSIONS, "Petition versions", version_attributes(), VERSION_INDEXES),
            (REMOVALS, "Petition removals", removal_attributes(), REMOVAL_INDEXES),
            (REPORTS, "Petition reports", report_attributes(), REPORT_INDEXES),
            (COMMENTS, "Petition comments", comment_attributes(), COMMENT_INDEXES),
            (COMMENT_REPORTS, "Petition comment reports", comment_report_attributes(), COMMENT_REPORT_INDEXES))
    for collection, name, creators, indexes in plan:
        ensure(f"collection {collection}", lambda collection=collection, name=name: db.create_collection(DATABASE_ID, collection, name))
        for key, create in creators.items():
            ensure(f"attribute {collection}.{key}", create)
        wait_for_attributes(collection, list(creators))
        ensure_indexes(collection, indexes)
    adjust_status_lists()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="make the changes (default: a dry run)")
    args = parser.parse_args()
    quiet_sdk_deprecation_warnings()
    if not args.yes:
        planned = ((PETITIONS, petition_attributes(), PETITION_INDEXES), (HISTORY, history_attributes(), HISTORY_INDEXES),
                   (SIGNATURES, signature_attributes(), SIGNATURE_INDEXES), (VERSIONS, version_attributes(), VERSION_INDEXES),
                   (REMOVALS, removal_attributes(), REMOVAL_INDEXES), (REPORTS, report_attributes(), REPORT_INDEXES),
                   (COMMENTS, comment_attributes(), COMMENT_INDEXES),
                   (COMMENT_REPORTS, comment_report_attributes(), COMMENT_REPORT_INDEXES))
        for collection, creators, indexes in planned:
            print(f"[dry run] {collection}: {len(creators)} attributes, {len(indexes)} indexes, "
                  "leaving whatever exists as it is")
        print(f"[dry run] would set petitions.status to {statuses()} and petition_history.action to {actions()}")
        return 0
    build_schema()
    print("\nPetitions are ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
