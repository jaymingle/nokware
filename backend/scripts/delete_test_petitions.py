"""List, and with --yes delete, test petitions: those whose title starts "[TEST]".

For each: its signatures (petition_signatures), its trail (petition_history)
and the petition itself, in that order. Nothing else refers to a petition.

A dry run by default: nothing is deleted without --yes. Deletion is permanent.

    backend/.venv/bin/python backend/scripts/delete_test_petitions.py [--yes]
"""

import sys
from typing import Any

from appwrite.query import Query

from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.petition_signatures import SIGNATURES_COLLECTION as SIGNATURES
from app.services.petitions import HISTORY_COLLECTION as HISTORY, PETITIONS_COLLECTION as PETITIONS

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


def test_petitions() -> list[Any]:
    return [p for p in documents(PETITIONS, [Query.starts_with("title", TEST_PREFIX)]) if p.data["title"].startswith(TEST_PREFIX)]


def related(petition_id: str) -> dict[str, list[Any]]:
    by_petition = [Query.equal("petitionId", petition_id)]
    return {SIGNATURES: documents(SIGNATURES, by_petition), HISTORY: documents(HISTORY, by_petition)}


def delete(petition: Any, rows: dict[str, list[Any]]) -> None:
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
        print(f"{petition.data['code']}  {petition.data['status']:<18} {len(rows[SIGNATURES]):>4} signature(s)  "
              f"{len(rows[HISTORY]):>3} trail entr(ies)  {petition.data['title'][:60]}")
        if apply:
            delete(petition, rows)
    verb = "deleted" if apply else "would delete (dry run; --yes to delete)"
    print(f"\n{len(petitions)} test petition(s) {verb}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
