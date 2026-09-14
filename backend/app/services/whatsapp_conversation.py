"""WhatsApp conversations: a question gets a cited answer, a report is drafted, confirmed and filed, a reference gets its status.

The same services as the web: report_intake.submit() and rag.answer_question().
A message is read by channel_intent. A report becomes a draft (in Redis, for 15
quiet minutes): it needs a description and an electoral area, may gather
photos, and is filed only when the citizen replies 1, so a question the router
misread is never filed. An unclear message gets "question or report?".

A report is read (report_intake.read_report) as soon as it is described. An
emergency (a danger to a person, a fire, a flood, a crime) gets every number
to try in that first reply, before any other question. A personal-safety
report is asked only for its sub-metro, which it may skip, never its
electoral area; an area it names is kept only as its sub-metro.

Photos are fetched from Twilio once, cleaned (no metadata), kept only as long
as the draft, and deleted from Twilio straight away. A personal-safety report
gets its reference and updates only if the citizen replies YES within the
hour. The chat reply is the receipt, so no separate "received" message is sent.
"""

import base64
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from app.config import get_settings
from app.services import channel_limits, channel_sessions, report_followups, report_intake, report_store
from app.contacts import EMERGENCY_TOPICS
from app.services.channel_answers import for_chat
from app.services.channel_contacts import medical_text, numbers_text
from app.services.channel_intent import Intent, read_message
from app.services.channel_status import status_text
from app.services.citizen_reports import MAX_PHOTOS, IntakeChannel
from app.services.ledger_documents import utc_now
from app.services.rag import AnswerLength, answer_question
from app.services.redis_store import get_redis, key, subject_key
from app.services.report_contacts import InvalidNumber, masked
from app.services.report_intake import DESCRIPTION_MIN, Receipt, ReportSubmission
from app.services.report_photos import PhotoRejected, clean_photo
from app.services.report_rules import Classification, ClassificationMethod, InvalidReport
from app.services.report_taxonomy import Category
from app.services import whatsapp_reply, whatsapp_safety
from app.services.whatsapp import WhatsAppError, WhatsAppNotConfigured, first_delivery, open_window, twilio
from app.teams import short_name
from app.wards import find_ward, sub_metros, ward_mentioned, wards

logger = logging.getLogger(__name__)

DRAFT_SECONDS = 15 * 60
PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
EMERGENCY_ABOVE = "If you need help now, the numbers above are there to try."
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
    latitude: float | None = None  # a location sent with WhatsApp's location button
    longitude: float | None = None
    place: str | None = None  # the place name or address WhatsApp sent with the pin


State = dict[str, Any]


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


def _saved(filed: Classification) -> dict[str, Any]:
    return {"category": filed.category.value, "topic": filed.topic, "severity": filed.severity,
            "recipients": list(filed.recipients), "method": filed.method.value}


def _classification(state: State) -> Classification:
    saved = state["filed"]
    return Classification(Category(saved["category"]), saved["topic"], saved["severity"], tuple(saved["recipients"]),
                          ClassificationMethod(saved["method"]))


def _private(state: State) -> bool:
    return bool(state.get("filed")) and state["filed"]["category"] == Category.PERSONAL_SAFETY


def _sub_metro_question() -> str:
    names = ", ".join(f"*{n}* {sub.name}" for n, sub in enumerate(sub_metros().values(), 1))
    return f"Which sub-metro are you in? It helps reach the nearest Social Welfare desk.\nReply {names}, or *0* to skip."


def _confirm_question(number: str, state: State) -> str:
    photos = get_redis().llen(_photos_key(number))
    with_photos = f" with {photos} photo{'s' if photos != 1 else ''}" if photos else ""
    if _private(state):
        who = " and ".join(short_name(r) for r in state["filed"]["recipients"])
        return (f"Ready to send your report{with_photos} to {who}. You can send photos first: only they will see them.\n"
                "Reply *1* to send it or *2* to cancel.")
    place = wards()[state["ward"]].name
    return f"Ready to file your report about {place}{with_photos}.\nReply *1* to file it or *2* to cancel. You can send photos first."


def _next(number: str, state: State) -> tuple[State, str]:
    """What the draft still needs: a description; then for personal safety the sub-metro (optional, never the
    electoral area), or for anything else the electoral area; then a yes."""
    if not state.get("description"):
        return {**state, "step": "describe"}, "Describe the problem and where it is, in a sentence or two."
    if _private(state) and "sub_metro" not in state:
        return {**state, "step": "sub_metro"}, _sub_metro_question()
    if not _private(state) and not state.get("ward"):
        return {**state, "step": "area"}, "Which electoral area is it in? Reply with its name, for example Kaneshie or Bubiashie."
    return {**state, "step": "confirm"}, _confirm_question(number, state)


def _prompt(number: str, state: State) -> None:
    """Ask the next question. An emergency's numbers come first, in the first reply after it is described."""
    state, question = _next(number, state)
    numbers = ""
    if state.get("filed") and not state.get("numbers_sent"):
        numbers, state = numbers_text(state["filed"]["topic"], state.get("sub_metro")), {**state, "numbers_sent": True}
    channel_sessions.save("whatsapp", number, state, DRAFT_SECONDS)
    get_redis().expire(_photos_key(number), DRAFT_SECONDS)
    whatsapp_reply.reply(number, "\n\n".join(part for part in (numbers, question) if part))


def _with_description(state: State, text: str) -> State:
    """The description, how it will be filed, and any place it names: for personal safety only the sub-metro."""
    filed = report_intake.read_report(text)
    ward = ward_mentioned(text)
    if filed.private:
        place = {"sub_metro": ward.sub_metro} if ward else {}
    else:
        place = {"ward": state.get("ward") or (ward.id if ward else None)}
    return {**{k: v for k, v in state.items() if k != "ward"}, "description": text, "filed": _saved(filed), **place}


def start_report(inbound: Inbound) -> None:
    if inbound.media:
        problem = _keep_photo(inbound.number, inbound.media)
        if problem:
            whatsapp_reply.reply(inbound.number, problem)
    text = inbound.text.strip()
    _prompt(inbound.number, _with_description({}, text) if len(text) >= DESCRIPTION_MIN else {})


def _receipt_text(receipt: Receipt) -> str:
    case = receipt.case
    who = " and ".join(short_name(r) for r in case["recipients"])
    emergency = f"\n{EMERGENCY_ABOVE}" if case["topic"] in EMERGENCY_TOPICS else ""
    return (f"Filed. Your reference is *{case['reference']}*.\nIt is with {who}. We'll message you here when it's resolved."
            f"{emergency}\nTrack it: {_site()}/report/status")


def _file(number: str, state: State) -> None:
    private = _private(state)
    # Someone in danger is never turned away by the hourly report limit (the message cap still holds).
    if not private and not channel_limits.REPORTS.allow(number, utc_now().timestamp()):
        _drop_draft(number)
        whatsapp_reply.reply(number, "You've filed several reports this hour. Please try again later.")
        return
    submission = ReportSubmission(
        description=state["description"], ward=None if private else state["ward"],
        sub_metro=state.get("sub_metro") if private else None, safety_topic=None, phone=None,
        whatsapp=number, notify=True, callback_consent=False, channel=IntakeChannel.WHATSAPP,
    )
    try:
        receipt = report_intake.submit(submission, draft_photos(number), utc_now(), _classification(state))
    except (InvalidReport, InvalidNumber, PhotoRejected) as error:
        whatsapp_reply.reply(number, f"{error} Reply *2* to cancel.")
        return
    _drop_draft(number)
    if receipt.case["isSensitive"]:
        whatsapp_safety.after_filing(number, receipt)  # who has it, and CALL, PLACE and YES for an hour
    else:
        whatsapp_reply.reply(number, _receipt_text(receipt))


def answer(number: str, question: str) -> None:
    if not channel_limits.QUESTIONS.allow(number, utc_now().timestamp()):
        whatsapp_reply.reply(number, "You've asked a lot of questions this hour. Please try again later.")
        return
    whatsapp_reply.reply(number, for_chat(answer_question(question, AnswerLength.CHAT), _site()))


def status(number: str, reference: str) -> None:
    if not channel_limits.LOOKUPS.allow(number, utc_now().timestamp()):
        whatsapp_reply.reply(number, "Too many lookups this hour. Please try again later.")
        return
    try:
        case = report_followups.find(reference)
    except report_followups.CaseNotFound:
        whatsapp_reply.reply(number, f"No case has the reference {reference}. Check it and send it again.")
        return
    found = report_followups.public_status(case, report_store.assignments_for(case["$id"]), utc_now())
    whatsapp_reply.reply(number, status_text(found, _site()))


def _sub_metro_named(text: str) -> str | None:
    """A sub-metro by its number in the list or its name; an electoral area named gives only its sub-metro."""
    ids = list(sub_metros())
    if text.isdigit():
        return ids[int(text) - 1] if 1 <= int(text) <= len(ids) else None
    by_name = next((i for i, sub in sub_metros().items() if sub.name.lower() == text.lower()), None)
    ward = find_ward(text) or ward_mentioned(text)
    return by_name or (ward.sub_metro if ward else None)


def _place_reply(state: State, text: str) -> State | str:
    """The answer to the place question: the state with it, or what to say if it can't be used."""
    if state["step"] == "sub_metro":
        if text == "0":
            return {**state, "sub_metro": None}  # skipped: nothing is kept
        chosen = _sub_metro_named(text)
        return {**state, "sub_metro": chosen} if chosen else "Reply with a number from the list, or *0* to skip."
    ward = find_ward(text) or ward_mentioned(text)
    if ward:
        return {**state, "ward": ward.id}
    return "I couldn't match that to an AMA electoral area. Try its name again, or reply *0* to cancel."


def _draft_step(inbound: Inbound, state: State) -> bool:
    """A message while a report is being drafted: a photo, the description, the place, or the yes."""
    number, text, step = inbound.number, inbound.text.strip(), state["step"]
    problem = _keep_photo(number, inbound.media) if inbound.media else None
    if problem:
        whatsapp_reply.reply(number, problem)
    if text.lower() == "cancel" or (step in ("area", "confirm") and text in ("0", "2")):
        _drop_draft(number)
        whatsapp_reply.reply(number, CANCELLED)
    elif step == "confirm" and text == "1":
        _file(number, state)
    elif step == "describe" and len(text) >= DESCRIPTION_MIN:
        _prompt(number, _with_description(state, text))
    elif step in ("area", "sub_metro") and text:
        placed = _place_reply(state, text)
        if isinstance(placed, str):
            whatsapp_reply.reply(number, placed)
        else:
            _prompt(number, placed)
    else:
        _prompt(number, state)
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


STEPS: dict[str, Callable[[Inbound, State], bool]] = {
    "describe": _draft_step, "area": _draft_step, "sub_metro": _draft_step, "confirm": _draft_step,
    "kind": _kind_step, "after": whatsapp_safety.after_step, "place": whatsapp_safety.place_step,
}


def _fresh(inbound: Inbound) -> None:
    reading = read_message(inbound.text, has_photo=inbound.media is not None)
    if reading.intent == Intent.STATUS and reading.reference:
        status(inbound.number, reading.reference)
    elif reading.intent == Intent.QUESTION:
        answer(inbound.number, inbound.text.strip())
    elif reading.intent == Intent.REPORT:
        start_report(inbound)
    elif reading.intent == Intent.MEDICAL:
        whatsapp_reply.reply(inbound.number, medical_text())
    elif reading.intent == Intent.THANKS:
        return  # "thanks" or "ok" needs no reply, and every reply costs money
    elif reading.intent == Intent.UNCLEAR:
        channel_sessions.save("whatsapp", inbound.number, {"step": "kind", "text": inbound.text.strip()}, DRAFT_SECONDS)
        whatsapp_reply.reply(inbound.number, ASK_KIND)
    else:
        whatsapp_reply.reply(inbound.number, HELP)


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
            whatsapp_reply.reply(inbound.number, problem)
            return
        state = channel_sessions.load("whatsapp", inbound.number)
        step = STEPS.get(state.get("step", "")) if state else None
        if state and step is None:  # a session from an older version of this flow: start again
            channel_sessions.clear("whatsapp", inbound.number)
        if not (state and step and step(inbound, state)):
            _fresh(inbound)
    except Exception:
        logger.exception("A WhatsApp message from %s couldn't be handled", masked(inbound.number))
        whatsapp_reply.reply(inbound.number, "Sorry, something went wrong. Please try again.")
