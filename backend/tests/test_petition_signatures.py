"""Petitions P2: one signature per confirmed number, the signer's choice of name, and the threshold sending it to the MCE."""

from datetime import datetime, timedelta, timezone
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import channel_limits, channel_sessions, petition_signatures, petitions, phone_proof, redis_store, ussd
from app.services.petition_rules import (
    InvalidPetition,
    PetitionAction,
    WrongState,
    check_signable,
    check_withdraw,
    clean_signer_name,
    threshold_fields,
)
from app.services.phone_proof import Channel

NOW = datetime(2026, 9, 15, 11, 0, tzinfo=timezone.utc)
PHONE, OTHER = "+233241234567", "+233201234568"
OPEN = {"$id": "p1", "code": "482913", "title": "[TEST] Desilt the Kaneshie drain", "status": "open", "threshold": 3,
        "signatureCount": 0, "publishedAt": "2026-09-14T09:00:00+00:00", "closesAt": (NOW + timedelta(days=60)).isoformat()}


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    fake = fakeredis.FakeRedis(decode_responses=True)
    for module in (redis_store, channel_limits, channel_sessions, phone_proof):
        monkeypatch.setattr(module, "get_redis", lambda: fake)
    return fake


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, server: fakeredis.FakeRedis) -> dict[str, Any]:
    """One petition and its signatures in dicts; the unique index is the dict key."""
    state: dict[str, Any] = {"petition": dict(OPEN), "signatures": {}, "trail": []}

    def store_signature(petition_id: str, key: str, name: str | None, channel: Channel, now: datetime) -> bool:
        if key in state["signatures"]:
            return False
        state["signatures"][key] = {"$id": key[:8], "named": name is not None, "name": name, "createdAt": now.isoformat()}
        return True

    monkeypatch.setattr(petitions, "public", lambda code: dict(state["petition"]))
    monkeypatch.setattr(petitions, "update_petition", lambda pid, changes: state.update(petition={**state["petition"], **changes}) or dict(state["petition"]))
    monkeypatch.setattr(petitions, "record_history", lambda p, action, actor, from_status, reason=None, note=None: state["trail"].append((action, actor.role)))
    monkeypatch.setattr(petition_signatures, "_store", store_signature)
    monkeypatch.setattr(petition_signatures, "total", lambda petition_id: len(state["signatures"]))
    monkeypatch.setattr(petition_signatures, "_mine", lambda petition_id, number: state["signatures"].get(petition_signatures.signer_key(petition_id, number)))
    return state


def test_a_signers_name_is_letters_only_and_shown_only_by_choice() -> None:
    assert clean_signer_name(False, "Ama Mensah") is None
    assert [clean_signer_name(True, n) for n in ("Ama Mensah", "Kwaku Ananse-Boateng", "Ɛfua Kɔdjo", "Dr. Ama")] == [
        "Ama Mensah", "Kwaku Ananse-Boateng", "Ɛfua Kɔdjo", "Dr. Ama"]
    for bad in ("Kofi 0241234567", "Ama: the MCE lies", "ama@example.com", " "):
        with pytest.raises(InvalidPetition):
            clean_signer_name(True, bad)


def test_reaching_the_threshold_gives_the_mce_30_days_and_happens_once() -> None:
    assert threshold_fields(OPEN, 2, NOW) == {"signatureCount": 2}
    reached = threshold_fields(OPEN, 3, NOW)
    assert reached["status"] == "awaiting_response" and reached["responseDue"] == (NOW + timedelta(days=30)).isoformat()
    assert threshold_fields({**OPEN, "status": "awaiting_response"}, 4, NOW) == {"signatureCount": 4}


def test_signing_stays_open_after_the_threshold_until_the_90_days_end() -> None:
    check_signable({**OPEN, "status": "awaiting_response"}, NOW)
    for closed in ({"status": "closed"}, {"status": "withdrawn"}, {"closesAt": NOW.isoformat()}, {"status": "in_review"}):
        with pytest.raises(WrongState):
            check_signable({**OPEN, **closed}, NOW)
    with pytest.raises(WrongState, match="gone to the MCE"):
        check_withdraw({**OPEN, "status": "awaiting_response"})


def test_one_signature_per_number_and_the_one_that_reaches_the_threshold_sends_it_to_the_mce(store: dict[str, Any]) -> None:
    assert petition_signatures.sign("482913", PHONE, Channel.WHATSAPP, False, None, NOW).added
    again = petition_signatures.sign("482913", PHONE, Channel.USSD, True, "Ama Mensah", NOW)
    assert not again.added and store["petition"]["signatureCount"] == 1
    petition_signatures.sign("482913", OTHER, Channel.USSD, True, "Ama Mensah", NOW)
    third = petition_signatures.sign("482913", "+233551234569", Channel.SMS, False, None, NOW)
    assert third.petition["status"] == "awaiting_response" and store["trail"] == [(PetitionAction.THRESHOLD_REACHED, "system")]
    assert [s["named"] for s in store["signatures"].values()] == [False, True, False]


def test_a_signature_holds_no_number_and_cant_be_matched_across_petitions() -> None:
    key = petition_signatures.signer_key("p1", PHONE)
    assert PHONE not in key and "241234567" not in key
    assert key != petition_signatures.signer_key("p2", PHONE) and key != phone_proof.phone_key(PHONE)


def test_a_named_signer_can_take_their_name_off_and_still_counts(store: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    petition_signatures.sign("482913", PHONE, Channel.WHATSAPP, True, "Ama Mensah", NOW)
    updates: list[dict[str, Any]] = []
    monkeypatch.setattr(petition_signatures, "get_databases", lambda: type("Db", (), {"update_document": lambda self, *a: updates.append(a[-1])})())
    assert petition_signatures.make_anonymous("482913", PHONE)["named"] is False
    assert updates == [{"named": False, "name": None}] and store["petition"]["signatureCount"] == 1


def test_a_closed_petition_takes_no_signatures(store: dict[str, Any]) -> None:
    store["petition"]["status"] = "closed"
    with pytest.raises(WrongState):
        petition_signatures.sign("482913", PHONE, Channel.WHATSAPP, False, None, NOW)


def test_signing_on_the_web_needs_a_confirmed_phone_and_a_real_name() -> None:
    client = TestClient(app)
    assert client.post("/api/petitions/482913/signatures", json={"show_name": False}).status_code == 401
    proof = phone_proof.issue_proof(PHONE, Channel.WHATSAPP, datetime.now(timezone.utc))
    response = client.post("/api/petitions/482913/signatures", json={"show_name": True, "name": "Call 0241234567"},
                           headers={"X-Phone-Proof": proof})
    assert response.status_code == 422 and "letters" in response.json()["detail"]


def _dial(*presses: str, number: str = PHONE) -> ussd.Reply:
    reply = ussd.respond(ussd.Dial("s1", number, "*928#", True), lambda *a: None)
    for press in presses:
        reply = ussd.respond(ussd.Dial("s1", number, press, False), lambda *a: None)
    return reply


def test_on_ussd_a_resident_signs_anonymously_or_is_told_who_sees_their_name(store: dict[str, Any]) -> None:
    assert _dial("6", "482 913").message.startswith("[TEST] Desilt the Kaneshie drain\n1 Sign, name not shown")
    assert _dial("6", "482913", "1") == ussd.Reply("Signed anonymously. 1 of 3 signatures. Thank you.", False)
    assert "including the department it concerns" in _dial("6", "482913", "2", number=OTHER).message
    assert _dial("6", "482913", "2", "Ama 2", number=OTHER).message.startswith("A name can have letters")
    assert _dial("6", "482913", "2", "Ama Mensah", number=OTHER).message == "Signed with your name shown. 2 of 3 signatures. Thank you."
    assert _dial("6", "482913", "1").message == "This number has already signed this petition."


def test_on_ussd_an_unknown_or_closed_petition_is_said_plainly(store: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    assert _dial("6", "4829").message == "A petition number has 6 digits. Try again:"

    def missing(code: str) -> dict[str, Any]:
        raise petitions.PetitionNotFound(code)

    monkeypatch.setattr(petitions, "public", missing)
    assert _dial("6", "111111").message == "No open petition has that number. Check it and dial again."
