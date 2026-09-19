"""Filing a citizen report, from any channel.

Nothing is written until the description, photos and numbers are all valid. The citizen's "received" message is
sent afterwards, by the caller, so a slow provider never delays the receipt.
"""

import hashlib
import logging
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.services import case_history, report_store
from app.services.case_history import CITIZEN, SYSTEM, CaseEntry, CaseHistoryAction
from app.services.case_workflow import AssignmentStatus, CaseStatus
from app.services.citizen_reports import DESCRIPTION_MAX, IntakeChannel
from app.services.report_classifier import CLASSIFIER_MODEL, model_verdict
from app.services.report_contacts import (
    ContactChoice,
    normalise_phone,
    normalise_whatsapp,
    save_contact,
    update_contact,
)
from app.services.report_photos import clean_photos, store_photos
from app.services.report_rules import (
    Classification,
    ClassificationMethod,
    InvalidReport,
    check_places,
    classify,
    locate,
    new_public_id,
    new_reference,
)
from app.services.report_taxonomy import TOPICS_BY_ID, Category
from app.teams import RECIPIENT_NAMES

logger = logging.getLogger(__name__)

DESCRIPTION_MIN = 10
REFERENCE_ATTEMPTS = 5
# How long the confirmation page's link can still answer the callback question. An hour was too short to be an offer
# at all: the question is about a phone call from the Police or Social Welfare, which someone in danger weighs in
# their own time and rarely at the moment of filing, and a link that has quietly expired asks them nothing. A week
# is long enough to come back to and short enough that the token dies well inside the case's own life.
PREFERENCES_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class ReportSubmission:
    description: str
    ward: str | None
    sub_metro: str | None
    safety_topic: str | None  # the citizen's own personal-safety declaration, from the safety form
    phone: str | None
    whatsapp: str | None
    notify: bool  # on the safety form, the citizen's explicit opt-in to messages
    callback_consent: bool  # on the safety form only
    channel: IntakeChannel = IntakeChannel.WEB
    spoken: str | None = None  # the language of the WhatsApp voice note the description was transcribed from


@dataclass(frozen=True)
class Receipt:
    case: dict[str, Any]
    messages_on: bool  # the citizen will get the received / resolved / escalated messages
    held_for_consent: bool  # filed as personal safety by the classifier: a call waits for the citizen's say
    preferences_token: str | None  # lets the confirmation page ask, once, within PREFERENCES_WINDOW


def _description(raw: str) -> str:
    text = raw.strip()
    if len(text) < DESCRIPTION_MIN:
        raise InvalidReport("Describe the problem in a sentence or two.")
    if len(text) > DESCRIPTION_MAX:
        raise InvalidReport("Keep the description under 8,000 characters.")
    return text


def _contact(submission: ReportSubmission) -> ContactChoice | None:
    """Opt-ins are settled once the report's category is known."""
    phone = normalise_phone(submission.phone) if submission.phone else None
    whatsapp = normalise_whatsapp(submission.whatsapp) if submission.whatsapp else None
    if not (phone or whatsapp):
        return None
    return ContactChoice(phone, whatsapp, notify=submission.notify, callback_consent=submission.callback_consent)


def _consented(choice: ContactChoice, submission: ReportSubmission) -> ContactChoice:
    """Messages and calls as agreed. Safety form: only what was ticked. Every other form: messages yes, calls never.

    That holds when the classifier, not the resident, reads the report as personal safety. What the resident agreed
    to is what they were asked: they gave a number on a form that promised messages about their report, and that
    consent is not made void by a reading they never saw. What such a case is sent is the neutral message — the
    reference alone, no category, no service, not even the word "report" — which is exactly why it exists: it tells
    whoever is holding the phone nothing. Weighed against it, holding messages back meant a resident who gave a
    number and heard nothing at all, ever.

    A call is the opposite trade. Someone from the Police or Social Welfare ringing can be overheard, or answered by
    the person the report is about, and no wording of ours controls what is said. So the callback waits for the
    resident's own answer, on the confirmation page, and is never assumed.
    """
    if submission.safety_topic is not None:
        return choice
    return ContactChoice(choice.phone, choice.whatsapp, notify=True, callback_consent=False)


def classification_note(filed: Classification) -> str:
    """How the report was filed, for the audit trail. Never quotes the report."""
    topic = TOPICS_BY_ID[filed.topic].label
    if filed.method == ClassificationMethod.CITIZEN:
        return f"Filed by the citizen as personal safety: {topic}."
    if filed.method == ClassificationMethod.AI:
        detail = "" if filed.private else f", severity {filed.severity}"
        return f"Classified by {CLASSIFIER_MODEL}: {filed.category.value.replace('_', ' ')}, {topic}{detail}."
    if filed.method == ClassificationMethod.KEYWORD_SCREEN:
        return "Words suggesting danger to a person filed it as personal safety."
    return "The classifier was unavailable; sent to Central Administration to be routed."


def _case_fields(
    filed: Classification, submission: ReportSubmission, description: str, photo_ids: list[str], now: datetime
) -> dict[str, Any]:
    place = locate(filed.category, submission.ward, submission.sub_metro)
    return {
        "category": filed.category.value,
        "topic": filed.topic,
        "severity": filed.severity,
        "description": description,
        "photoIds": photo_ids,
        "wardLocation": place.ward,
        "subMetro": place.sub_metro,
        "recipients": list(filed.recipients),
        "status": CaseStatus.ASSIGNED.value,
        "isSensitive": filed.private,
        "classifiedBy": filed.method.value,
        "classificationNote": classification_note(filed),
        "declaredSafety": submission.safety_topic is not None,
        "channel": submission.channel.value,
        "createdAt": now.isoformat(),
    }


def _drawn_ids(fields: dict[str, Any]) -> dict[str, Any]:
    """Both random, so a collision redraws them together."""
    civic = fields["category"] == Category.CIVIC_SERVICE
    return {"reference": new_reference(), **({"publicId": new_public_id(), "voiceCount": 0} if civic else {})}


def _create(case_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    for _ in range(REFERENCE_ATTEMPTS):
        try:
            return report_store.create_report(case_id, {**fields, "caseId": case_id, **_drawn_ids(fields)})
        except report_store.DuplicateReference:
            continue
    raise RuntimeError("Could not draw an unused case reference")


def _assign(case: dict[str, Any], now: datetime) -> None:
    for recipient in case["recipients"]:
        report_store.create_assignment(
            {
                "caseId": case["$id"],
                "recipient": recipient,
                "status": AssignmentStatus.ASSIGNED.value,
                "category": case["category"],
                "severity": case["severity"],
                "active": True,
                "assignedAt": now.isoformat(),
            }
        )


def voice_note(language: str) -> str:
    """Says the description is Nokware's transcription, not the resident's own typing."""
    translated = "" if language.strip().lower() == "english" else f", translated from {language}"
    return (f"Reported by a resident in a WhatsApp voice note. The description is a machine transcription{translated}, "
            "which the resident confirmed before it was filed.")


def _record_filing(case: dict[str, Any], spoken: str | None) -> None:
    case_id = case["$id"]
    note = voice_note(spoken) if spoken else None
    names = " and ".join(RECIPIENT_NAMES[r] for r in case["recipients"])
    entries = [
        CaseEntry(CaseHistoryAction.SUBMITTED, CITIZEN, to_status=CaseStatus.SUBMITTED.value, note=note),
        CaseEntry(CaseHistoryAction.CLASSIFIED, SYSTEM, note=case["classificationNote"]),
        CaseEntry(CaseHistoryAction.ASSIGNED, SYSTEM, from_status=CaseStatus.SUBMITTED.value,
                  to_status=CaseStatus.ASSIGNED.value, to_recipient=",".join(case["recipients"]),
                  note=f"Routed to {names}."),
    ]
    for entry in entries:
        case_history.record(case_id, entry)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _save_contact(case_id: str, choice: ContactChoice, ask_again: bool, now: datetime) -> str | None:
    save_contact(case_id, choice)
    if not ask_again:
        return None
    token = secrets.token_urlsafe(32)
    expires = (now + PREFERENCES_WINDOW).isoformat()
    update_contact(case_id, {"preferencesTokenHash": token_hash(token), "preferencesExpiresAt": expires})
    return token


def read_report(description: str) -> Classification:
    """A channel asks this before filing, so a personal-safety report gets its emergency numbers at once and is
    never asked for its electoral area."""
    return classify(description, None, model_verdict(description))


def _read_description(description: str, submission: ReportSubmission, filed: Classification | None) -> Classification:
    if filed is not None:
        return filed
    verdict = None if submission.safety_topic is not None else model_verdict(description)
    return classify(description, submission.safety_topic, verdict)


def submit(submission: ReportSubmission, photos: list[bytes], now: datetime, filed: Classification | None = None) -> Receipt:
    """Raises InvalidReport, InvalidNumber or PhotoRejected before anything is stored.
    filed: what read_report() already gave, if a channel asked first."""
    description = _description(submission.description)
    choice = _contact(submission)
    check_places(submission.ward, submission.sub_metro)  # a place that isn't on the list costs no model call
    # The model reads the description while Pillow re-encodes the photos: about a second each, and nothing is
    # stored until both have come back, so a rejected photo still stops the filing before anything is written.
    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(_read_description, description, submission, filed)
        cleaning = pool.submit(clean_photos, photos)
        filed, cleaned = reading.result(), cleaning.result()
    locate(filed.category, submission.ward, submission.sub_metro)  # check the place before writing anything
    case_id = str(uuid.uuid4())
    fields = _case_fields(filed, submission, description, store_photos(case_id, cleaned), now)
    case = _create(case_id, fields)
    # Routing, the trail and the citizen's number are written one after another on purpose. Sent together they
    # shared the keep-alive pool, and a connection Appwrite had closed took one of them down — a create is never
    # retried, because a repeated POST is a second report. Half a second of waiting is the cheaper mistake.
    _assign(case, now)
    _record_filing(case, submission.spoken)
    if choice is None:
        return Receipt(case=case, messages_on=False, held_for_consent=False, preferences_token=None)
    agreed = _consented(choice, submission)
    ask_about_calls = filed.private and submission.safety_topic is None
    if ask_about_calls:
        # Once, at info: a decision made for the resident rather than by them belongs on the record, so the quiet
        # about the category is a choice someone can find and read back, not a message that went missing.
        logger.info("Case %s was read as personal safety by the classifier, not declared by the resident: messages "
                    "are on, because they gave a number on a form that promised them, and what such a case is ever "
                    "sent is the neutral message, which names only the reference; only a call from a service waits "
                    "for their answer", case_id)
    token = _save_contact(case_id, agreed, ask_about_calls, now)
    return Receipt(case=case, messages_on=agreed.notify, held_for_consent=ask_about_calls, preferences_token=token)
