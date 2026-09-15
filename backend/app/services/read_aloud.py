"""Read aloud: a block of prose on the web, spoken, for someone who can't read it.

Three places only, where the content is prose someone needs to understand and
not being able to read it locks them out: an Ask answer, a report's
confirmation and a report's status page. Not a whole-page reader: screen
readers do that better.

It speaks only what the server itself produced, never text a browser sends:
an Ask answer comes back as its signed export view (the same signature exports
use), and a report is looked up by its reference. So it can't be used as a free
text-to-speech service.

Never about someone's safety, the same rule as WhatsApp's spoken replies: audio
can be overheard, and a voice reading out a report about abuse near the abuser
is a real harm. So no personal-safety report is read aloud, nor an Ask answer
whose question or answer carries words of danger to a person, nor the fixed
refusal of personal-safety figures.

Gemini's speech (the WhatsApp voice pipeline) as MP3, in parts that end at
sentences. Gemini's speech model is a preview: it takes almost as long to speak
as the audio lasts, and on long text it stalls and drops the connection. So a
reading is made a part at a time, the first short so the first words come
within seconds, and the page fetches each next part while the one before plays.
The same words give the same audio, so each part is kept in Redis for six hours
and paid for once; a daily cap on fresh parts (READ_ALOUD_DAILY_LIMIT) bounds
what speech can cost.
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
PART_CHARS = 320  # about 25 seconds, made while the part before plays
CACHE_SECONDS = 6 * 3600
REST_ON_SCREEN = "The rest of the answer is on the screen."
SOURCES_ON_SCREEN = "The documents it comes from are listed with the answer."
NOTHING_FOUND = "The page says where else to look, and how to request a document."
KEEP_REFERENCE = "Keep your reference: it is the only way to follow your report."
_REFERENCE = re.compile(r"\b([A-Z0-9]{4})-([A-Z0-9]{4})\b")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class NotReadAloud(Exception):
    """This content isn't read aloud; the message says why and is safe to show."""

    status_code = 409


class ReadAloudUnavailable(Exception):
    status_code = 503


def may_speak_answer(question: str, answer: str) -> bool:
    """Whether an Ask answer can be read aloud: nothing about someone's safety, in the question or the answer."""
    return not (suggests_danger_to_a_person(question) or suggests_danger_to_a_person(answer) or SAFETY_FIGURES_ANSWER in answer)


def answer_script(question: str, answer: str, status: str) -> str:
    if not may_speak_answer(question, answer):
        raise NotReadAloud("This answer isn't read aloud: it touches on someone's safety, and audio can be overheard.")
    if status == "no_information":
        return f"{NO_INFO_ANSWER} {NOTHING_FOUND}"
    text, shortened = cut(speakable(answer), READ_MAX_CHARS)
    return " ".join([text, *([REST_ON_SCREEN] if shortened else []), SOURCES_ON_SCREEN])


def _spelled(text: str) -> str:
    """A reference said character by character, in its two halves: "K 7 Q M, 4 T X P"."""
    return _REFERENCE.sub(lambda m: f"{' '.join(m[1])}, {' '.join(m[2])}", text)


def status_script(status: dict[str, Any], receipt: bool = False) -> str:
    """A report's status as its page shows it; on the confirmation, with the reminder to keep the reference.
    Never a personal-safety report's."""
    if status["private"]:
        raise NotReadAloud("A report about someone's safety isn't read aloud: audio can be overheard.")
    return _spelled(" ".join([headline(status), *spoken_details(status), *([KEEP_REFERENCE] if receipt else [])]))


def _sentences(script: str) -> list[str]:
    """The script's sentences, any too long for a part split between words."""
    return [piece for sentence in _SENTENCE_END.split(script.strip()) for piece in textwrap.wrap(sentence, PART_CHARS)]


def parts(script: str) -> list[str]:
    """The script in parts that end at sentences, each spoken on its own: the first short, so the words start soon."""
    made: list[str] = []
    part = ""
    for sentence in _sentences(script):
        limit = PART_CHARS if made else FIRST_PART_CHARS
        if part and len(part) + 1 + len(sentence) > limit:
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
    """The script spoken, as MP3: from the six-hour cache, or made now within the day's limit."""
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
