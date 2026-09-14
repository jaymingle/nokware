"""Callbacks from the messaging providers. Public routes: each is verified before it is trusted.

    GET /api/channels/sms/delivery    Arkesel's delivery report for one SMS (signed)
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.services import notifications
from app.services.arkesel_signatures import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify_webhook
from app.services.ledger_documents import utc_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("/sms/delivery")
def sms_delivery(request: Request) -> dict[str, bool]:
    """Record whether an SMS reached the phone. Unsigned, stale or forged reports are refused.

    A report is idempotent (it sets the row's delivery status), so a repeat of a
    valid one changes nothing and needs no duplicate check.
    """
    params = dict(request.query_params)
    signed = verify_webhook(
        params, request.headers.get(TIMESTAMP_HEADER, ""), request.headers.get(SIGNATURE_HEADER, ""),
        get_settings().arkesel_webhook_secret,
    )
    if not signed:
        raise HTTPException(status_code=401, detail="The report's signature is not valid.")
    message_id, status = params.get("sms_id") or params.get("id"), params.get("status")
    if not message_id or not status:
        logger.warning("Arkesel delivery report without an ID or status (fields: %s)", sorted(params))
        return {"recorded": False}
    return {"recorded": notifications.record_delivery(message_id, status, utc_now())}
