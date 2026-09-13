"""The case audit trail: one case_history entry per step in a citizen report's life.

Written by the server only and never edited. Each entry records who acted (a
snapshot of their name and role), the status before and after, the recipients
involved and any note. For a personal-safety case an entry never carries the
report's description: the trail says what happened, not what was reported.
"""

from enum import StrEnum

COLLECTION_ID = "case_history"
NOTE_MAX = 2048


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


class ActorRole(StrEnum):
    DEPARTMENT = "department"
    AGENCY = "agency"
    MCE = "mce"
    CITIZEN = "citizen"
    SYSTEM = "system"
