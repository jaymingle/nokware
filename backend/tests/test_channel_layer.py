"""The shared channel layer: Redis state, per-number limits, the SMS count, reading a message, and phone layouts."""

from datetime import date
from typing import Any

import fakeredis
import pytest
import redis

from app.services import channel_answers, channel_intent, channel_limits, channel_sessions, rag, redis_store, sms
from app.services.channel_answers import LIVE_DATA_NOTE, for_chat, for_sms
from app.services.channel_intent import Intent, find_reference, read_message
from app.services.channel_status import status_text
from app.services.rag import AnswerLength, Prepared, RagAnswer
from app.services.sms import DailyBudget, SmsError, SmsLimitReached, _RedisCount
from app.services.sms_text import is_gsm7, pages

NUMBER = "+233507387216"
SITE = "https://nokware.example.org"
TODAY = date(2026, 9, 14)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    server = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_store, "get_redis", lambda: server)
    for module in (channel_sessions, channel_limits, sms):
        monkeypatch.setattr(module, "get_redis", lambda: server)
    return server


def test_a_number_never_appears_in_redis(fake_redis: fakeredis.FakeRedis) -> None:
    channel_sessions.save("whatsapp", NUMBER, {"step": "area"}, ttl_seconds=900)
    channel_limits.QUESTIONS.allow(NUMBER, now=0)
    keys = fake_redis.keys("*")
    assert keys and all(k.startswith("nokware:") for k in keys)
    assert not any("507387216" in k or "507387216" in (fake_redis.get(k) or "") for k in keys)
    assert redis_store.subject_key(NUMBER) != redis_store.subject_key("+233241234567")


def test_a_session_comes_back_until_it_expires_or_is_cleared(fake_redis: fakeredis.FakeRedis) -> None:
    channel_sessions.save("ussd", "session-1", {"step": "area", "sub_metro": "okaikoi-south"}, ttl_seconds=120)
    assert channel_sessions.load("ussd", "session-1") == {"step": "area", "sub_metro": "okaikoi-south"}
    assert 0 < fake_redis.ttl(fake_redis.keys("nokware:session:ussd:*")[0]) <= 120
    channel_sessions.clear("ussd", "session-1")
    assert channel_sessions.load("ussd", "session-1") is None


def test_a_number_limit_counts_per_window(fake_redis: fakeredis.FakeRedis) -> None:
    limit = channel_limits.NumberLimit("test", limit=2, window_seconds=60)
    assert [limit.allow(NUMBER, now=10) for _ in range(3)] == [True, True, False]
    assert limit.allow("+233241234567", now=10)  # another number has its own count
    assert limit.allow(NUMBER, now=70)  # a new window


def test_the_sms_count_in_redis_survives_a_restart_and_refuses_when_unreachable(fake_redis: fakeredis.FakeRedis) -> None:
    DailyBudget(3, _RedisCount()).take(2, TODAY)
    with pytest.raises(SmsLimitReached):
        DailyBudget(3, _RedisCount()).take(2, TODAY)  # a fresh process sees the same count
    DailyBudget(3, _RedisCount()).take(1, TODAY)


def test_without_redis_the_sms_count_refuses_rather_than_spend_uncounted(monkeypatch: pytest.MonkeyPatch) -> None:
    def down() -> Any:
        raise redis.ConnectionError("refused")

    monkeypatch.setattr(sms, "get_redis", down)
    with pytest.raises(SmsError, match="can't be checked"):
        DailyBudget(3, _RedisCount()).take(1, TODAY)


@pytest.mark.parametrize(("text", "reference"), [
    ("K7QM-4TXP", "K7QM-4TXP"), ("status of k7qm 4txp please", "K7QM-4TXP"), ("k7qm4txp", "K7QM-4TXP"),
    ("KANESHIE", None), ("STREETSX", None), ("K7QM-4TXPZ", None), ("call 0244123456", None),
])
def test_a_reference_is_found_however_it_is_typed_but_never_in_a_word(text: str, reference: str | None) -> None:
    assert find_reference(text) == reference


def test_rules_read_the_easy_messages_without_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_intent, "_model_kind", lambda text, has_photo: pytest.fail("the model was asked"))
    assert read_message("Status of K7QM-4TXP?") == channel_intent.Reading(Intent.STATUS, "K7QM-4TXP")
    assert read_message("Hello!").intent == Intent.HELP
    assert read_message("", has_photo=True).intent == Intent.REPORT
    assert read_message("   ").intent == Intent.HELP


def test_the_model_reads_the_rest_and_a_failure_means_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_intent, "_model_kind", lambda text, has_photo: Intent.QUESTION)
    long_text = "What does the Assembly charge for a market stall, and is K7QM-4TXP my case number?"
    assert read_message(long_text).intent == Intent.QUESTION  # a reference inside a long message: the model decides

    class Broken:
        def with_structured_output(self, schema: Any) -> Any:
            raise TimeoutError("model timed out")

    monkeypatch.undo()
    monkeypatch.setattr(channel_intent, "get_quick_model", lambda: Broken())
    assert read_message("The gutter on our street is blocked").intent == Intent.UNCLEAR


def test_only_the_length_rule_changes_between_channels() -> None:
    prepared = Prepared("What are the fees?", [], {}, [])
    web, chat, text = (rag._prompt_input(prepared, length) for length in AnswerLength)
    assert web["length"] == "" and "1,000 characters" in chat["length"] and "240 characters" in text["length"]
    assert {k: v for k, v in web.items() if k != "length"} == {k: v for k, v in text.items() if k != "length"}


def _source(label: str, title: str, year: int | None = 2026) -> dict[str, Any]:
    return {"label": label, "cited": True, "title": title, "department_name": "Central Administration", "document_year": year}


ANSWER: RagAnswer = {
    "answer": "As of 14 September, Nokware's live report data shows **fewer than 5** open waste reports [R1].\n\n"
              "- The Assembly plans door-to-door collection [S2].\n- It aims for 70% separation at source [S2][S5].",
    "status": "answered",
    "sources": [_source("S2", "Accra Climate Action Plan"), _source("S2", "Accra Climate Action Plan"),
                _source("S5", "MEDIUM TERM DEVELOPMENT PLAN, 2026-2029 " * 4), _source("S9", "Fee-Fixing Resolution.")],
    "figures": [{"label": "R1", "cited": True, "description": "Open reports", "value": "fewer than 5", "rows": [], "counted_at": ""}],
    "search_queries": [],
}  # type: ignore[typeddict-item]


def test_a_chat_answer_numbers_its_sources_and_explains_live_data() -> None:
    text = for_chat(ANSWER, SITE)
    assert "*fewer than 5*" in text and "[R1]" not in text and "reports." in text
    assert "door-to-door collection [1]" in text and "source [1][2]" in text
    assert "\u2022 The Assembly plans" in text and "\n- " not in text  # WhatsApp would show markdown bullets as stars
    assert "Sources:\n[1] Accra Climate Action Plan (Central Administration, 2026)\n[2] MEDIUM TERM" in text
    assert text.count("Accra Climate Action Plan") == 1 and LIVE_DATA_NOTE in text
    assert channel_answers._describe(ANSWER["sources"][3], 90) == "Fee-Fixing Resolution (Central Administration, 2026)"


def test_an_sms_answer_is_plain_two_pages_at_most_with_one_source() -> None:
    long_answer = {**ANSWER, "answer": ANSWER["answer"] + " Also a sentence that goes on and on. " * 20}
    for answer in (ANSWER, long_answer):
        text = for_sms(answer, SITE)  # type: ignore[arg-type]
        assert is_gsm7(text) and pages(text) <= 2 and text.startswith("Nokware: ")
        assert text.endswith("Source: Accra Climate Action Plan (Central Administration, 2026).")
        assert "[" not in text and "*" not in text and " ." not in text
    refused = for_sms({**ANSWER, "answer": "Nokware doesn't publish figures on reports about someone's safety.",
                       "figures": []}, SITE)  # type: ignore[arg-type]
    assert refused == "Nokware doesn't publish figures on reports about someone's safety."  # no second "Nokware:"
    nothing = for_sms({**ANSWER, "status": "no_information"}, SITE)  # type: ignore[arg-type]
    assert "don't have information" in nothing and pages(nothing) == 1


CIVIC = {"reference": "UACQ-J75K", "private": False, "status": "resolved", "topic": "Street lighting", "ward": "Kinka",
         "recipients": ["Works Department"], "resolution_notes": [{"recipient": "Works Department", "note": "Lamp replaced."}],
         "voices": 2, "escalate_until": "2026-09-27T22:13:04+00:00"}


def test_a_status_says_what_where_who_and_what_next() -> None:
    text = status_text(CIVIC, SITE)
    assert text.startswith("Report UACQ-J75K (Street lighting in Kinka) was resolved by Works Department.")
    assert 'Works Department said: "Lamp replaced."' in text and "2 other residents say" in text
    assert "escalate it until 27 Sep" in text
    assert status_text(CIVIC, SITE, compact=True) == "Report UACQ-J75K (Street lighting in Kinka) was resolved by Works Department."


def test_a_personal_safety_status_says_only_its_stage() -> None:
    private = {"reference": "M3RD-8WQA", "private": True, "stage": "in_progress", "topic": "Abuse"}
    assert status_text(private, SITE) == "Reference M3RD-8WQA: in progress."
