"""A question spoken on Ask: heard through the WhatsApp voice pipeline, shown back to check, never asked here."""

import array
import io
import logging
import math
from typing import Any

import av
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import ask as ask_routes
from app.services import rate_limit, voice_transcribe
from app.services.voice_transcribe import Heard

QUESTION = "How much is a market stall at Kaneshie?"


def _recording(container: str, codec: str, seconds: float = 2.0) -> bytes:
    """A tone recorded the way a browser records: WebM/Opus (Chrome, Firefox) or MP4/AAC (Safari)."""
    out = io.BytesIO()
    with av.open(out, "w", format=container) as file:
        stream = file.add_stream(codec, rate=48_000, layout="mono")
        tone = array.array("h", (int(8000 * math.sin(2 * math.pi * 440 * n / 48_000)) for n in range(int(seconds * 48_000))))
        frame = av.AudioFrame.from_ndarray(np.frombuffer(tone.tobytes(), dtype="int16").reshape(1, -1), format="s16", layout="mono")
        frame.rate = 48_000
        for packet in stream.encode(frame):
            file.mux(packet)
        for packet in stream.encode(None):
            file.mux(packet)
    return out.getvalue()


WEBM = _recording("webm", "libopus")


@pytest.fixture
def heard(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Gemini's transcription stubbed (what it hears, and the formats it was given); the per-device limit reset."""
    seen: dict[str, Any] = {"heard": Heard(QUESTION, QUESTION, "English", True, False), "types": []}

    def transcribe(data: bytes, content_type: str) -> Heard:
        seen["types"].append(content_type)
        if isinstance(seen["heard"], Exception):
            raise seen["heard"]
        return seen["heard"]

    monkeypatch.setattr(voice_transcribe, "transcribe", transcribe)
    monkeypatch.setattr(ask_routes, "answer_question", lambda *a, **k: pytest.fail("a spoken question is never asked unchecked"))
    rate_limit.SPOKEN_QUESTIONS._hits.clear()
    return seen


def _send(data: bytes = WEBM, content_type: str = "audio/webm;codecs=opus") -> Any:
    return TestClient(app).post("/api/ask/voice", files={"audio": ("question.webm", data, content_type)})


def test_a_spoken_question_comes_back_as_words_to_check_and_nothing_is_asked(heard: dict[str, Any]) -> None:
    response = _send()
    assert response.status_code == 200
    assert response.json() == {"question": QUESTION, "language": "English", "understood": f'I understood: "{QUESTION}"'}
    assert heard["types"] == ["audio/webm;codecs=opus"]


def test_another_language_is_asked_in_english_and_says_it_was_translated_by_machine(heard: dict[str, Any]) -> None:
    heard["heard"] = Heard("Kaneshie dwam mu stall bo ye sɛn?", QUESTION, "Twi", True, False)
    body = _send().json()
    assert body["question"] == QUESTION and body["language"] == "Twi"
    assert body["understood"] == f'I understood: "{QUESTION}" (from Twi, translated by machine)'


@pytest.mark.parametrize(("problem", "status", "message"), [
    ("unclear", 422, ask_routes.VOICE_NOT_HEARD),
    ("invented", 422, ask_routes.VOICE_NOT_HEARD),
    ("echoed", 422, ask_routes.VOICE_NOT_HEARD),
    ("too_long", 422, ask_routes.VOICE_TOO_LONG),
    ("fails", 503, ask_routes.VOICE_FAILED),
    ("not_audio", 415, ask_routes.VOICE_NOT_AUDIO),
    ("too_big", 413, ask_routes.VOICE_TOO_LONG),
    ("empty", 422, ask_routes.VOICE_NOT_HEARD),
])
def test_a_recording_that_cannot_be_used_says_why(monkeypatch: pytest.MonkeyPatch, heard: dict[str, Any], problem: str, status: int,
                                                  message: str) -> None:
    data = WEBM
    if problem == "unclear":
        heard["heard"] = Heard("", "", "unknown", False, False)
    elif problem == "invented":  # two seconds can't hold this many words: Gemini made them up
        said = "Hello, good morning, please I want to ask about the Assembly and the fees for the stalls at Kaneshie market today."
        heard["heard"] = Heard(said, said, "English", True, False)
    elif problem == "echoed":  # Gemini wrote its instructions back (seen live); long enough to pass words per second
        monkeypatch.setattr(voice_transcribe, "seconds", lambda data: 59.0)
        heard["heard"] = Heard(voice_transcribe._instructions(), voice_transcribe._instructions(), "English", True, False)
    elif problem == "too_long":
        monkeypatch.setattr(voice_transcribe, "seconds", lambda data: 61.0)
    elif problem == "fails":
        heard["heard"] = voice_transcribe.TranscriptionFailed("x")
    elif problem == "not_audio":
        data = b"%PDF-1.7 not a recording"
    elif problem == "too_big":
        data = b"\0" * (ask_routes.VOICE_MAX_BYTES + 1)
    else:
        data = b""
    response = _send(data)
    assert (response.status_code, response.json()["detail"]) == (status, message)


def test_safari_mp4_recordings_are_read_and_re_encoded_for_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = voice_transcribe._Transcript(heard=QUESTION, english=QUESTION, language="English", clear=True, about_harm=False)
    asked: list[dict[str, Any]] = []

    class Gemini:
        models = property(lambda self: self)

        def generate_content(self, **kwargs: Any) -> Any:
            asked.append(kwargs)
            return type("Response", (), {"parsed": parsed, "text": ""})

    monkeypatch.setattr(voice_transcribe, "get_genai_client", Gemini)
    rate_limit.SPOKEN_QUESTIONS._hits.clear()
    for data, content_type in ((_recording("mp4", "aac"), "audio/mp4"), (WEBM, "audio/webm;codecs=opus")):
        assert _send(data, content_type).json()["question"] == QUESTION
    assert [kw["contents"][0].inline_data.mime_type for kw in asked] == ["audio/ogg", "audio/ogg"]


def test_spoken_questions_are_limited_per_device(heard: dict[str, Any]) -> None:
    for _ in range(rate_limit.SPOKEN_QUESTIONS.limit):
        assert _send().status_code == 200
    assert _send().status_code == 429


def test_the_words_are_never_logged(heard: dict[str, Any], caplog: pytest.LogCaptureFixture) -> None:
    heard["heard"] = Heard("My landlord threatens me", "My landlord threatens me", "English", True, True)
    with caplog.at_level(logging.DEBUG):
        _send()
        heard["heard"] = voice_transcribe.TranscriptionFailed("x")
        _send()
    assert "landlord" not in caplog.text
