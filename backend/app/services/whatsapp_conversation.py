"""WhatsApp conversations: a question gets a cited answer, a report is drafted, confirmed and filed, a reference gets its status.

The same services as the web: report_intake.submit() and rag.answer_question().
A message is read by channel_intent. A report becomes a draft (in Redis, for 15
quiet minutes): it needs a description and an electoral area, may gather
photos, and is filed only when the citizen replies 1, so a question the router
misread is never filed. An unclear message gets "question or report?".

Photos are fetched from Twilio once, cleaned (no metadata), kept only as long
as the draft, and deleted from Twilio straight away. A personal-safety report
gets its reference and "In danger now? Call 112." and updates only if the
citizen replies YES within the hour; the chat never names what it is about.
The chat reply is the receipt, so no separate "received" message is sent.
"""

import base64
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from app.config import get_settings
from app.services import channel_limits, channel_sessions, report_followups, report_intake, report_store
from app.services.channel_answers import for_chat
from app.services.channel_intent import Intent, read_message
from app.services.channel_status import status_text
from app.services.citizen_reports import MAX_PHOTOS, IntakeChannel, NotificationChannel
from app.services.ledger_documents import utc_now
from app.services.notifications import provider_for
from app.services.rag import AnswerLength, answer_question
from app.services.redis_store import get_redis, key, subject_key
from app.services.report_contacts import InvalidNumber, masked
from app.services.report_intake import DESCRIPTION_MIN, Receipt, ReportSubmission
from app.services.report_photos import PhotoRejected, clean_photo
from app.services.report_rules import InvalidReport
from app.services.report_taxonomy import Category
from app.services.whatsapp import WhatsAppError, WhatsAppNotConfigured, first_delivery, open_window, split, twilio
from app.services.workflow import NotAllowed
from app.teams import short_name
from app.wards import find_ward, ward_mentioned, wards

logger = logging.getLogger(__name__)

DRAFT_SECONDS = 15 * 60
UPDATES_SECONDS = 60 * 60  # the one-time updates choice after a safety filing: an hour, as on the web
PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
EMERGENCY = "In danger now? Call 112."
HELP = (
    "*Nokware* is the Accra Metropolitan Assembly's public record. Here you can:\n"
    "• Ask a question about the Assembly: fees, budgets, plans, services.\n"
    "• Report a problem, like a blocked drain or a broken streetlight. Send a photo too if you have one.\n"
    "• Send a case reference, like K7QM-4TXP, to see how it is going."
)
ASK_KIND = "Is this a question for Nokware, or a problem to report to the Assembly?\nReply *1* for a question or *2* for a report."
CANCELLED = "Cancelled: nothing was filed. If you meant to ask a question, send it again."


@dataclass(frozen=True)
class Media:
    url: str
    content_type: str


@dataclass(frozen=True)
class Inbound:
    number: str  # +E.164
    text: str
    media: Media | None
    message_sid: str


State = dict[str, Any]


def reply(number: str, text: str) -> None:
    """Send a reply in the chat (the citizen just wrote, so the 24-hour window is open)."""
    provider = provider_for(NotificationChannel.WHATSAPP)
    if provider is None:
        logger.info("WhatsApp reply to %s not sent (no provider is configured): %s", masked(number), text)
        return
    try:
        for piece in split(text):  # WhatsApp takes 1,600 characters a message
            provider.send(number, piece)
    except WhatsAppError:
        logger.exception("WhatsApp reply to %s failed", masked(number))


def _site() -> str:
    return get_settings().public_site_url.rstrip("/")


def _photos_key(number: str) -> str:
    return key("wa-photos", subject_key(number))


def draft_photos(number: str) -> list[bytes]:
    return [base64.b64decode(item) for item in get_redis().lrange(_photos_key(number), 0, -1)]


def _drop_draft(number: str) -> None:
    channel_sessions.clear("whatsapp", number)
    get_redis().delete(_photos_key(number))


def _keep_photo(number: str, media: Media) -> str | None:
    """Fetch, clean and hold a photo for the draft, and delete it from Twilio. A reason if it can't be used."""
    held = get_redis().llen(_photos_key(number))
    if held >= MAX_PHOTOS:
        return f"A report can have up to {MAX_PHOTOS} photos."
    try:
        client = twilio()
        data, _ = client.download(media.url)
        client.delete_media(media.url)
        cleaned = clean_photo(data, held + 1)
    except PhotoRejected as rejected:
        return str(rejected)
    except (WhatsAppError, WhatsAppNotConfigured, OSError):
        logger.exception("A WhatsApp photo from %s couldn't be fetched", masked(number))
        return "That photo couldn't be received. Please send it again."
    pipe = get_redis().pipeline()
    pipe.rpush(_photos_key(number), base64.b64encode(cleaned.data).decode())
    pipe.expire(_photos_key(number), DRAFT_SECONDS)
    pipe.execute()
    return None


def _prompt(number: str, state: State) -> None:
    """Ask for what the draft still needs: a description, then the electoral area, then a yes."""
    if not state.get("description"):
        state, text = {**state, "step": "describe"}, "Describe the problem and where it is, in a sentence or two."
    elif not state.get("ward"):
        state, text = {**state, "step": "area"}, "Which electoral area is it in? Reply with its name, for example Kaneshie or Bubiashie."
    else:
        photos = get_redis().llen(_photos_key(number))
        with_photos = f" with {photos} photo{'s' if photos != 1 else ''}" if photos else ""
        place = wards()[state["ward"]].name
        state = {**state, "step": "confirm"}
        text = f"Ready to file your report about {place}{with_photos}.\nReply *1* to file it or *2* to cancel. You can send photos first."
    channel_sessions.save("whatsapp", number, state, DRAFT_SECONDS)
    get_redis().expire(_photos_key(number), DRAFT_SECONDS)
    reply(number, text)


def _with_description(state: State, text: str) -> State:
    ward = ward_mentioned(text)
    return {**state, "description": text, "ward": state.get("ward") or (ward.id if ward else None)}


def start_report(inbound: Inbound) -> None:
    if inbound.media:
        problem = _keep_photo(inbound.number, inbound.media)
        if problem:
            reply(inbound.number, problem)
    text = inbound.text.strip()
    _prompt(inbound.number, _with_description({}, text) if len(text) >= DESCRIPTION_MIN else {})


def _receipt_text(receipt: Receipt) -> str:
    case = receipt.case
    if case["isSensitive"]:
        wanted = "\nReply *YES* within the hour if you want updates here. They never say what the report is about." if receipt.preferences_token else ""
        return f"Your reference is *{case['reference']}*. {EMERGENCY}{wanted}"
    who = " and ".join(short_name(r) for r in case["recipients"])
    emergency = f"\n{EMERGENCY}" if case["category"] == Category.PUBLIC_SAFETY else ""
    return (f"Filed. Your reference is *{case['reference']}*.\nIt is with {who}. We'll message you here when it's resolved."
            f"{emergency}\nTrack it: {_site()}/report/status")


def _file(number: str, state: State) -> None:
    if not channel_limits.REPORTS.allow(number, utc_now().timestamp()):
        _drop_draft(number)
        reply(number, "You've filed several reports this hour. Please try again later.")
        return
    submission = ReportSubmission(
        description=state["description"], ward=state["ward"], sub_metro=None, safety_topic=None, phone=None,
        whatsapp=number, notify=True, callback_consent=False, channel=IntakeChannel.WHATSAPP,
    )
    try:
        receipt = report_intake.submit(submission, draft_photos(number), utc_now())
    except (InvalidReport, InvalidNumber, PhotoRejected) as error:
        reply(number, f"{error} Reply *2* to cancel.")
        return
    _drop_draft(number)
    if receipt.case["isSensitive"] and receipt.preferences_token:
        updates = {"step": "updates", "reference": receipt.case["reference"], "token": receipt.preferences_token}
        channel_sessions.save("whatsapp", number, updates, UPDATES_SECONDS)
    reply(number, _receipt_text(receipt))


def answer(number: str, question: str) -> None:
    if not channel_limits.QUESTIONS.allow(number, utc_now().timestamp()):
        reply(number, "You've asked a lot of questions this hour. Please try again later.")
        return
    reply(number, for_chat(answer_question(question, AnswerLength.CHAT), _site()))


def status(number: str, reference: str) -> None:
    if not channel_limits.LOOKUPS.allow(number, utc_now().timestamp()):
        reply(number, "Too many lookups this hour. Please try again later.")
        return
    try:
        case = report_followups.find(reference)
    except report_followups.CaseNotFound:
        reply(number, f"No case has the reference {reference}. Check it and send it again.")
        return
    found = report_followups.public_status(case, report_store.assignments_for(case["$id"]), utc_now())
    reply(number, status_text(found, _site()))


def _draft_step(inbound: Inbound, state: State) -> bool:
    """A message while a report is being drafted: a photo, the description, the area, or the yes."""
    number, text, step = inbound.number, inbound.text.strip(), state["step"]
    problem = _keep_photo(number, inbound.media) if inbound.media else None
    if problem:
        reply(number, problem)
    ward = (find_ward(text) or ward_mentioned(text)) if step == "area" and text else None
    if text.lower() == "cancel" or (step in ("area", "confirm") and text in ("0", "2")):
        _drop_draft(number)
        reply(number, CANCELLED)
    elif step == "confirm" and text == "1":
        _file(number, state)
    elif step == "describe" and len(text) >= DESCRIPTION_MIN:
        _prompt(number, _with_description(state, text))
    elif step == "area" and text and not ward:
        reply(number, "I couldn't match that to an AMA electoral area. Try its name again, or reply *0* to cancel.")
    else:
        _prompt(number, {**state, "ward": ward.id} if ward else state)
    return True


def _kind_step(inbound: Inbound, state: State) -> bool:
    """The answer to "question or report?"; anything else is a new message."""
    choice = inbound.text.strip()
    if choice not in ("1", "2"):
        channel_sessions.clear("whatsapp", inbound.number)
        return False
    channel_sessions.clear("whatsapp", inbound.number)
    if choice == "1":
        answer(inbound.number, state["text"])
    else:
        start_report(replace(inbound, text=state["text"], media=None))
    return True


def _updates_step(inbound: Inbound, state: State) -> bool:
    """YES turns on updates for a personal-safety report; anything else leaves them off."""
    channel_sessions.clear("whatsapp", inbound.number)
    wanted = inbound.text.strip().lower() in ("yes", "y")
    if not wanted and inbound.text.strip().lower() not in ("no", "n"):
        return False
    try:
        choice = report_followups.Preferences(notify=wanted, callback_consent=False)
        report_followups.set_preferences(state["reference"], state["token"], choice, utc_now())
    except NotAllowed:
        reply(inbound.number, "That choice can't be changed now.")
        return True
    reply(inbound.number, f"Updates are on for {state['reference']}." if wanted else "No updates will be sent.")
    return True


STEPS: dict[str, Callable[[Inbound, State], bool]] = {
    "describe": _draft_step, "area": _draft_step, "confirm": _draft_step, "kind": _kind_step, "updates": _updates_step,
}


def _fresh(inbound: Inbound) -> None:
    reading = read_message(inbound.text, has_photo=inbound.media is not None)
    if reading.intent == Intent.STATUS and reading.reference:
        status(inbound.number, reading.reference)
    elif reading.intent == Intent.QUESTION:
        answer(inbound.number, inbound.text.strip())
    elif reading.intent == Intent.REPORT:
        start_report(inbound)
    elif reading.intent == Intent.THANKS:
        return  # "thanks" or "ok" needs no reply, and every reply costs money
    elif reading.intent == Intent.UNCLEAR:
        channel_sessions.save("whatsapp", inbound.number, {"step": "kind", "text": inbound.text.strip()}, DRAFT_SECONDS)
        reply(inbound.number, ASK_KIND)
    else:
        reply(inbound.number, HELP)


def _media_problem(media: Media | None) -> str | None:
    if media is None or media.content_type in PHOTO_TYPES:
        return None
    if media.content_type.startswith("audio/"):
        return "Voice notes can't be read yet. Please type your message."
    return "Only photos can be added to a report."


def handle(inbound: Inbound) -> None:
    """One incoming WhatsApp message, after the webhook has answered Twilio."""
    open_window(inbound.number)
    if not first_delivery(inbound.message_sid) or not channel_limits.MESSAGES.allow(inbound.number, utc_now().timestamp()):
        return
    try:
        problem = _media_problem(inbound.media)
        if problem:
            reply(inbound.number, problem)
            return
        state = channel_sessions.load("whatsapp", inbound.number)
        if not (state and STEPS[state["step"]](inbound, state)):
            _fresh(inbound)
    except Exception:
        logger.exception("A WhatsApp message from %s couldn't be handled", masked(inbound.number))
        reply(inbound.number, "Sorry, something went wrong. Please try again.")
