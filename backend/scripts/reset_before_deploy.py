"""Clear the activity data before the first deploy, leaving the Ledger and everyone's sign-ins alone.

What goes: citizen reports and everything attached to them, the notifications outbox, petitions and everything
attached to them, and the photo objects of both. All of it, not only the [TEST] rows.

What stays: the Ledger (its documents, their files, the Postgres chunks and embeddings), contacts, teams,
departments, taxonomy, phrases, every Appwrite user and team membership, and every collection, attribute, index
and bucket. Nothing here drops or alters a schema; it deletes rows and objects.

A case and a petition are taken apart by the same code the [TEST] deleters use — `delete_test_reports.delete_case`
and `delete_test_petitions.delete` — so there is one description of what hangs off each of them, not two that can
drift. This script chooses which records to hand it; it doesn't know a second way to delete one.

Nothing is deleted unless the collection is named in DELETE, and the run stops before touching anything if a
collection has appeared that is on neither list: an unknown collection is a question, not a thing to skip quietly.

A dry run by default:

    backend/.venv/bin/python backend/scripts/reset_before_deploy.py            # says what would go
    backend/.venv/bin/python backend/scripts/reset_before_deploy.py --yes      # deletes it
"""

import sys
from typing import Any

import delete_test_petitions as petitions_script
import delete_test_reports as reports_script

from app.config import get_settings
from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.citizen_reports import NOTIFICATIONS_COLLECTION, REPORTS_COLLECTION
from app.services.petitions import PETITIONS_COLLECTION
from app.services.storage import get_minio

# Every collection whose rows go, and why it is safe to say so: each holds what residents did, not what the
# Assembly published. The two parents are listed apart because their attachments are deleted with them.
CASE_PARENT, PETITION_PARENT = REPORTS_COLLECTION, PETITIONS_COLLECTION
DELETE = {CASE_PARENT, PETITION_PARENT, NOTIFICATIONS_COLLECTION,
          *reports_script.RELATED, *petitions_script.RELATED}
# Named rather than inferred: a collection that is on neither list stops the run.
KEEP = {"ledger_documents", "document_history"}
# The only object names this script may remove. Ledger files live in another bucket and are never touched.
PHOTO_PREFIXES = ("reports/", "petitions/")


def unknown_collections() -> list[str]:
    live = {collection.id for collection in get_databases().list_collections(DATABASE_ID).collections}
    return sorted(live - DELETE - KEEP)


def every(collection: str) -> list[Any]:
    return petitions_script.documents(collection, [])


def orphan_photos() -> list[str]:
    """Objects under the two prefixes that no surviving record names: what a reset leaves behind if it only
    followed records. After the rows are gone every one of them is an orphan, which is the point."""
    bucket = get_settings().minio_photos_bucket
    return [obj.object_name for prefix in PHOTO_PREFIXES
            for obj in get_minio().list_objects(bucket, prefix=prefix, recursive=True)]


def take_apart_cases(apply: bool) -> int:
    photos = reports_script.photo_objects()
    cases = every(CASE_PARENT)
    for case in cases:
        if apply:
            reports_script.delete_case(case, reports_script.related(case.id), photos.get(case.id, []))
    return len(cases)


def take_apart_petitions(apply: bool) -> int:
    found = every(PETITION_PARENT)
    for petition in found:
        if apply:
            petitions_script.delete(petition, petitions_script.related(petition.id))
    return len(found)


def clear(collection: str, apply: bool) -> int:
    rows = every(collection)
    if apply:
        for row in rows:
            get_databases().delete_document(DATABASE_ID, collection, row.id)
    return len(rows)


def sweep_photos(apply: bool) -> int:
    bucket, names = get_settings().minio_photos_bucket, orphan_photos()
    if apply:
        for name in names:
            get_minio().remove_object(bucket, name)
    return len(names)


def main() -> int:
    quiet_sdk_deprecation_warnings()
    apply = "--yes" in sys.argv[1:]
    strays = unknown_collections()
    if strays:
        print("Stopping: these collections are on neither the Delete nor the Keep list, so this script does not "
              f"know whether their rows should go: {', '.join(strays)}")
        return 1

    counts = {CASE_PARENT: take_apart_cases(apply), PETITION_PARENT: take_apart_petitions(apply)}
    # Whatever the two above didn't reach: outbox rows belonging to no case, and any row left by a half-run.
    for collection in sorted(DELETE - {CASE_PARENT, PETITION_PARENT}):
        counts[collection] = clear(collection, apply)
    counts["photo objects"] = sweep_photos(apply)

    width = max(len(name) for name in counts)
    for name, count in sorted(counts.items()):
        print(f"{name:{width}}  {count:>5}")
    verb = "deleted" if apply else "would be deleted (dry run; --yes to delete)"
    print(f"\n{sum(counts.values())} records and objects {verb}.")
    print(f"Kept, untouched: {', '.join(sorted(KEEP))}, every Appwrite user and team, "
          "the Ledger's Postgres chunks, and the ledger files bucket.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
