"""The rules a citizen report is filed by.

Every doubt resolves toward privacy: a report is personal safety if the citizen or the model says so, or if the
model gave nothing usable and the words suggest danger to a person. Moving a report out of personal safety is left
to a person, never done here. A personal-safety report keeps no ward, only a sub-metro at most.
"""

import re
import secrets
from dataclasses import dataclass
from enum import StrEnum

from app.services.report_taxonomy import (
    DEFAULT_SAFETY_TOPIC,
    TOPICS_BY_ID,
    TRIAGE_TOPIC,
    Category,
    recipients_for,
)
from app.wards import sub_metro_of, sub_metros, wards

SEVERITY_MIN, SEVERITY_MAX = 1, 5
PERSONAL_SAFETY_SEVERITY = SEVERITY_MAX  # set by rule, never judged by the model
DEFAULT_SEVERITY = 3  # when the model gives none

REFERENCE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # no 0/O, 1/I/L: easy to read aloud and type
REFERENCE_LENGTH = 8

# Words that suggest danger to a person. Used only when the model gave no usable
# answer or filed the report as an everyday civic matter: then a hit moves the
# report to personal safety, where it is private, rather than risk publishing it.
_DANGER_TO_A_PERSON = re.compile(
    r"\b("
    r"abus(e|ed|es|ing|ive)|rap(e|ed|ist|ing)|defil(e|ed|ement)|molest(ed|ing)?|"
    r"sexual(ly)?\s+(assault|abuse|harass)\w*|domestic\s+violence|violence\s+against|"
    r"assault(ed|ing|s)?|stab(bed|bing)?|kidnap(ped|ping)?|traffick(ed|ing)|"
    r"(beat|beats|beating|beaten|hit|hits|hitting|slap|slaps|slapped)\s+(me|her|him|my|his|the\s+child)|"
    r"(threat\w*|going)\s+to\s+kill|kill\s+(me|her|him|us|them|my)|"
    r"forced\s+marriage|child\s+labou?r"
    r")\b",
    re.IGNORECASE,
)


class ClassificationMethod(StrEnum):
    CITIZEN = "citizen"  # declared personal safety and chose its type; the model was not asked
    AI = "ai"
    KEYWORD_SCREEN = "keyword_screen"  # words of danger overrode, or stood in for, the model
    TRIAGE = "triage"  # the model failed; a person classifies it


@dataclass(frozen=True)
class ModelVerdict:
    """What the classifier returned, before any rule is applied."""

    category: str
    topic: str
    severity: int | None


@dataclass(frozen=True)
class Classification:
    category: Category
    topic: str
    severity: int
    recipients: tuple[str, ...]
    method: ClassificationMethod

    @property
    def private(self) -> bool:
        return self.category == Category.PERSONAL_SAFETY


class InvalidReport(ValueError):
    """The submission can't be filed as given (an unknown topic, ward or sub-metro)."""


def suggests_danger_to_a_person(text: str) -> bool:
    return bool(_DANGER_TO_A_PERSON.search(text))


def _filed(topic_id: str, method: ClassificationMethod, severity: int | None = None) -> Classification:
    topic = TOPICS_BY_ID[topic_id]
    if topic.private:
        severity = PERSONAL_SAFETY_SEVERITY
    else:
        severity = min(SEVERITY_MAX, max(SEVERITY_MIN, DEFAULT_SEVERITY if severity is None else severity))
    return Classification(topic.category, topic.id, severity, recipients_for(topic.id), method)


def _usable(verdict: ModelVerdict) -> bool:
    topic = TOPICS_BY_ID.get(verdict.topic)
    return topic is not None and topic.category == verdict.category


def _model_says_personal_safety(verdict: ModelVerdict) -> bool:
    topic = TOPICS_BY_ID.get(verdict.topic)
    return verdict.category == Category.PERSONAL_SAFETY or (topic is not None and topic.private)


def _declared(topic_id: str) -> Classification:
    topic = TOPICS_BY_ID.get(topic_id)
    if topic is None or not topic.private:
        raise InvalidReport("Choose what kind of danger this is.")
    return _filed(topic.id, ClassificationMethod.CITIZEN)


def classify(description: str, declared_safety_topic: str | None, verdict: ModelVerdict | None) -> Classification:
    """verdict is None when the model wasn't asked or failed."""
    if declared_safety_topic is not None:
        return _declared(declared_safety_topic)
    if verdict is not None and _model_says_personal_safety(verdict):
        return _filed(verdict.topic if _usable(verdict) else DEFAULT_SAFETY_TOPIC, ClassificationMethod.AI)
    danger = suggests_danger_to_a_person(description)
    if verdict is None or not _usable(verdict):
        method = ClassificationMethod.KEYWORD_SCREEN if danger else ClassificationMethod.TRIAGE
        return _filed(DEFAULT_SAFETY_TOPIC if danger else TRIAGE_TOPIC, method)
    if danger and verdict.category == Category.CIVIC_SERVICE:
        return _filed(DEFAULT_SAFETY_TOPIC, ClassificationMethod.KEYWORD_SCREEN)
    return _filed(verdict.topic, ClassificationMethod.AI, verdict.severity)


@dataclass(frozen=True)
class Location:
    ward: str | None
    sub_metro: str | None


def locate(category: Category, ward_id: str | None, sub_metro_id: str | None) -> Location:
    if ward_id is not None and ward_id not in wards():
        raise InvalidReport("Choose an electoral area from the list.")
    if sub_metro_id is not None and sub_metro_id not in sub_metros():
        raise InvalidReport("Choose a sub-metro from the list.")
    if category == Category.PERSONAL_SAFETY:
        return Location(ward=None, sub_metro=sub_metro_id or (sub_metro_of(ward_id) if ward_id else None))
    if ward_id is None:
        raise InvalidReport("Choose the electoral area where this is.")
    return Location(ward=ward_id, sub_metro=sub_metro_of(ward_id))


def new_reference() -> str:
    """Carries no personal information."""
    code = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(REFERENCE_LENGTH))
    return f"{code[:4]}-{code[4:]}"


PUBLIC_ID_LENGTH = 10


def new_public_id() -> str:
    """Unlike the reference or the case ID, it opens no status page, so it can be shown to anyone."""
    return "".join(secrets.choice(REFERENCE_ALPHABET.lower()) for _ in range(PUBLIC_ID_LENGTH))


def normalise_reference(typed: str) -> str | None:
    code = re.sub(r"[\s-]", "", typed).upper()
    if len(code) != REFERENCE_LENGTH or any(char not in REFERENCE_ALPHABET for char in code):
        return None
    return f"{code[:4]}-{code[4:]}"
