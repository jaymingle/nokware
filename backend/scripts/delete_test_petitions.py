"""List, and with --yes delete, test petitions: those whose title starts "[TEST]".

For each: its images in object storage, every row that names it — signatures,
trail, versions, removals, reports, comments, comment reports, department
shares — and then the petition itself. Every collection keyed by petitionId is
listed here, so a fixture leaves nothing orphaned behind it; a new one belongs
in RELATED.

A dry run by default: nothing is deleted without --yes. Deletion is permanent.

    backend/.venv/bin/python backend/scripts/delete_test_petitions.py [--yes]
"""

import sys
from typing import Any

from appwrite.query import Query

from app.config import get_settings
from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.petition_comments import COMMENT_REPORTS_COLLECTION, COMMENTS_COLLECTION
from app.services.petition_departments import SHARES_COLLECTION
from app.services.petition_removals import REMOVALS_COLLECTION
from app.services.petition_reports import REPORTS_COLLECTION
from app.services.petition_signatures import SIGNATURES_COLLECTION as SIGNATURES
from app.services.petition_versions import VERSIONS_COLLECTION
from app.services.petitions import HISTORY_COLLECTION as HISTORY
from app.services.petitions import PETITIONS_COLLECTION as PETITIONS
from app.services.storage import get_minio
from app.services.test_fixtures import TEST_PREFIX

PAGE = 100
# Comment reports are deleted before the comments they name, so a half-finished run never leaves a report
# pointing at nothing.
RELATED = (COMMENT_REPORTS_COLLECTION, COMMENTS_COLLECTION, SHARES_COLLECTION, REPORTS_COLLECTION,
           REMOVALS_COLLECTION, VERSIONS_COLLECTION, SIGNATURES, HISTORY)


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


def test_petitions() -> list[Any]:
    return [p for p in documents(PETITIONS, [Query.starts_with("title", TEST_PREFIX)]) if p.data["title"].startswith(TEST_PREFIX)]


def related(petition_id: str) -> dict[str, list[Any]]:
    by_petition = [Query.equal("petitionId", petition_id)]
    return {collection: documents(collection, by_petition) for collection in RELATED}


def delete_images(petition: Any) -> int:
    """The image files themselves. A version keeps the names of the images it had, so every version's are taken."""
    names = {name for version in documents(VERSIONS_COLLECTION, [Query.equal("petitionId", petition.id)])
             for name in version.data.get("imageIds") or []}
    names.update(petition.data.get("imageIds") or [])
    bucket = get_settings().minio_photos_bucket
    for name in names:
        get_minio().remove_object(bucket, name)
    return len(names)


def delete(petition: Any, rows: dict[str, list[Any]]) -> None:
    delete_images(petition)
    for collection, found in rows.items():
        for row in found:
            get_databases().delete_document(DATABASE_ID, collection, row.id)
    get_databases().delete_document(DATABASE_ID, PETITIONS, petition.id)


def main() -> int:
    quiet_sdk_deprecation_warnings()
    apply = "--yes" in sys.argv[1:]
    petitions = test_petitions()
    for petition in petitions:
        rows = related(petition.id)
        counted = ", ".join(f"{len(found)} {collection.removeprefix('petition_')}" for collection, found in rows.items() if found)
        print(f"{petition.data['code']}  {petition.data['status']:<18} {petition.data['title'][:52]:<52} {counted}")
        if apply:
            delete(petition, rows)
    verb = "deleted" if apply else "would delete (dry run; --yes to delete)"
    print(f"\n{len(petitions)} test petition(s) {verb}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
