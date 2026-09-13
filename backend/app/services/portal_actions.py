"""Portal changes: uploads, workflow actions and the deadline job.

Every change re-reads the document under a per-document lock, applies a
workflow transition, writes it and appends the audit entry, so two changes to
one document never interleave. The lock is per process: run the API as a
single worker until changes move to Appwrite transactions.
"""

import hashlib
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from appwrite.id import ID
from appwrite.query import Query

from app.services import document_history, ledger_documents, workflow
from app.services.auth import Principal
from app.services.document_history import SYSTEM_ACTOR, Actor, HistoryAction
from app.services.ingestion import ingest_document
from app.services.ledger_documents import LedgerStatus, parse_datetime, utc_now
from app.services.portal_queries import load
from app.services.storage import upload_ledger_file
from app.services.workflow import Action, Submission

logger = logging.getLogger(__name__)

JOB_BATCH = 100
INGESTION_GRACE = timedelta(minutes=15)  # a published document still unindexed after this is retried
INGESTION_RETRY_AFTER = timedelta(minutes=30)  # a failed ingestion is retried at most this often

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


@contextmanager
def document_lock(document_id: str) -> Iterator[None]:
    with _locks_guard:
        lock = _locks.setdefault(document_id, threading.Lock())
    with lock:
        yield


def _actor(principal: Principal) -> Actor:
    return Actor(id=principal.user_id, name=principal.name, role=principal.role.value)


def _object_name(document_id: str, pdf: bytes) -> str:
    """Unique to the document and the file's content, so a resubmission never overwrites."""
    return f"portal/{document_id}/{hashlib.sha256(pdf).hexdigest()[:16]}.pdf"


def create(principal: Principal, submission: Submission, pdf: bytes) -> dict[str, Any]:
    """Upload a new document: published for departments, held for contributors."""
    document_id = ID.unique()
    object_name = _object_name(document_id, pdf)
    fields = workflow.new_document(principal, submission, object_name, utc_now())  # role checks before storing
    upload_ledger_file(pdf, "document.pdf", object_name=object_name)
    record = ledger_documents.create_document(document_id, fields)
    action = HistoryAction.UPLOADED if record["status"] == LedgerStatus.PUBLISHED else HistoryAction.SUBMITTED
    document_history.record(record, action, _actor(principal), None)
    return record


def act(
    principal: Principal, document_id: str, action: Action, note: str | None = None, pdf: bytes | None = None
) -> tuple[dict[str, Any], bool]:
    """Apply a workflow action; returns the updated record and whether it was published."""
    with document_lock(document_id):
        document = load(document_id)
        file_id = _object_name(document_id, pdf) if pdf else None
        change = workflow.transition(action, document, principal, utc_now(), note, file_id)
        if pdf and file_id:
            upload_ledger_file(pdf, "document.pdf", object_name=file_id)
        updated = ledger_documents.update_document(document_id, change.changes)
        document_history.record(updated, change.history, _actor(principal), change.from_status, note)
    return updated, change.publishes


def publish_expired() -> list[str]:
    """Publish every document whose clock has run out; returns their IDs."""
    now = utc_now()
    published = []
    for candidate in _clocks_run_out(now):
        with document_lock(candidate["$id"]):
            change = workflow.expiry(load(candidate["$id"]), now)  # re-read: it may have changed
            if change is None:
                continue
            updated = ledger_documents.update_document(candidate["$id"], change.changes)
            document_history.record(updated, change.history, SYSTEM_ACTOR, change.from_status)
        published.append(candidate["$id"])
    return published


def _clocks_run_out(now: datetime) -> list[dict[str, Any]]:
    due = [Query.less_than_equal("heldUntil", now.isoformat()), Query.limit(JOB_BATCH)]
    held, _ = ledger_documents.list_documents([Query.equal("status", LedgerStatus.HELD.value), *due])
    escalated, _ = ledger_documents.list_documents(
        [Query.equal("status", LedgerStatus.DISPUTED.value), Query.equal("escalatedToMce", True), *due]
    )
    return held + escalated


def needs_ingestion(record: dict[str, Any], now: datetime) -> bool:
    """Whether a published, unindexed document is due another ingestion attempt.

    One still processing gets INGESTION_GRACE to finish first; one that failed is
    retried once INGESTION_RETRY_AFTER has passed since the failure was recorded,
    so a document that always fails doesn't cost an attempt on every run.
    """
    if record.get("status") != LedgerStatus.PUBLISHED or record.get("ingestedAt"):
        return False
    if record.get("ingestionError"):
        failed_at = parse_datetime(record.get("$updatedAt"))
        return failed_at is None or failed_at <= now - INGESTION_RETRY_AFTER
    published_at = parse_datetime(record.get("publishedAt"))
    return published_at is None or published_at <= now - INGESTION_GRACE


def ingestion_backlog() -> list[str]:
    """Published documents whose ingestion failed or stalled and is due a retry."""
    now = utc_now()
    records, _ = ledger_documents.list_documents(
        [Query.equal("status", LedgerStatus.PUBLISHED.value), Query.is_null("ingestedAt"), Query.limit(JOB_BATCH)]
    )
    return [record["$id"] for record in records if needs_ingestion(record, now)]


def deadline_job() -> tuple[list[str], list[str]]:
    """Publish documents whose clock has run out, and list what needs ingesting.

    Returns (published IDs, IDs to ingest): the newly published plus any
    backlog. Callers ingest them, in the background or inline.
    """
    published = publish_expired()
    return published, list(dict.fromkeys([*published, *ingestion_backlog()]))


def run_deadline_job() -> None:
    """The whole job, ingestion included; for the app's own periodic runner."""
    published, to_ingest = deadline_job()
    if published:
        logger.info("Deadline job published %d document(s): %s", len(published), ", ".join(published))
    for document_id in to_ingest:
        ingest_quietly(document_id)


def ingest_quietly(document_id: str) -> None:
    """Background ingestion. Failures are recorded on the document for the job to retry."""
    try:
        ingest_document(document_id)
    except Exception:
        logger.exception("Ingestion failed for %s", document_id)
