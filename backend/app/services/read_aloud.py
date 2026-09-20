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
from app.services.phrases import Language, phrase
from app.services.rag import SAFETY_FIGURES_ANSWER
from app.services.redis_store import get_redis, key
from app.services.report_rules import REFERENCE_ALPHABET, suggests_danger_to_a_person
from app.services.voice_audio import Encoded
from app.services.voice_speech import SpeechFailed, cut, speak, speakable

READ_MAX_CHARS = 1800  # about two and a half minutes: Gemini reads about 13 characters a second
# Gemini takes about 0.7 seconds a second of finished audio, so the first words arrive sooner only if the first
# part is shorter — 200 characters cost the listener 11 seconds of silence before anything was said.
FIRST_PART_CHARS = 90  # about 7 seconds of speech, made in about 5
PART_CHARS = 320  # about 25 seconds of prose, made while the part before plays
CLAUSE_MIN = 40  # a first part shorter than this is a fragment, not an opening
FIRST_PART_MAX = 160  # how far into a long first sentence to look for a pause worth splitting at
SPLIT_ABOVE = 150  # below this much speaking, the whole answer is made in about the time one opening would take
# Measured against the TTS model: 20 characters of prose ran 3.3 seconds, 43 characters with one amount 10.8, and
# 200 characters with three amounts 30.4. That is about 0.08 seconds a character and 6 seconds a figure, so a figure
# costs about as much to say as 60 characters of prose.
FIGURE_COST = 60
# A part holds at most this many figures, so a fee table is read a few rows at a time: figures take longer to say
# than words (a 320-character part of a fee table ran 45 seconds), and the break between parts is the listener's
# chance to take in a figure before the next.
PART_FIGURES = 3
FIRST_PART_FIGURES = 1  # figures are slow to say, and the first part is the one the listener waits through
CACHE_SECONDS = 24 * 3600  # a part costs a TTS call to make and about 80 KB to keep; a day of asking is free
REST_ON_SCREEN = phrase("speech.rest_on_screen")
SOURCES_ON_SCREEN = phrase("speech.sources_on_screen")
NOTHING_FOUND = phrase("speech.nothing_found")
# Read aloud only in a language whose fixed lines Nokware has written by hand: the sentences around an answer are
# never machine-translated, so a language the catalogue doesn't hold can't be spoken without inventing them.
SPOKEN_LANGUAGES = (Language.ENGLISH, Language.FRENCH)
NOT_IN_THIS_LANGUAGE = phrase("speech.not_in_this_language")
KEEP_REFERENCE = "Keep your reference: it is the only way to follow your report."
_REFERENCE = re.compile(rf"\b([{REFERENCE_ALPHABET}]{{4}})-([{REFERENCE_ALPHABET}]{{4}})\b")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_CLAUSE = re.compile(r"[,;:] ")
_JOIN = re.compile(r" (and|but|so|which|while|because) ")
# Two digits or more (an amount, a count, a year), but not an ordinal: "31st December" is quick to say.
_FIGURE = re.compile(r"(?<![A-Za-z\d])\d[\d,]*\d(?:\.\d+)?(?![\d,]|st\b|nd\b|rd\b|th\b)")


class NotReadAloud(Exception):
    """This content isn't read aloud; the message says why and is safe to show."""

    status_code = 409


class ReadAloudUnavailable(Exception):
    status_code = 503


def may_speak_answer(question: str, answer: str) -> bool:
    return not (suggests_danger_to_a_person(question) or suggests_danger_to_a_person(answer) or SAFETY_FIGURES_ANSWER in answer)


def may_speak_language(language: str) -> bool:
    return any(language == spoken.value for spoken in SPOKEN_LANGUAGES)


def answer_script(question: str, answer: str, status: str, spoken: str | None = None, language: str = "en") -> str:
    """The English answer is what the safety rule is judged on, whatever language is read aloud: the check reads
    English, and a translation must never be the thing that slips a safety answer past it."""
    if not may_speak_answer(question, answer):
        raise NotReadAloud("This answer isn't read aloud: it touches on someone's safety, and audio can be overheard.")
    if not may_speak_language(language):
        raise NotReadAloud(NOT_IN_THIS_LANGUAGE)
    said = Language(language)
    if status == "no_information":
        return f"{phrase('ask.no_information', said)} {phrase('speech.nothing_found', said)}"
    text, shortened = cut(speakable(spoken or answer), READ_MAX_CHARS)
    rest = [phrase("speech.rest_on_screen", said)] if shortened else []
    return " ".join([text, *rest, phrase("speech.sources_on_screen", said)])


def _spelled(text: str) -> str:
    """"K 7 Q M, 4 T X P"."""
    return _REFERENCE.sub(lambda m: f"{' '.join(m[1])}, {' '.join(m[2])}", text)


def status_script(status: dict[str, Any], receipt: bool = False) -> str:
    if status["private"]:
        raise NotReadAloud("A report about someone's safety isn't read aloud: audio can be overheard.")
    return _spelled(" ".join([headline(status), *spoken_details(status), *([KEEP_REFERENCE] if receipt else [])]))


def _opening(sentence: str) -> list[str]:
    """The first sentence, split where a speaker would pause anyway, so the opening can be spoken while the rest is
    still being made. Only at a comma, semicolon or colon: a seam mid-phrase ("...for Public Works in its" /
    "2026 budget") is worse to listen to than the few seconds it saves, so a sentence with no pause in it is left
    whole."""
    if len(sentence) <= FIRST_PART_CHARS:
        return [sentence]
    window = sentence[:FIRST_PART_MAX]
    pauses = [match.end() for match in _CLAUSE.finditer(window) if match.end() >= CLAUSE_MIN]
    # Figures are read slowly: two amounts take longer to say than a line of prose twice their length. Where the
    # only comma comes after both, the conjunction between them is the pause a speaker would use anyway.
    if not any(_figures(sentence[:at]) <= FIRST_PART_FIGURES for at in pauses):
        pauses += [match.start() for match in _JOIN.finditer(window) if match.start() >= CLAUSE_MIN]
    within = [at for at in pauses if _figures(sentence[:at]) <= FIRST_PART_FIGURES] or pauses
    if not within:
        return [sentence]
    at = min(within, key=lambda end: abs(end - FIRST_PART_CHARS))
    return [sentence[:at].strip(), sentence[at:].strip()]


def _sentences(script: str) -> list[str]:
    pieces = [piece for sentence in _SENTENCE_END.split(script.strip()) for piece in textwrap.wrap(sentence, PART_CHARS)]
    if not pieces or _speaking_cost(script) <= SPLIT_ABOVE:  # a short answer is made in one call: a seam buys nothing
        return pieces
    return [*_opening(pieces[0]), *pieces[1:]]


def _figures(text: str) -> int:
    return len(_FIGURE.findall(text))


def _speaking_cost(text: str) -> int:
    """How long this takes to say, in characters of prose. Length alone misleads: three amounts in 196 characters
    run to half a minute of audio, and the wait is set by the audio, not the text."""
    return len(text) + _figures(text) * FIGURE_COST


def parts(script: str) -> list[str]:
    script = script.strip()
    # A short answer with few figures is made in one call: splitting it would cost a second request and a seam to
    # save a second or two of waiting.
    if script and _speaking_cost(script) <= SPLIT_ABOVE and _figures(script) <= PART_FIGURES:
        return [script]
    made: list[str] = []
    part = ""
    for sentence in _sentences(script):
        limit = PART_CHARS if made else FIRST_PART_CHARS
        allowed = PART_FIGURES if made else FIRST_PART_FIGURES
        measure = len if made else _speaking_cost  # the first part is the one the listener waits through
        full = measure(f"{part} {sentence}") > limit or _figures(part) + _figures(sentence) > allowed
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
