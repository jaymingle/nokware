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
)
from app.services.channel_intent import Intent, Reading
from app.services.citizen_reports import IntakeChannel, NotificationChannel, NotificationEvent
from app.services.report_intake import Receipt, ReportSubmission
from app.services.whatsapp import TwilioWhatsApp, WhatsAppError, split
from app.services.whatsapp_conversation import ASK_KIND, CANCELLED, Inbound, Media

NUMBER = "+233507387216"
TOKEN = "twilio-auth-token"
PUBLIC = "https://nokware.example.org"
CIVIC = {"$id": "c1", "reference": "K7QM-4TXP", "category": "civic_service", "isSensitive": False, "recipients": ["dept-works"]}
SAFETY = {"$id": "c2", "reference": "M3RD-8WQA", "category": "personal_safety", "isSensitive": True,
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


# The conversation: Redis faked, replies collected, the models and Twilio stubbed.

@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch, redis_server: fakeredis.FakeRedis) -> list[str]:
    replies: list[str] = []
    monkeypatch.setattr(whatsapp_conversation, "reply", lambda number, text: replies.append(text))
    return replies


def say(text: str = "", media: Media | None = None, sid: list[int] = [0]) -> None:  # noqa: B006
    sid[0] += 1
    whatsapp_conversation.handle(Inbound(NUMBER, text, media, f"SM-{sid[0]}"))


def _reads(monkeypatch: pytest.MonkeyPatch, intent: str) -> None:
    """The router's verdict, without the model."""
    monkeypatch.setattr(whatsapp_conversation, "read_message", lambda text, has_photo=False: Reading(Intent(intent)))


def _filing(monkeypatch: pytest.MonkeyPatch, case: dict[str, Any], token: str | None = None) -> list[tuple[ReportSubmission, list[bytes]]]:
    filed: list[tuple[ReportSubmission, list[bytes]]] = []

    def submit(submission: ReportSubmission, photos: list[bytes], now: Any) -> Receipt:
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


def test_personal_safety_gets_a_neutral_receipt_and_updates_only_on_yes(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    _reads(monkeypatch, "report")
    _filing(monkeypatch, SAFETY, token="one-time")
    chosen: list[Any] = []
    monkeypatch.setattr(report_followups, "set_preferences", lambda ref, token, choice, now: chosen.append((ref, token, choice.notify)) or (SAFETY, choice.notify))
    say("My neighbour beats his wife every night in Kaneshie")
    say("1")
    receipt = chat[-1]
    assert receipt.startswith("Your reference is *M3RD-8WQA*. In danger now? Call 112.") and "Reply *YES*" in receipt
    for giveaway in ("Police", "Social Welfare", "abuse", "safety"):
        assert giveaway not in receipt
    say("yes")
    assert chosen == [("M3RD-8WQA", "one-time", True)] and chat[-1] == "Updates are on for M3RD-8WQA."


def test_a_reference_gets_its_status(monkeypatch: pytest.MonkeyPatch, chat: list[str]) -> None:
    monkeypatch.setattr(report_followups, "find", lambda ref: CIVIC)
    monkeypatch.setattr(whatsapp_conversation.report_store, "assignments_for", lambda case_id: [])
    status = {"reference": "K7QM-4TXP", "private": False, "status": "assigned", "topic": "Drainage and flooding",
              "ward": "Kaneshie", "recipients": ["Works Department"]}
    monkeypatch.setattr(report_followups, "public_status", lambda case, assignments, now: status)
    say("K7QM-4TXP")
    assert chat[-1] == "Report K7QM-4TXP (Drainage and flooding in Kaneshie) was received and is with Works Department."


def test_voice_notes_and_other_files_are_turned_away_and_a_repeat_is_ignored(chat: list[str]) -> None:
    say("", Media("https://api.twilio.com/media/ME10", "audio/ogg"))
    say("", Media("https://api.twilio.com/media/ME11", "application/pdf"))
    assert chat == ["Voice notes can't be read yet. Please type your message.", "Only photos can be added to a report."]
    whatsapp_conversation.handle(Inbound(NUMBER, "", Media("u", "application/pdf"), "SM-repeat"))
    whatsapp_conversation.handle(Inbound(NUMBER, "", Media("u", "application/pdf"), "SM-repeat"))
    assert len(chat) == 3


def test_replies_go_by_twilio_in_pieces_of_1600(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    class Provider:
        name, delivers = "twilio", True

        def send(self, to: str, body: str) -> str:
            sent.append(body)
            return "SM"

    monkeypatch.setattr(whatsapp_conversation, "provider_for", lambda channel: Provider() if channel == NotificationChannel.WHATSAPP else None)
    whatsapp_conversation.reply(NUMBER, "\n\n".join("word " * 100 for _ in range(6)))
    assert len(sent) == 2 and all(len(piece) <= 1600 for piece in sent)


def test_thanks_gets_no_reply(chat: list[str]) -> None:
    say("Thank you!")
    assert chat == []
