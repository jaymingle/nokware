"""Where citizen reports are stored: collection IDs and stored values.

citizen_reports holds the case itself; case_assignments one row per recipient;
report_contacts the citizen's numbers, apart from everything else and never
returned by a queue or case route; notifications the outbox of messages sent;
case_voices the residents who said an open civic issue affects them too.
"""

from enum import StrEnum

REPORTS_COLLECTION = "citizen_reports"
ASSIGNMENTS_COLLECTION = "case_assignments"
CONTACTS_COLLECTION = "report_contacts"
NOTIFICATIONS_COLLECTION = "notifications"
VOICES_COLLECTION = "case_voices"
PHOTOS_BUCKET = "nokware-report-photos"

DESCRIPTION_MAX = 8192
MAX_PHOTOS = 10
# What a resident may attach when escalating a resolved case: fewer than when filing, because an escalation is
# "here is what is still wrong", not the whole report again.
MAX_ESCALATION_PHOTOS = 5
VOICE_NAME_MAX = 80


class IntakeChannel(StrEnum):
    WEB = "web"
    USSD = "ussd"
    WHATSAPP = "whatsapp"


class NotificationEvent(StrEnum):
    SUBMITTED = "submitted"
    STARTED = "started"  # the first recipient started work; the others starting is not news to the citizen
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    REASSIGNED = "reassigned"  # the case moved to another office; never sent about a personal-safety case
    REOPENED = "reopened"  # the MCE sent it back to be finished


class NotificationChannel(StrEnum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


class NotificationStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    NOT_SENT = "not_sent"  # recorded only: no provider is configured for the channel yet
