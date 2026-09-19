"""The four grounds a petition can be removed on, written once.

A removal and a reader's report of a petition stand on the same four grounds, and a reader must find the same words
wherever they meet them: the removal form a contributor uses, the tombstone left behind, the report form on a
petition's page, USSD and WhatsApp. So the grounds live here, and their words live in the phrase catalogue beside
the rest of Nokware's fixed text; nothing else in the code writes them out again.

Nobody is refused a ground for being wrong about it. A report is a reader's opinion, kept as given; only a
contributor's removal acts, and only on a ground named here.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.services.phrases import Language, phrase


class Ground(StrEnum):
    PRIVATE_INDIVIDUAL = "private_individual"  # names or attacks a private person
    INCITES_VIOLENCE = "incites_violence"
    PERSONAL_DATA = "personal_data"
    DUPLICATE = "duplicate"  # another open petition already asks for this


class Dismissal(StrEnum):
    """Why a contributor leaves a reported petition standing. Two fixed reasons: a dismissal explains the decision,
    it doesn't invite an argument with whoever reported it, who never reads it."""

    NOT_THE_GROUND = "not_the_ground"
    ALREADY_HANDLED = "already_handled"


@dataclass(frozen=True)
class GroundRule:
    key: Ground
    phrase_key: str
    names_another_petition: bool  # a duplicate is the only ground that can't be judged without the other petition


GROUNDS: dict[Ground, GroundRule] = {
    Ground.PRIVATE_INDIVIDUAL: GroundRule(Ground.PRIVATE_INDIVIDUAL, "petition.ground.private_individual", False),
    Ground.INCITES_VIOLENCE: GroundRule(Ground.INCITES_VIOLENCE, "petition.ground.incites_violence", False),
    Ground.PERSONAL_DATA: GroundRule(Ground.PERSONAL_DATA, "petition.ground.personal_data", False),
    Ground.DUPLICATE: GroundRule(Ground.DUPLICATE, "petition.ground.duplicate", True),
}
DISMISSALS: dict[Dismissal, str] = {
    Dismissal.NOT_THE_GROUND: "petition.dismissal.not_the_ground",
    Dismissal.ALREADY_HANDLED: "petition.dismissal.already_handled",
}


def in_plain_words(ground: Ground, language: Language = Language.ENGLISH) -> str:
    return phrase(GROUNDS[ground].phrase_key, language)


def dismissal_in_plain_words(reason: Dismissal, language: Language = Language.ENGLISH) -> str:
    return phrase(DISMISSALS[reason], language)


def needs_another_petition(ground: Ground) -> bool:
    return GROUNDS[ground].names_another_petition
