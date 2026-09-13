"""List, and with --yes delete, test citizen reports: those whose description starts "[TEST]".

For each: the case, its assignments, audit trail, contact, outbox rows and
photos. Also lists photos under reports/ that belong to no case (left by a
filing that failed after its photos were stored).

A dry run by default: nothing is deleted without --yes.

    backend/.venv/bin/python backend/scripts/delete_test_reports.py [--yes]
"""

import sys
from typing import Any

from appwrite.query import Query

from app.config import get_settings
from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.case_history import COLLECTION_ID as HISTORY
from app.services.citizen_reports import (
    ASSIGNMENTS_COLLECTION,
    CONTACTS_COLLECTION,
    NOTIFICATIONS_COLLECTION,
    REPORTS_COLLECTION,
)
from app.services.storage import get_minio

TEST_PREFIX = "[TEST]"
PAGE = 100


def documents(collection: str, queries: list[str]) -> list[Any]:
    found: list[Any] = []
    while True:
        page_queries = [*queries, Query.limit(PAGE), Query.order_asc("$id")]
        if found:
            page_queries.append(Query.cursor_after(found[-1].id))
        page = get_databases().list_documents(DATABASE_ID, collection, queries=page_queries).documents
        found.extend(page)
        if len(page) < PAGE:
            return found


def photo_objects() -> dict[str, list[str]]:
    """Every stored report photo, by the case ID in its path."""
    by_case: dict[str, list[str]] = {}
    bucket = get_settings().minio_photos_bucket
    for obj in get_minio().list_objects(bucket, prefix="reports/", recursive=True):
        by_case.setdefault(obj.object_name.split("/")[1], []).append(obj.object_name)
    return by_case


def related(case_id: str) -> dict[str, list[Any]]:
    by_case = [Query.equal("caseId", case_id)]
    return {
        ASSIGNMENTS_COLLECTION: documents(ASSIGNMENTS_COLLECTION, by_case),
        HISTORY: documents(HISTORY, by_case),
        NOTIFICATIONS_COLLECTION: documents(NOTIFICATIONS_COLLECTION, by_case),
        CONTACTS_COLLECTION: documents(CONTACTS_COLLECTION, by_case),
    }


def delete_case(case: Any, rows: dict[str, list[Any]], photos: list[str]) -> None:
    db = get_databases()
    for collection, found in rows.items():
        for document in found:
            db.delete_document(DATABASE_ID, collection, document.id)
    for name in photos:
        get_minio().remove_object(get_settings().minio_photos_bucket, name)
    db.delete_document(DATABASE_ID, REPORTS_COLLECTION, case.id)


def main() -> int:
    quiet_sdk_deprecation_warnings()
    delete = "--yes" in sys.argv
    cases = documents(REPORTS_COLLECTION, [Query.starts_with("description", TEST_PREFIX)])
    photos = photo_objects()
    known = {d.id for d in documents(REPORTS_COLLECTION, [])}
    orphans = [name for case_id, names in photos.items() if case_id not in known for name in names]
    for case in cases:
        rows = related(case.id)
        counts = ", ".join(f"{len(found)} {collection}" for collection, found in rows.items())
        print(f"{case.id}  {case.data['reference']}  {case.data['category']:16} {case.data['status']:12} "
              f"{counts}, {len(photos.get(case.id, []))} photo(s)")
        if delete:
            delete_case(case, rows, photos.get(case.id, []))
    for name in orphans:
        print(f"orphan photo  {name}")
        if delete:
            get_minio().remove_object(get_settings().minio_photos_bucket, name)
    print(f"{len(cases)} test report(s), {len(orphans)} orphan photo(s).")
    print("Deleted." if delete else "Dry run: nothing deleted. Re-run with --yes to delete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
