"""Nokware's fixed text in English, French and Twi, and the rule that keeps an unchecked translation off a screen.

Fixed text — the sentences Ask puts around an answer, the safety steps, the
emergency lines — is written by hand in app/data/phrases/, never translated while
someone is waiting. A translation model is used for what can't be written in
advance (a resident's question, an answer from the documents); everything a
reader might act on comes from here.

Two rules:

- **English is the source.** A key missing from another language shows in
  English. Nothing is ever half-written on screen.
- **Critical text waits for a named reviewer.** Text marked critical in en.json
  is text someone may act on while in danger: the safety steps, the emergency
  heading, the medical line, the call-list warning. It ships in another language
  only when that language's entry names who checked it and when. Until then the
  reader gets the English, which is checked. A machine that drops a negative
  turns "don't confront them yourself" into its opposite, and that is not a
  wording problem.

Twi carries no text yet, by the same rule: it waits for a speaker rather than
Nokware's guess. scripts/phrases_to_review.py prints what each language still
needs, with the English beside it.
"""

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parents[1] / "data" / "phrases"


class Language(StrEnum):
    """The languages Nokware writes in. English is the source; the rest are written from it."""

    ENGLISH = "en"
    FRENCH = "fr"
    TWI = "tw"


NAMES = {Language.ENGLISH: "English", Language.FRENCH: "French", Language.TWI: "Twi"}


@dataclass(frozen=True)
class Missing:
    """A phrase a language doesn't show yet, and why."""

    key: str
    language: Language
    english: str
    critical: bool
    reason: str  # "not written" or "not reviewed"


@lru_cache
def _catalogue(language: Language) -> dict[str, dict[str, Any]]:
    path = DATA / f"{language.value}.json"
    return dict(json.loads(path.read_text())["phrases"]) if path.exists() else {}


def keys() -> list[str]:
    return list(_catalogue(Language.ENGLISH))


def is_critical(key: str) -> bool:
    """Whether this is text someone may act on while in danger."""
    return bool(_catalogue(Language.ENGLISH)[key].get("critical"))


def english(key: str) -> str:
    return str(_catalogue(Language.ENGLISH)[key]["text"])


def reviewer(key: str, language: Language) -> str | None:
    """Who checked this translation, if anyone has."""
    return _catalogue(language).get(key, {}).get("reviewed_by")


def phrase(key: str, language: Language = Language.ENGLISH) -> str:
    """The text to show. English where the language hasn't written it, or where critical text hasn't been reviewed."""
    if language is Language.ENGLISH:
        return english(key)
    written = _catalogue(language).get(key)
    if not written or (is_critical(key) and not written.get("reviewed_by")):
        return english(key)
    return str(written["text"])


def shows_english(key: str, language: Language) -> bool:
    """Whether a reader in this language sees the English, so a page can say so rather than look untranslated."""
    return language is not Language.ENGLISH and phrase(key, language) == english(key)


def missing(language: Language) -> list[Missing]:
    """What this language doesn't show yet: not written at all, or written but not reviewed where it must be."""
    found = []
    for key in keys():
        written = _catalogue(language).get(key)
        if not written:
            found.append(Missing(key, language, english(key), is_critical(key), "not written"))
        elif is_critical(key) and not written.get("reviewed_by"):
            found.append(Missing(key, language, english(key), True, "not reviewed"))
    return found
