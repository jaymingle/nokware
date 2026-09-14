"""Callbacks from the messaging providers. Public routes: each is verified before it is trusted.

    GET  /api/channels/sms/delivery       Arkesel's delivery report for one SMS (signed)
    POST /api/channels/ussd/{token}       one keypress in an Arkesel USSD session (secret in the URL)
    POST /api/channels/whatsapp           one incoming WhatsApp message, from Twilio (signed)
    POST /api/channels/whatsapp/status    Twilio's delivery status for a WhatsApp message (signed)
    GET  /api/channels/whatsapp/audio/{name}  a spoken reply for Twilio to fetch (a random link, for 10 minutes)
"""

import hmac
import logging
from typing import Any

import redis
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.services import notifications, ussd, whatsapp, whatsapp_conversation, whatsapp_voice
from app.services.arkesel_signatures import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify_webhook
from app.services.ledger_documents import utc_now
from app.services.redis_store import RedisUnavailable
from app.services.report_contacts import InvalidNumber, normalise_phone, normalise_whatsapp

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


EMPTY_TWIML = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>"


async def _signed_form(request: Request, path: str) -> dict[str, str]:
    """Twilio's form fields, once its signature over them and the public URL checks out."""
    form = {name: str(value) for name, value in (await request.form()).items()}
    if not whatsapp.signed_by_twilio(path, form, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(status_code=403, detail="The request's signature is not valid.")
    return form


def _inbound(form: dict[str, str]) -> whatsapp_conversation.Inbound | None:
    try:
        number = normalise_whatsapp(form.get("From", "").removeprefix("whatsapp:"))
    except InvalidNumber:
        return None
    media = None
    if form.get("NumMedia", "0") != "0" and form.get("MediaUrl0"):
        media = whatsapp_conversation.Media(form["MediaUrl0"], form.get("MediaContentType0", ""))
    latitude, longitude = _coordinate(form.get("Latitude")), _coordinate(form.get("Longitude"))
    place = form.get("Address") or form.get("Label") or None
    return whatsapp_conversation.Inbound(number, form.get("Body", ""), media, form.get("MessageSid", ""), latitude, longitude, place)


def _coordinate(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


@router.post("/whatsapp")
async def whatsapp_message(request: Request, tasks: BackgroundTasks) -> Response:
    """Twilio gets an empty answer at once; the reply (an answer can take 13 seconds) follows by the API."""
    inbound = _inbound(await _signed_form(request, whatsapp.WEBHOOK_PATH))
    if inbound is not None:
        tasks.add_task(whatsapp_conversation.handle, inbound)
    return Response(EMPTY_TWIML, media_type="text/xml")


@router.post("/whatsapp/status")
async def whatsapp_status(request: Request) -> dict[str, bool]:
    """A WhatsApp message's delivery; one refused because WhatsApp's window had closed goes by SMS instead."""
    form = await _signed_form(request, whatsapp.STATUS_PATH)
    message_sid, status = form.get("MessageSid", ""), form.get("MessageStatus", "")
    if not (message_sid and status):
        return {"recorded": False}
    await run_in_threadpool(whatsapp_voice.release, message_sid, status)
    recorded = await run_in_threadpool(notifications.record_delivery, message_sid, status, utc_now())
    if status in ("failed", "undelivered"):
        await run_in_threadpool(notifications.whatsapp_undelivered, message_sid, form.get("ErrorCode", ""))
    return {"recorded": recorded}


@router.api_route("/whatsapp/audio/{name}", methods=["GET", "HEAD"])
def whatsapp_audio(name: str) -> Response:
    """A spoken reply, fetched by Twilio as it sends the voice note. The link is random and lasts 10 minutes, and
    the audio is an answer from public documents, never anything about a report."""
    try:
        found = whatsapp_voice.held(name)
    except (redis.RedisError, RedisUnavailable):
        found = None
    if found is None:
        raise HTTPException(status_code=404, detail="Not found.")
    data, content_type = found
    return Response(data, media_type=content_type, headers={"Cache-Control": "no-store"})
