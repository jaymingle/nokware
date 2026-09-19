"""USSD: every screen fits, each menu path does what it says, and the callback's secret is checked."""

import json
import logging
import time
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.contacts import CONTACTS_FILE, EMERGENCY_TOPICS
from app.main import RedactChannelSecrets, app
from app.routes import channels
from app.safety_steps import STEPS
from app.services import (
    channel_answers,
    channel_intent,
    channel_limits,
    channel_sessions,
    redis_store,
    report_followups,
    report_intake,
    ussd,
)
from app.services.channel_contacts import numbers_sms
from app.services.citizen_reports import IntakeChannel, NotificationEvent
from app.services.report_contacts import ContactChoice, normalise_phone
from app.services.report_intake import Receipt, ReportSubmission
from app.services.report_rules import Classification, ClassificationMethod
from app.services.report_taxonomy import TOPICS_BY_ID
from app.services.sms_text import is_gsm7, pages
from app.services.ussd import CONFIRM, MENU, SEND, UPDATES_ASK, Dial, sub_metro_screen, ward_screen
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
    monkeypatch.setattr(channel_intent, "is_medical", lambda text: False)  # the quick model, unless a test says otherwise
    return []


def keys(later: list[tuple[Any, ...]], *presses: str, session_id: str = "s1") -> ussd.Reply:
    """Dial, then press each key in turn; the last screen."""
    add = lambda *args: later.append(args)
    reply = ussd.respond(Dial(session_id, PHONE, "*928*1#", True), add)
    for press in presses:
        reply = ussd.respond(Dial(session_id, PHONE, press, False), add)
    return reply


def test_every_fixed_screen_fits_one_plain_screen() -> None:
    screens = [MENU, CONFIRM, SEND, f"Reference M3RD-8WQA received. More numbers: https://nokware.tstitagency.com/contacts/emergency\n{UPDATES_ASK}", ussd.MEDICAL, sub_metro_screen(), *(ward_screen(i) for i in sub_metros()),
               ussd.MEDICAL_REPORT, *(step + ussd.CONTINUE for step in ussd.help_pages("abuse", True)), f"Reference M3RD-8WQA received.\n{ussd.NUMBERS_OFFER}",
               f"The numbers were already sent to this phone today. Keep your reference M3RD-8WQA.\n{ussd.CALL_LIST}"]
    for screen in screens:
        assert len(screen) <= ussd.SCREEN_MAX and is_gsm7(screen), screen


LONG_ANSWER = ("The approved budget for 2026 is GH1 million. Waste management takes GH200,000 of it. "
               "Drains take GH50,000. Street lighting takes GH50,000 more. The rest is staff and offices. "
               "These are approved amounts, not money released or spent, and they come from the 2026 budget.")


def _answering(monkeypatch: pytest.MonkeyPatch, text: str = LONG_ANSWER) -> None:
    monkeypatch.setattr(ussd, "answer_question", lambda question, length: {"answer": text, "status": "answered"})


def test_an_answer_is_read_on_the_screen_and_nothing_is_texted_unless_it_is_asked_for(
        session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    """Reading it costs the resident nothing, so nothing is sent and nothing is capped until they ask for it."""
    _answering(monkeypatch)
    reply = keys(session, "2", "What is AMA's approved budget for 2026?")
    assert reply.more and reply.message.endswith(ussd.MORE_MENU) and session == []


def test_paging_reaches_the_end_of_the_answer_and_loses_none_of_it(
        session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    """The screens a resident reads, joined, are the answer: none is cut and nothing falls between them."""
    _answering(monkeypatch)
    pages, reply = [], keys(session, "2", "What is AMA's approved budget for 2026?")
    while True:
        assert len(reply.message) <= ussd.SCREEN_MAX and "..." not in reply.message
        last = reply.message.endswith(ussd.LAST_MENU)
        pages.append(reply.message.removesuffix(ussd.LAST_MENU if last else ussd.MORE_MENU))
        if last:
            break
        reply = ussd.respond(Dial("s1", PHONE, "1", False), lambda *args: session.append(args))
    assert len(pages) > 1 and " ".join(pages) == channel_answers.flat_text(LONG_ANSWER)


def test_the_cap_falls_on_sending_the_answer_not_on_reading_it(
        session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    """Refused the text, the resident still has the answer in front of them, and the screen says so."""
    _answering(monkeypatch, "Short enough for one screen.")
    monkeypatch.setattr(channel_limits, "SMS_ANSWERS", channel_limits.NumberLimit("sms-answers", 1, 86400))
    assert keys(session, "2", "What are the market fees?", "1", session_id="a").message.startswith("Thank you")
    refused = keys(session, "2", "And the toll fees?", "1", session_id="b")
    assert ussd.REFUSED_SMS in refused.message and refused.message.endswith("\n0 Menu") and refused.more
    assert len(session) == 1


def test_the_answer_goes_by_sms_in_parts_and_a_failure_still_gets_a_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(ussd, "send_sms", lambda to, text: sent.append((to, text)) or True)
    monkeypatch.setattr(ussd, "for_sms", lambda answer, site: ["Nokware: first. (1/2)", "second. (2/2)"])
    monkeypatch.setattr(ussd, "answer_question", lambda q, length: {"status": "answered", "answer": "x"})
    ussd.send_answer_by_sms(PHONE, "What is the budget?")
    assert [text for _, text in sent] == ["Nokware: first. (1/2)", "second. (2/2)"]
    monkeypatch.setattr(ussd, "answer_question", lambda q, length: 1 / 0)
    ussd.send_answer_by_sms(PHONE, "Where is the moon?")
    assert ussd.ANSWER_FAILED in sent[-1][1] and {to for to, _ in sent} == {PHONE}


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
    assert keys(session, "3", "bad").message.startswith("Please describe it")  # too short: asked again
    kaneshie = str(ussd._ward_ids("okaikoi-south").index("kaneshie") + 1)
    reply = keys(session, "3", "The drain at Kaneshie market is choked", "9", "2", kaneshie, "1", session_id="s2")
    assert reply.message == "Report K7QM-4TXP filed with Works Department. We'll SMS you when it's resolved. Keep this reference."
    assert not reply.more
    filed = submitted[0]
    assert (filed.ward, filed.phone, filed.channel, filed.whatsapp) == ("kaneshie", PHONE, IntakeChannel.USSD, None)
    assert session[-1][1:] == (CIVIC, NotificationEvent.SUBMITTED)


def test_filing_without_updates_keeps_the_number_out(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    submitted, submit = _filed(CIVIC, messages_on=False, monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    reply = keys(session, "3", "The drain at Kaneshie market is choked", "2", "1", "2")
    assert submitted[0].phone is None and "We'll SMS" not in reply.message and not session


def test_cancel_files_nothing(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_intake, "read_report", lambda description: _classified("drainage"))
    monkeypatch.setattr(report_intake, "submit", lambda *args: pytest.fail("filed"))
    assert keys(session, "3", "The drain at Kaneshie market is choked", "2", "1", "0").message == "Cancelled. Nothing was filed."


def _contacts(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Any], list[Any]]:
    """What would be kept of the citizen's number: every save and every change, recorded instead of stored."""
    saved: list[Any] = []
    changed: list[Any] = []
    monkeypatch.setattr(ussd, "save_contact", lambda case_id, choice: saved.append((case_id, choice)))
    monkeypatch.setattr(ussd, "update_contact", lambda case_id, changes: changed.append((case_id, changes)))
    monkeypatch.setattr(report_followups, "find", lambda reference: SAFETY)
    return saved, changed


def test_personal_safety_shows_numbers_first_asks_only_the_sub_metro_and_updates_only_on_yes(
    session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    submitted, submit = _filed(SAFETY, messages_on=False, monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    saved, changed = _contacts(monkeypatch)
    first = keys(session, "3", "My neighbour beats his wife every night")
    assert first.message.startswith(ussd.HELP_HEADING + "\nPolice: 191, 18555, 0302 779 300 (HQ)") and first.message.endswith("1 Next")
    shown = [first.message] + [ussd.respond(Dial("s1", PHONE, "1", False), lambda *a: None).message for _ in range(3)]
    assert "DOVVSU (domestic violence): 0551 000 900" in shown[0]
    assert "Helpline of Hope (abuse, children): 0800 800 800" in shown[1] and "Social Welfare: 0550 006 688" in shown[1]
    assert shown[2].startswith("If you can leave now, go to a neighbour") and "ask for DOVVSU" in shown[2]
    assert shown[3].endswith("1 Continue")  # what to do, then on
    place = ussd.respond(Dial("s1", PHONE, "1", False), lambda *a: None)
    assert place.message.startswith("Which sub-metro are you in?") and place.message.endswith("0 Skip")
    assert "electoral area" not in place.message
    confirm = ussd.respond(Dial("s1", PHONE, "2", False), lambda *a: None)  # Okaikoi South: its desk, then the confirm
    assert confirm.message == "Your Social Welfare desk: 0303 935 397\n" + SEND
    assert "SMS" not in confirm.message  # messages are asked about once, after filing, with the reason beside them
    screen = ussd.respond(Dial("s1", PHONE, "1", False), lambda *args: session.append(args))
    assert (submitted[0].ward, submitted[0].sub_metro, submitted[0].phone) == (None, "okaikoi-south", None)  # sent without the number
    assert screen.more and screen.message.startswith("Reference M3RD-8WQA received. More numbers:") and screen.message.endswith(UPDATES_ASK)
    for giveaway in ("Police", "Social Welfare", "abuse", "safety"):
        assert giveaway not in screen.message
    assert saved == []  # nothing kept before they say yes
    call = ussd.respond(Dial("s1", PHONE, "1", False), lambda *args: session.append(args))
    assert call.more and call.message == "Updates are on.\nMay Ghana Police Service or Social Welfare phone you on this number about it?\n1 Yes\n2 No"
    assert saved == [("c2", ContactChoice(normalise_phone(PHONE), None, notify=True, callback_consent=False))]  # updates alone
    assert session == [(ussd.notify_quietly, SAFETY, NotificationEvent.SUBMITTED)]
    offer = ussd.respond(Dial("s1", PHONE, "1", False), lambda *a: None)
    assert offer.more and offer.message == "Done. Ghana Police Service or Social Welfare may phone you.\n" + ussd.NUMBERS_OFFER
    assert changed == [("c2", {"callbackConsent": True})]


def test_saying_no_to_updates_and_calls_keeps_no_number(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    """The first screen used to offer "File, no SMS", which kept no number. One ask after filing must keep that
    promise: a number is stored only because they said yes to something."""
    _, submit = _filed(SAFETY, messages_on=False, monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    saved, changed = _contacts(monkeypatch)
    offer = keys(session, "3", "My husband beats me", *_through_help("abuse"), "0", "1", "2", "2")
    assert offer.message == "No one will phone you.\n" + ussd.NUMBERS_OFFER
    assert saved == [] and changed == [] and session == []


def test_a_call_only_keeps_the_number_for_calls_and_nothing_else(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    _, submit = _filed(SAFETY, messages_on=False, monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    saved, changed = _contacts(monkeypatch)
    keys(session, "3", "My husband beats me", *_through_help("abuse"), "0", "1", "2", "1")
    assert saved == [("c2", ContactChoice(normalise_phone(PHONE), None, notify=False, callback_consent=True))]
    assert changed == [] and session == []  # no messages sent


def test_a_session_that_drops_before_the_question_keeps_no_number(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    """USSD sessions drop, and a phone can be taken mid-session: nothing is kept until an answer is given."""
    submitted, submit = _filed(SAFETY, messages_on=False, monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    saved, changed = _contacts(monkeypatch)
    receipt = keys(session, "3", "My husband beats me", *_through_help("abuse"), "0", "1")
    assert receipt.message.endswith(UPDATES_ASK) and submitted[0].phone is None and saved == [] and changed == []


def test_a_safety_reporter_can_skip_the_sub_metro(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    submitted, submit = _filed(SAFETY, messages_on=False, monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    confirm = keys(session, "3", "Someone has threatened to kill me", *_through_help("threat_to_life"), "0")
    assert confirm.message == SEND  # no desk to show
    receipt = ussd.respond(Dial("s1", PHONE, "1", False), lambda *a: None)
    assert (submitted[0].ward, submitted[0].sub_metro) == (None, None)
    assert receipt.more and receipt.message.startswith("Reference M3RD-8WQA received.") and receipt.message.endswith(UPDATES_ASK)


def _through_help(topic: str) -> list[str]:
    return ["1"] * len(ussd.help_pages(topic, TOPICS_BY_ID[topic].category == "personal_safety"))


def test_every_emergency_shows_every_number_to_call_on_screens_that_fit(session: list[tuple[Any, ...]]) -> None:
    expected = {"fire": ("192", "0299 340 383", "193"), "disaster": ("0302 964 884", "193"), "road_accident": ("191", "18555", "193"),
                "public_crime": ("191", "0302 779 300"), "child_at_risk": ("0800 800 800", "0550 006 688", "0501 614 877", "0551 000 900")}
    for topic in EMERGENCY_TOPICS:
        private = TOPICS_BY_ID[topic].category == "personal_safety"
        pages = ussd.help_pages(topic, private)
        assert pages[0].startswith(ussd.HELP_HEADING), topic
        for page in pages:
            assert len(page + ussd.CONTINUE) <= ussd.SCREEN_MAX and is_gsm7(page), (topic, page)
        assert all(number in "\n".join(pages) for number in expected.get(topic, ("112",))), topic
        assert (STEPS[0] in "\n".join(pages)) == private and len(pages) <= 4, topic  # two of numbers, two of steps
    assert ussd.help_pages("drainage", False) == []
    assert len(ussd.safety_sub_metro_screen()) <= ussd.SCREEN_MAX


def _offered(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch, session_id: str) -> ussd.Reply:
    _, submit = _filed({**SAFETY, "subMetro": "ashiedu-keteke"}, messages_on=False, monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    # Ashiedu Keteke, send, no updates, no calls: then the numbers are offered.
    return keys(session, "3", "My husband beats me", *_through_help("abuse"), "1", "1", "2", "2", session_id=session_id)


def test_the_numbers_go_by_sms_only_when_asked_for(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    assert _offered(session, monkeypatch, "no").more
    declined = ussd.respond(Dial("no", PHONE, "2", False), lambda *args: session.append(args))
    assert declined == ussd.Reply(f"No SMS sent. Keep your reference M3RD-8WQA.\n{ussd.CALL_LIST}", False) and not session
    _offered(session, monkeypatch, "yes")
    assert ussd.respond(Dial("yes", PHONE, "9", False), lambda *a: None).message.startswith("Choose 1 or 2.")
    sent = ussd.respond(Dial("yes", PHONE, "1", False), lambda *args: session.append(args))
    assert sent.message.startswith("The numbers are on their way by SMS. Keep your reference M3RD-8WQA.") and not sent.more
    (send, to, text), = session
    assert (send, to) == (ussd.send_sms, PHONE) and "Social Welfare: 0553 260 046, head office 0550 006 688" in text
    assert "DOVVSU: 0551 000 900" in text
    assert text.startswith("Call 112 first.") and pages(text) <= 2 and is_gsm7(text)
    for giveaway in ("abuse", "violence", "children", "danger", "Nokware"):
        assert giveaway not in text  # the sender says who it's from; nothing says why


def test_the_numbers_sms_is_limited_per_phone(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_limits, "NUMBERS_SMS", channel_limits.NumberLimit("numbers-sms", 1, 86400))
    for session_id in ("a", "b"):
        _offered(session, monkeypatch, session_id)
        last = ussd.respond(Dial(session_id, PHONE, "1", False), lambda *args: session.append(args))
    assert len(session) == 1 and last.message.startswith("The numbers were already sent to this phone today.")


def test_every_numbers_sms_fits_two_pages() -> None:
    for topic in EMERGENCY_TOPICS:
        for sub_metro in (None, *sub_metros()):
            text = numbers_sms(topic, sub_metro)
            assert pages(text) <= 2 and is_gsm7(text), (topic, sub_metro)


def test_a_slow_safety_filing_still_offers_the_numbers(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ussd, "FILING_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(report_intake, "read_report", lambda description: _classified("abuse"))
    monkeypatch.setattr(report_intake, "submit", lambda *args: time.sleep(0.3) or Receipt(SAFETY, False, False, None))
    monkeypatch.setattr(ussd, "send_sms", lambda to, text: True)
    slow = keys(session, "3", "My husband beats me", *_through_help("abuse"), "0", "1")
    assert slow.message == "Your report is being filed. Your reference will come by SMS.\n" + ussd.NUMBERS_OFFER
    done = ussd.respond(Dial("s1", PHONE, "1", False), lambda *args: session.append(args))
    assert done.message == f"The numbers are on their way by SMS.\n{ussd.CALL_LIST}" and session[0][0] is ussd.send_sms


def test_a_slow_model_leaves_the_rules_to_decide_and_they_still_catch_danger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ussd, "CLASSIFY_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(report_intake, "read_report", lambda description: time.sleep(0.3) or _classified("drainage"))
    assert ussd._read("He beats her and she fears for her life").private
    assert ussd._read("The gutter by the school is blocked").topic == "other_civic"  # triage: a person routes it


def test_checking_a_case_shows_its_status_in_one_screen(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_followups, "find", lambda ref: CIVIC if ref == "K7QM-4TXP" else (_ for _ in ()).throw(report_followups.CaseNotFound(ref)))
    monkeypatch.setattr(ussd.report_store, "assignments_for", lambda case_id: [])
    monkeypatch.setattr(report_followups, "history_for", lambda case: [])
    status = {"reference": "K7QM-4TXP", "private": False, "status": "in_progress", "topic": "Drainage and flooding",
              "ward": "Kaneshie", "recipients": ["Works Department"]}
    monkeypatch.setattr(report_followups, "public_status", lambda case, assignments, now, history=None: status)
    assert keys(session, "4", "k7qm 4txp").message == "Report K7QM-4TXP (Drainage and flooding in Kaneshie) is in progress with Works Department."
    assert keys(session, "4", "hello", session_id="x").more  # not a reference: asked again
    assert keys(session, "4", "ZZZZ-2222", session_id="y").message.startswith("No case has the reference ZZZZ-2222")


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
    assert RedactChannelSecrets().filter(record) and TOKEN not in record.getMessage()
    assert "/api/channels/ussd/[secret]" in record.getMessage()


def test_emergency_numbers_lead_the_menu_and_say_first_that_nothing_is_filed(
    session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two taps to an ambulance is a service even though Nokware does nothing with it — but nobody in an emergency
    should read past "Ask a question" to reach it, and nobody should think a report was filed."""
    monkeypatch.setattr(report_intake, "submit", lambda *args: pytest.fail("filed"))
    reply = keys(session, "1")
    assert not reply.more and reply.message.startswith("Numbers to call now. Nokware gives them; it can't send help.")
    for number in ("112", "193", "191", "192"):
        assert number in reply.message
    assert len(reply.message) <= ussd.SCREEN_MAX and ussd.MENU.splitlines()[1] == "1 Emergency numbers"


def test_more_numbers_point_to_the_emergency_page_not_the_directory(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    _, submit = _filed(SAFETY, messages_on=False, token="one-time", monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    receipt = keys(session, "3", "My husband beats me", *_through_help("abuse"), "0", "1")
    assert receipt.message.split("More numbers: ")[1].startswith("http://localhost:3000/contacts/emergency")


def test_a_ussd_session_from_an_older_version_ends_cleanly(session: list[tuple[Any, ...]]) -> None:
    channel_sessions.save("ussd", "old", {"step": "retired-step"}, 60)
    assert ussd.respond(Dial("old", PHONE, "1", False), lambda *a: None) == ussd.Reply("Your session ended. Please dial again.", False)
    assert channel_sessions.load("ussd", "old") is None


def test_the_medical_screens_give_the_ambulance_numbers_in_contacts_json() -> None:
    listed = {c["id"]: [n["number"] for n in c["numbers"]] for c in json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))["contacts"]}
    ambulance, emergency = [*listed["ambulance-193"], *listed["nas"]], listed["emergency-112"][0]
    assert f"Ambulance: {', '.join(ambulance)}. Or call {emergency}." in ussd.MEDICAL
    assert f"Ambulance: {', '.join(ambulance)}, or {emergency}." in ussd.MEDICAL_REPORT
    assert f"Nothing was filed. Ambulance: {ambulance[0]}, or call {emergency}." == ussd.MEDICAL_NOT_FILED


def test_a_medical_emergency_described_as_a_report_gets_the_ambulance_and_is_not_filed(
    session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(report_intake, "read_report", lambda description: _classified("public_health"))
    monkeypatch.setattr(channel_intent, "is_medical", lambda text: "collapsed" in text)
    monkeypatch.setattr(report_intake, "submit", lambda *args: pytest.fail("filed"))
    screen = keys(session, "3", "A man has collapsed at Kaneshie market and is not breathing")
    assert screen.more and screen.message == ussd.MEDICAL_REPORT and "193" in screen.message and "112" in screen.message
    assert keys(session, "3", "A man has collapsed at Kaneshie market", "0").message.startswith("Nothing was filed.")


def test_a_citizen_can_file_what_the_model_took_for_medical(session: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_intent, "is_medical", lambda text: True)
    submitted, submit = _filed(SAFETY, messages_on=False, monkeypatch=monkeypatch)
    monkeypatch.setattr(report_intake, "submit", submit)
    first = keys(session, "3", "My husband hit me and I am bleeding", "1")
    assert first.message.startswith(ussd.HELP_HEADING)  # the emergency numbers, as for any danger to a person
    keys(session, "3", "My husband hit me and I am bleeding", "1", *_through_help("abuse"), "0", "1", session_id="s2")
    assert submitted and submitted[0].sub_metro is None


def test_the_medical_check_waits_no_longer_than_the_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ussd, "CLASSIFY_WAIT_SECONDS", 0.05)
    slow = ussd._filing.submit(lambda: time.sleep(0.3) or True)
    assert ussd._medical_now(slow, time.monotonic()) is False  # unknown in time: the report goes on
    assert ussd._medical_now(ussd._filing.submit(lambda: True), time.monotonic()) is True
