"""Create the document_history collection (the portal's audit trail) in Appwrite.

Idempotent: attributes and indexes that already exist are left alone, so it is
safe to re-run. The collection has no client permissions; only the server,
using its API key, reads and writes it.

    backend/.venv/bin/python backend/scripts/create_document_history.py
"""

import sys
import time
from collections.abc import Callable

from appwrite.enums.databases_index_type import DatabasesIndexType
from appwrite.exception import AppwriteException

from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.document_history import COLLECTION_ID, NOTE_MAX, HistoryAction
from app.services.ledger_documents import LedgerStatus

ROLES = ["department", "contributor", "mce", "system"]
STATUSES = [status.value for status in LedgerStatus]
ATTRIBUTE_WAIT_SECONDS = 60


def attribute_creators() -> dict[str, Callable[[], object]]:
    db, coll = get_databases(), (DATABASE_ID, COLLECTION_ID)
    return {
        "documentId": lambda: db.create_string_attribute(*coll, "documentId", 64, True),
        "department": lambda: db.create_string_attribute(*coll, "department", 128, True),
        "action": lambda: db.create_enum_attribute(*coll, "action", [a.value for a in HistoryAction], True),
        "actorId": lambda: db.create_string_attribute(*coll, "actorId", 128, True),
        "actorName": lambda: db.create_string_attribute(*coll, "actorName", 256, True),
        "actorRole": lambda: db.create_enum_attribute(*coll, "actorRole", ROLES, True),
        "fromStatus": lambda: db.create_enum_attribute(*coll, "fromStatus", STATUSES, False),
        "toStatus": lambda: db.create_enum_attribute(*coll, "toStatus", STATUSES, True),
        "note": lambda: db.create_string_attribute(*coll, "note", NOTE_MAX, False),
        "fileId": lambda: db.create_string_attribute(*coll, "fileId", 256, False),
        "at": lambda: db.create_datetime_attribute(*coll, "at", True),
    }


INDEXES = {"idx_document_at": ["documentId", "at"], "idx_department_at": ["department", "at"]}


def ensure(label: str, create: Callable[[], object]) -> None:
    try:
        create()
        print(f"created   {label}")
    except AppwriteException as exc:
        if exc.code != 409:
            raise
        print(f"exists    {label}")


def wait_for_attributes(keys: list[str]) -> None:
    """Indexes can only be built once their attributes are available."""
    deadline = time.monotonic() + ATTRIBUTE_WAIT_SECONDS
    while time.monotonic() < deadline:
        listing = get_databases().list_attributes(DATABASE_ID, COLLECTION_ID)
        statuses = {a.key: str(getattr(a.status, "value", a.status)) for a in listing.attributes}
        if all(statuses.get(key) == "available" for key in keys):
            return
        time.sleep(2)
    raise TimeoutError(f"attributes not available after {ATTRIBUTE_WAIT_SECONDS}s")


def main() -> int:
    quiet_sdk_deprecation_warnings()
    db = get_databases()
    ensure(f"collection {COLLECTION_ID}", lambda: db.create_collection(DATABASE_ID, COLLECTION_ID, "Document history"))
    creators = attribute_creators()
    for key, create in creators.items():
        ensure(f"attribute {key}", create)
    wait_for_attributes(list(creators))
    # Appwrite reports a duplicate index as a 400, not a 409, so check first.
    existing = {index.key for index in db.list_indexes(DATABASE_ID, COLLECTION_ID).indexes}
    for key, attributes in INDEXES.items():
        if key in existing:
            print(f"exists    index {key}")
            continue
        db.create_index(DATABASE_ID, COLLECTION_ID, key, DatabasesIndexType.KEY, attributes)
        print(f"created   index {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
