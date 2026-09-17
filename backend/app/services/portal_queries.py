"""Portal reads: the queues each role works from, single documents and files."""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from appwrite.query import Query

from app.services import ledger_documents
from app.services.appwrite_client import get_users
from app.services.auth import Principal
from app.services.ledger_documents import LedgerStatus, parse_datetime
from app.services.storage import get_ledger_file_url
from app.services.workflow import NotAllowed, can_view

QUEUE_LIMIT = 100
FILE_LINK_SECONDS = 600
_FAR_FUTURE = datetime.max.replace(tzinfo=UTC)

_names: dict[str, str] = {}  # user ID -> display name; names are effectively static


class DocumentNotFound(Exception):
    pass


def load(document_id: str) -> dict[str, Any]:
    document = ledger_documents.find_document(document_id)
    if document is None:
        raise DocumentNotFound(document_id)
    return document


def load_visible(principal: Principal, document_id: str) -> dict[str, Any]:
    document = load(document_id)
    if not can_view(principal, document):
        raise NotAllowed("You can't see this document.")
    return document


def file_link(principal: Principal, document_id: str) -> str:
    return get_ledger_file_url(load_visible(principal, document_id)["fileId"], expires=FILE_LINK_SECONDS)


def public_file_link(document_id: str) -> str:
    """Anything unpublished is reported as not found, so the public can't learn that a held, disputed or withdrawn
    document exists."""
    document = load(document_id)
    if document.get("status") != LedgerStatus.PUBLISHED:
        raise DocumentNotFound(document_id)
    return get_ledger_file_url(document["fileId"], expires=FILE_LINK_SECONDS)


def review_queue(principal: Principal) -> list[dict[str, Any]]:
    records, _ = ledger_documents.list_documents(
        [
            Query.equal("department", principal.department),
            Query.equal("status", [LedgerStatus.HELD.value, LedgerStatus.DISPUTED.value]),
            Query.limit(QUEUE_LIMIT),
        ]
    )
    return sorted(records, key=_urgency)


def _urgency(record: dict[str, Any]) -> tuple[bool, datetime]:
    return record["status"] != LedgerStatus.HELD, parse_datetime(record.get("heldUntil")) or _FAR_FUTURE


def library(principal: Principal, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    return ledger_documents.list_documents(
        [
            Query.equal("department", principal.department),
            Query.equal("status", LedgerStatus.PUBLISHED.value),
            Query.order_desc("publishedAt"),
            Query.limit(limit),
            Query.offset(offset),
        ]
    )


def submissions(principal: Principal) -> list[dict[str, Any]]:
    records, _ = ledger_documents.list_documents(
        [Query.equal("uploadedBy", principal.user_id), Query.order_desc("$createdAt"), Query.limit(QUEUE_LIMIT)]
    )
    return records


def escalations() -> list[dict[str, Any]]:
    records, _ = ledger_documents.list_documents(
        [
            Query.equal("status", LedgerStatus.DISPUTED.value),
            Query.equal("escalatedToMce", True),
            Query.order_asc("heldUntil"),
            Query.limit(QUEUE_LIMIT),
        ]
    )
    return records


def display_names(user_ids: Iterable[str | None]) -> dict[str, str]:
    wanted = {user_id for user_id in user_ids if user_id}
    missing = sorted(wanted - _names.keys())
    if missing:
        users = get_users().list(queries=[Query.equal("$id", missing), Query.limit(len(missing))]).users
        _names.update({user.id: user.name for user in users})
    return {user_id: _names[user_id] for user_id in wanted if user_id in _names}
