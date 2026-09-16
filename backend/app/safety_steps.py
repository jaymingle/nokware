"""What to do right now, for someone reporting a danger to a person: the same steps on every channel.

The wording is the catalogue's (app/data/phrases/en.json, keys safety.steps.*), so there is one copy of it. Each
step is critical text: in another language it shows only once a named person has reviewed it (phrases.py).

Shown after the numbers to call and before any question: on the web safety
form, in the first WhatsApp reply after the report is described, and on two
USSD screens. Each step is something to do in the moment, not general advice.
DOVVSU, the Police's Domestic Violence and Victim Support Unit, is in the
contacts data with the helpline the Police publish (police.gov.gh), so the
numbers above the steps carry it.
"""

from app.services.phrases import Language, phrase
from app.services.phrases import keys as phrase_keys

KEYS = tuple(key for key in phrase_keys() if key.startswith("safety.steps."))


def steps(language: Language = Language.ENGLISH) -> tuple[str, ...]:
    """The steps in the reader's language, or in English where that language's steps haven't been reviewed."""
    return tuple(phrase(key, language) for key in KEYS)


STEPS = steps()
