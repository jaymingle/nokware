"""Voice notes on WhatsApp: heard, handled as if typed, and a question answered aloud as well as in text.

In: the note is fetched from Twilio once and deleted there at once; it is never
stored. It may be up to 3 minutes long, 10 an hour per number. A transcript with
more words than anyone could say in the note's length is taken as unheard: on a
very short note, Gemini can invent a whole sentence. Gemini's English
for it is handled exactly like a typed message, through every step of the chat;
a lone spoken choice ("one", "yes", "remove") or a spelled-out reference is read
as its typed form, so someone who can't type can use every menu.

Out: only an answer to a question is spoken, after the text answer that carries
the sources, and only in English. Never a report, a status, a safety or medical
reply, and never anything about harm to a person, by Gemini's reading or by the
report rules' danger words: a voice note about abuse could play aloud near the
abuser. Each spoken reply is an extra WhatsApp message, so there are 10 a day per
number and VOICE_DAILY_LIMIT across everyone; past either, the text answer stands.

Twilio fetches the voice note from the API's public address, at a random link
held in Redis for 10 minutes and deleted as soon as Twilio reports on the message.
"""

import base64
import logging
import re
import secrets
from datetime import datetime

import redis

from app.config import get_settings
from app.services import channel_limits, voice_speech, whatsapp_reply
from app.services.ask_figures import SAFETY_FIGURES_ANSWER
from app.services.ledger_documents import utc_now
from app.services.rag import RagAnswer
from app.services.redis_store import RedisUnavailable, get_redis, key
from app.services.report_contacts import masked
from app.services.report_rules import suggests_danger_to_a_person
from app.services.voice_audio import AudioRejected, Encoded, seconds
from app.services.voice_transcribe import Heard, TranscriptionFailed, transcribe
from app.services.whatsapp import WhatsAppError, WhatsAppNotConfigured, twilio

logger = logging.getLogger(__name__)

VOICE_MAX_SECONDS = 180
WORDS_PER_SECOND = 4  # brisk speech is about 3; more than this, and the words weren't all said
HOLD_SECONDS = 10 * 60
AUDIO_PATH = "/api/channels/whatsapp/audio"
AUDIO_TYPES = {"ogg": "audio/ogg", "mp3": "audio/mpeg"}
FINAL_STATUSES = frozenset({"sent", "delivered", "read", "failed", "undelivered"})  # Twilio has fetched the file by then
TOO_MANY = "You've sent a lot of voice notes this hour. Please type your message, or try again later."
TOO_LONG = "Voice notes can be up to 3 minutes. Please send a shorter one, or type your message."
NOT_HEARD = "I couldn't make out that voice note. Please try again somewhere quieter, or type your message."
FAILED = "That voice note couldn't be read just now. Please try again, or type your message."
NUMBER_WORDS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
                "seven": "7", "eight": "8", "nine": "9"}
FILLER = frozenset({"number", "option", "choice", "reply", "please", "the", "it", "is", "its", "dash"})
COMMANDS = frozenset({"yes", "no", "cancel", "call", "place", "remove"})
_NAME = re.compile(r"^([A-Za-z0-9_-]{32,64})\.(ogg|mp3)$")


def is_voice(content_type: str) -> bool:
    return content_type.lower().startswith("audio/")


def _fetch(url: str) -> tuple[bytes, str]:
    """The voice note from Twilio, deleted there at once. Raises WhatsAppError or WhatsAppNotConfigured."""
    client = twilio()
    data, content_type = client.download(url)
    client.delete_media(url)
    return data, content_type


def _listen(url: str, content_type: str) -> Heard | str:
    """What the voice note says, or what to tell the citizen if it can't be used."""
    try:
        data, fetched_type = _fetch(url)
        length = seconds(data)
        if length > VOICE_MAX_SECONDS:
            return TOO_LONG
        heard = transcribe(data, content_type or fetched_type)
    except (WhatsAppError, WhatsAppNotConfigured, AudioRejected, TranscriptionFailed, OSError):
        logger.exception("A WhatsApp voice note couldn't be read")
        return FAILED
    sayable = len(heard.heard.split()) <= WORDS_PER_SECOND * length + 3
    return heard if heard.clear and heard.english and sayable else NOT_HEARD


def hear(number: str, url: str, content_type: str) -> Heard | None:
    """A voice note's words; None once the citizen has been told why it can't be used."""
    if not channel_limits.VOICE_NOTES.allow(number, utc_now().timestamp()):
        whatsapp_reply.reply(number, TOO_MANY)
        return None
    heard = _listen(url, content_type)
    if isinstance(heard, str):
        whatsapp_reply.reply(number, heard)
        return None
    return heard


def _spelled_reference(words: list[str]) -> str | None:
    """A reference said letter by letter ("X Y H N six A five T") as XYHN-6A5T."""
    characters = [NUMBER_WORDS.get(word, word) for word in words]
    if len(characters) == 8 and all(len(c) == 1 and c.isalnum() for c in characters):
        joined = "".join(characters).upper()
        return f"{joined[:4]}-{joined[4:]}"
    return None


def as_typed(text: str) -> str:
    """What the citizen would have typed: a lone choice as "1" or "yes", a spelled reference as K7QM-4TXP."""
    words = [word for word in re.sub(r"[^\w\s]", " ", text.lower()).split() if word not in FILLER]
    if len(words) == 1 and (words[0] in NUMBER_WORDS or words[0].isdigit() or words[0] in COMMANDS):
        return NUMBER_WORDS.get(words[0], words[0])
    return _spelled_reference(words) or text.strip()


def understood(english: str, language: str) -> str:
    """How a voice note's words are shown back, so the citizen can catch a mistake."""
    translated = "" if language.strip().lower() == "english" else f" (from {language}, translated by machine)"
    return f'I understood: "{english}"{translated}'


def _today_allows(now: datetime) -> bool:
    counter = key("spoken-today", now.date().isoformat())
    pipe = get_redis().pipeline()
    pipe.incr(counter)
    pipe.expire(counter, 2 * 86400)
    used, _ = pipe.execute()
    return int(used) <= get_settings().voice_daily_limit


def _may_speak(number: str, heard: Heard, answer: RagAnswer) -> bool:
    """Only an answer that is safe to play aloud, within the limits, with a public address for Twilio to fetch."""
    if not get_settings().public_api_url:
        return False
    if heard.about_harm or suggests_danger_to_a_person(heard.english) or suggests_danger_to_a_person(answer["answer"]):
        return False
    if SAFETY_FIGURES_ANSWER in answer["answer"]:
        return False
    now = utc_now()
    return channel_limits.SPOKEN_REPLIES.allow(number, now.timestamp()) and _today_allows(now)


def _hold(note: Encoded) -> tuple[str, str]:
    """Keep the voice note for Twilio to fetch; its token and public link."""
    token = secrets.token_urlsafe(32)
    get_redis().set(key("wa-audio", token), f"{note.extension}:{base64.b64encode(note.data).decode()}", ex=HOLD_SECONDS)
    return token, f"{get_settings().public_api_url.rstrip('/')}{AUDIO_PATH}/{token}.{note.extension}"


def speak_answer(number: str, answer: RagAnswer, heard: Heard) -> None:
    """After the text answer, the same answer aloud, when that is safe and allowed. A failure leaves the text."""
    try:
        if not _may_speak(number, heard, answer):
            return
        note = voice_speech.speak(voice_speech.spoken_script(answer))
        token, url = _hold(note)
        sid = whatsapp_reply.reply_audio(number, url, f"{note.seconds:.0f} s, {len(note.data) // 1024} KB {note.content_type}")
        if sid:
            get_redis().set(key("wa-audio-sid", sid), token, ex=HOLD_SECONDS)
    except (voice_speech.SpeechFailed, redis.RedisError, RedisUnavailable):
        logger.warning("No spoken reply for %s: it couldn't be made", masked(number), exc_info=True)


def held(name: str) -> tuple[bytes, str] | None:
    """A held voice note by its link's last part ("<token>.ogg"), with its content type."""
    match = _NAME.match(name)
    stored = get_redis().get(key("wa-audio", match[1])) if match else None
    if not match or not stored:
        return None
    extension, _, data = str(stored).partition(":")
    return (base64.b64decode(data), AUDIO_TYPES[extension]) if extension == match[2] else None


def release(message_sid: str, status: str) -> None:
    """Twilio has reported on a voice note it sent, so it has the file: delete the held copy."""
    if status not in FINAL_STATUSES:
        return
    try:
        token = get_redis().getdel(key("wa-audio-sid", message_sid))
        if token:
            get_redis().delete(key("wa-audio", str(token)))
    except (redis.RedisError, RedisUnavailable):
        logger.warning("Couldn't delete a held voice note", exc_info=True)
