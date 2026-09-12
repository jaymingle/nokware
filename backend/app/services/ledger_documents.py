"""Access to the ledger_documents collection in Appwrite.

One place for the collection's ID, its status values and the reads and writes
the backend makes, so ingestion, the AMA import and the portal routes agree.
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from appwrite.exception import AppwriteException

from app.services.appwrite_client import DATABASE_ID, get_databases

COLLECTION_ID = "ledger_documents"
INGESTION_ERROR_MAX = 1024  # size of the ingestionError attribute


class LedgerStatus(StrEnum):
    HELD = "held"
    PUBLISHED = "published"
    DISPUTED = "disputed"
    WITHDRAWN = "withdrawn"


class SourceType(StrEnum):
    AGENCY = "agency"
    CONTRIBUTOR = "contributor"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_document(document_id: str) -> dict[str, Any]:
    """Return the document's attributes. Raises AppwriteException (404) if missing."""
    return get_databases().get_document(DATABASE_ID, COLLECTION_ID, document_id).data


def find_document(document_id: str) -> dict[str, Any] | None:
    """Like get_document, but None when the document does not exist."""
    try:
        return get_document(document_id)
    except AppwriteException as exc:
        if exc.code == 404:
            return None
        raise


def create_document(document_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return get_databases().create_document(DATABASE_ID, COLLECTION_ID, document_id, data).data


def update_document(document_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return get_databases().update_document(DATABASE_ID, COLLECTION_ID, document_id, data).data


def mark_ingested(document_id: str, chunk_count: int, note: str | None = None) -> None:
    """Record a completed ingestion.

    chunk_count=0 with a note means the document is published but not
    searchable (e.g. an image-only PDF). ingestedAt being set is what tells the
    import and any retry that this document is done.
    """
    update_document(
        document_id,
        {"ingestedAt": now_iso(), "chunkCount": chunk_count, "ingestionError": note},
    )


def mark_ingestion_failed(document_id: str, error: str) -> None:
    """Record a failed attempt. ingestedAt is cleared so a retry picks it up."""
    update_document(
        document_id,
        {"ingestedAt": None, "chunkCount": None, "ingestionError": error[:INGESTION_ERROR_MAX]},
    )
