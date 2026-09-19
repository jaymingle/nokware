"""The petition rules, as pure functions with no Appwrite calls, so every rule is unit-tested and the routes can't drift.

Lifecycle:
  a draft that passes the screen is published by the person who wrote it -> open (90 days)
  open -> awaiting_response at its threshold (the MCE has 30 days; a late response is still taken) -> responded
  open for 90 days without reaching it -> closed; the creator can close it themselves until it reaches its threshold
  open, awaiting_response, responded or closed -> removed, by a verified contributor, on one of four grounds

A response is not the end of the exchange, and none of what follows moves the petition anywhere: the MCE shares the
petition with a department, which writes one note under its own name, and the petitioner replies once to the
response. What stands on the page is a conversation, not another state.

Nobody approves a petition into existence. The Assembly is usually what a petition is about, so the MCE cannot
publish, refuse or remove one: it decides only whether to answer. What comes down comes down on a named ground,
against a published tombstone that says which, and the creator can mend the words and publish it again.
"""

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from app.services.ledger_documents import parse_datetime
from app.services.petition_grounds import Ground
from app.services.phrases import phrase
from app.services.report_taxonomy import TOPICS, TOPICS_BY_ID, Category, Topic
from app.teams import DEPARTMENT_TEAMS
from app.wards import wards

OPEN_FOR = timedelta(days=90)
RESPONSE_WINDOW = timedelta(days=30)  # the MCE's time to answer publicly once a petition reaches its threshold
TITLE_MIN, TITLE_MAX = 15, 150
BODY_MIN, BODY_MAX = 50, 4000
NAME_MAX = 80
NOTE_MAX = 1000  # a line of the audit trail
DEPARTMENT_NOTE_MAX = 500  # one department's answer, on the public page, to a petition the MCE shared with it
REPLY_MAX = 1000  # the petitioner's reply to the response the MCE published
REMOVAL_NOTE_MAX = 500  # what a contributor writes for the record when they remove a petition
REPORT_NOTE_MAX = 300  # what a reader may add when they report one
DOCUMENTS_MAX = 3
IMAGES_MAX = 4  # a petition shows more of a place than a report does: four sides of one problem
CODE_DIGITS = 6  # digits only, so a petition can be typed on a USSD keypad or read aloud
FIRST_VERSION = 1


class PetitionStatus(StrEnum):
    OPEN = "open"
    AWAITING_RESPONSE = "awaiting_response"  # reached its threshold: the MCE must respond publicly
    RESPONDED = "responded"
    REMOVED = "removed"  # a contributor took it down on one of the four grounds; only the tombstone is public
    CLOSED = "closed"


# What the database held before the MCE's review gate was taken out. No code puts a petition into one of these
# again; they stay named here so the schema still accepts a row the migration has yet to move, and so the
# migration's mapping reads against the same words the old rows carry.
LEGACY_STATUSES = ("in_review", "refused", "withdrawn")
LEGACY_ACTIONS = ("resubmitted", "auto_published", "refused")
# How a petition the old process ended is described to a reader. A refusal is named as a refusal under the process
# that made it, never as a contributor's removal: saying a contributor took it down would be untrue.
LEGACY_LABELS: dict[str, str] = {
    "refused": "petition.legacy.refused",
    "withdrawn": "petition.legacy.withdrawn",
    "in_review": "petition.legacy.closed_in_move",
}


class Scope(StrEnum):
    METRO = "metro"  # the whole Assembly
    AREA = "area"  # one electoral area


class PetitionAction(StrEnum):
    PUBLISHED = "published"  # the creator published it: there is no other way one begins
    EDITED = "edited"  # a new version of a petition that was standing
    REPUBLISHED = "republished"  # a new version of one that had been removed
    REMOVED = "removed"
    WITHDRAWN = "withdrawn"  # the creator closed their own petition
    CLOSED = "closed"
    MADE_ANONYMOUS = "made_anonymous"
    THRESHOLD_REACHED = "threshold_reached"
    RESPONDED = "responded"
    NO_RESPONSE = "no_response"  # 30 days after the threshold, with no response
    SHARED = "shared"  # the MCE sent the petition to a department for its answer
    DEPARTMENT_NOTE = "department_note"  # that department wrote its one note
    CREATOR_REPLIED = "creator_replied"  # the petitioner answered the MCE's response
    IMAGE_REMOVED = "image_removed"  # a contributor took one photo off; the petition and the rest stand
    CREATOR_NOTIFIED = "creator_notified"  # a message to the creator: never public


@dataclass(frozen=True)
class ResponseKind:
    label: str  # as the public reads it


RESPONSE_KINDS: dict[str, ResponseKind] = {
    "will_act": ResponseKind("The Assembly will act"),
    "referred": ResponseKind("Referred to a department"),
    "cannot_act": ResponseKind("The Assembly can't act"),
}
RESPONSE_MIN, RESPONSE_MAX = 50, 4000

STATUS_WORDS: dict[PetitionStatus, str] = {
    PetitionStatus.OPEN: "petition.status.open",
    PetitionStatus.AWAITING_RESPONSE: "petition.status.awaiting_response",
    PetitionStatus.RESPONDED: "petition.status.responded",
    PetitionStatus.REMOVED: "petition.status.removed",
    PetitionStatus.CLOSED: "petition.status.closed",
}


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
    images: tuple[str, ...] = ()  # what the creator shows, as stored object names


def _text(value: str, name: str, low: int, high: int) -> str:
    text = " ".join(value.split()) if name == "title" else value.strip()
    if len(text) < low:
        raise InvalidPetition(f"Write a little more in the {name}: at least {low} characters.")
    if len(text) > high:
        raise InvalidPetition(f"Keep the {name} under {high:,} characters.")
    return text


def clean_draft(draft: Draft) -> Draft:
    if draft.topic not in {t.id for t in petition_topics()}:
        raise InvalidPetition("Choose a topic from the list.")
    ward = draft.ward if draft.scope == Scope.AREA else None
    if draft.scope == Scope.AREA and ward not in wards():
        raise InvalidPetition("Choose the electoral area the petition is about.")
    documents = tuple(dict.fromkeys(draft.documents))
    if len(documents) > DOCUMENTS_MAX:
        raise InvalidPetition(f"Cite at most {DOCUMENTS_MAX} documents.")
    if len(draft.images) > IMAGES_MAX:
        raise InvalidPetition(f"Attach at most {IMAGES_MAX} images.")
    return Draft(_text(draft.title, "title", TITLE_MIN, TITLE_MAX), _text(draft.body, "reasons", BODY_MIN, BODY_MAX),
                 draft.topic, draft.scope, ward, (draft.issue or "").strip() or None, documents, draft.images)


def clean_name(show_name: bool, name: str | None) -> str | None:
    given = " ".join((name or "").split()) if show_name else ""
    if show_name and not given:
        raise InvalidPetition("Enter the name to show, or choose to stay anonymous.")
    if len(given) > NAME_MAX:
        raise InvalidPetition(f"Keep the name under {NAME_MAX} characters.")
    return given or None


def draft_fields(draft: Draft) -> dict[str, Any]:
    return {"title": draft.title, "body": draft.body, "topic": draft.topic, "recipients": list(TOPICS_BY_ID[draft.topic].recipients),
            "scope": draft.scope.value, "wardLocation": draft.ward, "issueId": draft.issue,
            "documentIds": list(draft.documents), "imageIds": list(draft.images)}


def threshold_for(scope: Scope, area_threshold: int, metro_threshold: int) -> int:
    return area_threshold if scope == Scope.AREA else metro_threshold


def publish_fields(now: datetime, threshold: int) -> dict[str, Any]:
    """The threshold is fixed now, so a later change to the setting never moves the goal."""
    return {"status": PetitionStatus.OPEN.value, "submittedAt": now.isoformat(), "publishedAt": now.isoformat(),
            "closesAt": (now + OPEN_FOR).isoformat(), "threshold": threshold, "version": FIRST_VERSION,
            "versionedAt": now.isoformat(), "removalCount": 0}


def version_of(petition: dict[str, Any]) -> int:
    """A petition written before versions were kept stands at its first version."""
    return int(petition.get("version") or FIRST_VERSION)


EDITABLE = (PetitionStatus.OPEN, PetitionStatus.AWAITING_RESPONSE, PetitionStatus.REMOVED)


def check_editable(petition: dict[str, Any]) -> None:
    """A petition the MCE has answered is fixed: the answer was given to those words. A closed one is history."""
    if petition.get("status") not in EDITABLE:
        raise WrongState(phrase("petition.edit.not_editable"))


def edit_fields(draft: Draft, petition: dict[str, Any], now: datetime) -> dict[str, Any]:
    """A new version of the words. A removed petition comes back to the state it was removed from, its closing date
    untouched: time spent down is not time won."""
    changes: dict[str, Any] = {**draft_fields(draft), "version": version_of(petition) + 1, "versionedAt": now.isoformat()}
    if petition.get("status") == PetitionStatus.REMOVED:
        changes.update(status=str(petition.get("removedFromStatus") or PetitionStatus.OPEN.value),
                       removedAt=None, removalGround=None, removalDuplicateOf=None, removedFromStatus=None)
    return changes


def edit_action(petition: dict[str, Any]) -> PetitionAction:
    return PetitionAction.REPUBLISHED if petition.get("status") == PetitionStatus.REMOVED else PetitionAction.EDITED


def removal_fields(ground: Ground, duplicate_of: str | None, petition: dict[str, Any], now: datetime) -> dict[str, Any]:
    """What a removal changes on the petition itself. Nothing public is built from these: the tombstone is built
    from the removal record, so no title, body or image can reach a reader through them."""
    return {"status": PetitionStatus.REMOVED.value, "removedAt": now.isoformat(), "removalGround": ground.value,
            "removalDuplicateOf": duplicate_of, "removedFromStatus": str(petition["status"]),
            "removalCount": removals_of(petition) + 1}


def removals_of(petition: dict[str, Any]) -> int:
    return int(petition.get("removalCount") or 0)


def check_removable(petition: dict[str, Any]) -> None:
    if petition.get("status") == PetitionStatus.REMOVED:
        raise WrongState(phrase("petition.removal.already_removed"))


def check_withdraw(petition: dict[str, Any]) -> None:
    if petition.get("status") == PetitionStatus.AWAITING_RESPONSE:
        raise WrongState("It has reached its signatures and gone to the MCE, so it can't be withdrawn now.")
    if petition.get("status") != PetitionStatus.OPEN:
        raise WrongState("This petition has already closed.")


SIGNING = (PetitionStatus.OPEN, PetitionStatus.AWAITING_RESPONSE)
_NAME = re.compile(r"^[^\W\d_]+(?:[ .'’-]+[^\W\d_]+)*\.?$")  # letters, with spaces, dots, apostrophes and hyphens between


def check_signable(petition: dict[str, Any], now: datetime) -> None:
    closes = parse_datetime(petition.get("closesAt"))
    if petition.get("status") not in SIGNING or closes is None or closes <= now:
        raise WrongState("This petition has closed, so it takes no more signatures.")


def clean_signer_name(show_name: bool, name: str | None) -> str | None:
    """Letters only, so the name field can't carry a number or a message."""
    given = clean_name(show_name, name)
    if given and not _NAME.match(given):
        raise InvalidPetition("A name can have letters, spaces, hyphens and apostrophes only.")
    return given


def threshold_fields(petition: dict[str, Any], signatures: int, now: datetime) -> dict[str, Any]:
    changes: dict[str, Any] = {"signatureCount": signatures}
    threshold = petition.get("threshold")
    if petition.get("status") == PetitionStatus.OPEN and threshold and signatures >= threshold:
        changes.update(status=PetitionStatus.AWAITING_RESPONSE.value, thresholdReachedAt=now.isoformat(),
                       responseDue=(now + RESPONSE_WINDOW).isoformat())
    return changes


def closing_due(petition: dict[str, Any], now: datetime) -> bool:
    closes = parse_datetime(petition.get("closesAt"))
    return petition.get("status") == PetitionStatus.OPEN and closes is not None and closes <= now


def is_public(petition: dict[str, Any]) -> bool:
    """Public from the moment it is published, and still public once it has closed. A removed petition is not: its
    page is the tombstone, which is built from the removal record alone."""
    return bool(petition.get("publishedAt")) and petition.get("status") != PetitionStatus.REMOVED


def creator_actions(petition: dict[str, Any]) -> list[str]:
    status = petition.get("status")
    actions = ["edit"] if status in EDITABLE else []
    if status == PetitionStatus.OPEN:
        actions.append("withdraw")
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


def check_department(team: str) -> None:
    """A petition is shared with a department of the Assembly, from the one list of them there is."""
    if team not in DEPARTMENT_TEAMS:
        raise InvalidPetition(phrase("petition.share.not_a_department"))


def check_repliable(petition: dict[str, Any]) -> None:
    """One reply answers one response. It is the response that is being replied to, so there is nothing to reply
    to until the MCE has published one, and nothing to reply to on a removed petition, whose response is down
    with it."""
    if not is_public(petition) or not petition.get("respondedAt"):
        raise WrongState(phrase("petition.reply.no_response"))
    if petition.get("replyAt"):
        raise WrongState(phrase("petition.reply.already_replied"))


def reply_fields(text: str, now: datetime) -> dict[str, Any]:
    """Kept on the petition beside the response it answers: one response, one reply, read and removed together."""
    return {"replyText": text, "replyAt": now.isoformat()}


def response_overdue(petition: dict[str, Any], now: datetime) -> bool:
    due = parse_datetime(petition.get("responseDue"))
    return (petition.get("status") == PetitionStatus.AWAITING_RESPONSE and due is not None and due <= now
            and not petition.get("noResponseAt"))


def responded_late(petition: dict[str, Any]) -> bool:
    due, responded = parse_datetime(petition.get("responseDue")), parse_datetime(petition.get("respondedAt"))
    return due is not None and responded is not None and responded > due


def days_late(petition: dict[str, Any]) -> int:
    """Never rounded up, so lateness is never overstated."""
    if not responded_late(petition):
        return 0
    due, responded = parse_datetime(petition["responseDue"]), parse_datetime(petition["respondedAt"])
    return (responded - due).days if due and responded else 0
