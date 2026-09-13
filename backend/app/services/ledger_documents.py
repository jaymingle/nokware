"""Access to the ledger_documents collection in Appwrite.

One place for the collection's ID, its status values and the reads and writes
the backend makes, so ingestion, the AMA import and the portal routes agree.
"""

import re
from collections.abc import Iterable
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from appwrite.exception import AppwriteException
from appwrite.models import Document
from appwrite.query import Query

from app.services.appwrite_client import DATABASE_ID, get_databases

COLLECTION_ID = "ledger_documents"
INGESTION_ERROR_MAX = 1024  # size of the ingestionError attribute
EARLIEST_YEAR = 1900
_YEAR_RANGE = re.compile(r"\b((?:19|20)\d{2})\s*[-–—/]\s*(?:19|20)?\d{2}\b")
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")


class LedgerStatus(StrEnum):
    HELD = "held"
    PUBLISHED = "published"
    DISPUTED = "disputed"
    WITHDRAWN = "withdrawn"


class SourceType(StrEnum):
    AGENCY = "agency"
    CONTRIBUTOR = "contributor"


class IngestionState(StrEnum):
    PROCESSING = "processing"  # published, chunks not written yet
    SEARCHABLE = "searchable"
    NOT_SEARCHABLE = "not_searchable"  # ingested, but no extractable text
    FAILED = "failed"  # the last attempt failed; the deadline job retries it


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utc_now().isoformat()


def parse_datetime(value: str | None) -> datetime | None:
    """Appwrite datetime strings (ISO 8601 with offset) as aware datetimes."""
    return datetime.fromisoformat(value) if value else None


def plausible_year(year: int | None) -> int | None:
    """Keep a year only if it could be a document's own year (not in the future)."""
    return year if year and EARLIEST_YEAR <= year <= datetime.now().year else None


def year_from_title(title: str) -> int | None:
    """A document's year as stated in its title.

    A range such as "Medium Term Development Plan, 2026-2029" gives its first
    year; otherwise the first plausible year in the title is used.
    """
    year_range = _YEAR_RANGE.search(title)
    if year_range:
        return plausible_year(int(year_range.group(1)))
    for match in _YEAR.findall(title):
        year = plausible_year(int(match))
        if year:
            return year
    return None


def _record(document: Document) -> dict[str, Any]:
    """The document's attributes plus its $id and $createdAt."""
    return {**document.data, "$id": document.id, "$createdAt": document.createdat}


def get_documents(document_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Fetch many documents in one call; missing ids are simply absent."""
    ids = list(dict.fromkeys(document_ids))
    if not ids:
        return {}
    records, _ = list_documents([Query.equal("$id", ids), Query.limit(len(ids))])
    return {record["$id"]: record for record in records}


def list_documents(queries: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Documents matching the queries, and the total number that match."""
    listing = get_databases().list_documents(DATABASE_ID, COLLECTION_ID, queries=queries)
    return [_record(document) for document in listing.documents], int(listing.total)


def get_document(document_id: str) -> dict[str, Any]:
    """Return the document's attributes. Raises AppwriteException (404) if missing."""
    return _record(get_databases().get_document(DATABASE_ID, COLLECTION_ID, document_id))


def find_document(document_id: str) -> dict[str, Any] | None:
    """Like get_document, but None when the document does not exist."""
    try:
        return get_document(document_id)
    except AppwriteException as exc:
        if exc.code == 404:
            return None
        raise


def create_document(document_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return _record(get_databases().create_document(DATABASE_ID, COLLECTION_ID, document_id, data))


def update_document(document_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return _record(get_databases().update_document(DATABASE_ID, COLLECTION_ID, document_id, data))


def ingestion_state(record: dict[str, Any]) -> IngestionState | None:
    """Where a published document is in ingestion; None for unpublished ones."""
    if record.get("status") != LedgerStatus.PUBLISHED:
        return None
    if record.get("ingestedAt"):
        return IngestionState.SEARCHABLE if record.get("chunkCount") else IngestionState.NOT_SEARCHABLE
    return IngestionState.FAILED if record.get("ingestionError") else IngestionState.PROCESSING


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
