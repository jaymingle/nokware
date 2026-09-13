"""Where citizen reports are stored: collection IDs and stored values.

citizen_reports holds the case itself; case_assignments one row per recipient;
report_contacts the citizen's numbers, apart from everything else and never
returned by a queue or case route; notifications the outbox of messages sent.
"""

from enum import StrEnum

REPORTS_COLLECTION = "citizen_reports"
ASSIGNMENTS_COLLECTION = "case_assignments"
CONTACTS_COLLECTION = "report_contacts"
NOTIFICATIONS_COLLECTION = "notifications"
PHOTOS_BUCKET = "nokware-report-photos"

DESCRIPTION_MAX = 8192
MAX_PHOTOS = 10


class IntakeChannel(StrEnum):
    WEB = "web"
    USSD = "ussd"
    WHATSAPP = "whatsapp"


class NotificationEvent(StrEnum):
    SUBMITTED = "submitted"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class NotificationChannel(StrEnum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


class NotificationStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
