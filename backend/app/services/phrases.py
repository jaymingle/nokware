"""Nokware's fixed text in English, French and Twi, and the rule that keeps an unchecked translation off a screen.

Fixed text is written by hand, never translated by a model while someone is waiting. English is the source: a key
missing from another language shows in English, so nothing is half-written on screen.

Critical text is what someone may act on while in danger, and ships in another language only once a named person
has reviewed it. A machine that drops a negative turns "don't confront them yourself" into its opposite. Twi carries
no text yet, by the same rule: it waits for a speaker rather than Nokware's guess.
"""

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parents[1] / "data" / "phrases"


class Language(StrEnum):
    ENGLISH = "en"
    FRENCH = "fr"
    TWI = "tw"


NAMES = {Language.ENGLISH: "English", Language.FRENCH: "French", Language.TWI: "Twi"}


@dataclass(frozen=True)
class Missing:
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
    return bool(_catalogue(Language.ENGLISH)[key].get("critical"))


def english(key: str) -> str:
    return str(_catalogue(Language.ENGLISH)[key]["text"])


def phrase(key: str, language: Language = Language.ENGLISH) -> str:
    if language is Language.ENGLISH:
        return english(key)
    written = _catalogue(language).get(key)
    if not written or (is_critical(key) and not written.get("reviewed_by")):
        return english(key)
    return str(written["text"])


def missing(language: Language) -> list[Missing]:
    found = []
    for key in keys():
        written = _catalogue(language).get(key)
        if not written:
            found.append(Missing(key, language, english(key), is_critical(key), "not written"))
        elif is_critical(key) and not written.get("reviewed_by"):
            found.append(Missing(key, language, english(key), True, "not reviewed"))
    return found
