"""Filing a citizen report, from any channel: the web form now, USSD and WhatsApp later.

submit() checks everything first (description, photos, numbers) and writes only
once all of it is valid: photos are cleaned, the report is classified and
filed, one assignment is made per recipient, the numbers are stored apart, and
every step goes to the case's audit trail. The citizen's "received" message is
sent afterwards, by the caller, so a slow provider never delays the receipt.
"""

import hashlib
import secrets
import uuid
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
    classify,
    locate,
    new_public_id,
    new_reference,
)
from app.services.report_taxonomy import TOPICS_BY_ID, Category
from app.teams import RECIPIENT_NAMES

DESCRIPTION_MIN = 10
REFERENCE_ATTEMPTS = 5
PREFERENCES_WINDOW = timedelta(hours=1)


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


@dataclass(frozen=True)
class Receipt:
    case: dict[str, Any]
    messages_on: bool  # the citizen will get the received / resolved / escalated messages
    held_for_consent: bool  # filed as personal safety by the classifier: messages wait for the citizen's say
    preferences_token: str | None  # lets the confirmation page ask, once, within the hour


def _description(raw: str) -> str:
    text = raw.strip()
    if len(text) < DESCRIPTION_MIN:
        raise InvalidReport("Describe the problem in a sentence or two.")
    if len(text) > DESCRIPTION_MAX:
        raise InvalidReport("Keep the description under 8,000 characters.")
    return text


def _contact(submission: ReportSubmission) -> ContactChoice | None:
    """The numbers, validated. Opt-ins are settled once the report's category is known."""
    phone = normalise_phone(submission.phone) if submission.phone else None
    whatsapp = normalise_whatsapp(submission.whatsapp) if submission.whatsapp else None
    if not (phone or whatsapp):
        return None
    return ContactChoice(phone, whatsapp, notify=submission.notify, callback_consent=submission.callback_consent)


def _consented(choice: ContactChoice, submission: ReportSubmission, filed: Classification) -> ContactChoice:
    """Messages and calls as agreed. Safety form: only what was ticked. Normal form: messages yes, calls never.
    Filed as personal safety by the classifier: nothing until the citizen says (they never saw the safety wording)."""
    if submission.safety_topic is not None:
        return choice
    if filed.private:
        return ContactChoice(choice.phone, choice.whatsapp, notify=False, callback_consent=False)
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
    """A fresh reference, and for a civic report a public ID for the issue list (both random, so drawn together)."""
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


def _record_filing(case: dict[str, Any]) -> None:
    case_id = case["$id"]
    case_history.record(case_id, CaseEntry(CaseHistoryAction.SUBMITTED, CITIZEN, to_status=CaseStatus.SUBMITTED.value))
    case_history.record(case_id, CaseEntry(CaseHistoryAction.CLASSIFIED, SYSTEM, note=case["classificationNote"]))
    names = " and ".join(RECIPIENT_NAMES[r] for r in case["recipients"])
    entry = CaseEntry(
        CaseHistoryAction.ASSIGNED,
        SYSTEM,
        from_status=CaseStatus.SUBMITTED.value,
        to_status=CaseStatus.ASSIGNED.value,
        to_recipient=",".join(case["recipients"]),
        note=f"Routed to {names}.",
    )
    case_history.record(case_id, entry)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _save_contact(case_id: str, choice: ContactChoice, ask_again: bool, now: datetime) -> str | None:
    """Store the numbers; when the citizen must be asked again about messages, return a one-time token."""
    save_contact(case_id, choice)
    if not ask_again:
        return None
    token = secrets.token_urlsafe(32)
    expires = (now + PREFERENCES_WINDOW).isoformat()
    update_contact(case_id, {"preferencesTokenHash": token_hash(token), "preferencesExpiresAt": expires})
    return token


def read_report(description: str) -> Classification:
    """How a report will be filed, before it is: a channel asks this first, so a personal-safety report gets
    its emergency numbers at once and is never asked for its electoral area. Pass the result to submit()."""
    return classify(description, None, model_verdict(description))


def submit(submission: ReportSubmission, photos: list[bytes], now: datetime, filed: Classification | None = None) -> Receipt:
    """File a report. Raises InvalidReport, InvalidNumber or PhotoRejected before anything is stored.
    filed: the classification read_report() already gave for this description, if a channel asked first."""
    description = _description(submission.description)
    cleaned = clean_photos(photos)
    choice = _contact(submission)
    if filed is None:
        verdict = None if submission.safety_topic is not None else model_verdict(description)
        filed = classify(description, submission.safety_topic, verdict)
    locate(filed.category, submission.ward, submission.sub_metro)  # check the place before writing anything
    case_id = str(uuid.uuid4())
    fields = _case_fields(filed, submission, description, store_photos(case_id, cleaned), now)
    case = _create(case_id, fields)
    _assign(case, now)
    _record_filing(case)
    if choice is None:
        return Receipt(case=case, messages_on=False, held_for_consent=False, preferences_token=None)
    agreed = _consented(choice, submission, filed)
    held = filed.private and submission.safety_topic is None
    token = _save_contact(case_id, agreed, held, now)
    return Receipt(case=case, messages_on=agreed.notify, held_for_consent=held, preferences_token=token)
