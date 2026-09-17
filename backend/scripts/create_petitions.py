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

All server-only: no client permissions. A dry run by default: it prints
what it would do. --yes applies it. It only adds; nothing is deleted. Safe to
re-run.

    backend/.venv/bin/python backend/scripts/create_petitions.py [--yes]
"""

import argparse
import sys

from appwrite.services.databases import Databases
from create_citizen_reports import ENCRYPTED_MIN, ID, KEY, TEAM, UNIQUE, Creator, ensure, ensure_indexes, values, wait_for_attributes

from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.petition_rules import (
    BODY_MAX,
    CODE_DIGITS,
    NAME_MAX,
    NOTE_MAX,
    REFUSALS,
    RESPONSE_KINDS,
    RESPONSE_MAX,
    TITLE_MAX,
    PetitionAction,
    PetitionStatus,
    PublishedBy,
    Scope,
)
from app.services.petition_signatures import SIGNATURES_COLLECTION as SIGNATURES
from app.services.petitions import HISTORY_COLLECTION as HISTORY
from app.services.petitions import PETITIONS_COLLECTION as PETITIONS
from app.services.phone_proof import Channel

HASH = 64  # a sha256 hex digest
TOPIC = 64
STATUS = 20
ISSUE_ID = 20


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
    }


def petition_state(db: Databases, c: tuple[str, str]) -> dict[str, Creator]:
    return {
        "status": lambda: db.create_enum_attribute(*c, "status", values(PetitionStatus), True),
        "submittedAt": lambda: db.create_datetime_attribute(*c, "submittedAt", True),
        "reviewDeadline": lambda: db.create_datetime_attribute(*c, "reviewDeadline", False),
        "resubmissions": lambda: db.create_integer_attribute(*c, "resubmissions", False, min=0, default=0),
        "publishedAt": lambda: db.create_datetime_attribute(*c, "publishedAt", False),
        "publishedBy": lambda: db.create_enum_attribute(*c, "publishedBy", values(PublishedBy), False),
        "closesAt": lambda: db.create_datetime_attribute(*c, "closesAt", False),
        "closedAt": lambda: db.create_datetime_attribute(*c, "closedAt", False),
        "threshold": lambda: db.create_integer_attribute(*c, "threshold", False, min=1),
        "signatureCount": lambda: db.create_integer_attribute(*c, "signatureCount", False, min=0, default=0),
        "refusalReason": lambda: db.create_enum_attribute(*c, "refusalReason", list(REFUSALS), False),
        "refusalNote": lambda: db.create_string_attribute(*c, "refusalNote", NOTE_MAX + 24, False),
        "duplicateOf": lambda: db.create_string_attribute(*c, "duplicateOf", CODE_DIGITS, False),
        "createdAt": lambda: db.create_datetime_attribute(*c, "createdAt", True),
        "thresholdReachedAt": lambda: db.create_datetime_attribute(*c, "thresholdReachedAt", False),
        "responseDue": lambda: db.create_datetime_attribute(*c, "responseDue", False),
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
        "action": lambda: db.create_enum_attribute(*c, "action", values(PetitionAction), True),
        "actorId": lambda: db.create_string_attribute(*c, "actorId", ID, True),
        "actorName": lambda: db.create_string_attribute(*c, "actorName", 256, False),
        "actorRole": lambda: db.create_enum_attribute(*c, "actorRole", ["creator", "mce", "system"], True),
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
        "createdAt": lambda: db.create_datetime_attribute(*c, "createdAt", True),
    }


def adjust_status_lists() -> None:
    db = get_databases()
    db.update_enum_attribute(DATABASE_ID, PETITIONS, "status", values(PetitionStatus), True, None)
    db.update_enum_attribute(DATABASE_ID, HISTORY, "action", values(PetitionAction), True, None)
    print("updated   petitions.status (up to responded), petition_history.action (up to creator_notified)")


PETITION_INDEXES = {
    "uniq_code": (UNIQUE, ["code"]),
    "idx_status_reviewDeadline": (KEY, ["status", "reviewDeadline"]),
    "idx_status_closesAt": (KEY, ["status", "closesAt"]),
    "idx_status_publishedAt": (KEY, ["status", "publishedAt"]),
    "idx_publishedBy": (KEY, ["publishedBy"]),
    "idx_creatorKey": (KEY, ["creatorKey"]),
    "idx_purgeAt": (KEY, ["purgeAt"]),
    "idx_status_responseDue": (KEY, ["status", "responseDue"]),
    "idx_status_signatures": (KEY, ["status", "signatureCount"]),
    "idx_status_respondedAt": (KEY, ["status", "respondedAt"]),
}
HISTORY_INDEXES = {"idx_petition_at": (KEY, ["petitionId", "at"]), "idx_action": (KEY, ["action"])}
SIGNATURE_INDEXES = {
    "uniq_signerKey": (UNIQUE, ["signerKey"]),
    "idx_petition_named_created": (KEY, ["petitionId", "named", "createdAt"]),
}


def build_schema() -> None:
    db = get_databases()
    plan = ((PETITIONS, "Petitions", petition_attributes(), PETITION_INDEXES),
            (HISTORY, "Petition history", history_attributes(), HISTORY_INDEXES),
            (SIGNATURES, "Petition signatures", signature_attributes(), SIGNATURE_INDEXES))
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
        print(f"[dry run] would create collections {PETITIONS} ({len(petition_attributes())} attributes, "
              f"{len(PETITION_INDEXES)} indexes), {HISTORY} ({len(history_attributes())} attributes, "
              f"{len(HISTORY_INDEXES)} indexes) and {SIGNATURES} ({len(signature_attributes())} attributes, "
              f"{len(SIGNATURE_INDEXES)} indexes), leaving any that exist as they are, and set the status lists "
              "to include every status and trail step up to P3's responded, no_response and creator_notified")
        return 0
    build_schema()
    print("\nPetitions are ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
