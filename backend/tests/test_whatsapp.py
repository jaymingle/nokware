"""WhatsApp: Twilio's API and signatures, the 24-hour window and its SMS fallback, and every conversation path."""

import io
from typing import Any
from urllib.parse import parse_qsl

import fakeredis
import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.main import app
from app.routes import channels
from app.services import (
    channel_limits,
    channel_sessions,
    notifications,
    redis_store,
    report_followups,
    report_intake,
    whatsapp,
    whatsapp_conversation,
    whatsapp_reply,
    whatsapp_safety,
)
from app.services.channel_intent import Intent, Reading
from app.services.citizen_reports import IntakeChannel, NotificationChannel, NotificationEvent
from app.services.report_intake import Receipt, ReportSubmission
from app.services.report_rules import Classification, ClassificationMethod
from app.services.report_taxonomy import TOPICS_BY_ID, Category
from app.services.whatsapp import TwilioWhatsApp, WhatsAppError, split
from app.services.whatsapp_conversation import ASK_KIND, CANCELLED, Inbound, Media

NUMBER = "+233507387216"
TOKEN = "twilio-auth-token"
PUBLIC = "https://nokware.example.org"
CIVIC = {"$id": "c1", "reference": "K7QM-4TXP", "category": "civic_service", "topic": "drainage", "isSensitive": False,
         "recipients": ["dept-works"]}
SAFETY = {"$id": "c2", "reference": "M3RD-8WQA", "category": "personal_safety", "topic": "abuse", "isSensitive": True,
          "recipients": ["agency-police", "dept-social-welfare"]}


@pytest.fixture
def redis_server(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    server = fakeredis.FakeRedis(decode_responses=True)
    for module in (redis_store, channel_sessions, channel_limits, whatsapp, whatsapp_conversation):
        monkeypatch.setattr(module, "get_redis", lambda: server)
    return server


def _settings(monkeypatch: pytest.MonkeyPatch, **update: Any) -> None:
    settings = get_settings().model_copy(update={"twilio_auth_token": TOKEN, "public_api_url": PUBLIC, **update})
    for module in (whatsapp, notifications, channels):
        monkeypatch.setattr(module, "get_settings", lambda: settings)


def test_a_long_reply_splits_between_paragraphs() -> None:
    text = "\n\n".join(f"Paragraph {n}. " + "word " * 60 for n in range(8))
    pieces = split(text)
    assert len(pieces) > 1 and all(len(piece) <= 1600 for piece in pieces)
    assert all(piece.startswith("Paragraph") for piece in pieces) and "".join(pieces).count("Paragraph") == 8


def test_a_message_is_posted_to_twilio_with_the_status_callback() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"sid": "SM1", "status": "queued"})

    client = TwilioWhatsApp("AC1", TOKEN, "whatsapp:+14155238886", f"{PUBLIC}/api/channels/whatsapp/status",
                            httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.send(NUMBER, "Hello") == "SM1"
    form = dict(parse_qsl(seen[0].content.decode()))
    assert form == {"From": "whatsapp:+14155238886", "To": f"whatsapp:{NUMBER}", "Body": "Hello",
                    "StatusCallback": f"{PUBLIC}/api/channels/whatsapp/status"}
    assert seen[0].url.path == "/2010-04-01/Accounts/AC1/Messages.json" and seen[0].headers["authorization"].startswith("Basic ")
    refusing = TwilioWhatsApp("AC1", TOKEN, "whatsapp:+1", client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(401, json={"code": 20003, "message": "Authenticate"}))))
    with pytest.raises(WhatsAppError, match="20003"):
        refusing.send(NUMBER, "Hello")


def test_only_twilios_signature_for_our_public_url_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    params = {"From": f"whatsapp:{NUMBER}", "Body": "Hello", "MessageSid": "SM2"}
    signature = RequestValidator(TOKEN).compute_signature(f"{PUBLIC}/api/channels/whatsapp", params)
    assert whatsapp.signed_by_twilio("/api/channels/whatsapp", params, signature)
    assert not whatsapp.signed_by_twilio("/api/channels/whatsapp", {**params, "Body": "Changed"}, signature)
    assert not whatsapp.signed_by_twilio("/api/channels/whatsapp/status", params, signature)
    _settings(monkeypatch, public_api_url="")
    assert not whatsapp.signed_by_twilio("/api/channels/whatsapp", params, signature)


def test_the_window_opens_when_the_citizen_writes_and_a_repeat_is_seen(redis_server: fakeredis.FakeRedis) -> None:
    assert not whatsapp.window_open(NUMBER)
    whatsapp.open_window(NUMBER)
    assert whatsapp.window_open(NUMBER) and not whatsapp.window_open("+233241234567")
    assert whatsapp.first_delivery("SM3") and not whatsapp.first_delivery("SM3")


def _capture_sends(monkeypatch: pytest.MonkeyPatch, contact: dict[str, Any]) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(notifications, "contact_for", lambda case_id: contact)
    monkeypatch.setattr(notifications, "_send", lambda case_id, event, channel, number, message, why="": sent.append((channel.value, why)))
    return sent


@pytest.mark.parametrize(("window", "contact", "provider", "expected"), [
    (False, {"notify": True, "whatsapp": NUMBER}, "twilio", [("sms", notifications.WINDOW_CLOSED)]),
    (True, {"notify": True, "whatsapp": NUMBER}, "twilio", [("whatsapp", "")]),
    (False, {"notify": True, "whatsapp": "+447700900123"}, "twilio", [("whatsapp", "")]),  # not Ghanaian: no fallback
    (False, {"notify": True, "whatsapp": NUMBER, "phone": NUMBER}, "twilio", [("sms", ""), ("whatsapp", "")]),  # has SMS
    (False, {"notify": True, "whatsapp": NUMBER}, "log", [("whatsapp", "")]),
])
def test_a_whatsapp_update_goes_by_sms_only_when_whatsapp_cannot_carry_it(
    monkeypatch: pytest.MonkeyPatch, window: bool, contact: dict[str, Any], provider: str, expected: list[tuple[str, str]]
) -> None:
    _settings(monkeypatch, whatsapp_provider=provider)
    monkeypatch.setattr(notifications, "window_open", lambda number: window)
    sent = _capture_sends(monkeypatch, contact)
    notifications.notify(CIVIC, NotificationEvent.RESOLVED)
    assert sent == expected


def test_twilios_window_error_sends_the_update_by_sms_once(monkeypatch: pytest.MonkeyPatch, redis_server: fakeredis.FakeRedis) -> None:
    _settings(monkeypatch, whatsapp_provider="twilio")
    sent = _capture_sends(monkeypatch, {"notify": True, "whatsapp": NUMBER})
    row = {"$id": "n1", "caseId": "c1", "channel": "whatsapp", "event": "resolved", "template": "resolved", "body": "Resolved."}
    monkeypatch.setattr(notifications, "_outbox_row", lambda sid: row)
    assert not notifications.whatsapp_undelivered("SM4", "63001")
    assert notifications.whatsapp_undelivered("SM4", "63016")
    assert not notifications.whatsapp_undelivered("SM4", "63016")  # a repeated callback
    assert sent == [("sms", notifications.WINDOW_CLOSED)]


def _signed_post(client: TestClient, path: str, form: dict[str, str]) -> httpx.Response:
    signature = RequestValidator(TOKEN).compute_signature(f"{PUBLIC}{path}", form)
    return client.post(path, data=form, headers={"X-Twilio-Signature": signature})


def test_the_webhook_answers_twilio_at_once_and_handles_the_message_after(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    handled: list[Inbound] = []
    monkeypatch.setattr(whatsapp_conversation, "handle", handled.append)
    client = TestClient(app)
    form = {"From": f"whatsapp:{NUMBER}", "Body": "Hello", "MessageSid": "SM5", "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/ME1", "MediaContentType0": "image/jpeg"}
    assert client.post("/api/channels/whatsapp", data=form).status_code == 403
    response = _signed_post(client, "/api/channels/whatsapp", form)
    assert response.status_code == 200 and "<Response></Response>" in response.text
    assert handled == [Inbound(NUMBER, "Hello", Media("https://api.twilio.com/media/ME1", "image/jpeg"), "SM5")]


def test_the_status_callback_records_delivery_and_falls_back_on_the_window_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    calls: list[Any] = []
    monkeypatch.setattr(notifications, "record_delivery", lambda sid, status, now: calls.append((sid, status)) or True)
    monkeypatch.setattr(notifications, "whatsapp_undelivered", lambda sid, code: calls.append(("fallback", code)) or True)
    client = TestClient(app)
    assert _signed_post(client, "/api/channels/whatsapp/status", {"MessageSid": "SM6", "MessageStatus": "delivered"}).json() == {"recorded": True}
    _signed_post(client, "/api/channels/whatsapp/status", {"MessageSid": "SM7", "MessageStatus": "undelivered", "ErrorCode": "63016"})
    assert calls == [("SM6", "delivered"), ("SM7", "undelivered"), ("fallback", "63016")]


@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch, redis_server: fakeredis.FakeRedis) -> list[str]:
    replies: list[str] = []
    monkeypatch.setattr(whatsapp_reply, "reply", lambda number, text: replies.append(text))
    return replies


def say(text: str = "", media: Media | None = None, sid: list[int] = [0]) -> None:  # noqa: B006
    sid[0] += 1
    whatsapp_conversation.handle(Inbound(NUMBER, text, media, f"SM-{sid[0]}"))


def _reads(monkeypatch: pytest.MonkeyPatch, intent: str) -> None:
    """The router's verdict, without the model."""
    monkeypatch.setattr(whatsapp_conversation, "read_message", lambda text, has_photo=False: Reading(Intent(intent)))


def _classified(topic: str) -> Classification:
    found = TOPICS_BY_ID[topic]
    return Classification(found.category, topic, 5 if found.category == Category.PERSONAL_SAFETY else 3, found.recipients, ClassificationMethod.AI)


def _filing(monkeypatch: pytest.MonkeyPatch, case: dict[str, Any], token: str | None = None, topic: str = "drainage") -> list[tuple[ReportSubmission, list[bytes]]]:
    filed: list[tuple[ReportSubmission, list[bytes]]] = []
    monkeypatch.setattr(report_intake, "read_report", lambda description: _classified(topic))

    def submit(submission: ReportSubmission, photos: list[bytes], now: Any, classification: Classification | None = None) -> Receipt:
        assert classification == _classified(topic)  # filed as it was read: the model isn't asked twice
        filed.append((submission, photos))
        private = case["isSensitive"]
        return Receipt(case=case, messages_on=not private, held_for_consent=private and token is not None, preferences_token=token)

    monkeypatch.setattr(report_intake, "submit", submit)
    return filed


def test_a_question_gets_a_cited_chat_answer(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    _reads(monkeypatch, "question")
    asked: list[Any] = []
    monkeypatch.setattr(whatsapp_conversation, "answer_question", lambda q, length: asked.append((q, length)) or {"status": "no_information"})
    say("What does AMA charge for a market stall?")
    assert asked[0][0] == "What does AMA charge for a market stall?" and asked[0][1].value == "chat"
    assert "don't have information" in chat[0]


def test_a_report_naming_its_area_is_confirmed_then_filed_from_this_number(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    _reads(monkeypatch, "report")
    filed = _filing(monkeypatch, CIVIC)
    say("The drain at Kaneshie market is choked")
    assert chat[-1].startswith("Ready to file your report about Kaneshie.") and not filed
    say("1")
    submission, photos = filed[0]
    assert (submission.ward, submission.whatsapp, submission.phone, submission.channel) == ("kaneshie", NUMBER, None, IntakeChannel.WHATSAPP)
    assert photos == [] and chat[-1].startswith("Filed. Your reference is *K7QM-4TXP*.\nIt is with Works Department.")
    assert channel_sessions.load("whatsapp", NUMBER) is None


def test_a_report_without_an_area_asks_for_one_and_can_be_cancelled(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    _reads(monkeypatch, "report")
    filed = _filing(monkeypatch, CIVIC)
    say("The streetlight outside the school is out")
    assert chat[-1].startswith("Which electoral area is it in?")
    say("Nowhere town")
    assert "couldn't match" in chat[-1]
    say("it's in bubuashie")
    assert chat[-1].startswith("Ready to file your report about Bubiashie.")
    say("2")
    assert chat[-1] == CANCELLED and not filed


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "teal").save(buffer, "JPEG")
    return buffer.getvalue()


def test_a_photo_starts_a_draft_is_deleted_from_twilio_and_goes_with_the_report(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    _reads(monkeypatch, "report")
    filed = _filing(monkeypatch, CIVIC)
    deleted: list[str] = []

    class FakeTwilio:
        def download(self, url: str) -> tuple[bytes, str]:
            return _jpeg(), "image/jpeg"

        def delete_media(self, url: str) -> None:
            deleted.append(url)

    monkeypatch.setattr(whatsapp_conversation, "twilio", lambda: FakeTwilio())
    say("", Media("https://api.twilio.com/media/ME9", "image/jpeg"))
    assert chat[-1].startswith("Describe the problem") and deleted == ["https://api.twilio.com/media/ME9"]
    say("Rubbish dumped by the Kaneshie footbridge")
    assert "with 1 photo." in chat[-1]
    say("1")
    assert len(filed[0][1]) == 1 and filed[0][1][0][:2] == b"\xff\xd8"  # the cleaned JPEG
    assert whatsapp_conversation.draft_photos(NUMBER) == []


def test_unclear_asks_question_or_report_and_uses_the_first_message(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    _reads(monkeypatch, "unclear")
    asked: list[str] = []
    monkeypatch.setattr(whatsapp_conversation, "answer_question", lambda q, length: asked.append(q) or {"status": "no_information"})
    say("market tolls")
    assert chat[-1] == ASK_KIND
    say("1")
    assert asked == ["market tolls"]


def test_personal_safety_gets_every_number_first_and_only_a_sub_metro_question(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    _reads(monkeypatch, "report")
    filed = _filing(monkeypatch, SAFETY, token="one-time", topic="abuse")
    chosen: list[Any] = []
    monkeypatch.setattr(report_followups, "set_preferences", lambda ref, token, choice, now: chosen.append((ref, token, choice.notify)) or (SAFETY, choice.notify))
    say("My husband beats me every night")
    first = chat[-1]
    assert first.startswith("*If anyone is in danger now*") and "0800 800 800" in first and "0591 476 884" in first
    assert first.index("0800 800 800") < first.index("Which sub-metro are you in?")  # the numbers come before any question
    assert "*DOVVSU (domestic violence)*\n0551 000 900" in first
    steps = first.index("*What to do now*\n- If you can leave now, go to a neighbour, family, or the nearest police station.")
    assert first.index("0800 800 800") < steps < first.index("Which sub-metro are you in?") and "ask for DOVVSU" in first
    assert "electoral area" not in first and "Assembly Member" not in first
    say("2")  # Okaikoi South
    assert chat[-1].startswith("Ready to send your report to Ghana Police Service and Social Welfare. You can send photos first: only they will see them.")
    say("1")
    submission = filed[0][0]
    assert (submission.ward, submission.sub_metro, submission.whatsapp) == (None, "okaikoi-south", NUMBER)
    receipt = chat[-1]
    assert receipt.startswith("This has gone to Ghana Police Service and Social Welfare. Your reference is *M3RD-8WQA*.")
    assert "*CALL*" in receipt and "*PLACE*" in receipt and "*YES*" in receipt and "Assembly" not in receipt
    say("yes")
    assert chosen == [("M3RD-8WQA", "one-time", True)] and chat[-1] == "Updates are on for M3RD-8WQA."


def test_an_area_named_in_a_safety_report_is_kept_only_as_its_sub_metro(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    _reads(monkeypatch, "report")
    filed = _filing(monkeypatch, SAFETY, topic="abuse")
    say("My neighbour in Kaneshie beats his wife and I fear for her")
    assert "Which sub-metro" not in chat[-1] and "0303 935 397 (Okaikoi South desk)" in chat[-1]  # their desk, from the area
    say("1")
    assert (filed[0][0].ward, filed[0][0].sub_metro) == (None, "okaikoi-south")
    assert "kaneshie" not in str(channel_sessions.load("whatsapp", NUMBER))


def test_a_safety_reporter_can_skip_the_sub_metro(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    _reads(monkeypatch, "report")
    filed = _filing(monkeypatch, SAFETY, topic="threat_to_life")
    say("Someone has threatened to kill me")
    say("0")
    say("1")
    assert (filed[0][0].ward, filed[0][0].sub_metro) == (None, None)


def test_a_fire_gets_its_numbers_first_then_the_area_question(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    _reads(monkeypatch, "report")
    _filing(monkeypatch, {**CIVIC, "category": "public_safety", "topic": "fire", "recipients": ["agency-gnfs"]}, topic="fire")
    say("A house is on fire near the market")
    assert chat[-1].startswith("*If anyone is in danger now*") and "*Fire service*\n192" in chat[-1]
    assert chat[-1].endswith("Reply with its name, for example Kaneshie or Bubiashie.")
    assert "What to do now" not in chat[-1]  # the steps are for a danger to a person


def test_a_reference_gets_its_status(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    monkeypatch.setattr(report_followups, "find", lambda ref: CIVIC)
    monkeypatch.setattr(whatsapp_conversation.report_store, "assignments_for", lambda case_id: [])
    status = {"reference": "K7QM-4TXP", "private": False, "status": "assigned", "topic": "Drainage and flooding",
              "ward": "Kaneshie", "recipients": ["Works Department"]}
    monkeypatch.setattr(report_followups, "public_status", lambda case, assignments, now: status)
    say("K7QM-4TXP")
    assert chat[-1] == "Report K7QM-4TXP (Drainage and flooding in Kaneshie) was received and is with Works Department."


def test_files_other_than_photos_and_voice_notes_are_turned_away_and_a_repeat_is_ignored(chat: list[str]) -> None:
    say("", Media("https://api.twilio.com/media/ME11", "application/pdf"))
    assert chat == ["Only photos and voice notes can be read. Please type your message."]
    whatsapp_conversation.handle(Inbound(NUMBER, "", Media("u", "application/pdf"), "SM-repeat"))
    whatsapp_conversation.handle(Inbound(NUMBER, "", Media("u", "application/pdf"), "SM-repeat"))
    assert len(chat) == 2


def test_replies_go_by_twilio_in_pieces_of_1600(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    class Provider:
        name, delivers = "twilio", True

        def send(self, to: str, body: str) -> str:
            sent.append(body)
            return "SM"

    monkeypatch.setattr(whatsapp_reply, "provider_for", lambda channel: Provider() if channel == NotificationChannel.WHATSAPP else None)
    whatsapp_reply.reply(NUMBER, "\n\n".join("word " * 100 for _ in range(6)))
    assert len(sent) == 2 and all(len(piece) <= 1600 for piece in sent)


def test_thanks_gets_no_reply(chat: list[str]) -> None:
    say("Thank you!")
    assert chat == []


@pytest.fixture
def filed_safety(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> dict[str, Any]:
    """A personal-safety report just filed on WhatsApp; the contact record and Twilio's log faked."""
    _reads(monkeypatch, "report")
    _filing(monkeypatch, SAFETY, token="one-time", topic="abuse")
    effects: dict[str, Any] = {"contact": {}, "shared": [], "deleted": [], "removed": True}
    monkeypatch.setattr(whatsapp_safety, "update_contact", lambda case_id, changes: effects["contact"].update(changes))
    monkeypatch.setattr(whatsapp_safety.report_locations, "share", lambda *args: effects["shared"].append(args[:4]))
    monkeypatch.setattr(whatsapp_safety.report_locations, "remove", lambda case_id: effects["removed"])

    class FakeTwilio:
        def delete_message(self, sid: str) -> None:
            effects["deleted"].append(sid)

    monkeypatch.setattr(whatsapp_safety, "twilio", lambda: FakeTwilio())
    say("My husband beats me every night")
    say("0")
    say("1")
    return effects


def test_call_lets_the_responders_phone_and_is_apart_from_updates(filed_safety: dict[str, Any], chat: list[str]) -> None:
    say("CALL")
    assert filed_safety["contact"] == {"callbackConsent": True}
    assert chat[-1] == "Done. Ghana Police Service or Social Welfare may phone you on this number about this report."


def test_place_takes_a_pin_stores_it_apart_and_deletes_the_message_from_twilio(filed_safety: dict[str, Any], chat: list[str]) -> None:
    say("PLACE")
    assert "location button" in chat[-1] and "never the MCE" in chat[-1] and "deleted 30 days after" in chat[-1]
    whatsapp_conversation.handle(Inbound(NUMBER, "", None, "SM-pin", latitude=5.567, longitude=-0.235, place="Kaneshie clinic"))
    assert filed_safety["shared"] == [("c2", "Kaneshie clinic", 5.567, -0.235)] and filed_safety["deleted"] == ["SM-pin"]
    assert chat[-1].startswith("Saved. Only the Police and Social Welfare handling your report can see it")
    assert "Kaneshie" not in str(channel_sessions.load("whatsapp", NUMBER))  # never kept in Redis


def test_place_takes_a_typed_address_or_can_be_left(filed_safety: dict[str, Any], chat: list[str]) -> None:
    say("PLACE")
    say("0")
    assert chat[-1] == "No location was shared." and not filed_safety["shared"]
    say("PLACE")
    say("House 12, behind the market clinic")
    assert filed_safety["shared"] == [("c2", "House 12, behind the market clinic", None, None)]


def test_remove_confirms_only_when_the_location_is_gone(filed_safety: dict[str, Any], chat: list[str]) -> None:
    say("REMOVE")
    assert chat[-1] == "Your location has been deleted. The Police and Social Welfare can no longer see it."
    filed_safety["removed"] = False
    say("remove")
    assert "couldn't be deleted" in chat[-1]


def test_after_the_hour_the_choices_are_gone(filed_safety: dict[str, Any], chat: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    channel_sessions.clear("whatsapp", NUMBER)  # the hour's state has expired
    _reads(monkeypatch, "unclear")
    say("CALL")
    assert chat[-1] == ASK_KIND and filed_safety["contact"] == {}


def test_a_location_from_whatsapps_button_arrives_as_a_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    handled: list[Inbound] = []
    monkeypatch.setattr(whatsapp_conversation, "handle", handled.append)
    form = {"From": f"whatsapp:{NUMBER}", "Body": "", "MessageSid": "SM-loc", "NumMedia": "0",
            "Latitude": "5.567", "Longitude": "-0.235", "Address": "Kaneshie clinic"}
    assert _signed_post(TestClient(app), "/api/channels/whatsapp", form).status_code == 200
    assert (handled[0].latitude, handled[0].longitude, handled[0].place) == (5.567, -0.235, "Kaneshie clinic")


def test_someone_ill_gets_the_ambulance_numbers_and_nothing_is_filed(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    _reads(monkeypatch, "medical")
    monkeypatch.setattr(report_intake, "submit", lambda *args: pytest.fail("filed"))
    say("My father has collapsed and isn't breathing properly")
    assert chat[-1].startswith("This isn't something the Assembly can act on") and "193" in chat[-1]
    assert channel_sessions.load("whatsapp", NUMBER) is None


def test_a_session_from_an_older_version_starts_again_instead_of_failing(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    channel_sessions.save("whatsapp", NUMBER, {"step": "updates", "reference": "OLD1-OLD1"}, 3600)
    _reads(monkeypatch, "unclear")
    say("hello there, is anyone reading this")
    assert chat[-1] == ASK_KIND and channel_sessions.load("whatsapp", NUMBER) == {"step": "kind", "text": "hello there, is anyone reading this"}


def test_the_hourly_report_limit_never_turns_away_someone_in_danger(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    monkeypatch.setattr(channel_limits, "REPORTS", channel_limits.NumberLimit("reports", 0, 3600))  # already used up
    _reads(monkeypatch, "report")
    filed = _filing(monkeypatch, SAFETY, topic="abuse")
    say("My husband beats me every night")
    say("0")
    say("1")
    assert len(filed) == 1 and chat[-1].startswith("This has gone to")
