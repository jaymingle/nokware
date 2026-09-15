"""What became of each SMS sent through BMS: asked of BMS, since it sends no delivery reports of its own.

Arkesel calls the API back with a signed delivery report. BMS has no delivery
webhook for SMS at all, so a scheduled job (BMS_DELIVERY_POLL_SECONDS) asks it
instead, for every BMS message in the outbox sent between a minute and two days
ago whose delivery isn't settled yet. Each answer lands on the outbox row the
way a report would (notifications.record_delivery), so staff see "DELIVERED"
or "FAILED" whichever provider carried the message.

Nothing comes in, so nothing inbound can be forged: this replaces Arkesel's
verified webhook with outbound requests the API makes itself, a different
shape of risk rather than a worse one. Asking costs nothing.
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
    """BMS messages sent in the asking window whose delivery isn't settled, oldest first."""
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
    """Ask BMS about each unsettled message; return how many rows changed. A failed ask waits for the next run."""
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
