"""USSD: every screen fits, each menu path does what it says, and the callback's secret is checked."""

import logging
import time
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import RedactUssdSecret, app
from app.routes import channels
from app.services import channel_limits, channel_sessions, redis_store, report_followups, report_intake, ussd
from app.services.citizen_reports import IntakeChannel, NotificationEvent
from app.contacts import EMERGENCY_TOPICS
from app.services.report_intake import Receipt, ReportSubmission
from app.services.report_rules import Classification, ClassificationMethod
from app.services.report_taxonomy import TOPICS_BY_ID
from app.services.sms_text import is_gsm7
from app.services.ussd import CONFIRM, MENU, Dial, sub_metro_screen, ward_screen
from app.wards import sub_metros

PHONE = "+233507387216"
TOKEN = "ussd-secret-token"
CIVIC = {"$id": "c1", "reference": "K7QM-4TXP", "category": "civic_service", "topic": "drainage", "isSensitive": False,
         "recipients": ["dept-works"]}
SAFETY = {"$id": "c2", "reference": "M3RD-8WQA", "category": "personal_safety", "topic": "abuse", "isSensitive": True,
          "recipients": ["agency-police", "dept-social-welfare"]}


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Redis faked, and whatever runs after the screen collected instead of run."""
    server = fakeredis.FakeRedis(decode_responses=True)
    for module in (redis_store, channel_sessions, channel_limits):
        monkeypatch.setattr(module, "get_redis", lambda: server)
    return []


def keys(later: list[tuple[Any, ...]], *presses: str, session_id: str = "s1") -> ussd.Reply:
    """Dial, then press each key in turn; the last screen."""
    add = lambda *args: later.append(args)  # noqa: E731
    reply = ussd.respond(Dial(session_id, PHONE, "*928*1#", True), add)
    for press in presses:
        reply = ussd.respond(Dial(session_id, PHONE, press, False), add)
    return reply


def test_every_fixed_screen_fits_one_plain_screen() -> None:
    screens = [MENU, CONFIRM, sub_metro_screen(), *(ward_screen(i) for i in sub_metros())]
    for screen in screens:
        assert len(screen) <= ussd.SCREEN_MAX and is_gsm7(screen), screen


def test_a_question_ends_the_session_and_its_answer_follows_by_sms(session: list[tuple[Any, ...]]) -> None:
    reply = keys(session, "1", "What does AMA charge for a market stall?")
    assert reply == ussd.Reply("Thank you. Your answer is on its way by SMS.", False)
    assert session == [(ussd.answer_by_sms, PHONE, "What does AMA charge for a market stall?")]


def test_answers_by_sms_are_limited_per_number(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_limits, "SMS_ANSWERS", channel_limits.NumberLimit("sms-answers", 1, 86400))
    keys(session, "1", "What are the market fees?", session_id="a")
    assert "today's answers" in keys(session, "1", "And the toll fees?", session_id="b").message
    assert len(session) == 1


def test_the_answer_sms_is_the_sms_layout_and_a_failure_still_gets_a_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(ussd, "send_sms", lambda to, text: sent.append((to, text)) or True)
    monkeypatch.setattr(ussd, "answer_question", lambda q, length: {"status": "no_information"})
    ussd.answer_by_sms(PHONE, "Where is the moon?")
    monkeypatch.setattr(ussd, "answer_question", lambda q, length: 1 / 0)
    ussd.answer_by_sms(PHONE, "Where is the moon?")
    assert "don't have information" in sent[0][1] and "sorry" in sent[1][1] and {to for to, _ in sent} == {PHONE}


def _classified(topic: str) -> Classification:
    found = TOPICS_BY_ID[topic]
    return Classification(found.category, topic, 3, found.recipients, ClassificationMethod.AI)


def _filed(case: dict[str, Any], messages_on: bool = True, token: str | None = None, monkeypatch: Any = None) -> Any:
    submitted: list[ReportSubmission] = []
    if monkeypatch is not None:
        monkeypatch.setattr(report_intake, "read_report", lambda description: _classified(case["topic"]))

    def submit(submission: ReportSubmission, photos: list[bytes], now: Any, classification: Any = None) -> Receipt:
        assert classification == _classified(case["topic"])  # filed as it was read
        submitted.append(submission)
        return Receipt(case=case, messages_on=messages_on, held_for_consent=token is not None, preferences_token=token)

    return submitted, submit


def test_a_report_is_described_placed_confirmed_and_filed(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    submitted, submit = _filed(CIVIC, monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    assert keys(session, "2", "bad").message.startswith("Please describe it")  # too short: asked again
    kaneshie = str(ussd._ward_ids("okaikoi-south").index("kaneshie") + 1)
    reply = keys(session, "2", "The drain at Kaneshie market is choked", "9", "2", kaneshie, "1", session_id="s2")
    assert reply.message == "Report K7QM-4TXP filed with Works Department. We'll SMS you when it's resolved. Keep this reference."
    assert not reply.more
    filed = submitted[0]
    assert (filed.ward, filed.phone, filed.channel, filed.whatsapp) == ("kaneshie", PHONE, IntakeChannel.USSD, None)
    assert session[-1][1:] == (CIVIC, NotificationEvent.SUBMITTED)


def test_filing_without_updates_keeps_the_number_out(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    submitted, submit = _filed(CIVIC, messages_on=False, monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    reply = keys(session, "2", "The drain at Kaneshie market is choked", "2", "1", "2")
    assert submitted[0].phone is None and "We'll SMS" not in reply.message and not session


def test_cancel_files_nothing(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_intake, "read_report", lambda description: _classified("drainage"))
    monkeypatch.setattr(report_intake, "submit", lambda *args: pytest.fail("filed"))
    assert keys(session, "2", "The drain at Kaneshie market is choked", "2", "1", "0").message == "Cancelled. Nothing was filed."


def test_personal_safety_shows_numbers_first_asks_only_the_sub_metro_and_updates_only_on_yes(
    session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    submitted, submit = _filed(SAFETY, messages_on=False, token="one-time", monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    chosen: list[Any] = []
    monkeypatch.setattr(report_followups, "set_preferences", lambda ref, token, choice, now: chosen.append((ref, token, choice)) or (SAFETY, choice.notify))
    help_screen = keys(session, "2", "My neighbour beats his wife every night")
    assert help_screen.message.startswith("Police: 112, 191. Helpline: 0800 800 800") and help_screen.message.endswith("1 Continue")
    place = ussd.respond(Dial("s1", PHONE, "1", False), lambda *a: None)
    assert place.message.startswith("Which sub-metro are you in?") and place.message.endswith("0 Skip")
    assert "electoral area" not in place.message
    ussd.respond(Dial("s1", PHONE, "2", False), lambda *a: None)  # Okaikoi South, then the confirm screen
    screen = ussd.respond(Dial("s1", PHONE, "1", False), lambda *args: session.append(args))
    assert (submitted[0].ward, submitted[0].sub_metro) == (None, "okaikoi-south")
    assert screen.more and screen.message.startswith("Reference M3RD-8WQA received. More numbers:")
    for giveaway in ("Police", "Social Welfare", "abuse", "safety"):
        assert giveaway not in screen.message
    done = ussd.respond(Dial("s1", PHONE, "1", False), lambda *args: session.append(args))
    assert done.message == "Updates are on. Keep your reference." and chosen[0][:2] == ("M3RD-8WQA", "one-time")
    assert session == [(ussd.notify_quietly, SAFETY, NotificationEvent.SUBMITTED)]


def test_a_safety_reporter_can_skip_the_sub_metro(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    submitted, submit = _filed(SAFETY, messages_on=False, monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    keys(session, "2", "Someone has threatened to kill me", "1", "0", "2")
    assert (submitted[0].ward, submitted[0].sub_metro) == (None, None)


def test_every_emergency_numbers_screen_fits(session: list[tuple[Any, ...]]) -> None:
    for topic in EMERGENCY_TOPICS:
        screen = ussd.numbers_screen(topic)
        assert len(screen) <= ussd.SCREEN_MAX and is_gsm7(screen) and screen.endswith("1 Continue"), topic
    assert len(ussd.safety_sub_metro_screen()) <= ussd.SCREEN_MAX


def test_a_slow_model_leaves_the_rules_to_decide_and_they_still_catch_danger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ussd, "CLASSIFY_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(report_intake, "read_report", lambda description: time.sleep(0.3) or _classified("drainage"))
    assert ussd._read("He beats her and she fears for her life").private
    assert ussd._read("The gutter by the school is blocked").topic == "other_civic"  # triage: a person routes it


def test_checking_a_case_shows_its_status_in_one_screen(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_followups, "find", lambda ref: CIVIC if ref == "K7QM-4TXP" else (_ for _ in ()).throw(report_followups.CaseNotFound(ref)))
    monkeypatch.setattr(ussd.report_store, "assignments_for", lambda case_id: [])
    status = {"reference": "K7QM-4TXP", "private": False, "status": "in_progress", "topic": "Drainage and flooding",
              "ward": "Kaneshie", "recipients": ["Works Department"]}
    monkeypatch.setattr(report_followups, "public_status", lambda case, assignments, now: status)
    assert keys(session, "3", "k7qm 4txp").message == "Report K7QM-4TXP (Drainage and flooding in Kaneshie) is in progress with Works Department."
    assert keys(session, "3", "hello", session_id="x").more  # not a reference: asked again
    assert keys(session, "3", "ZZZZ-2222", session_id="y").message.startswith("No case has the reference ZZZZ-2222")


def test_an_expired_session_asks_to_dial_again(session: list[tuple[Any, ...]]) -> None:
    assert ussd.respond(Dial("gone", PHONE, "1", False), lambda *a: None) == ussd.Reply("Your session ended. Please dial again.", False)


def test_the_callback_needs_its_secret_and_always_answers_with_a_screen(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channels, "get_settings", lambda: get_settings().model_copy(update={"arkesel_ussd_token": TOKEN}))
    client = TestClient(app)
    body = {"sessionID": "s9", "userID": "NOKWARE", "newSession": True, "msisdn": "233507387216", "userData": "*928*1#", "network": "MTN"}
    assert client.post("/api/channels/ussd/wrong", json=body).status_code == 404
    reply = client.post(f"/api/channels/ussd/{TOKEN}", json=body).json()
    assert reply == {"sessionID": "s9", "userID": "NOKWARE", "msisdn": "233507387216", "message": MENU, "continueSession": True}
    monkeypatch.setattr(ussd, "respond", lambda dial, later: 1 / 0)
    broken = client.post(f"/api/channels/ussd/{TOKEN}", json={**body, "newSession": False}).json()
    assert broken["continueSession"] is False and "dial again" in broken["message"]
    foreign = client.post(f"/api/channels/ussd/{TOKEN}", json={**body, "msisdn": "447700900123"}).json()
    assert "Ghanaian" in foreign["message"]


def test_without_a_token_ussd_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channels, "get_settings", lambda: get_settings().model_copy(update={"arkesel_ussd_token": ""}))
    body = {"sessionID": "s9", "msisdn": "233507387216", "newSession": True}
    assert TestClient(app).post("/api/channels/ussd/", json=body).status_code == 404
    assert TestClient(app).post("/api/channels/ussd/anything", json=body).status_code == 404


def test_the_ussd_secret_never_reaches_the_access_log() -> None:
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                               ("127.0.0.1:5000", "POST", f"/api/channels/ussd/{TOKEN}", "1.1", 200), None)
    assert RedactUssdSecret().filter(record) and TOKEN not in record.getMessage()
    assert "/api/channels/ussd/[secret]" in record.getMessage()
