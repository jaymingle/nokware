"""Callbacks from the messaging providers. Public routes: each is verified before it is trusted.

    GET  /api/channels/sms/delivery    Arkesel's delivery report for one SMS (signed)
    POST /api/channels/ussd/{token}    one keypress in an Arkesel USSD session (secret in the URL)
"""

import hmac
import logging
from typing import Any

import redis
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.services import notifications, ussd
from app.services.arkesel_signatures import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify_webhook
from app.services.ledger_documents import utc_now
from app.services.redis_store import RedisUnavailable
from app.services.report_contacts import InvalidNumber, normalise_phone

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


class UssdRequest(BaseModel):
    """Arkesel's USSD callback, as its sample application reads it."""

    model_config = ConfigDict(extra="ignore")

    session_id: str = Field(alias="sessionID", min_length=1, max_length=128)
    user_id: str = Field("", alias="userID", max_length=128)
    new_session: bool = Field(False, alias="newSession")
    msisdn: str = Field(max_length=20)
    user_data: str = Field("", alias="userData", max_length=500)


def _ussd_reply(request: UssdRequest, tasks: BackgroundTasks) -> ussd.Reply:
    try:
        phone = normalise_phone(request.msisdn)
    except InvalidNumber:
        return ussd.end("Nokware's USSD service is for Ghanaian mobile numbers.")
    dial = ussd.Dial(request.session_id, phone, request.user_data, request.new_session)
    try:
        return ussd.respond(dial, tasks.add_task)
    except (RedisUnavailable, redis.RedisError):
        logger.exception("USSD session state is unavailable")
        return ussd.end("Nokware is busy. Please dial again in a minute.")
    except Exception:  # Arkesel must always get a screen, never an error page
        logger.exception("A USSD step failed")
        return ussd.end("Sorry, something went wrong. Please dial again.")


@router.post("/ussd/{token}")
def ussd_session(token: str, request: UssdRequest, tasks: BackgroundTasks) -> dict[str, Any]:
    """The next screen. Arkesel doesn't sign USSD callbacks yet, so the URL's secret is the only check:
    a wrong one looks like no route at all."""
    expected = get_settings().arkesel_ussd_token
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=404, detail="Not Found")
    reply = _ussd_reply(request, tasks)
    return {"sessionID": request.session_id, "userID": request.user_id, "msisdn": request.msisdn,
            "message": reply.message, "continueSession": reply.more}
