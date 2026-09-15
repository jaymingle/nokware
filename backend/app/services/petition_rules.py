"""The petition rules: what a petition must hold, what the MCE may decide, and when each clock runs out.

Pure functions over a petition record, with no Appwrite calls, so every rule is
unit-tested and the routes cannot drift from each other.

Lifecycle:
  a resident with a verified phone submits a petition -> in_review; the MCE has 72 hours
    the MCE publishes it -> open
    the MCE refuses it, for one of the fixed reasons only -> refused
      the creator edits and resubmits it (at most twice) -> in_review, with a fresh 72 hours
    the MCE decides nothing in 72 hours -> open: it publishes automatically
  it reaches its threshold of signatures -> awaiting_response; the MCE has 30 days to respond publicly
    (it keeps taking signatures until its 90 days are up, or the MCE responds)
    the MCE responds: will act, referred to a department, or can't act and why -> responded
    30 days pass with no response -> still awaiting_response, and the page says so plainly; a late response is
    still taken, and says how late it was
  open for 90 days without reaching it -> closed
  the creator may withdraw it until it reaches its threshold or closes -> withdrawn

One signature per confirmed Ghanaian number per petition. A signer is
anonymous unless they choose to show their name, which is then public.

The MCE is usually the petition's target, so moderation can't be a veto: a
refusal must name a reason from REFUSALS, the public list counts refusals by
reason, and silence publishes.
"""

import math
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from app.services.ledger_documents import parse_datetime
from app.services.report_taxonomy import TOPICS, TOPICS_BY_ID, Category, Topic
from app.teams import DEPARTMENT_TEAMS
from app.wards import wards

REVIEW_WINDOW = timedelta(hours=72)  # the MCE's time to publish or refuse; then it publishes automatically
OPEN_FOR = timedelta(days=90)
RESPONSE_WINDOW = timedelta(days=30)  # the MCE's time to answer publicly once a petition reaches its threshold
MAX_RESUBMISSIONS = 2
TITLE_MIN, TITLE_MAX = 15, 150
BODY_MIN, BODY_MAX = 50, 4000
NAME_MAX = 80
NOTE_MAX = 1000
DOCUMENTS_MAX = 3
CODE_DIGITS = 6  # digits only, so a petition can be typed on a USSD keypad or read aloud


class PetitionStatus(StrEnum):
    IN_REVIEW = "in_review"
    REFUSED = "refused"
    OPEN = "open"
    AWAITING_RESPONSE = "awaiting_response"  # reached its threshold: the MCE must respond publicly
    RESPONDED = "responded"
    CLOSED = "closed"
    WITHDRAWN = "withdrawn"


class Scope(StrEnum):
    METRO = "metro"  # the whole Assembly
    AREA = "area"  # one electoral area


class PublishedBy(StrEnum):
    MCE = "mce"
    AUTOMATIC = "automatic"  # the MCE didn't decide within 72 hours


class PetitionAction(StrEnum):
    SUBMITTED = "submitted"
    RESUBMITTED = "resubmitted"
    PUBLISHED = "published"
    AUTO_PUBLISHED = "auto_published"
    REFUSED = "refused"
    WITHDRAWN = "withdrawn"
    CLOSED = "closed"
    MADE_ANONYMOUS = "made_anonymous"
    THRESHOLD_REACHED = "threshold_reached"
    RESPONDED = "responded"
    NO_RESPONSE = "no_response"  # 30 days after the threshold, with no response
    CREATOR_NOTIFIED = "creator_notified"  # a message to the creator: never public


@dataclass(frozen=True)
class Refusal:
    label: str  # as the public list counts it
    explanation: str  # as the creator reads it


REFUSALS: dict[str, Refusal] = {
    "private_individual": Refusal(
        "Names a private individual",
        "It names or targets a private person. A petition can ask the Assembly to act, or name a public official in their "
        "public role, but not a private individual."),
    "personal_safety": Refusal(
        "About someone's personal safety",
        "It is about someone's personal safety. That goes to the Assembly privately, through Report, not in public."),
    "duplicate": Refusal(
        "Duplicates an open petition",
        "An open petition already asks for this. Add your support to that one instead."),
    "not_assembly": Refusal(
        "Not the Assembly's responsibility",
        "What it asks for isn't something the Accra Metropolitan Assembly is responsible for."),
    "hate_or_incitement": Refusal(
        "Hate speech or incitement",
        "It contains hate speech or encourages violence."),
    "personal_data": Refusal(
        "Contains personal data",
        "It contains someone's personal data, such as a phone number, a home address or an ID number."),
}


@dataclass(frozen=True)
class ResponseKind:
    label: str  # as the public reads it


RESPONSE_KINDS: dict[str, ResponseKind] = {
    "will_act": ResponseKind("The Assembly will act"),
    "referred": ResponseKind("Referred to a department"),
    "cannot_act": ResponseKind("The Assembly can't act"),
}
RESPONSE_MIN, RESPONSE_MAX = 50, 4000


class PetitionError(Exception):
    status_code = 400


class NotAllowed(PetitionError):
    status_code = 403


class WrongState(PetitionError):
    status_code = 409


class InvalidPetition(PetitionError):
    status_code = 422


def petition_topics() -> list[Topic]:
    """Everyday topics, and public-safety topics an Assembly department handles. Personal safety never; nor what only
    the Police or the Fire Service handle, which aren't the Assembly's."""
    return [t for t in TOPICS if t.category == Category.CIVIC_SERVICE
            or (t.category == Category.PUBLIC_SAFETY and all(r in DEPARTMENT_TEAMS for r in t.recipients))]


def new_code() -> str:
    return str(10 ** (CODE_DIGITS - 1) + secrets.randbelow(9 * 10 ** (CODE_DIGITS - 1)))


def normalise_code(typed: str) -> str | None:
    """A petition number as typed ("482 913", "482-913"), or None if it isn't one."""
    code = typed.strip().replace(" ", "").replace("-", "")
    return code if re.fullmatch(f"[0-9]{{{CODE_DIGITS}}}", code) else None


@dataclass(frozen=True)
class Draft:
    title: str  # what the petition asks the Assembly to do
    body: str  # why
    topic: str
    scope: Scope
    ward: str | None  # the electoral area, for an area petition
    issue: str | None  # an open civic issue's public ID
    documents: tuple[str, ...]  # Ledger document IDs the creator cites


def _text(value: str, name: str, low: int, high: int) -> str:
    text = " ".join(value.split()) if name == "title" else value.strip()
    if len(text) < low:
        raise InvalidPetition(f"Write a little more in the {name}: at least {low} characters.")
    if len(text) > high:
        raise InvalidPetition(f"Keep the {name} under {high:,} characters.")
    return text


def clean_draft(draft: Draft) -> Draft:
    """The draft as it will be stored, or InvalidPetition saying what to fix."""
    if draft.topic not in {t.id for t in petition_topics()}:
        raise InvalidPetition("Choose a topic from the list.")
    ward = draft.ward if draft.scope == Scope.AREA else None
    if draft.scope == Scope.AREA and ward not in wards():
        raise InvalidPetition("Choose the electoral area the petition is about.")
    documents = tuple(dict.fromkeys(draft.documents))
    if len(documents) > DOCUMENTS_MAX:
        raise InvalidPetition(f"Cite at most {DOCUMENTS_MAX} documents.")
    return Draft(_text(draft.title, "title", TITLE_MIN, TITLE_MAX), _text(draft.body, "reasons", BODY_MIN, BODY_MAX),
                 draft.topic, draft.scope, ward, (draft.issue or "").strip() or None, documents)


def clean_name(show_name: bool, name: str | None) -> str | None:
    """A name to show publicly, only when the person chose to show one."""
    given = " ".join((name or "").split()) if show_name else ""
    if show_name and not given:
        raise InvalidPetition("Enter the name to show, or choose to stay anonymous.")
    if len(given) > NAME_MAX:
        raise InvalidPetition(f"Keep the name under {NAME_MAX} characters.")
    return given or None


def draft_fields(draft: Draft) -> dict[str, Any]:
    return {"title": draft.title, "body": draft.body, "topic": draft.topic, "recipients": list(TOPICS_BY_ID[draft.topic].recipients),
            "scope": draft.scope.value, "wardLocation": draft.ward, "issueId": draft.issue, "documentIds": list(draft.documents)}


def review_fields(now: datetime) -> dict[str, Any]:
    return {"status": PetitionStatus.IN_REVIEW.value, "submittedAt": now.isoformat(),
            "reviewDeadline": (now + REVIEW_WINDOW).isoformat(), "refusalReason": None, "refusalNote": None, "duplicateOf": None}


def threshold_for(scope: Scope, area_threshold: int, metro_threshold: int) -> int:
    return area_threshold if scope == Scope.AREA else metro_threshold


def publish_fields(petition: dict[str, Any], by: PublishedBy, now: datetime, threshold: int) -> dict[str, Any]:
    """Opening for signatures. The threshold is fixed now, so a later change to the setting never moves the goal."""
    return {"status": PetitionStatus.OPEN.value, "publishedAt": now.isoformat(), "publishedBy": by.value,
            "closesAt": (now + OPEN_FOR).isoformat(), "threshold": threshold}


def review_expired(petition: dict[str, Any], now: datetime) -> bool:
    deadline = parse_datetime(petition.get("reviewDeadline"))
    return petition.get("status") == PetitionStatus.IN_REVIEW and deadline is not None and deadline <= now


def check_review(petition: dict[str, Any], now: datetime) -> None:
    """The MCE may decide only while the petition is in review and its clock is still running."""
    if petition.get("status") != PetitionStatus.IN_REVIEW:
        raise WrongState("This petition is no longer waiting for a decision.")
    if review_expired(petition, now):
        raise WrongState("The 72 hours have passed, so this petition publishes automatically.")


def refusal_fields(reason: str, note: str | None, duplicate_of: str | None) -> dict[str, Any]:
    if reason not in REFUSALS:
        raise InvalidPetition("Choose one of the reasons a petition can be refused for.")
    if reason == "duplicate" and not duplicate_of:
        raise InvalidPetition("Give the number of the open petition this one duplicates.")
    note = (note or "").strip() or None
    if note and len(note) > NOTE_MAX:
        raise InvalidPetition(f"Keep the note under {NOTE_MAX:,} characters.")
    return {"status": PetitionStatus.REFUSED.value, "refusalReason": reason, "refusalNote": note,
            "duplicateOf": duplicate_of if reason == "duplicate" else None}


def check_resubmit(petition: dict[str, Any]) -> None:
    if petition.get("status") != PetitionStatus.REFUSED:
        raise WrongState("Only a refused petition can be edited and sent back for review.")
    if (petition.get("resubmissions") or 0) >= MAX_RESUBMISSIONS:
        raise WrongState(f"A refused petition can be sent back {MAX_RESUBMISSIONS} times, and this one has been.")


def check_withdraw(petition: dict[str, Any]) -> None:
    if petition.get("status") == PetitionStatus.AWAITING_RESPONSE:
        raise WrongState("It has reached its signatures and gone to the MCE, so it can't be withdrawn now.")
    if petition.get("status") not in (PetitionStatus.IN_REVIEW, PetitionStatus.REFUSED, PetitionStatus.OPEN):
        raise WrongState("This petition has already closed.")


SIGNING = (PetitionStatus.OPEN, PetitionStatus.AWAITING_RESPONSE)
_NAME = re.compile(r"^[^\W\d_]+(?:[ .'’-]+[^\W\d_]+)*\.?$")  # letters, with spaces, dots, apostrophes and hyphens between


def check_signable(petition: dict[str, Any], now: datetime) -> None:
    closes = parse_datetime(petition.get("closesAt"))
    if petition.get("status") not in SIGNING or closes is None or closes <= now:
        raise WrongState("This petition has closed, so it takes no more signatures.")


def clean_signer_name(show_name: bool, name: str | None) -> str | None:
    """A signer's name to show publicly: letters only, so the name field can't carry a number or a message."""
    given = clean_name(show_name, name)
    if given and not _NAME.match(given):
        raise InvalidPetition("A name can have letters, spaces, hyphens and apostrophes only.")
    return given


def threshold_fields(petition: dict[str, Any], signatures: int, now: datetime) -> dict[str, Any]:
    """The new count, and, the moment it reaches the threshold, the MCE's 30 days to respond."""
    changes: dict[str, Any] = {"signatureCount": signatures}
    threshold = petition.get("threshold")
    if petition.get("status") == PetitionStatus.OPEN and threshold and signatures >= threshold:
        changes.update(status=PetitionStatus.AWAITING_RESPONSE.value, thresholdReachedAt=now.isoformat(),
                       responseDue=(now + RESPONSE_WINDOW).isoformat())
    return changes


def closing_due(petition: dict[str, Any], now: datetime) -> bool:
    closes = parse_datetime(petition.get("closesAt"))
    return petition.get("status") == PetitionStatus.OPEN and closes is not None and closes <= now


def was_published(petition: dict[str, Any]) -> bool:
    """Whether the public may see it: it was published, even if it has since closed or been withdrawn."""
    return bool(petition.get("publishedAt"))


def creator_actions(petition: dict[str, Any]) -> list[str]:
    status = petition.get("status")
    actions = ["withdraw"] if status in (PetitionStatus.IN_REVIEW, PetitionStatus.REFUSED, PetitionStatus.OPEN) else []
    if status == PetitionStatus.REFUSED and (petition.get("resubmissions") or 0) < MAX_RESUBMISSIONS:
        actions.append("resubmit")
    if petition.get("creatorName"):
        actions.append("make_anonymous")
    return actions


@dataclass(frozen=True)
class Response:
    kind: str
    text: str
    department: str | None  # the department it is referred to
    documents: tuple[str, ...]  # Ledger documents the MCE cites


def response_fields(petition: dict[str, Any], response: Response, now: datetime) -> dict[str, Any]:
    """The MCE's public response, checked. Only a petition that reached its threshold is owed one; a late one is taken."""
    if petition.get("status") != PetitionStatus.AWAITING_RESPONSE:
        raise WrongState("Only a petition that has reached its signatures, and not been answered, is waiting for a response.")
    if response.kind not in RESPONSE_KINDS:
        raise InvalidPetition("Choose what the response is: the Assembly will act, it's referred to a department, or it can't act.")
    if response.kind == "referred" and response.department not in DEPARTMENT_TEAMS:
        raise InvalidPetition("Choose the department it is referred to.")
    documents = tuple(dict.fromkeys(response.documents))
    if len(documents) > DOCUMENTS_MAX:
        raise InvalidPetition(f"Cite at most {DOCUMENTS_MAX} documents.")
    text = _text(response.text, "response", RESPONSE_MIN, RESPONSE_MAX)
    return {"status": PetitionStatus.RESPONDED.value, "respondedAt": now.isoformat(), "responseKind": response.kind,
            "responseText": text, "responseDepartment": response.department if response.kind == "referred" else None,
            "responseDocumentIds": list(documents)}


def response_overdue(petition: dict[str, Any], now: datetime) -> bool:
    """The 30 days have passed with no response, and that hasn't been recorded yet."""
    due = parse_datetime(petition.get("responseDue"))
    return (petition.get("status") == PetitionStatus.AWAITING_RESPONSE and due is not None and due <= now
            and not petition.get("noResponseAt"))


def days_late(petition: dict[str, Any]) -> int:
    """How many days after the 30-day deadline the MCE responded; 0 if in time."""
    due, responded = parse_datetime(petition.get("responseDue")), parse_datetime(petition.get("respondedAt"))
    if due is None or responded is None or responded <= due:
        return 0
    return math.ceil((responded - due).total_seconds() / 86400)
