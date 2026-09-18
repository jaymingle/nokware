"""Create the Appwrite structure for Citizen Reports.

- Teams for the agencies that receive safety reports: Police and GNFS.
- citizen_reports and case_history, created empty in Stage A, extended in
  place: new attributes are added and two existing ones adjusted (status gains
  "escalated"; assignedDepartment becomes optional, since recipients now live in
  case_assignments). Nothing is deleted.
- New collections: case_assignments, report_contacts (numbers encrypted at
  rest) and notifications (the outbox).

Idempotent: what already exists is left alone, so it is safe to re-run. No
collection has client permissions; only the server reads and writes them.

    backend/.venv/bin/python backend/scripts/create_citizen_reports.py
"""

import sys
import time
from collections.abc import Callable

from appwrite.enums.databases_index_type import DatabasesIndexType
from appwrite.exception import AppwriteException
from appwrite.query import Query

from app.services.appwrite_client import DATABASE_ID, get_databases, get_teams, quiet_sdk_deprecation_warnings
from app.services.case_history import COLLECTION_ID as HISTORY
from app.services.case_history import NOTE_MAX, ActorRole, CaseHistoryAction
from app.services.case_workflow import AssignmentStatus, CaseStatus
from app.services.citizen_reports import (
    ASSIGNMENTS_COLLECTION as ASSIGNMENTS,
)
from app.services.citizen_reports import (
    CONTACTS_COLLECTION as CONTACTS,
)
from app.services.citizen_reports import (
    NOTIFICATIONS_COLLECTION as NOTIFICATIONS,
)
from app.services.citizen_reports import (
    REPORTS_COLLECTION as REPORTS,
)
from app.services.citizen_reports import (
    IntakeChannel,
    NotificationChannel,
    NotificationEvent,
    NotificationStatus,
)
from app.services.report_rules import ClassificationMethod
from app.services.report_taxonomy import Category
from app.teams import AGENCY_TEAMS

ATTRIBUTE_WAIT_SECONDS = 300  # a collection of ~30 attributes can take minutes on this server
# Appwrite lists 25 attributes or indexes unless asked for more: a collection with more than 25 would
# otherwise look as if its later ones never became available.
LISTING = [Query.limit(500)]
ID = 36  # a UUID
TEAM = 64
HASH = 64  # a sha256 hex digest
ENCRYPTED_MIN = 150  # Appwrite's minimum size for an encrypted string; a phone number needs far less
Creator = Callable[[], object]


def values(enum: type) -> list[str]:
    return [member.value for member in enum]


def ensure(label: str, create: Creator) -> None:
    try:
        create()
        print(f"created   {label}")
    except AppwriteException as exc:
        if exc.code != 409:
            raise
        print(f"exists    {label}")


def report_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, REPORTS)
    return {
        "reference": lambda: db.create_string_attribute(*c, "reference", 16, True),
        "topic": lambda: db.create_string_attribute(*c, "topic", 64, True),
        "subMetro": lambda: db.create_string_attribute(*c, "subMetro", 64, False),
        "recipients": lambda: db.create_string_attribute(*c, "recipients", TEAM, True, array=True),
        "classifiedBy": lambda: db.create_enum_attribute(*c, "classifiedBy", values(ClassificationMethod), True),
        "classificationNote": lambda: db.create_string_attribute(*c, "classificationNote", 512, False),
        "declaredSafety": lambda: db.create_boolean_attribute(*c, "declaredSafety", False, default=False),
        "channel": lambda: db.create_enum_attribute(*c, "channel", values(IntakeChannel), True),
        "resolvedAt": lambda: db.create_datetime_attribute(*c, "resolvedAt", False),
        "escalatedAt": lambda: db.create_datetime_attribute(*c, "escalatedAt", False),
        "escalationNote": lambda: db.create_string_attribute(*c, "escalationNote", NOTE_MAX, False),
    }


def adjust_reports() -> None:
    db, c = get_databases(), (DATABASE_ID, REPORTS)
    db.update_enum_attribute(*c, "status", values(CaseStatus), False, None)
    db.update_string_attribute(*c, "assignedDepartment", False, None)
    print("updated   citizen_reports.status (adds escalated), assignedDepartment (now optional, unused)")


def history_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, HISTORY)
    return {
        "actorName": lambda: db.create_string_attribute(*c, "actorName", 256, True),
        "actorRole": lambda: db.create_enum_attribute(*c, "actorRole", values(ActorRole), True),
        "fromStatus": lambda: db.create_enum_attribute(*c, "fromStatus", values(CaseStatus), False),
        "toStatus": lambda: db.create_enum_attribute(*c, "toStatus", values(CaseStatus), False),
        "note": lambda: db.create_string_attribute(*c, "note", NOTE_MAX, False),
        "channel": lambda: db.create_enum_attribute(*c, "channel", values(NotificationChannel), False),
    }


def adjust_history() -> None:
    get_databases().update_enum_attribute(DATABASE_ID, HISTORY, "action", values(CaseHistoryAction), True, None)
    print("updated   case_history.action (the full set of case steps)")


def adjust_notifications() -> None:
    """The outbox's enums, re-derived from the Python ones: status gained "not_sent" (recorded while no provider is
    wired in) and event gained "started" (a recipient began work). Re-running writes the same set again."""
    db = get_databases()
    existing = {a.key for a in db.list_attributes(DATABASE_ID, NOTIFICATIONS, queries=LISTING).attributes}
    if "status" in existing:
        db.update_enum_attribute(DATABASE_ID, NOTIFICATIONS, "status", values(NotificationStatus), True, None)
        print("updated   notifications.status (the full set of outcomes)")
    if "event" in existing:
        db.update_enum_attribute(DATABASE_ID, NOTIFICATIONS, "event", values(NotificationEvent), True, None)
        print("updated   notifications.event (the full set of moments a citizen hears about)")


def assignment_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, ASSIGNMENTS)
    return {
        "caseId": lambda: db.create_string_attribute(*c, "caseId", ID, True),
        "recipient": lambda: db.create_string_attribute(*c, "recipient", TEAM, True),
        "status": lambda: db.create_enum_attribute(*c, "status", values(AssignmentStatus), True),
        "category": lambda: db.create_enum_attribute(*c, "category", values(Category), True),
        "severity": lambda: db.create_integer_attribute(*c, "severity", True, min=1, max=5),
        "active": lambda: db.create_boolean_attribute(*c, "active", False, default=True),
        "assignedAt": lambda: db.create_datetime_attribute(*c, "assignedAt", True),
        "acknowledgedAt": lambda: db.create_datetime_attribute(*c, "acknowledgedAt", False),
        "resolvedAt": lambda: db.create_datetime_attribute(*c, "resolvedAt", False),
        "resolutionNote": lambda: db.create_string_attribute(*c, "resolutionNote", NOTE_MAX, False),
    }


def contact_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, CONTACTS)
    return {
        "caseId": lambda: db.create_string_attribute(*c, "caseId", ID, True),
        "phone": lambda: db.create_string_attribute(*c, "phone", ENCRYPTED_MIN, False, encrypt=True),
        "whatsapp": lambda: db.create_string_attribute(*c, "whatsapp", ENCRYPTED_MIN, False, encrypt=True),
        "notify": lambda: db.create_boolean_attribute(*c, "notify", False, default=False),
        "callbackConsent": lambda: db.create_boolean_attribute(*c, "callbackConsent", False, default=False),
        "purgeAt": lambda: db.create_datetime_attribute(*c, "purgeAt", False),
        # A one-time token (stored hashed) that lets the confirmation page ask
        # again about messages when the classifier filed a report as personal safety.
        "preferencesTokenHash": lambda: db.create_string_attribute(*c, "preferencesTokenHash", HASH, False),
        "preferencesExpiresAt": lambda: db.create_datetime_attribute(*c, "preferencesExpiresAt", False),
    }


def notification_attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, NOTIFICATIONS)
    return {
        "caseId": lambda: db.create_string_attribute(*c, "caseId", ID, True),
        "event": lambda: db.create_enum_attribute(*c, "event", values(NotificationEvent), True),
        "channel": lambda: db.create_enum_attribute(*c, "channel", values(NotificationChannel), True),
        "template": lambda: db.create_string_attribute(*c, "template", 64, True),
        "body": lambda: db.create_string_attribute(*c, "body", 1024, True),
        "status": lambda: db.create_enum_attribute(*c, "status", values(NotificationStatus), True),
        "provider": lambda: db.create_string_attribute(*c, "provider", 64, False),
        "providerMessageId": lambda: db.create_string_attribute(*c, "providerMessageId", 128, False),
        "error": lambda: db.create_string_attribute(*c, "error", 512, False),
        "createdAt": lambda: db.create_datetime_attribute(*c, "createdAt", True),
        "sentAt": lambda: db.create_datetime_attribute(*c, "sentAt", False),
    }


KEY, UNIQUE = DatabasesIndexType.KEY, DatabasesIndexType.UNIQUE
INDEXES: dict[str, dict[str, tuple[DatabasesIndexType, list[str]]]] = {
    REPORTS: {
        "uniq_reference": (UNIQUE, ["reference"]),
        "idx_category_created": (KEY, ["category", "createdAt"]),
        "idx_subMetro": (KEY, ["subMetro"]),
        # The missed-message sweep looks for cases by when each moment happened: filed, resolved, escalated.
        # idx_category_created can't serve those — its first column is the category, not the date.
        "idx_createdAt": (KEY, ["createdAt"]),
        "idx_resolvedAt": (KEY, ["resolvedAt"]),
        "idx_escalatedAt": (KEY, ["escalatedAt"]),
    },
    HISTORY: {"idx_case_timestamp": (KEY, ["caseId", "timestamp"])},
    ASSIGNMENTS: {
        "idx_recipient_active_status": (KEY, ["recipient", "active", "status"]),
        "idx_caseId": (KEY, ["caseId"]),
        # The missed-message sweep looks for work started lately, and only the assignment records when that was.
        "idx_acknowledgedAt": (KEY, ["acknowledgedAt"]),
    },
    CONTACTS: {"uniq_caseId": (UNIQUE, ["caseId"]), "idx_purgeAt": (KEY, ["purgeAt"])},
    NOTIFICATIONS: {"idx_caseId": (KEY, ["caseId"]), "idx_status": (KEY, ["status"])},
}
NEW_COLLECTIONS = {ASSIGNMENTS: "Case assignments", CONTACTS: "Report contacts", NOTIFICATIONS: "Notifications"}


def wait_for_attributes(collection: str, keys: list[str]) -> None:
    """Indexes can only be built once their attributes are available."""
    deadline = time.monotonic() + ATTRIBUTE_WAIT_SECONDS
    waiting = keys
    while time.monotonic() < deadline:
        listing = get_databases().list_attributes(DATABASE_ID, collection, queries=LISTING)
        statuses = {a.key: str(getattr(a.status, "value", a.status)) for a in listing.attributes}
        waiting = [f"{key} ({statuses.get(key, 'missing')})" for key in keys if statuses.get(key) != "available"]
        if not waiting:
            return
        time.sleep(2)
    raise TimeoutError(f"{collection}: not available after {ATTRIBUTE_WAIT_SECONDS}s: {', '.join(waiting)}")


def ensure_indexes(collection: str, indexes: dict[str, tuple[DatabasesIndexType, list[str]]] | None = None) -> None:
    # Appwrite reports a duplicate index as a 400, not a 409, so check first.
    db = get_databases()
    existing = {index.key for index in db.list_indexes(DATABASE_ID, collection, queries=LISTING).indexes}
    for key, (kind, attributes) in (indexes or INDEXES[collection]).items():
        if key in existing:
            print(f"exists    index {collection}.{key}")
            continue
        db.create_index(DATABASE_ID, collection, key, kind, attributes)
        print(f"created   index {collection}.{key}")


def build(collection: str, creators: dict[str, Creator]) -> None:
    for key, create in creators.items():
        ensure(f"attribute {collection}.{key}", create)
    wait_for_attributes(collection, list(creators))
    ensure_indexes(collection)


def main() -> int:
    quiet_sdk_deprecation_warnings()
    for team in AGENCY_TEAMS:
        ensure(f"team {team}", lambda team=team: get_teams().create(team, team))
    db = get_databases()
    for collection, name in NEW_COLLECTIONS.items():
        ensure(f"collection {collection}", lambda c=collection, n=name: db.create_collection(DATABASE_ID, c, n))
    adjust_reports()
    adjust_history()
    build(REPORTS, report_attributes())
    build(HISTORY, history_attributes())
    build(ASSIGNMENTS, assignment_attributes())
    build(CONTACTS, contact_attributes())
    build(NOTIFICATIONS, notification_attributes())
    adjust_notifications()
    return 0


if __name__ == "__main__":
    sys.exit(main())
