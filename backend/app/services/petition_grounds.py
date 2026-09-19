"""The four grounds a petition or a comment can be removed on, written once.

A removal and a reader's report stand on the same four grounds, and a reader must find the same words wherever
they meet them: the removal form a contributor uses, the tombstone left behind, the report form on a petition's
page, USSD and WhatsApp. So the grounds live here, and their words live in the phrase catalogue beside the rest
of Nokware's fixed text; nothing else in the code writes them out again.

The keys are the same for a petition and for a comment; the words are not always. A comment duplicates no
petition — it repeats another comment on the page it stands on — so a ground can carry a second phrase key for
when it is read about a comment, and Subject picks between them. Where a ground carries none, both read alike.

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
    DUPLICATE = "duplicate"  # another open petition already asks for this; another comment already says it


class Subject(StrEnum):
    """What a ground is being read about. It chooses the wording, never the stored value."""

    PETITION = "petition"
    COMMENT = "comment"


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
    comment_phrase_key: str | None = None  # set only where a comment's words differ from a petition's

    def words_key(self, subject: Subject) -> str:
        return self.comment_phrase_key if subject is Subject.COMMENT and self.comment_phrase_key else self.phrase_key


GROUNDS: dict[Ground, GroundRule] = {
    Ground.PRIVATE_INDIVIDUAL: GroundRule(Ground.PRIVATE_INDIVIDUAL, "petition.ground.private_individual", False),
    Ground.INCITES_VIOLENCE: GroundRule(Ground.INCITES_VIOLENCE, "petition.ground.incites_violence", False),
    Ground.PERSONAL_DATA: GroundRule(Ground.PERSONAL_DATA, "petition.ground.personal_data", False),
    Ground.DUPLICATE: GroundRule(Ground.DUPLICATE, "petition.ground.duplicate", True,
                                 comment_phrase_key="petition.ground.duplicate_comment"),
}
DISMISSALS: dict[Dismissal, str] = {
    Dismissal.NOT_THE_GROUND: "petition.dismissal.not_the_ground",
    Dismissal.ALREADY_HANDLED: "petition.dismissal.already_handled",
}


def in_plain_words(ground: Ground, language: Language = Language.ENGLISH,
                   subject: Subject = Subject.PETITION) -> str:
    return phrase(GROUNDS[ground].words_key(subject), language)


def dismissal_in_plain_words(reason: Dismissal, language: Language = Language.ENGLISH) -> str:
    return phrase(DISMISSALS[reason], language)


def needs_another_petition(ground: Ground, subject: Subject = Subject.PETITION) -> bool:
    """Only a petition's duplicate names one. A comment's repeats another comment on the page it already stands
    on, so there is no number to ask for and none is stored."""
    return GROUNDS[ground].names_another_petition and subject is Subject.PETITION
