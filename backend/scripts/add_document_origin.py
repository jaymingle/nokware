"""Add the `origin` attribute to ledger_documents and fill it in for every record.

`origin` says how a document entered the Ledger: "ama_website" for the AMA
import, "portal" for uploads through the Institution Portal. Ask shows it, so
an answer can tell "Published by Finance on ama.gov.gh" from "Submitted by
Finance".

The import is recognised by what it wrote, both of which the portal never
writes: a document ID starting "ama-" and a file stored under "ama/". A record
matching only one of the two is reported and left unset, for a person to check.

Idempotent: the attribute is created once, and records that already carry the
right origin are not rewritten.

    backend/.venv/bin/python backend/scripts/add_document_origin.py [--dry-run]
"""

import sys
import time
from collections import Counter
from typing import Any

from appwrite.exception import AppwriteException
from appwrite.query import Query

from app.services import ledger_documents
from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.ledger_documents import COLLECTION_ID, Origin

ATTRIBUTE = "origin"
PAGE_SIZE = 100
ATTRIBUTE_WAIT_SECONDS = 60
IMPORT_ID_PREFIX = "ama-"
IMPORT_FILE_PREFIX = "ama/"


def ensure_attribute() -> None:
    try:
        get_databases().create_enum_attribute(DATABASE_ID, COLLECTION_ID, ATTRIBUTE, [o.value for o in Origin], False)
        print(f"created   attribute {ATTRIBUTE}")
    except AppwriteException as exc:
        if exc.code != 409:
            raise
        print(f"exists    attribute {ATTRIBUTE}")
    deadline = time.monotonic() + ATTRIBUTE_WAIT_SECONDS
    while time.monotonic() < deadline:
        attribute = get_databases().get_attribute(DATABASE_ID, COLLECTION_ID, ATTRIBUTE)
        if str(getattr(attribute, "status", "")) in ("available", "AttributeStatus.AVAILABLE"):
            return
        time.sleep(2)
    raise TimeoutError(f"attribute {ATTRIBUTE} not available after {ATTRIBUTE_WAIT_SECONDS}s")


def all_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    while True:
        queries = [Query.limit(PAGE_SIZE), Query.order_asc("$id")]
        if records:
            queries.append(Query.cursor_after(records[-1]["$id"]))
        page, _ = ledger_documents.list_documents(queries)
        records.extend(page)
        if len(page) < PAGE_SIZE:
            return records


def origin_of(record: dict[str, Any]) -> Origin | None:
    """The record's origin, or None when the two import markers disagree."""
    by_id = record["$id"].startswith(IMPORT_ID_PREFIX)
    by_file = (record.get("fileId") or "").startswith(IMPORT_FILE_PREFIX)
    if by_id != by_file:
        return None
    return Origin.AMA_WEBSITE if by_id else Origin.PORTAL


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    quiet_sdk_deprecation_warnings()
    if not dry_run:
        ensure_attribute()
    counts: Counter[str] = Counter()
    for record in all_records():
        origin = origin_of(record)
        if origin is None:
            counts["unclear"] += 1
            print(f"UNCLEAR   {record['$id']}  fileId={record.get('fileId')}  {record.get('title')}")
        elif record.get(ATTRIBUTE) == origin.value:
            counts[f"{origin.value} (already set)"] += 1
        else:
            counts[f"{origin.value} (set now)" if not dry_run else f"{origin.value} (would set)"] += 1
            if not dry_run:
                ledger_documents.update_document(record["$id"], {ATTRIBUTE: origin.value})
    for label, count in sorted(counts.items()):
        print(f"{count:5}  {label}")
    return 1 if counts["unclear"] else 0


if __name__ == "__main__":
    sys.exit(main())
