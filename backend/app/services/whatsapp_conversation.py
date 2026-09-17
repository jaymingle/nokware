"""WhatsApp conversations: questions, reports and status lookups, over the same services as the web.

A report is filed only when the citizen replies 1, so a question the router misread is never filed. An emergency gets
every number to try in the first reply, before any other question. A personal-safety report is asked only for its
sub-metro, never its electoral area.

Photos are cleaned of metadata, kept only as long as the draft, and deleted from Twilio straight away. The chat reply
is the receipt, so no separate "received" message is sent.

A personal-safety report from a voice note is never shown back in its own words, so a mishearing is still caught
without leaving a readable copy of the disclosure in the chat.
"""

import base64
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import Any

from app.config import get_settings
from app.contacts import EMERGENCY_TOPICS
from app.services import (
    channel_limits,
    channel_sessions,
    phone_proof,
    report_followups,
    report_intake,
    report_store,
    whatsapp_reply,
    whatsapp_safety,
    whatsapp_voice,
)
from app.services.channel_answers import for_chat
from app.services.channel_contacts import medical_text, numbers_text, steps_text
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
from app.services.voice_transcribe import Heard, understood
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
    "• Send a case reference, like K7QM-4TXP, to see how it is going.\n"
    "Type, or send a voice note."
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
    heard: Heard | None = None  # a voice note's words (text is then their English, as if typed)


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
    spoken = state.get("spoken_language")
    if _private(state):
        who = " and ".join(short_name(r) for r in state["filed"]["recipients"])
        if spoken:
            # Never the words back: they'd leave a readable copy of the disclosure on a phone the abuser may pick up.
            return ("I understood this as a report about someone's safety. You can send photos first: "
                    f"only they will see them.\nReply *1* to send it to {who}, or *2* to cancel and type it instead.")
        return (f"Ready to send your report{with_photos} to {who}. You can send photos first: only they will see them.\n"
                "Reply *1* to send it or *2* to cancel.")
    heard = f"{understood(state['description'], spoken)}\n" if spoken else ""
    place = wards()[state["ward"]].name
    return f"{heard}Ready to file your report about {place}{with_photos}.\nReply *1* to file it or *2* to cancel. You can send photos first."


def _next(number: str, state: State) -> tuple[State, str]:
    if not state.get("description"):
        return {**state, "step": "describe"}, "Describe the problem and where it is, in a sentence or two."
    if _private(state) and "sub_metro" not in state:
        return {**state, "step": "sub_metro"}, _sub_metro_question()
    if not _private(state) and not state.get("ward"):
        return {**state, "step": "area"}, "Which electoral area is it in? Reply with its name, for example Kaneshie or Bubiashie."
    return {**state, "step": "confirm"}, _confirm_question(number, state)


def _prompt(number: str, state: State) -> None:
    state, question = _next(number, state)
    numbers = ""
    if state.get("filed") and not state.get("numbers_sent"):
        numbers, state = numbers_text(state["filed"]["topic"], state.get("sub_metro")), {**state, "numbers_sent": True}
        numbers = "\n\n".join(part for part in (numbers, steps_text() if _private(state) else "") if part)
    channel_sessions.save("whatsapp", number, state, DRAFT_SECONDS)
    get_redis().expire(_photos_key(number), DRAFT_SECONDS)
    whatsapp_reply.reply(number, "\n\n".join(part for part in (numbers, question) if part))


def _with_description(state: State, text: str, heard: Heard | None) -> State:
    filed = report_intake.read_report(text)
    ward = ward_mentioned(text)
    if filed.private:
        place = {"sub_metro": ward.sub_metro} if ward else {}
    else:
        place = {"ward": state.get("ward") or (ward.id if ward else None)}
    kept = {k: v for k, v in state.items() if k not in ("ward", "spoken_language")}
    spoken = {"spoken_language": heard.language} if heard else {}
    return {**kept, "description": text, "filed": _saved(filed), **place, **spoken}


def start_report(inbound: Inbound) -> None:
    if inbound.media:
        problem = _keep_photo(inbound.number, inbound.media)
        if problem:
            whatsapp_reply.reply(inbound.number, problem)
    text = inbound.text.strip()
    _prompt(inbound.number, _with_description({}, text, inbound.heard) if len(text) >= DESCRIPTION_MIN else {})


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
        spoken=state.get("spoken_language"),
    )
    try:
        receipt = report_intake.submit(submission, draft_photos(number), utc_now(), _classification(state))
    except (InvalidReport, InvalidNumber, PhotoRejected) as error:
        whatsapp_reply.reply(number, f"{error} Reply *2* to cancel.")
        return
    _drop_draft(number)
    if receipt.case["isSensitive"]:
        whatsapp_safety.after_filing(number, receipt)
    else:
        whatsapp_reply.reply(number, _receipt_text(receipt))


def answer(number: str, question: str, heard: Heard | None = None) -> None:
    if not channel_limits.QUESTIONS.allow(number, utc_now().timestamp()):
        whatsapp_reply.reply(number, "You've asked a lot of questions this hour. Please try again later.")
        return
    found = answer_question(question, AnswerLength.CHAT)
    shown = [understood(heard.english, heard.language)] if heard else []
    whatsapp_reply.reply(number, "\n\n".join([*shown, for_chat(found, _site())]))
    if heard:
        whatsapp_voice.speak_answer(number, found, heard)


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
    ids = list(sub_metros())
    if text.isdigit():
        return ids[int(text) - 1] if 1 <= int(text) <= len(ids) else None
    by_name = next((i for i, sub in sub_metros().items() if sub.name.lower() == text.lower()), None)
    ward = find_ward(text) or ward_mentioned(text)
    return by_name or (ward.sub_metro if ward else None)


def _place_reply(state: State, text: str) -> State | str:
    if state["step"] == "sub_metro":
        if text == "0":
            return {**state, "sub_metro": None}
        chosen = _sub_metro_named(text)
        return {**state, "sub_metro": chosen} if chosen else "Reply with a number from the list, or *0* to skip."
    ward = find_ward(text) or ward_mentioned(text)
    if ward:
        return {**state, "ward": ward.id}
    return "I couldn't match that to an AMA electoral area. Try its name again, or reply *0* to cancel."


def _draft_step(inbound: Inbound, state: State) -> bool:
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
        _prompt(number, _with_description(state, text, inbound.heard))
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
    """Anything but 1 or 2 is read as a new message."""
    choice = inbound.text.strip()
    channel_sessions.clear("whatsapp", inbound.number)
    if choice not in ("1", "2"):
        return False
    heard = Heard(**state["heard"]) if state.get("heard") else None
    if choice == "1":
        answer(inbound.number, state["text"], heard)
    else:
        start_report(replace(inbound, text=state["text"], media=None, heard=heard))
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
        answer(inbound.number, inbound.text.strip(), inbound.heard)
    elif reading.intent == Intent.REPORT:
        start_report(inbound)
    elif reading.intent == Intent.MEDICAL:
        whatsapp_reply.reply(inbound.number, medical_text())
    elif reading.intent == Intent.THANKS:
        return  # "thanks" or "ok" needs no reply, and every reply costs money
    elif reading.intent == Intent.UNCLEAR:
        kind = {"step": "kind", "text": inbound.text.strip(), **({"heard": asdict(inbound.heard)} if inbound.heard else {})}
        channel_sessions.save("whatsapp", inbound.number, kind, DRAFT_SECONDS)
        whatsapp_reply.reply(inbound.number, ASK_KIND)
    else:
        whatsapp_reply.reply(inbound.number, HELP)


def _media_problem(media: Media | None) -> str | None:
    if media is None or media.content_type in PHOTO_TYPES:
        return None
    return "Only photos and voice notes can be read. Please type your message."


def _heard(inbound: Inbound) -> Inbound | None:
    """None if a voice note couldn't be used."""
    if not (inbound.media and whatsapp_voice.is_voice(inbound.media.content_type)):
        return inbound
    heard = whatsapp_voice.hear(inbound.number, inbound.media.url, inbound.media.content_type)
    return replace(inbound, text=whatsapp_voice.as_typed(heard.english), media=None, heard=heard) if heard else None


def _confirm_code(number: str, code: str) -> None:
    if channel_limits.CODE_CLAIMS.allow(number, utc_now().timestamp()):
        claimed = phone_proof.claim(code, number, phone_proof.Channel.WHATSAPP, utc_now())
        whatsapp_reply.reply(number, phone_proof.CLAIM_REPLIES[claimed])


def _route(inbound: Inbound) -> None:
    problem = _media_problem(inbound.media)
    if problem:
        whatsapp_reply.reply(inbound.number, problem)
        return
    code = None if inbound.media else phone_proof.typed_code(inbound.text)
    if code:
        _confirm_code(inbound.number, code)
        return
    state = channel_sessions.load("whatsapp", inbound.number)
    step = STEPS.get(state.get("step", "")) if state else None
    if state and step is None:  # a session from an older version of this flow: start again
        channel_sessions.clear("whatsapp", inbound.number)
    if not (state and step and step(inbound, state)):
        _fresh(inbound)


def handle(inbound: Inbound) -> None:
    """Runs after the webhook has answered Twilio."""
    open_window(inbound.number)
    if not first_delivery(inbound.message_sid) or not channel_limits.MESSAGES.allow(inbound.number, utc_now().timestamp()):
        return
    try:
        as_typed = _heard(inbound)
        if as_typed is not None:
            _route(as_typed)
    except Exception:
        logger.exception("A WhatsApp message from %s couldn't be handled", masked(inbound.number))
        whatsapp_reply.reply(inbound.number, "Sorry, something went wrong. Please try again.")
