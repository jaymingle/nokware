"""Read aloud: a block of prose on the web, spoken, for someone who can't read it. Not a whole-page reader: screen
readers do that better.

It speaks only what the server itself produced, never text a browser sends, so it can't be used as a free
text-to-speech service.

Never about someone's safety: audio can be overheard, and a voice reading out a report about abuse near the abuser
is a real harm.

Gemini's speech model is a preview: it takes almost as long to speak as the audio lasts, and on long text it stalls
and drops the connection. So a reading is made a part at a time, the first short so the first words come within
seconds. Each part is cached so the same words are paid for once.
"""

import base64
import hashlib
import json
import re
import textwrap
from datetime import datetime
from typing import Any

from app.config import get_settings
from app.services.channel_status import headline, spoken_details
from app.services.rag import NO_INFO_ANSWER, SAFETY_FIGURES_ANSWER
from app.services.redis_store import get_redis, key
from app.services.report_rules import suggests_danger_to_a_person
from app.services.voice_audio import Encoded
from app.services.voice_speech import SpeechFailed, cut, speak, speakable

READ_MAX_CHARS = 1800  # about two and a half minutes: Gemini reads about 13 characters a second
FIRST_PART_CHARS = 200  # about 15 seconds of speech, made in about 12
PART_CHARS = 320  # about 25 seconds of prose, made while the part before plays
# A part holds at most this many figures, so a fee table is read a few rows at a time: figures take longer to say
# than words (a 320-character part of a fee table ran 45 seconds), and the break between parts is the listener's
# chance to take in a figure before the next.
PART_FIGURES = 3
CACHE_SECONDS = 6 * 3600
REST_ON_SCREEN = "The rest of the answer is on the screen."
SOURCES_ON_SCREEN = "The documents it comes from are listed with the answer."
NOTHING_FOUND = "The page says where else to look, and how to request a document."
KEEP_REFERENCE = "Keep your reference: it is the only way to follow your report."
_REFERENCE = re.compile(r"\b([A-Z0-9]{4})-([A-Z0-9]{4})\b")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
# Two digits or more (an amount, a count, a year), but not an ordinal: "31st December" is quick to say.
_FIGURE = re.compile(r"(?<![A-Za-z\d])\d[\d,]*\d(?:\.\d+)?(?![\d,]|st\b|nd\b|rd\b|th\b)")


class NotReadAloud(Exception):
    """This content isn't read aloud; the message says why and is safe to show."""

    status_code = 409


class ReadAloudUnavailable(Exception):
    status_code = 503


def may_speak_answer(question: str, answer: str) -> bool:
    return not (suggests_danger_to_a_person(question) or suggests_danger_to_a_person(answer) or SAFETY_FIGURES_ANSWER in answer)


def answer_script(question: str, answer: str, status: str) -> str:
    if not may_speak_answer(question, answer):
        raise NotReadAloud("This answer isn't read aloud: it touches on someone's safety, and audio can be overheard.")
    if status == "no_information":
        return f"{NO_INFO_ANSWER} {NOTHING_FOUND}"
    text, shortened = cut(speakable(answer), READ_MAX_CHARS)
    return " ".join([text, *([REST_ON_SCREEN] if shortened else []), SOURCES_ON_SCREEN])


def _spelled(text: str) -> str:
    """"K 7 Q M, 4 T X P"."""
    return _REFERENCE.sub(lambda m: f"{' '.join(m[1])}, {' '.join(m[2])}", text)


def status_script(status: dict[str, Any], receipt: bool = False) -> str:
    if status["private"]:
        raise NotReadAloud("A report about someone's safety isn't read aloud: audio can be overheard.")
    return _spelled(" ".join([headline(status), *spoken_details(status), *([KEEP_REFERENCE] if receipt else [])]))


def _sentences(script: str) -> list[str]:
    return [piece for sentence in _SENTENCE_END.split(script.strip()) for piece in textwrap.wrap(sentence, PART_CHARS)]


def _figures(text: str) -> int:
    return len(_FIGURE.findall(text))


def parts(script: str) -> list[str]:
    made: list[str] = []
    part = ""
    for sentence in _sentences(script):
        limit = PART_CHARS if made else FIRST_PART_CHARS
        full = len(part) + 1 + len(sentence) > limit or _figures(part) + _figures(sentence) > PART_FIGURES
        if part and full:
            made.append(part)
            part = sentence
        else:
            part = f"{part} {sentence}".lstrip()
    return [*made, part] if part else made


def _cache_key(script: str) -> str:
    return key("speech", hashlib.sha256(f"{get_settings().gemini_tts_voice}:{script}".encode()).hexdigest()[:32])


def _today_allows(now: datetime) -> bool:
    counter = key("speech", "day", now.date().isoformat())
    pipe = get_redis().pipeline()
    pipe.incr(counter)
    pipe.expire(counter, 2 * 86400)
    used, _ = pipe.execute()
    return int(used) <= get_settings().read_aloud_daily_limit


def audio(script: str, now: datetime) -> Encoded:
    cached = get_redis().get(_cache_key(script))
    if cached:
        held = json.loads(cached)
        return Encoded(base64.b64decode(held["data"]), held["type"], held["extension"], held["seconds"])
    if not _today_allows(now):
        raise ReadAloudUnavailable("Reading aloud has reached today's limit. It will be back tomorrow.")
    try:
        spoken = speak(script, for_web=True)
    except SpeechFailed:
        raise ReadAloudUnavailable("The audio couldn't be made just now. Try again in a minute.") from None
    held = {"data": base64.b64encode(spoken.data).decode(), "type": spoken.content_type, "extension": spoken.extension,
            "seconds": spoken.seconds}
    get_redis().set(_cache_key(script), json.dumps(held), ex=CACHE_SECONDS)
    return spoken
