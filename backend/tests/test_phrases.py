"""Fixed text in three languages, and the rule that keeps an unchecked translation off a screen."""

import json
from pathlib import Path

import pytest

from app.services import phrases
from app.services.phrases import DATA, Language, english, is_critical, keys, missing, phrase, shows_english

CRITICAL = "safety.steps.someone_else"  # a lost negative here tells someone to confront an abuser
ORDINARY = "ask.no_information"


def catalogue(language: Language) -> dict[str, dict[str, object]]:
    return dict(json.loads((DATA / f"{language.value}.json").read_text())["phrases"])


def test_a_language_that_has_written_the_text_shows_it() -> None:
    assert phrase(ORDINARY, Language.FRENCH) == "Je n'ai pas d'information à ce sujet dans le Registre."
    assert phrase(ORDINARY) == english(ORDINARY)


def test_text_someone_acts_on_in_danger_stays_english_until_a_named_person_reviews_it() -> None:
    written = catalogue(Language.FRENCH)[CRITICAL]["text"]
    assert written and written != english(CRITICAL)  # French is drafted…
    assert phrase(CRITICAL, Language.FRENCH) == english(CRITICAL)  # …and still not shown
    assert shows_english(CRITICAL, Language.FRENCH)


def test_a_reviewed_translation_ships(monkeypatch: pytest.MonkeyPatch) -> None:
    reviewed = {**catalogue(Language.FRENCH)}
    reviewed[CRITICAL] = {**reviewed[CRITICAL], "reviewed_by": "A. Mensah", "reviewed_on": "2026-09-20"}
    monkeypatch.setattr(phrases, "_catalogue", lambda language: reviewed if language is Language.FRENCH else catalogue(language))
    assert phrase(CRITICAL, Language.FRENCH) == reviewed[CRITICAL]["text"]
    assert not shows_english(CRITICAL, Language.FRENCH)
    assert phrases.reviewer(CRITICAL, Language.FRENCH) == "A. Mensah"


def test_a_language_with_nothing_written_shows_english_throughout() -> None:
    assert catalogue(Language.TWI) == {}, "Twi waits for a speaker rather than Nokware's guess"
    assert all(phrase(key, Language.TWI) == english(key) for key in keys())
    assert len(missing(Language.TWI)) == len(keys())


@pytest.mark.parametrize("language", [Language.FRENCH, Language.TWI])
def test_what_is_outstanding_is_listed_for_whoever_will_check_it(language: Language) -> None:
    for gap in missing(language):
        assert gap.english and gap.reason in ("not written", "not reviewed")
        assert gap.critical == is_critical(gap.key)
    assert all(gap.reason == "not reviewed" for gap in missing(Language.FRENCH))  # French is drafted, not checked


def test_the_safety_steps_the_channels_show_are_the_catalogue_steps() -> None:
    """One wording, in one place: the steps in app/safety_steps.py are the English the catalogue holds."""
    from app import safety_steps

    written = [english(key) for key in keys() if key.startswith("safety.steps.")]
    assert list(safety_steps.STEPS) == written


def test_every_language_file_is_written_against_the_english_keys() -> None:
    for path in sorted(Path(DATA).glob("*.json")):
        language = Language(path.stem)
        unknown = set(catalogue(language)) - set(keys())
        assert not unknown, f"{path.name} has keys English doesn't: {unknown}"
        assert json.loads(path.read_text())["about"], f"{path.name} must say what it is"
