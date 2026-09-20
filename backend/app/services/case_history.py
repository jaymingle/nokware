"""The case audit trail, written by the server only and never edited.

For a personal-safety case an entry never carries the report's description: the trail says what happened, not what
was reported.

An entry has two kinds of words. `note` is the server's own line about what happened ("Works Department started
work."). `staffNote` is what a member of staff wrote for the resident at that stage, kept apart from the server's
line so it can be shown, trimmed or withheld on its own: the resident's timeline shows it, the MCE's outline of a
personal-safety case does not, and neither has to pick a sentence apart to find it. It lives on the entry it belongs
to, so a note can never float free of its stage.
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
STAFF_NOTE_MAX = 500  # what staff may write at a stage; the same cap the routes accept
ENTRIES_PER_CASE_MAX = 100


class CaseHistoryAction(StrEnum):
    SUBMITTED = "submitted"
    CLASSIFIED = "classified"  # topic, severity and recipients, and how they were decided
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    REASSIGNED = "reassigned"
    REOPENED = "reopened"  # the MCE sent an escalated case back to its recipients
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
    staff_note: str | None = None  # what a member of staff wrote at this stage, for the resident to read
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
            "staffNote": entry.staff_note[:STAFF_NOTE_MAX] if entry.staff_note else None,
            "channel": entry.channel,
            "timestamp": now_iso(),
        },
    )


def entries_for(case_id: str) -> list[dict[str, Any]]:
    listing = get_databases().list_documents(
        DATABASE_ID,
        COLLECTION_ID,
        queries=[Query.equal("caseId", case_id), Query.order_asc("timestamp"), Query.limit(ENTRIES_PER_CASE_MAX)],
    )
    return [entry.data for entry in listing.documents]
