"""The case audit trail: one case_history entry per step in a citizen report's life.

Written by the server only and never edited. Each entry records who acted (a
snapshot of their name and role), the status before and after, the recipients
involved and any note. For a personal-safety case an entry never carries the
report's description: the trail says what happened, not what was reported.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from appwrite.id import ID
from appwrite.query import Query

from app.services.appwrite_client import DATABASE_ID, get_databases
from app.services.auth import Principal
from app.services.ledger_documents import now_iso

COLLECTION_ID = "case_history"
NOTE_MAX = 2048
ENTRIES_PER_CASE_MAX = 100


class CaseHistoryAction(StrEnum):
    SUBMITTED = "submitted"
    CLASSIFIED = "classified"  # topic, severity and recipients, and how they were decided
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    REASSIGNED = "reassigned"
    ESCALATION_CONFIRMED = "escalation_confirmed"
    RECLASSIFIED = "reclassified"  # a person changed the category, e.g. out of personal safety
    NOTIFIED = "notified"  # "SMS sent", never the number
    CONTACT_DELETED = "contact_deleted"
    LOCATION_SHARED = "location_shared"  # a personal-safety reporter chose to share where they are; never the place
    LOCATION_VIEWED = "location_viewed"  # a responder opened it: the service and the time, shown to the citizen
    LOCATION_REMOVED = "location_removed"


class ActorRole(StrEnum):
    DEPARTMENT = "department"
    AGENCY = "agency"
    MCE = "mce"
    CITIZEN = "citizen"
    SYSTEM = "system"


@dataclass(frozen=True)
class CaseActor:
    id: str
    name: str
    role: ActorRole


def actor(principal: Principal) -> CaseActor:
    """A signed-in person as the trail records them: a snapshot of their name and role."""
    return CaseActor(id=principal.user_id, name=principal.name, role=ActorRole(principal.role.value))


CITIZEN = CaseActor(id="citizen", name="The citizen", role=ActorRole.CITIZEN)
SYSTEM = CaseActor(id="system", name="Nokware", role=ActorRole.SYSTEM)


@dataclass(frozen=True)
class CaseEntry:
    """One step to record. Never put a personal-safety report's description in a note."""

    action: CaseHistoryAction
    actor: CaseActor
    from_status: str | None = None
    to_status: str | None = None
    from_recipient: str | None = None
    to_recipient: str | None = None
    note: str | None = None
    channel: str | None = None


def record(case_id: str, entry: CaseEntry) -> None:
    get_databases().create_document(
        DATABASE_ID,
        COLLECTION_ID,
        ID.unique(),
        {
            "caseId": case_id,
            "action": entry.action.value,
            "byUser": entry.actor.id,
            "actorName": entry.actor.name,
            "actorRole": entry.actor.role.value,
            "fromStatus": entry.from_status,
            "toStatus": entry.to_status,
            "fromDept": entry.from_recipient,
            "toDept": entry.to_recipient,
            "note": entry.note[:NOTE_MAX] if entry.note else None,
            "channel": entry.channel,
            "timestamp": now_iso(),
        },
    )


def entries_for(case_id: str) -> list[dict[str, Any]]:
    """A case's trail, oldest first."""
    listing = get_databases().list_documents(
        DATABASE_ID,
        COLLECTION_ID,
        queries=[Query.equal("caseId", case_id), Query.order_asc("timestamp"), Query.limit(ENTRIES_PER_CASE_MAX)],
    )
    return [entry.data for entry in listing.documents]
