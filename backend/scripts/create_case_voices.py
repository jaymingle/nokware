"""Create the Appwrite structure for "add your voice", and give existing civic reports a public ID.

- citizen_reports gains publicId (a civic issue's public ID; the reference and
  the case ID open a status page, so neither can be shown) and voiceCount.
- A new collection, case_voices: one row per resident who said an open civic
  issue affects them too. A name, if given, is encrypted at rest and deleted 30
  days after the case closes; the device hash lets one browser add one voice.
- Every existing civic-service report without a public ID gets one.

A dry run by default: it prints what it would do. --yes applies it. It only
adds; nothing is deleted. Safe to re-run.

    backend/.venv/bin/python backend/scripts/create_case_voices.py [--yes]
"""

import argparse
import sys

from appwrite.exception import AppwriteException
from appwrite.query import Query
from create_citizen_reports import ENCRYPTED_MIN, ID, KEY, UNIQUE, Creator, ensure, ensure_indexes, wait_for_attributes

from app.services.appwrite_client import DATABASE_ID, every_record, get_databases, quiet_sdk_deprecation_warnings
from app.services.citizen_reports import REPORTS_COLLECTION as REPORTS
from app.services.citizen_reports import VOICES_COLLECTION as VOICES
from app.services.report_rules import PUBLIC_ID_LENGTH, new_public_id
from app.services.report_taxonomy import Category

HASH = 64  # a sha256 hex digest


def report_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, REPORTS)
    return {
        "publicId": lambda: db.create_string_attribute(*c, "publicId", PUBLIC_ID_LENGTH, False),
        "voiceCount": lambda: db.create_integer_attribute(*c, "voiceCount", False, min=0, default=0),
    }


def voice_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, VOICES)
    return {
        "caseId": lambda: db.create_string_attribute(*c, "caseId", ID, True),
        "named": lambda: db.create_boolean_attribute(*c, "named", True),
        "name": lambda: db.create_string_attribute(*c, "name", ENCRYPTED_MIN, False, encrypt=True),
        "deviceHash": lambda: db.create_string_attribute(*c, "deviceHash", HASH, True),
        "createdAt": lambda: db.create_datetime_attribute(*c, "createdAt", True),
        "purgeAt": lambda: db.create_datetime_attribute(*c, "purgeAt", False),
    }


REPORT_INDEXES = {"uniq_publicId": (UNIQUE, ["publicId"]), "idx_category_status": (KEY, ["category", "status"])}
VOICE_INDEXES = {"uniq_deviceHash": (UNIQUE, ["deviceHash"]), "idx_caseId": (KEY, ["caseId"]), "idx_purgeAt": (KEY, ["purgeAt"])}


def build_schema() -> None:
    db = get_databases()
    ensure(f"collection {VOICES}", lambda: db.create_collection(DATABASE_ID, VOICES, "Case voices"))
    plan = ((REPORTS, report_attributes(), REPORT_INDEXES), (VOICES, voice_attributes(), VOICE_INDEXES))
    for collection, creators, indexes in plan:
        for key, create in creators.items():
            ensure(f"attribute {collection}.{key}", create)
        wait_for_attributes(collection, list(creators))
        ensure_indexes(collection, indexes)


def civic_without_public_id() -> list[dict[str, str]]:
    everyday = every_record(REPORTS, [Query.equal("category", Category.CIVIC_SERVICE.value), Query.select(["reference"])])
    have = {r["$id"] for r in every_record(REPORTS, [Query.is_not_null("publicId"), Query.select(["reference"])])}
    return [r for r in everyday if r["$id"] not in have]


def dry_run_missing() -> list[dict[str, str]]:
    """The civic reports a run would give a public ID: all of them, before publicId exists."""
    try:
        return civic_without_public_id()
    except AppwriteException:  # publicId isn't an attribute yet
        return every_record(REPORTS, [Query.equal("category", Category.CIVIC_SERVICE.value), Query.select(["reference"])])


def backfill() -> int:
    missing = civic_without_public_id()
    for report in missing:
        print(f"  public ID for {report['reference']}")
        get_databases().update_document(DATABASE_ID, REPORTS, report["$id"], {"publicId": new_public_id(), "voiceCount": 0})
    return len(missing)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="make the changes (default: a dry run)")
    args = parser.parse_args()
    quiet_sdk_deprecation_warnings()
    if not args.yes:
        print("[dry run] would create collection case_voices, add citizen_reports.publicId and .voiceCount, and their indexes"
              " (any that exist are left as they are)")
        missing = dry_run_missing()
        print(f"[dry run] {len(missing)} civic report(s) would get a public ID: {', '.join(r['reference'] for r in missing) or 'none'}")
        return 0
    build_schema()
    count = backfill()
    print(f"\n{count} civic report(s) given a public ID.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
