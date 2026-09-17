"""An answer read aloud: the words to say, Gemini's speech, and a WhatsApp voice note (or, for the web's
read-aloud button, an MP3) of it.

The spoken reply follows the text answer, which carries the sources, so the
voice gives the gist in about 50 seconds: the answer's own opening, cut at a
sentence, without citation tags, markdown or links, and ending "The sources
are in the message above." Cedi amounts are said as cedis, and whole amounts
without their ".00" (else "thirty point zero zero"). English only.

The speech model is a preview (GEMINI_TTS_MODEL), so it is a setting; it returns
raw 16-bit PCM, which voice_audio makes into OGG/Opus.
"""

import re

import httpx
from google.genai import errors, types

from app.config import get_settings
from app.services.citations import KINDS
from app.services.llm import get_genai_client
from app.services.rag import NO_INFO_ANSWER, RagAnswer
from app.services.voice_audio import AudioRejected, Encoded, for_browser, voice_note, wav

SPOKEN_MAX_CHARS = 620  # with the closing sentence, about 50 seconds: Gemini reads about 13 characters a second
TIMEOUT_MS = 45_000
PCM_RATE = 24_000  # Gemini's speech, unless its MIME type says otherwise
SOURCES_ABOVE = "The sources are in the message above."
NOTHING_FOUND = "The message above says where else to look, and how to request a document."
_TAG = re.compile(rf"\s*\[[{KINDS}]\d+\]")
_LINK = re.compile(r"\(?https?://[^\s)]*[^\s).,;:!?]\)?")  # a link ends before the sentence's own punctuation
_MARKUP = re.compile(r"\*\*|__|^#+\s*|`", re.MULTILINE)
_BULLET = re.compile(r"^\s*(?:[*•-]|\d+\.)\s+(.+?)\s*$", re.MULTILINE)
_CEDIS = re.compile(r"(?:GHS|GH¢|GH₵|₵)\s?(\d[\d,]*(?:\.\d+)?)")
_WHOLE = re.compile(r"(\d)\.00\b")
_RATE = re.compile(r"rate=(\d+)")


class SpeechFailed(RuntimeError):
    """Gemini's speech couldn't be made or encoded."""


class NoSpeech(SpeechFailed):
    """Gemini answered, but with no audio."""


def _cut(text: str, limit: int) -> str:
    """At most limit characters, ending at a sentence."""
    if len(text) <= limit:
        return text
    window = text[:limit]
    end = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
    return window[: end + 1] if end > limit // 3 else window.rsplit(" ", 1)[0] + "."


def speakable(text: str) -> str:
    """Text as it should be said: no citation tags, markdown or links; list items as sentences; cedis as cedis."""
    text = _BULLET.sub(lambda m: m[1] if m[1].endswith((".", "?", "!", ":")) else m[1] + ".", text)
    text = _WHOLE.sub(r"\1", _CEDIS.sub(r"\1 Ghana cedis", _MARKUP.sub("", _LINK.sub("", _TAG.sub("", text)))))
    return re.sub(r"\s+([.,;:!?])", r"\1", " ".join(text.split()))  # no space left where a link stood before its full stop


def cut(text: str, limit: int) -> tuple[str, bool]:
    """At most limit characters, ending at a sentence; and whether anything was left out."""
    shortened = _cut(text, limit)
    return shortened, len(shortened) < len(text)


def spoken_script(answer: RagAnswer) -> str:
    """What the voice note says: the gist of the answer, then a pointer to the text with the sources."""
    if answer["status"] == "no_information":
        return f"{NO_INFO_ANSWER} {NOTHING_FOUND}"
    return f"{_cut(speakable(answer['answer']), SPOKEN_MAX_CHARS)} {SOURCES_ABOVE}"


def _pcm(script: str) -> tuple[bytes, int]:
    settings = get_settings()
    voice = types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=settings.gemini_tts_voice))
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=voice),
        http_options=types.HttpOptions(timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=2)),
    )
    prompt = f'Read this aloud clearly, at an unhurried pace, for a listener in Accra. Say "AMA" as the letters A, M, A.\n\n{script}'
    response = get_genai_client().models.generate_content(model=settings.gemini_tts_model, contents=prompt, config=config)
    content = response.candidates[0].content if response.candidates else None
    blob = content.parts[0].inline_data if content and content.parts else None
    if blob is None or not blob.data:
        raise NoSpeech("Gemini returned no speech.")
    rate = _RATE.search(blob.mime_type or "")
    return blob.data, int(rate[1]) if rate else PCM_RATE


def _speech(script: str) -> tuple[bytes, int]:
    """Gemini's speech, asked once more if the reply has no audio in it: the preview model sometimes sends none,
    and says so at once, so asking again costs a second or two."""
    try:
        return _pcm(script)
    except NoSpeech:
        return _pcm(script)


def speak(script: str, for_web: bool = False) -> Encoded:
    """The script as a WhatsApp voice note, or as an MP3 for a web page. Raises SpeechFailed."""
    try:
        pcm, rate = _speech(script)
        return (for_browser if for_web else voice_note)(wav(pcm, rate))
    except (errors.APIError, httpx.HTTPError, AudioRejected, AttributeError, IndexError, OSError) as error:
        raise SpeechFailed(f"The spoken reply couldn't be made ({type(error).__name__}).") from None
