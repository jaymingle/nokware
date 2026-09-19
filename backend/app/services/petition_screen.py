"""The checks a petition's words pass before it goes to the MCE.

Two stop it outright, because a public petition is the wrong place for them:
- words of danger to a person (the same screen report intake uses): that goes
  privately through Report;
- someone's personal data, found by pattern: a phone number, an email address,
  a Ghana Card number.

One only warns: Gemini's reading that the petition names a private person. A
model can be wrong about who is a public official, so the creator may edit it
or send it as it is, and the MCE, who can refuse it for that reason, decides.
If Gemini can't be reached, the petition goes on with the pattern checks alone.
"""

import logging
import re
from dataclasses import dataclass

import httpx
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.services.llm import CHAT_MODEL, get_genai_client
from app.services.report_rules import suggests_danger_to_a_person

logger = logging.getLogger(__name__)

TIMEOUT_MS = 15_000
_PERSONAL_DATA = (
    ("a phone number", re.compile(r"(?<!\d)(?:\+?233[\s-]?|0)[235]\d(?:[\s-]?\d){7}(?!\d)")),
    ("an email address", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("a Ghana Card number", re.compile(r"\bGHA[\s-]?\d{9}[\s-]?\d\b", re.IGNORECASE)),
)
SAFETY_STOP = ("This sounds like it's about someone's safety. That shouldn't be in a public petition: report it privately "
               "through Report, where only the people who can help will see it.")

_INSTRUCTIONS = """You check a petition to the Accra Metropolitan Assembly (Ghana) before it is published.
Answer two questions about the petition below.
names_private_individual: does it name, or plainly identify, a private person (a neighbour, a trader, a landlord, a
family)? Public officials acting in their public role (the MCE, an Assembly Member, a department head, a minister),
businesses, institutions and places are NOT private individuals.
private_individual: if so, the words that name or identify them, copied exactly; otherwise empty.
Judge only what is written. Never guess."""


class _Reading(BaseModel):
    names_private_individual: bool
    private_individual: str


@dataclass(frozen=True)
class Screening:
    stop: str | None  # why it can't go as written, or None
    warning: str | None  # what the creator should know before sending it anyway, or None


def personal_data(text: str) -> str | None:
    return next((kind for kind, pattern in _PERSONAL_DATA if pattern.search(text)), None)


def private_person(text: str) -> str | None:
    """Whether the words name a private individual, as the model reads them. Advisory: a model that fails or times
    out returns None, because a check nobody can run is not a reason to stop someone working."""
    config = types.GenerateContentConfig(
        temperature=0.0, thinking_config=types.ThinkingConfig(thinking_budget=0),
        response_mime_type="application/json", response_schema=_Reading,
        http_options=types.HttpOptions(timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=2)),
    )
    try:
        response = get_genai_client().models.generate_content(
            model=CHAT_MODEL, contents=[_INSTRUCTIONS, f"Petition:\n{text}"], config=config)
        reading = response.parsed if isinstance(response.parsed, _Reading) else _Reading.model_validate_json(response.text or "")
    except (errors.APIError, httpx.HTTPError, ValidationError, ValueError, OSError) as error:
        logger.warning("The petition check for private individuals didn't run (%s)", type(error).__name__)
        return None
    return (reading.private_individual.strip() or "someone") if reading.names_private_individual else None


def hard_stop(title: str, body: str) -> str | None:
    """Checked on the draft and again when it is sent."""
    text = f"{title}\n\n{body}"
    if suggests_danger_to_a_person(text):
        return SAFETY_STOP
    found = personal_data(text)
    return f"It contains {found}. Take it out: a petition is public, and personal data can't be in it." if found else None


def screen(title: str, body: str) -> Screening:
    stop = hard_stop(title, body)
    if stop:
        return Screening(stop, None)
    person = private_person(f"{title}\n\n{body}")
    warning = (f"This seems to name a private person (“{person}”). A petition can't: the MCE can refuse it for that. "
               "Edit it, or send it as it is if they are a public official acting in their role.") if person else None
    return Screening(None, warning)
