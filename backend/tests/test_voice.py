"""Voice on WhatsApp: a voice note heard and handled as typed, shown back, and only a question's answer spoken."""

import array
import io
import logging
import math
import wave
from typing import Any
from urllib.parse import parse_qsl

import av
import fakeredis
import httpx
import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.main import RedactChannelSecrets, app
from app.routes import channels
from app.services import (
    channel_limits,
    channel_sessions,
    notifications,
    redis_store,
    report_intake,
    voice_audio,
    voice_speech,
    voice_transcribe,
    whatsapp,
    whatsapp_conversation,
    whatsapp_reply,
    whatsapp_voice,
)
from app.services.channel_intent import Intent, Reading
from app.services.rag import RagAnswer
from app.services.report_intake import Receipt, ReportSubmission
from app.services.report_rules import Classification, ClassificationMethod
from app.services.report_taxonomy import TOPICS_BY_ID, Category
from app.services.voice_audio import Encoded
from app.services.voice_transcribe import Heard
from app.services.whatsapp import TwilioWhatsApp
from app.services.whatsapp_conversation import Inbound, Media

NUMBER = "+233507387216"
TOKEN = "twilio-auth-token"
PUBLIC = "https://nokware.example.org"
VOICE = Media("https://api.twilio.com/2010-04-01/Accounts/AC1/Messages/MM1/Media/ME1", "audio/ogg")
QUESTION = Heard("How much is a market stall at Kaneshie?", "How much is a market stall at Kaneshie?", "English", True, False)
ANSWER: RagAnswer = {"answer": "A stall at Kaneshie costs **GHS 50** a month [S1].", "status": "answered",
                     "sources": [], "figures": [], "search_queries": []}
NOTE = Encoded(b"OggS-spoken-reply", "audio/ogg", "ogg", 9.0)
CIVIC = {"$id": "c1", "reference": "K7QM-4TXP", "category": "civic_service", "topic": "drainage", "isSensitive": False,
         "recipients": ["dept-works"]}
SAFETY = {"$id": "c2", "reference": "M3RD-8WQA", "category": "personal_safety", "topic": "abuse", "isSensitive": True,
          "recipients": ["agency-police", "dept-social-welfare"]}


def _pcm(seconds: float, rate: int = 24_000) -> bytes:
    """A tone, as the 16-bit mono PCM Gemini's speech returns."""
    samples = array.array("h", (int(8000 * math.sin(2 * math.pi * 440 * n / rate)) for n in range(int(seconds * rate))))
    return samples.tobytes()


# Audio: PyAV encodes OGG/Opus, or MP3 when Opus can't be made.

def test_speech_becomes_an_ogg_opus_voice_note_of_the_same_length() -> None:
    note = voice_audio.voice_note(voice_audio.wav(_pcm(2.0), 24_000))
    assert note.data.startswith(b"OggS") and (note.content_type, note.extension) == ("audio/ogg", "ogg")
    with av.open(io.BytesIO(note.data)) as container:
        assert container.streams.audio[0].codec_context.name == "opus"
    assert 1.9 < note.seconds < 2.2 and 1.9 < voice_audio.seconds(note.data) < 2.2


def test_mp3_stands_in_when_opus_cannot_be_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = ("ogg", "no-such-codec", 24_000, "audio/ogg", "ogg")
    monkeypatch.setattr(voice_audio, "FORMATS", (broken, voice_audio.FORMATS[1]))
    note = voice_audio.voice_note(voice_audio.wav(_pcm(1.0), 24_000))
    assert (note.content_type, note.extension) == ("audio/mpeg", "mp3") and 0.9 < note.seconds < 1.3


def test_a_file_that_is_not_audio_is_rejected() -> None:
    with pytest.raises(voice_audio.AudioRejected):
        voice_audio.seconds(b"%PDF-1.7 not a voice note")


# What is said aloud, and Gemini's speech.

def test_the_spoken_script_is_the_gist_without_tags_markup_or_links_and_points_to_the_sources() -> None:
    answer: RagAnswer = {**ANSWER, "answer": "## Fees\n* A stall costs **GHS 1,200** a year [S1]\n- Pay at the sub-metro [S2]\n"
                                             "See https://ama.gov.gh/fees for more [R1]."}
    script = voice_speech.spoken_script(answer)
    assert script == ("Fees A stall costs 1,200 Ghana cedis a year. Pay at the sub-metro. See for more. "
                      "The sources are in the message above.")
    long = voice_speech.spoken_script({**ANSWER, "answer": "This is one sentence of the answer. " * 60})
    assert len(long) < voice_speech.SPOKEN_MAX_CHARS + 60 and long.endswith("sentence of the answer. The sources are in the message above.")
    assert voice_speech.spoken_script({**ANSWER, "status": "no_information"}).startswith("I don't have information")


class _Genai:
    """Gemini's client, stubbed: one canned response (or error) for generate_content, recording what was asked."""

    def __init__(self, response: Any) -> None:
        self.response, self.asked = response, []
        self.models = self

    def generate_content(self, **kwargs: Any) -> Any:
        self.asked.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _speech_response(pcm: bytes) -> Any:
    blob = type("Blob", (), {"data": pcm, "mime_type": "audio/L16;codec=pcm;rate=24000"})
    part = type("Part", (), {"inline_data": blob})
    return type("Response", (), {"candidates": [type("Candidate", (), {"content": type("Content", (), {"parts": [part]})})]})


def test_gemini_speech_is_made_a_voice_note_and_a_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Genai(_speech_response(_pcm(1.5)))
    monkeypatch.setattr(voice_speech, "get_genai_client", lambda: client)
    note = voice_speech.speak("A stall costs 50 Ghana cedis.")
    assert note.data.startswith(b"OggS") and 1.4 < note.seconds < 1.7
    assert client.asked[0]["model"] == get_settings().gemini_tts_model and "50 Ghana cedis" in client.asked[0]["contents"]
    monkeypatch.setattr(voice_speech, "get_genai_client", lambda: _Genai(httpx.ConnectTimeout("slow")))
    with pytest.raises(voice_speech.SpeechFailed):
        voice_speech.speak("Hello")


# Transcription: Gemini listens, told the place names and how references are spelled.

def test_a_voice_note_is_transcribed_with_the_place_names_and_a_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = voice_transcribe._Transcript(heard="Me ho yɛ", english="I am fine", language="Twi", clear=True, about_harm=False)
    client = _Genai(type("Response", (), {"parsed": parsed, "text": ""}))
    monkeypatch.setattr(voice_transcribe, "get_genai_client", lambda: client)
    heard = voice_transcribe.transcribe(b"OggS...", "audio/ogg; codecs=opus")
    assert heard == Heard("Me ho yɛ", "I am fine", "Twi", True, False) and not heard.in_english
    audio, prompt = client.asked[0]["contents"]
    assert audio.inline_data.mime_type == "audio/ogg" and "Kaneshie" in prompt and "K7QM-4TXP" in prompt
    assert client.asked[0]["config"].temperature == 0.0
    monkeypatch.setattr(voice_transcribe, "get_genai_client", lambda: _Genai(httpx.ReadTimeout("slow")))
    with pytest.raises(voice_transcribe.TranscriptionFailed):
        voice_transcribe.transcribe(b"OggS...", "audio/ogg")


def test_a_format_gemini_cannot_read_is_re_encoded_first(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = voice_transcribe._Transcript(heard="Hello", english="Hello", language="English", clear=True, about_harm=False)
    client = _Genai(type("Response", (), {"parsed": parsed, "text": ""}))
    monkeypatch.setattr(voice_transcribe, "get_genai_client", lambda: client)
    voice_transcribe.transcribe(voice_audio.wav(_pcm(1.0), 16_000), "audio/amr")
    assert client.asked[0]["contents"][0].inline_data.mime_type == "audio/ogg"


# A spoken choice or reference reads as its typed form.

@pytest.mark.parametrize(("said", "typed"), [
    ("One.", "1"), ("Number two, please", "2"), ("zero", "0"), ("Yes please.", "yes"), ("Remove.", "remove"),
    ("X Y H N six A five T", "XYHN-6A5T"), ("The drain at Kaneshie is blocked.", "The drain at Kaneshie is blocked."),
])
def test_a_spoken_choice_or_reference_reads_as_typed(said: str, typed: str) -> None:
    assert whatsapp_voice.as_typed(said) == typed


# The conversation, with Redis faked and Twilio, Gemini and the replies stubbed.

@pytest.fixture
def redis_server(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    server = fakeredis.FakeRedis(decode_responses=True)
    for module in (redis_store, channel_sessions, channel_limits, whatsapp, whatsapp_conversation, whatsapp_voice):
        monkeypatch.setattr(module, "get_redis", lambda: server)
    return server


def _settings(monkeypatch: pytest.MonkeyPatch, **update: Any) -> None:
    settings = get_settings().model_copy(update={"twilio_auth_token": TOKEN, "public_api_url": PUBLIC, **update})
    for module in (whatsapp, whatsapp_voice, notifications, channels):
        monkeypatch.setattr(module, "get_settings", lambda: settings)


class _Twilio:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def download(self, url: str) -> tuple[bytes, str]:
        return b"OggS-voice-note", "audio/ogg"

    def delete_media(self, url: str) -> None:
        self.deleted.append(url)


@pytest.fixture
def phone(monkeypatch: pytest.MonkeyPatch, redis_server: fakeredis.FakeRedis) -> dict[str, Any]:
    """What the citizen sees: text replies, voice notes sent, files deleted from Twilio; and what is heard."""
    seen: dict[str, Any] = {"text": [], "audio": [], "twilio": _Twilio(), "heard": QUESTION, "spoken": []}
    _settings(monkeypatch)
    monkeypatch.setattr(whatsapp_reply, "reply", lambda number, text: seen["text"].append(text))
    monkeypatch.setattr(whatsapp_reply, "reply_audio", lambda number, url, about: seen["audio"].append(url) or "MMspoken")
    monkeypatch.setattr(whatsapp_voice, "twilio", lambda: seen["twilio"])
    monkeypatch.setattr(whatsapp_voice, "seconds", lambda data: 12.0)
    monkeypatch.setattr(whatsapp_voice, "transcribe", lambda data, content_type: seen["heard"])
    monkeypatch.setattr(whatsapp_voice.voice_speech, "speak", lambda script: seen["spoken"].append(script) or NOTE)
    monkeypatch.setattr(whatsapp_conversation, "answer_question", lambda question, length: ANSWER)
    return seen


def speak_note(sid: list[int] = [0]) -> None:  # noqa: B006
    sid[0] += 1
    whatsapp_conversation.handle(Inbound(NUMBER, "", VOICE, f"SMvoice-{sid[0]}"))


def say(text: str, sid: list[int] = [0]) -> None:  # noqa: B006
    sid[0] += 1
    whatsapp_conversation.handle(Inbound(NUMBER, text, None, f"SMtext-{sid[0]}"))


def _reads(monkeypatch: pytest.MonkeyPatch, intent: str) -> None:
    monkeypatch.setattr(whatsapp_conversation, "read_message", lambda text, has_photo=False: Reading(Intent(intent)))


def test_a_voice_question_is_shown_back_answered_in_text_and_then_aloud(monkeypatch: pytest.MonkeyPatch, phone: dict[str, Any]) -> None:
    _reads(monkeypatch, "question")
    speak_note()
    assert phone["twilio"].deleted == [VOICE.url]  # the voice note leaves Twilio at once
    assert phone["text"][0].startswith('I understood: "How much is a market stall at Kaneshie?"\n\nA stall at Kaneshie costs *GHS 50*')
    assert phone["spoken"] == ["A stall at Kaneshie costs 50 Ghana cedis a month. The sources are in the message above."]
    assert len(phone["audio"]) == 1 and phone["audio"][0].startswith(f"{PUBLIC}/api/channels/whatsapp/audio/")


def test_twilio_fetches_the_spoken_reply_once_and_it_is_deleted_when_twilio_reports(monkeypatch: pytest.MonkeyPatch, phone: dict[str, Any]) -> None:
    _reads(monkeypatch, "question")
    speak_note()
    path = phone["audio"][0].removeprefix(PUBLIC)
    client = TestClient(app)
    fetched = client.get(path)
    assert fetched.status_code == 200 and fetched.content == NOTE.data and fetched.headers["content-type"] == "audio/ogg"
    assert client.get(path.replace(".ogg", ".mp3")).status_code == 404 and client.get(f"{path[:-12]}x.ogg").status_code == 404
    monkeypatch.setattr(notifications, "record_delivery", lambda sid, status, now: True)
    form = {"MessageSid": "MMspoken", "MessageStatus": "sent"}
    signature = RequestValidator(TOKEN).compute_signature(f"{PUBLIC}/api/channels/whatsapp/status", form)
    client.post("/api/channels/whatsapp/status", data=form, headers={"X-Twilio-Signature": signature})
    assert client.get(path).status_code == 404


def test_a_question_in_another_language_is_shown_back_translated_and_answered_in_english(monkeypatch: pytest.MonkeyPatch, phone: dict[str, Any]) -> None:
    _reads(monkeypatch, "question")
    phone["heard"] = Heard("Ɛyɛ sɛn na wɔtɔn dwam wɔ Kaneshie?", "How much is a market stall at Kaneshie?", "Twi", True, False)
    speak_note()
    assert phone["text"][0].startswith('I understood: "How much is a market stall at Kaneshie?" (from Twi, translated by machine)')
    assert phone["spoken"] and phone["spoken"][0].startswith("A stall at Kaneshie")


@pytest.mark.parametrize("heard", [
    Heard("Where do I report that my husband beats me?", "Where do I report that my husband beats me?", "English", True, True),
    Heard("Who handles it when a man threatens a neighbour?", "Who handles it when a man threatens a neighbour?", "English", True, True),
    Heard("My uncle hits me, who can help?", "My uncle hits me, who can help?", "English", True, False),  # the danger words
])
def test_nothing_about_harm_to_a_person_is_ever_spoken(monkeypatch: pytest.MonkeyPatch, phone: dict[str, Any], heard: Heard) -> None:
    _reads(monkeypatch, "question")
    phone["heard"] = heard
    speak_note()
    assert phone["text"] and phone["audio"] == [] and phone["spoken"] == []


def _classified(topic: str) -> Classification:
    found = TOPICS_BY_ID[topic]
    return Classification(found.category, topic, 5 if found.category == Category.PERSONAL_SAFETY else 3, found.recipients, ClassificationMethod.AI)


def _filing(monkeypatch: pytest.MonkeyPatch, case: dict[str, Any], topic: str) -> list[ReportSubmission]:
    filed: list[ReportSubmission] = []
    monkeypatch.setattr(report_intake, "read_report", lambda description: _classified(topic))

    def submit(submission: ReportSubmission, photos: list[bytes], now: Any, classification: Classification | None = None) -> Receipt:
        filed.append(submission)
        return Receipt(case=case, messages_on=True, held_for_consent=False, preferences_token=None)

    monkeypatch.setattr(report_intake, "submit", submit)
    monkeypatch.setattr(whatsapp_conversation.whatsapp_safety, "after_filing", lambda number, receipt: None)
    return filed


def test_a_voice_report_is_shown_back_before_it_is_filed_and_a_spoken_one_files_it(monkeypatch: pytest.MonkeyPatch, phone: dict[str, Any]) -> None:
    _reads(monkeypatch, "report")
    filed = _filing(monkeypatch, CIVIC, "drainage")
    phone["heard"] = Heard("Gutter no a ɛwɔ Kaneshie market no asi", "The drain at Kaneshie market is blocked.", "Twi", True, False)
    speak_note()
    confirm = phone["text"][-1]
    assert confirm.startswith('I understood: "The drain at Kaneshie market is blocked." (from Twi, translated by machine)\n'
                              "Ready to file your report about Kaneshie.") and not filed
    phone["heard"] = Heard("Baako", "One.", "Twi", True, False)
    speak_note()
    assert filed[0].description == "The drain at Kaneshie market is blocked." and filed[0].spoken == "Twi"
    assert phone["text"][-1].startswith("Filed. Your reference is *K7QM-4TXP*.") and phone["audio"] == [] and phone["spoken"] == []


def test_a_voice_safety_report_gets_its_numbers_first_and_nothing_spoken(monkeypatch: pytest.MonkeyPatch, phone: dict[str, Any]) -> None:
    _reads(monkeypatch, "report")
    filed = _filing(monkeypatch, SAFETY, "abuse")
    phone["heard"] = Heard("My husband beats me every night.", "My husband beats me every night.", "English", True, True)
    speak_note()
    assert phone["text"][-1].startswith("*If anyone is in danger now*") and "sub-metro" in phone["text"][-1]
    say("0")
    assert phone["text"][-1].startswith('I understood: "My husband beats me every night."\nReady to send your report to Ghana Police Service')
    say("1")
    assert filed[0].spoken == "English" and filed[0].ward is None and phone["audio"] == [] and phone["spoken"] == []


@pytest.mark.parametrize(("problem", "expected"), [
    ("unclear", whatsapp_voice.NOT_HEARD), ("invented", whatsapp_voice.NOT_HEARD), ("too_long", whatsapp_voice.TOO_LONG),
    ("fails", whatsapp_voice.FAILED),
])
def test_a_voice_note_that_cannot_be_used_says_why_and_nothing_else_happens(monkeypatch: pytest.MonkeyPatch, phone: dict[str, Any], problem: str, expected: str) -> None:
    asked: list[str] = []
    monkeypatch.setattr(whatsapp_conversation, "read_message", lambda text, has_photo=False: asked.append(text) or Reading(Intent.QUESTION))
    if problem == "unclear":
        phone["heard"] = Heard("", "", "unknown", False, False)
    elif problem == "invented":  # half a second of "One." heard as a sentence (seen live from Gemini)
        monkeypatch.setattr(whatsapp_voice, "seconds", lambda data: 0.44)
        said = "Hello. Good morning. Please, I want to ask about the AMA."
        phone["heard"] = Heard(said, said, "English", True, False)
    elif problem == "too_long":
        monkeypatch.setattr(whatsapp_voice, "seconds", lambda data: 181.0)
    else:
        monkeypatch.setattr(whatsapp_voice, "transcribe", lambda data, content_type: (_ for _ in ()).throw(voice_transcribe.TranscriptionFailed("x")))
    speak_note()
    assert phone["text"] == [expected] and asked == [] and phone["twilio"].deleted == [VOICE.url]


def test_voice_notes_are_limited_per_hour(monkeypatch: pytest.MonkeyPatch, phone: dict[str, Any]) -> None:
    _reads(monkeypatch, "thanks")
    for _ in range(channel_limits.VOICE_NOTES.limit + 1):
        speak_note()
    assert phone["text"] == [whatsapp_voice.TOO_MANY]


@pytest.mark.parametrize("why", ["daily_limit", "no_public_address", "speech_fails"])
def test_without_a_spoken_reply_the_text_answer_still_stands(monkeypatch: pytest.MonkeyPatch, phone: dict[str, Any], why: str) -> None:
    _reads(monkeypatch, "question")
    if why == "daily_limit":
        _settings(monkeypatch, voice_daily_limit=0)
    elif why == "no_public_address":
        _settings(monkeypatch, public_api_url="")
    else:
        monkeypatch.setattr(whatsapp_voice.voice_speech, "speak", lambda script: (_ for _ in ()).throw(voice_speech.SpeechFailed("x")))
    speak_note()
    assert phone["text"][0].startswith("I understood:") and phone["audio"] == []


def test_a_typed_question_is_never_spoken(monkeypatch: pytest.MonkeyPatch, phone: dict[str, Any]) -> None:
    _reads(monkeypatch, "question")
    say("How much is a market stall at Kaneshie?")
    assert phone["text"][0].startswith("A stall at Kaneshie") and phone["audio"] == [] and phone["spoken"] == []


def test_the_trail_says_a_description_is_a_confirmed_machine_transcription() -> None:
    assert report_intake.voice_note("English") == ("Reported by a resident in a WhatsApp voice note. The description is a "
                                                   "machine transcription, which the resident confirmed before it was filed.")
    assert ", translated from Twi," in report_intake.voice_note("Twi")


def test_a_voice_note_goes_to_twilio_as_media_without_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"sid": "MM1"})

    client = TwilioWhatsApp("AC1", TOKEN, "whatsapp:+14155238886", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.send(NUMBER, "", media_url=f"{PUBLIC}/api/channels/whatsapp/audio/abc.ogg") == "MM1"
    assert dict(parse_qsl(seen[0].content.decode())) == {"From": "whatsapp:+14155238886", "To": f"whatsapp:{NUMBER}",
                                                         "MediaUrl": f"{PUBLIC}/api/channels/whatsapp/audio/abc.ogg"}


def test_a_spoken_replys_link_is_kept_out_of_the_access_log() -> None:
    link = "/api/channels/whatsapp/audio/" + "t" * 43 + ".ogg"
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("1.2.3.4:5", "GET", link, "1.1", 200), None)
    assert RedactChannelSecrets().filter(record) and "t" * 43 not in record.getMessage()
    assert "/api/channels/whatsapp/audio/[secret]" in record.getMessage()


def test_the_wav_wrapper_is_16_bit_mono() -> None:
    with wave.open(io.BytesIO(voice_audio.wav(_pcm(0.5), 24_000))) as file:
        assert (file.getnchannels(), file.getsampwidth(), file.getframerate(), file.getnframes()) == (1, 2, 24_000, 12_000)
