"""The audit trail: one document_history entry per upload and status change.

Entries are written by the server only and never edited. Each one records who
acted (a snapshot of their name and role, so the trail reads correctly even if
an account changes later), the status before and after, any note (a dispute
reason, a contributor's response, a ruling), and the file in force at the time.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from appwrite.id import ID
from appwrite.query import Query

from app.services.appwrite_client import DATABASE_ID, get_databases
from app.services.ledger_documents import LedgerStatus, now_iso

COLLECTION_ID = "document_history"
NOTE_MAX = 2048
ENTRIES_PER_DOCUMENT_MAX = 100


class HistoryAction(StrEnum):
    UPLOADED = "uploaded"  # a department's own document, published at once
    SUBMITTED = "submitted"  # a contributor's document, held for review
    ACCEPTED = "accepted"
    DISPUTED = "disputed"
    DISPUTE_ACCEPTED = "dispute_accepted"
    RESUBMITTED = "resubmitted"
    ESCALATED = "escalated"
    UPHELD = "upheld"
    OVERRULED = "overruled"
    AUTO_PUBLISHED = "auto_published"  # the review clock ran out


@dataclass(frozen=True)
class Actor:
    id: str
    name: str
    role: str  # a Role value, or "system"


SYSTEM_ACTOR = Actor(id="system", name="Automatic publication", role="system")


def record(
    document: dict[str, Any],
    action: HistoryAction,
    actor: Actor,
    from_status: LedgerStatus | None,
    note: str | None = None,
) -> None:
    """Append an entry for a document as it stands after the change."""
    get_databases().create_document(
        DATABASE_ID,
        COLLECTION_ID,
        ID.unique(),
        {
            "documentId": document["$id"],
            "department": document["department"],
            "action": action.value,
            "actorId": actor.id,
            "actorName": actor.name,
            "actorRole": actor.role,
            "fromStatus": from_status.value if from_status else None,
            "toStatus": document["status"],
            "note": note[:NOTE_MAX] if note else None,
            "fileId": document.get("fileId"),
            "at": now_iso(),
        },
    )


def entries_for(document_id: str) -> list[dict[str, Any]]:
    """A document's trail, oldest first."""
    listing = get_databases().list_documents(
        DATABASE_ID,
        COLLECTION_ID,
        queries=[Query.equal("documentId", document_id), Query.order_asc("at"), Query.limit(ENTRIES_PER_DOCUMENT_MAX)],
    )
    return [entry.data for entry in listing.documents]
