"""Read aloud: only what the server produced, never anything about someone's safety, paid for once."""

from datetime import UTC, datetime
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import ask as ask_routes
from app.services import ask_export, read_aloud, redis_store, report_followups, report_store
from app.services.phrases import Language, phrase
from app.services.rag import NO_INFO_ANSWER, SAFETY_FIGURES_ANSWER
from app.services.read_aloud import NotReadAloud, ReadAloudUnavailable
from app.services.voice_audio import Encoded
from app.services.voice_speech import SpeechFailed

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
ANSWER = "**Market stall** fees are set in the Fee-Fixing Resolution [S1]: GH¢ 30.00 a month (https://ama.gov.gh/fees.pdf)."
STATUS = {"private": False, "reference": "K7QM-4TXP", "status": "resolved", "topic": "Drainage and flooding", "ward": "Kaneshie",
          "recipients": ["Works Department"], "resolution_notes": [{"recipient": "Works Department", "note": "Desilted on 12 September."}],
          "voices": 3, "escalate_until": "2026-09-29T12:00:00+00:00"}


@pytest.fixture
def spoken(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Redis faked, and Gemini's speech replaced by a counter of what it was asked to say."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(read_aloud, "get_redis", lambda: fake)
    monkeypatch.setattr(redis_store, "get_redis", lambda: fake)
    said: list[str] = []
    monkeypatch.setattr(read_aloud, "speak", lambda script, for_web=False: said.append(script) or Encoded(b"ID3-mp3", "audio/mpeg", "mp3", 4.2))
    return said


def test_an_answer_is_read_as_words_with_where_its_sources_are() -> None:
    script = read_aloud.answer_script("What does a market stall cost?", ANSWER, "answered")
    assert script == ("Market stall fees are set in the Fee-Fixing Resolution: 30 Ghana cedis a month. "
                      "The documents it comes from are listed with the answer.")
    long = read_aloud.answer_script("Tell me everything", "The Assembly plans many things. " * 100, "answered")
    assert len(long) < read_aloud.READ_MAX_CHARS + 120 and read_aloud.REST_ON_SCREEN in long
    assert read_aloud.answer_script("Where is the rates office?", NO_INFO_ANSWER, "no_information").startswith(NO_INFO_ANSWER)


def test_a_reading_is_made_in_parts_that_end_at_sentences_the_first_short() -> None:
    script = read_aloud.answer_script("Tell me everything", "The Assembly plans many things for the markets. " * 40, "answered")
    made = read_aloud.parts(script)
    assert len(made[0]) <= read_aloud.FIRST_PART_MAX and all(len(part) <= read_aloud.PART_CHARS for part in made)
    assert " ".join(made) == script and all(part.endswith(".") for part in made[1:]) and len(made) <= 8
    assert read_aloud.parts("Hello, Accra.") == ["Hello, Accra."]
    run_on = "word " * 200  # no full stop anywhere: split between words
    assert all(0 < len(part) <= read_aloud.PART_CHARS for part in read_aloud.parts(run_on))


def test_a_fee_table_is_read_a_few_figures_at_a_time() -> None:
    table = "Fees for 2026:\n" + "\n".join(f"* Makola Stores - {c}: {100 + i * 25}.00 [S1]" for i, c in enumerate("ABCDEFGH"))
    made = read_aloud.parts(read_aloud.answer_script("What do stores cost?", table, "answered"))
    assert all(read_aloud._figures(part) <= read_aloud.PART_FIGURES for part in made) and len(made) >= 3
    assert made[1].startswith("Makola Stores") and made[1].endswith(".")  # a row is never cut in two
    assert read_aloud._figures("31st December Market Stores - A: 800. The 2026 Resolution, K 7 Q M.") == 2  # 800 and 2026


def test_nothing_about_someones_safety_is_read_aloud() -> None:
    for question, answer in (("My husband beats me, who can help?", "Call the Police."),
                             ("How many reports?", f"{SAFETY_FIGURES_ANSWER} The rest."),
                             ("Where do I go?", "If someone threatened to kill you, call 191.")):
        assert not read_aloud.may_speak_answer(question, answer)
        with pytest.raises(NotReadAloud):
            read_aloud.answer_script(question, answer, "answered")
    with pytest.raises(NotReadAloud):
        read_aloud.status_script({**STATUS, "private": True, "stage": "received"})


def test_a_status_is_read_as_its_page_shows_it_with_the_reference_spelled_out() -> None:
    script = read_aloud.status_script(STATUS)
    assert script.startswith("Report K 7 Q M, 4 T X P (Drainage and flooding in Kaneshie) was resolved by Works Department.")
    assert 'Works Department said: "Desilted on 12 September."' in script and "3 other residents say it affects them too." in script
    assert "escalate it until 29 Sep on this page" in script and "report/status" not in script
    assert read_aloud.status_script(STATUS, receipt=True).endswith(read_aloud.KEEP_REFERENCE)


def test_the_same_words_are_spoken_once_and_the_day_has_a_limit(spoken: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    assert read_aloud.audio("Hello, Accra.", NOW).data == b"ID3-mp3"
    assert read_aloud.audio("Hello, Accra.", NOW).content_type == "audio/mpeg" and spoken == ["Hello, Accra."]  # cached
    settings = read_aloud.get_settings().model_copy(update={"read_aloud_daily_limit": 1})
    monkeypatch.setattr(read_aloud, "get_settings", lambda: settings)
    with pytest.raises(ReadAloudUnavailable, match="today's limit"):
        read_aloud.audio("Something new.", NOW)


def test_a_speech_failure_says_so_plainly(spoken: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(script: str, for_web: bool = False) -> Encoded:
        raise SpeechFailed("no audio")

    monkeypatch.setattr(read_aloud, "speak", fail)
    with pytest.raises(ReadAloudUnavailable, match="couldn't be made"):
        read_aloud.audio("Hello.", NOW)


def _view(question: str, answer: str) -> dict[str, Any]:
    answered = ask_export.Answered(question, answer, "answered", [], [], None, None)
    return ask_export.export_view(answered, NOW).model_dump(mode="json")


def test_only_an_answer_the_api_gave_is_read_aloud(spoken: list[str]) -> None:
    client = TestClient(app)
    view = _view("What does a market stall cost?", ANSWER)
    response = client.post("/api/speech/answer", json={"view": view})
    assert response.status_code == 200 and response.headers["content-type"] == "audio/mpeg" and response.content == b"ID3-mp3"
    made = int(response.headers["x-speech-parts"])
    assert client.post("/api/speech/answer", json={"view": view, "part": made}).status_code == 404  # no part beyond the last
    forged = {**view, "answer": "Anything at all, read aloud for free."}
    assert client.post("/api/speech/answer", json={"view": forged}).status_code == 403
    unsafe = _view("Someone is beating my neighbour", "Call the Police on 191.")
    assert client.post("/api/speech/answer", json={"view": unsafe}).status_code == 409


def test_a_report_is_read_by_its_reference_never_a_private_one(spoken: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_followups, "find", lambda reference: {"$id": "c1"})
    monkeypatch.setattr(report_store, "assignments_for", lambda case_id: [])
    monkeypatch.setattr(report_followups, "public_status", lambda case, assignments, now: STATUS)
    client = TestClient(app)
    first = client.post("/api/speech/report", json={"reference": "K7QM-4TXP", "kind": "receipt"})
    assert first.status_code == 200 and int(first.headers["x-speech-parts"]) >= 2  # the confirmation runs past one short part
    assert client.post("/api/speech/report", json={"reference": "K7QM-4TXP", "kind": "receipt", "part": 1}).status_code == 200
    assert spoken[0].startswith("Report K 7 Q M") and spoken[1] != spoken[0]
    monkeypatch.setattr(report_followups, "public_status", lambda case, assignments, now: {**STATUS, "private": True, "stage": "received"})
    assert client.post("/api/speech/report", json={"reference": "K7QM-4TXP"}).status_code == 409


def test_the_answer_says_whether_it_can_be_read_aloud() -> None:
    done = {"type": "done", "answer": ANSWER, "status": "answered", "cited": [], "chart": None, "chart_note": None}
    assert ask_routes._signed("What does a market stall cost?", done, {})["speakable"] is True
    assert ask_routes._signed("My uncle beats me", done, {})["speakable"] is False


def test_the_first_words_are_reached_sooner_by_splitting_where_a_speaker_would_pause() -> None:
    """The listener waits through the first part alone, and Gemini takes about 0.7 seconds a second of audio."""
    budget = ("AMA approved GH¢ 20,270,110 for Head Office and GH¢ 20,232,848 for Public Works in its 2026 budget, "
              "which together make up about half of the approved total. Education was approved GH¢ 7,786,630.")
    made = read_aloud.parts(budget)
    assert made[0] == "AMA approved GH¢ 20,270,110 for Head Office"  # the pause before the second amount
    assert read_aloud._figures(made[0]) <= read_aloud.FIRST_PART_FIGURES and " ".join(made) == budget


def test_a_sentence_with_nowhere_to_pause_is_left_whole() -> None:
    """A seam mid-phrase is worse to listen to than the seconds it saves."""
    unbroken = ("The Assembly has not published a quarterly financial report for the third quarter of 2025 anywhere "
                "that Nokware can find. The publishing record shows every period it was due and what was asked for "
                "under the Right to Information Act, with the date each request was sent to the Assembly.")
    made = read_aloud.parts(unbroken)
    assert made[0].endswith("can find.") and " ".join(made) == unbroken


def test_a_short_answer_is_still_made_in_one_go() -> None:
    short = "Residents filed 12 reports last month. Most were about waste collection and drains."
    assert read_aloud.parts(short) == [short]


def test_figures_count_towards_the_opening_because_they_are_slow_to_say() -> None:
    """Three amounts in under 200 characters run to half a minute of audio: length alone would read that as short."""
    amounts = "Head Office got GH¢ 20,270,110, Public Works GH¢ 20,232,848 and Education GH¢ 7,786,630 in 2026."
    prose = "Head Office, Public Works and Education were each given a share of the approved budget for the coming year."
    assert read_aloud._speaking_cost(amounts) > read_aloud._speaking_cost(prose) + 60 >= len(prose)
    assert len(read_aloud.parts(amounts)) > 1


def test_an_answer_is_read_in_the_language_it_was_given_in() -> None:
    """A French answer had no Listen button and no word about why. The sentences around it come from the catalogue,
    never a machine, so only a language whose fixed lines are written by hand can be spoken at all."""
    french = "La mairie a approuvé 20 270 110 cédis pour le siège en 2026."
    script = read_aloud.answer_script("Combien pour le siège en 2026 ?", "AMA approved 20,270,110 cedis.", "answered",
                                      spoken=french, language="fr")
    assert script.startswith(french) and phrase("speech.sources_on_screen", Language.FRENCH) in script
    assert "The documents it comes from" not in script  # not a word of English in a French reading


def test_a_language_nokware_has_not_written_is_not_spoken_and_says_so() -> None:
    with pytest.raises(NotReadAloud, match="isn't available in this language"):
        read_aloud.answer_script("Sɛn na AMA de sika bɛyɛ adwuma?", "AMA approved 20,270,110 cedis.", "answered",
                                 spoken="Twi words here", language="tw")
    assert read_aloud.may_speak_language("en") and read_aloud.may_speak_language("fr")
    assert not read_aloud.may_speak_language("tw")


def test_the_safety_rule_reads_the_english_whatever_language_is_spoken() -> None:
    """A translation must never be the thing that slips a safety answer past a check written in English."""
    with pytest.raises(NotReadAloud, match="someone's safety"):
        read_aloud.answer_script("Combien de cas de violence domestique ?",
                                 "Nokware doesn't publish figures on reports about someone's safety.", "answered",
                                 spoken="Nokware ne publie pas ces chiffres.", language="fr")
