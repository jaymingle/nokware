"""Remove every "[TEST] ..." Ledger document and everything derived from it.

For each ledger_documents record whose title starts with "[TEST] ", deletes, in
order (so Ask stops finding it first):
  1. its chunks in Postgres (document_chunks)
  2. its PDFs in MinIO: every object under portal/<document id>/, which covers
     resubmitted versions (AMA import objects under ama/ are never touched)
  3. its audit entries (document_history)
  4. the record itself

A dry run by default: it lists what would go and changes nothing. Pass --yes
to delete. Deletion is permanent.

    backend/.venv/bin/python backend/scripts/delete_test_documents.py          # dry run
    backend/.venv/bin/python backend/scripts/delete_test_documents.py --yes    # delete
"""

import argparse
import sys
from dataclasses import dataclass
from typing import Any

from appwrite.query import Query

from app.config import get_settings
from app.services import document_history, ledger_documents
from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.storage import get_minio
from app.services.vectorstore import DOCUMENT_ID_COLUMN, TABLE_NAME, connect

TEST_PREFIX = "[TEST] "
PAGE = 100


@dataclass
class TestDocument:
    record: dict[str, Any]
    chunks: int
    objects: list[str]
    history_ids: list[str]


def test_records() -> list[dict[str, Any]]:
    found, cursor = [], None
    while True:
        queries = [Query.limit(PAGE), *([Query.cursor_after(cursor)] if cursor else [])]
        page, _ = ledger_documents.list_documents(queries)
        found += [r for r in page if str(r.get("title", "")).startswith(TEST_PREFIX)]
        if len(page) < PAGE:
            return found
        cursor = page[-1]["$id"]


def chunk_count(document_id: str | None = None) -> int:
    where = f" WHERE {DOCUMENT_ID_COLUMN} = %s" if document_id else ""
    with connect() as conn:
        return conn.execute(f"SELECT count(*) FROM {TABLE_NAME}{where}", [document_id] if document_id else []).fetchone()[0]


def inspect(record: dict[str, Any]) -> TestDocument:
    document_id = record["$id"]
    listing = get_databases().list_documents(
        DATABASE_ID, document_history.COLLECTION_ID, queries=[Query.equal("documentId", document_id), Query.limit(PAGE)]
    )
    objects = get_minio().list_objects(get_settings().minio_ledger_bucket, prefix=f"portal/{document_id}/", recursive=True)
    return TestDocument(
        record=record,
        chunks=chunk_count(document_id),
        objects=[obj.object_name for obj in objects],
        history_ids=[entry.id for entry in listing.documents],
    )


def delete(document: TestDocument) -> None:
    document_id = document.record["$id"]
    with connect() as conn:
        conn.execute(f"DELETE FROM {TABLE_NAME} WHERE {DOCUMENT_ID_COLUMN} = %s", [document_id])
    for object_name in document.objects:
        get_minio().remove_object(get_settings().minio_ledger_bucket, object_name)
    for entry_id in document.history_ids:
        get_databases().delete_document(DATABASE_ID, document_history.COLLECTION_ID, entry_id)
    get_databases().delete_document(DATABASE_ID, ledger_documents.COLLECTION_ID, document_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete [TEST] Ledger documents and their data.")
    parser.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    args = parser.parse_args()
    quiet_sdk_deprecation_warnings()
    documents = [inspect(record) for record in test_records()]
    for doc in documents:
        print(
            f"{doc.record['$id']}  {doc.record.get('status', ''):<10} {doc.record['title']}\n"
            f"    {doc.chunks} chunk(s), {len(doc.objects)} file(s), {len(doc.history_ids)} audit entr(ies)"
        )
    print(f"{len(documents)} [TEST] document(s). Chunks in Postgres now: {chunk_count()}")
    if not args.yes:
        print("Dry run: nothing deleted. Re-run with --yes to delete.")
        return 0
    for doc in documents:
        delete(doc)
    print(f"Deleted {len(documents)} document(s). Chunks in Postgres now: {chunk_count()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
