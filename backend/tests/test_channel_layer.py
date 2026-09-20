"""The shared channel layer: Redis state, per-number limits, the SMS count, reading a message, and phone layouts."""

from datetime import date
from typing import Any

import fakeredis
import pytest
import redis

from app.services import channel_answers, channel_intent, channel_limits, channel_sessions, rag, redis_store, sms, ussd
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
    assert read_message("Ok, thanks!").intent == Intent.THANKS and read_message("Medaase").intent == Intent.THANKS
    assert read_message("", has_photo=True).intent == Intent.REPORT
    assert read_message("   ").intent == Intent.HELP


def test_the_model_reads_the_rest_and_a_failure_means_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_intent, "_model_kind", lambda text, has_photo: Intent.QUESTION)
    long_text = "What does the Assembly charge for a market stall, and is K7QM-4TXP my case number?"
    assert read_message(long_text).intent == Intent.QUESTION  # a reference inside a long message: the model decides
    monkeypatch.setattr(channel_intent, "_model_kind", lambda text, has_photo: Intent.STATUS)
    asked = "What is happening with my report XYHN-6A5T? I sent it last week."  # as a voice note says it
    assert read_message(asked) == channel_intent.Reading(Intent.STATUS, "XYHN-6A5T")
    assert read_message("What is happening with the report I sent last week?").intent == Intent.HELP  # which report?

    class Broken:
        def with_structured_output(self, schema: Any) -> Any:
            raise TimeoutError("model timed out")

    monkeypatch.undo()
    monkeypatch.setattr(channel_intent, "get_quick_model", lambda: Broken())
    assert read_message("The gutter on our street is blocked").intent == Intent.UNCLEAR


def test_only_the_length_rule_changes_between_channels() -> None:
    prepared = Prepared("What are the fees?", [], {}, [])
    web, chat, text, shorter = (rag._prompt_input(prepared, length) for length in AnswerLength)
    assert web["length"] == "" and "1,000 characters" in chat["length"] and "300 characters" in text["length"]
    assert "complete short answer" in text["length"] and "never a first instalment" in text["length"]
    # The re-ask is shorter still, and just as firm that shorter means fewer things said, not a sentence stopped.
    assert "160 characters" in shorter["length"] and "never by stopping early" in shorter["length"]
    for other in (text, shorter):
        assert {k: v for k, v in web.items() if k != "length"} == {k: v for k, v in other.items() if k != "length"}


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


BUDGET_FIGURE = {"label": "B1", "cited": True, "description": "Waste budget", "value": "GH¢ 20,270,110", "rows": [],
                 "counted_at": None, "source": "documents", "document_title": "Composite Budget 2026", "year": 2026}
LONG = " Also a sentence that goes on and on about the collection rounds. " * 8


def _long() -> Any:
    return {**ANSWER, "answer": ANSWER["answer"] + LONG}


def _body(part: str) -> str:
    """A part without its "(1/3)"."""
    return part.rsplit(" (", 1)[0] if part.endswith(")") else part


def test_an_sms_answer_is_plain_numbered_parts_no_wider_than_a_page() -> None:
    parts = for_sms(ANSWER, SITE)  # type: ignore[arg-type]
    assert [part[-6:] for part in parts] == [f" ({n}/{len(parts)})" for n in range(1, len(parts) + 1)]
    assert all(is_gsm7(part) and pages(part) == 1 for part in parts)
    assert sum(pages(part) for part in parts) <= channel_answers.SMS_PARTS
    joined = " ".join(_body(part) for part in parts)
    assert joined.startswith(f"Nokware: {channel_answers.flat_text(ANSWER['answer'])}")  # nothing of it is lost
    assert "[" not in joined and "*" not in joined and " ." not in joined
    assert "Also at nokware.example.org/ask" in parts[-1]


def test_sms_parts_break_where_a_sentence_ends_and_never_mid_word() -> None:
    parts = for_sms(_long(), SITE, shorter=lambda: ANSWER)  # type: ignore[arg-type]
    whole = f"Nokware: {channel_answers.flat_text(ANSWER['answer'])}"
    assert len(parts) > 1 and all(_body(part).endswith(".") for part in parts[:-1])
    assert " ".join(_body(part) for part in parts).startswith(whole)  # every word, in order, none broken
    assert _body(parts[0]) == whole[: len(_body(parts[0]))]  # the first break is where its last sentence ends


def test_an_sms_answer_is_never_cut_and_never_calls_itself_the_first_part() -> None:
    """A reader who can't tell a short answer from a cut one doesn't know whether to go looking for the rest."""
    nothing: Any = {**ANSWER, "status": "no_information"}
    for answer in (ANSWER, _long(), nothing):
        for parts in (for_sms(answer, SITE), for_sms(answer, SITE, lambda: _long())):  # type: ignore[arg-type]
            text = " ".join(parts)
            assert "..." not in text and "First part" not in text
            assert "*" not in text and " - " not in text  # no markdown reaches a phone, on any path
            assert all(pages(part) == 1 for part in parts)  # a part is a page: none of them costs two credits
            assert sum(pages(part) for part in parts) <= channel_answers.SMS_PARTS
    assert "don't have information" in for_sms(nothing, SITE)[0] and len(for_sms(nothing, SITE)) == 1
    refused = for_sms({**ANSWER, "answer": "Nokware doesn't publish figures on reports about someone's safety.",
                       "figures": []}, SITE)  # type: ignore[arg-type]
    assert refused[0].startswith("Nokware doesn't publish")  # no second "Nokware:"


def test_every_document_the_answer_cites_is_named_not_only_the_first() -> None:
    """One document named as the source of a whole answer tells the resident a figure came from a document it didn't."""
    last = for_sms(ANSWER, SITE)[-1]  # type: ignore[arg-type]
    assert "Sources: " in last and "Source: " not in last
    assert "Accra Climate Action Plan" in last and ("MEDIUM TERM" in last or "and 1 more" in last)
    one: Any = {**ANSWER, "answer": "A stall costs GH¢30 a month [S2].", "figures": []}
    assert "Source: Accra Climate Action Plan (Central Administration, 2026)." in for_sms(one, SITE)[-1]


def test_a_budget_figure_names_the_document_it_was_read_from_and_costs_one_alphabet() -> None:
    both: Any = {**ANSWER, "figures": [BUDGET_FIGURE],
                 "answer": "AMA budgeted GH¢ 20,270,110 for waste in 2026 [B1]. It plans door-to-door collection [S2]."}
    parts = for_sms(both, SITE)
    assert "GHS 20,270,110" in parts[0] and all(is_gsm7(part) for part in parts)  # a cedi sign would treble the cost
    assert "Composite Budget 2026" in parts[-1] and "Accra Climate Action Plan" in parts[-1]


def test_an_answer_too_long_is_asked_for_again_shorter_once_and_only_once(caplog: pytest.LogCaptureFixture) -> None:
    asked: list[str] = []

    def shorter() -> Any:
        asked.append("asked")
        return {**ANSWER, "answer": "Fewer than 5 waste reports are open [R1]."}

    parts = for_sms(_long(), SITE, shorter)
    assert asked == ["asked"] and "Fewer than 5 waste reports are open." in parts[0]
    for_sms(ANSWER, SITE, shorter)  # type: ignore[arg-type]
    assert asked == ["asked"]  # an answer that fits is never re-asked
    with caplog.at_level("WARNING"):
        stubborn = for_sms(_long(), SITE, lambda: _long())
    assert asked == ["asked"] and "shorter" in caplog.text
    assert stubborn[-1].endswith(f"More at nokware.example.org/ask ({len(stubborn)}/{len(stubborn)})")
    assert all(_body(part).endswith(".") for part in stubborn[:-1])  # only whole sentences went out


def test_ussd_screens_page_the_answer_and_leave_the_menu_its_room() -> None:
    menu = "\n1 More\n0 Back"
    screens = channel_answers.screens(_long()["answer"], len(menu))
    assert len(screens) > 1 and all(len(screen) + len(menu) <= ussd.SCREEN_MAX and is_gsm7(screen) for screen in screens)
    assert all(screen.endswith((".", "!", "?", ",", ";", ":")) for screen in screens)
    assert " ".join(screens) == channel_answers.flat_text(_long()["answer"])  # the whole answer, and only it
    assert channel_answers.SCREEN_MAX == ussd.SCREEN_MAX


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
