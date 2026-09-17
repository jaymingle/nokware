"""What became of each SMS sent through BMS, polled because BMS has no delivery webhook for SMS.

Each answer lands on the outbox row the way an Arkesel report would, so staff see the same statuses whichever
provider carried the message. Nothing comes in, so nothing inbound can be forged. Asking costs nothing.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from appwrite.query import Query

from app.services import notifications
from app.services.appwrite_client import DATABASE_ID, get_databases
from app.services.citizen_reports import NOTIFICATIONS_COLLECTION, NotificationStatus
from app.services.sms import SmsError
from app.services.sms_bms import bms

logger = logging.getLogger(__name__)

SETTLED = frozenset({"DELIVERED", "UNDELIVERED", "FAILED", "REJECTED", "EXPIRED"})  # BMS won't change these
FIRST_ASK = timedelta(minutes=1)  # a report seldom exists sooner
LAST_ASK = timedelta(days=2)  # after this, whatever BMS last said stands
BATCH = 100


def unsettled(now: datetime) -> list[dict[str, Any]]:
    rows = get_databases().list_documents(DATABASE_ID, NOTIFICATIONS_COLLECTION, queries=[
        Query.equal("status", NotificationStatus.SENT.value),
        Query.equal("provider", "bms"),
        Query.greater_than_equal("sentAt", (now - LAST_ASK).isoformat()),
        Query.less_than_equal("sentAt", (now - FIRST_ASK).isoformat()),
        Query.order_asc("sentAt"),
        Query.limit(BATCH),
    ]).documents
    return [{"$id": row.id, **row.data} for row in rows if row.data.get("deliveryStatus") not in SETTLED]


def poll(now: datetime) -> int:
    """Returns how many rows changed. A failed ask waits for the next run."""
    changed = 0
    for row in unsettled(now):
        campaign_id = row.get("providerMessageId")
        if not campaign_id:
            continue
        try:
            status = bms().delivery_status(campaign_id)
        except SmsError as error:
            logger.warning("BMS delivery check for outbox row %s failed: %s", row["$id"], error)
            continue
        if status and status != row.get("deliveryStatus") and notifications.record_delivery(campaign_id, status, now):
            changed += 1
    return changed
