"""What to do right now, for someone reporting a danger to a person: the same steps on every channel.

The wording is the catalogue's (app/data/phrases/en.json, keys safety.steps.*), so there is one copy of it. Each
step is critical text: in another language it shows only once a named person has reviewed it (phrases.py).

Shown after the numbers to call and before any question. Each step is something to do in the moment, not general
advice.
"""

from app.services.phrases import Language, phrase
from app.services.phrases import keys as phrase_keys

KEYS = tuple(key for key in phrase_keys() if key.startswith("safety.steps."))


def steps(language: Language = Language.ENGLISH) -> tuple[str, ...]:
    """English where that language's steps haven't been reviewed."""
    return tuple(phrase(key, language) for key in KEYS)


STEPS = steps()
