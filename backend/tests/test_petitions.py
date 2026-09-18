"""Petitions P1: the rules, confirming a phone, the checks on a draft, the MCE's decision and the clock, and what the public sees."""

from datetime import UTC, datetime, timedelta
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import petition_presenters as present
from app.services import (
    channel_limits,
    channel_sessions,
    petition_clock,
    petition_ledger,
    petition_rules,
    petition_screen,
    petitions,
    phone_proof,
    redis_store,
    ussd,
    whatsapp_conversation,
    whatsapp_reply,
)
from app.services.auth import Principal, Role
from app.services.petition_rules import (
    Draft,
    InvalidPetition,
    PetitionAction,
    PetitionStatus,
    PublishedBy,
    Scope,
    WrongState,
    check_resubmit,
    check_review,
    clean_draft,
    clean_name,
    creator_actions,
    normalise_code,
    publish_fields,
    refusal_fields,
)
from app.services.phone_proof import Channel, Claim, ProofError
from app.services.whatsapp_conversation import Inbound

NOW = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
PHONE = "+233241234567"
MCE = Principal("u-m", "The MCE", "m@x.org", Role.MCE)
DRAFT = Draft("Desilt the Odaw drain before the rains", "The drain at Kaneshie floods every June and the market has to close.",
              "drainage", Scope.AREA, "kaneshie", None, ())


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    fake = fakeredis.FakeRedis(decode_responses=True)
    for module in (redis_store, channel_limits, channel_sessions, phone_proof):
        monkeypatch.setattr(module, "get_redis", lambda: fake)
    return fake


def _petition(**changes: Any) -> dict[str, Any]:
    base = {"$id": "p1", "code": "482913", "title": DRAFT.title, "body": DRAFT.body, "topic": "drainage",
            "recipients": ["dept-works"], "scope": "area", "wardLocation": "kaneshie", "subMetro": "okaikoi-south",
            "status": "in_review", "submittedAt": NOW.isoformat(), "reviewDeadline": (NOW + timedelta(hours=72)).isoformat(),
            "resubmissions": 0, "signatureCount": 0, "creatorKey": phone_proof.phone_key(PHONE), "creatorPhone": PHONE,
            "creatorName": None, "issueId": None, "documentIds": []}
    return {**base, **changes}



def test_a_petition_is_about_something_the_assembly_handles_and_never_personal_safety() -> None:
    topics = {t.id for t in petition_rules.petition_topics()}
    assert {"drainage", "roads", "disaster", "structural_danger"} <= topics
    assert not topics & {"abuse", "child_at_risk", "public_crime", "fire", "road_accident"}
    with pytest.raises(InvalidPetition):
        clean_draft(Draft(**{**DRAFT.__dict__, "topic": "abuse"}))


def test_a_draft_is_tidied_and_checked() -> None:
    tidy = clean_draft(Draft("  Desilt   the Odaw drain before the rains ", DRAFT.body, "drainage", Scope.METRO, "kaneshie", " ", ("d1", "d1")))
    assert (tidy.title, tidy.ward, tidy.issue, tidy.documents) == ("Desilt the Odaw drain before the rains", None, None, ("d1",))
    for bad in ({"title": "Fix it"}, {"body": "Too short."}, {"ward": None}, {"ward": "nowhere"}, {"documents": ("a", "b", "c", "d")}):
        with pytest.raises(InvalidPetition):
            clean_draft(Draft(**{**DRAFT.__dict__, **bad}))


def test_a_name_is_shown_only_when_chosen() -> None:
    assert clean_name(False, "Ama Mensah") is None
    assert clean_name(True, "  Ama   Mensah ") == "Ama Mensah"
    with pytest.raises(InvalidPetition):
        clean_name(True, " ")


def test_the_mce_decides_within_72_hours_and_then_it_publishes_itself() -> None:
    check_review(_petition(), NOW + timedelta(hours=71))
    with pytest.raises(WrongState, match="publishes automatically"):
        check_review(_petition(), NOW + timedelta(hours=72))
    with pytest.raises(WrongState):
        check_review(_petition(status="open"), NOW)
    opened = publish_fields(_petition(), PublishedBy.AUTOMATIC, NOW, 150)
    assert opened["publishedBy"] == "automatic" and opened["threshold"] == 150
    assert opened["closesAt"] == (NOW + timedelta(days=90)).isoformat()


def test_a_refusal_must_give_a_fixed_reason_and_a_duplicate_names_the_petition() -> None:
    assert refusal_fields("not_assembly", "  ", None)["refusalNote"] is None
    for reason, duplicate in (("i_dont_like_it", None), ("duplicate", None)):
        with pytest.raises(InvalidPetition):
            refusal_fields(reason, None, duplicate)
    assert refusal_fields("duplicate", None, "111111")["duplicateOf"] == "111111"


def test_a_refused_petition_can_go_back_twice_and_the_creator_can_always_withdraw() -> None:
    check_resubmit(_petition(status="refused", resubmissions=1))
    with pytest.raises(WrongState):
        check_resubmit(_petition(status="refused", resubmissions=2))
    assert creator_actions(_petition(status="refused")) == ["withdraw", "resubmit"]
    assert creator_actions(_petition(status="open", creatorName="Ama")) == ["withdraw", "make_anonymous"]
    assert creator_actions(_petition(status="closed")) == []


def test_a_petition_number_is_six_digits_however_it_is_typed() -> None:
    assert [normalise_code(t) for t in ("482 913", "482-913", "482913", "48291", "4829134", "48a913")] == [
        "482913", "482913", "482913", None, None, None]
    assert normalise_code(petition_rules.new_code()) is not None



def test_a_whatsapp_code_confirms_the_number_once_and_redis_never_holds_it(server: fakeredis.FakeRedis) -> None:
    challenge = phone_proof.new_challenge()
    assert phone_proof.state(challenge.secret).state == "waiting"
    assert phone_proof.claim(f"Nokware code {challenge.code}", PHONE, Channel.WHATSAPP, NOW) == Claim.PROVEN
    assert phone_proof.claim(challenge.code, "+233207654321", Channel.WHATSAPP, NOW) == Claim.UNKNOWN  # used
    held = phone_proof.state(challenge.secret)
    proof = phone_proof.open_proof(held.proof, NOW)
    assert (held.state, proof.number, proof.channel, proof.hint) == ("proven", PHONE, Channel.WHATSAPP, "+233…67")
    stored = " ".join(" ".join(server.hgetall(k).values()) if server.type(k) == "hash" else server.get(k) for k in server.keys())  # noqa: SIM118 (Redis, not a dict)
    assert "241234567" not in stored and "241234567" not in " ".join(server.keys())


def test_only_a_ghanaian_number_is_confirmed(server: fakeredis.FakeRedis) -> None:
    challenge = phone_proof.new_challenge()
    assert phone_proof.claim(challenge.code, "+447700900123", Channel.WHATSAPP, NOW) == Claim.NOT_GHANAIAN
    assert phone_proof.state(challenge.secret).state == "waiting"
    assert phone_proof.claim("000000", PHONE, Channel.USSD, NOW) == Claim.UNKNOWN


def test_a_proof_that_is_altered_or_expired_is_refused() -> None:
    token = phone_proof.issue_proof(PHONE, Channel.USSD, NOW)
    assert phone_proof.open_proof(token, NOW + timedelta(hours=11)).number == PHONE
    for bad in (None, "", token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1], "not-a-token"):
        with pytest.raises(ProofError):
            phone_proof.open_proof(bad, NOW)
    with pytest.raises(ProofError, match="expired"):
        phone_proof.open_proof(token, NOW + timedelta(hours=12))


def test_the_code_is_read_from_a_whatsapp_message() -> None:
    assert [phone_proof.typed_code(t) for t in ("Nokware code 482173", "code: 482 173", "CODE 482-173.", "482173",
                                                  "my code is 482173", "Nokware code 48217")] == [
        "482173", "482173", "482173", None, None, None]


def test_sms_codes_stay_off_until_switched_on(server: fakeredis.FakeRedis, monkeypatch: pytest.MonkeyPatch) -> None:
    challenge = phone_proof.new_challenge()
    with pytest.raises(phone_proof.SmsUnavailable):
        phone_proof.send_sms_code(challenge.secret, PHONE, NOW)
    settings = phone_proof.get_settings().model_copy(update={"sms_verification_codes": True})
    monkeypatch.setattr(phone_proof, "get_settings", lambda: settings)
    texted: list[str] = []
    monkeypatch.setattr(phone_proof, "_text_code", lambda number, code: texted.append(code))
    assert phone_proof.send_sms_code(challenge.secret, "024 123 4567", NOW) == "+233…67"
    with pytest.raises(ProofError, match="4 tries left"):
        phone_proof.confirm_sms_code(challenge.secret, "999999" if texted[0] != "999999" else "111111", NOW)
    assert phone_proof.confirm_sms_code(challenge.secret, texted[0], NOW).state == "proven"


def test_whatsapp_and_ussd_hand_a_code_to_the_page(server: fakeredis.FakeRedis, monkeypatch: pytest.MonkeyPatch) -> None:
    replies: list[str] = []
    monkeypatch.setattr(whatsapp_reply, "reply", lambda number, text: replies.append(text))
    first, second = phone_proof.new_challenge(), phone_proof.new_challenge()
    whatsapp_conversation._route(Inbound(number=PHONE, text=f"Nokware code {first.code}", message_sid="SM1", media=None))
    assert replies == [phone_proof.CLAIM_REPLIES[Claim.PROVEN]] and phone_proof.state(first.secret).state == "proven"
    ussd.respond(ussd.Dial("s1", PHONE, "*928#", True), lambda *a: None)
    assert ussd.respond(ussd.Dial("s1", PHONE, "5", False), lambda *a: None).message.startswith("Enter the 6-digit code")
    reply = ussd.respond(ussd.Dial("s1", PHONE, second.code, False), lambda *a: None)
    assert reply == ussd.Reply(ussd.CODE_REPLIES[Claim.PROVEN], False) and phone_proof.state(second.secret).state == "proven"



def test_danger_to_a_person_and_personal_data_stop_a_petition(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(petition_screen, "_private_person", lambda text: None)
    assert petition_screen.screen("Stop the landlord who beats his wife", DRAFT.body).stop == petition_screen.SAFETY_STOP
    for text in ("Call me on 024 123 4567", "Write to ama@example.com", "Card GHA-123456789-0", "Ring +233 20 765 4321"):
        assert "Take it out" in (petition_screen.screen(DRAFT.title, f"{DRAFT.body} {text}").stop or ""), text
    assert petition_screen.screen(DRAFT.title, f"{DRAFT.body} The 2024 budget set aside GH¢ 250,000.").stop is None


def test_a_private_person_only_warns_and_a_missing_model_lets_it_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(petition_screen, "_private_person", lambda text: "Auntie Esi")
    screened = petition_screen.screen(DRAFT.title, DRAFT.body)
    assert screened.stop is None and "Auntie Esi" in (screened.warning or "")
    monkeypatch.setattr(petition_screen, "_private_person", lambda text: None)
    assert petition_screen.screen(DRAFT.title, DRAFT.body) == petition_screen.Screening(None, None)



@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"petition": _petition(), "trail": []}
    monkeypatch.setattr(petitions, "find", lambda code: dict(state["petition"]))
    monkeypatch.setattr(petitions, "update_petition", lambda pid, changes: state.update(petition={**state["petition"], **changes}) or dict(state["petition"]))
    monkeypatch.setattr(petitions, "record_history", lambda p, action, actor, from_status, reason=None, note=None:
                        state["trail"].append((action, actor.role, from_status, reason, note)))
    return state


def test_the_mce_publishes_or_refuses_and_the_trail_says_who(stored: dict[str, Any]) -> None:
    petitions.decide(MCE, "482913", False, "not_assembly", "This is the Ghana Highway Authority's road.", None, NOW)
    assert stored["petition"]["status"] == "refused" and stored["petition"]["purgeAt"] == (NOW + timedelta(days=30)).isoformat()
    assert stored["trail"] == [(PetitionAction.REFUSED, "mce", "in_review", "not_assembly", "This is the Ghana Highway Authority's road.")]
    stored["petition"] = _petition()
    petitions.decide(MCE, "482913", True, None, None, None, NOW)
    assert stored["petition"]["status"] == "open" and stored["petition"]["publishedBy"] == "mce"
    assert stored["petition"]["threshold"] == 150  # an electoral area


def test_undecided_after_72_hours_it_publishes_automatically(stored: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(petition_clock, "_due", lambda queries: [stored["petition"]] if stored["petition"]["status"] == "in_review" and "in_review" in str(queries) else [])
    told: list[str] = []
    monkeypatch.setattr(petition_clock.petition_updates, "notify_quietly", lambda petition, update: told.append(update.value))
    assert petition_clock.run_clock(NOW + timedelta(hours=71)) == {"published": [], "closed": [], "unanswered": []}
    assert petition_clock.run_clock(NOW + timedelta(hours=72))["published"] == ["482913"]
    assert stored["petition"]["publishedBy"] == "automatic" and stored["trail"][-1][:2] == (PetitionAction.AUTO_PUBLISHED, "system")
    assert told == ["auto_published"]
    with pytest.raises(WrongState):
        petitions.decide(MCE, "482913", False, "not_assembly", None, None, NOW + timedelta(hours=73))


def test_only_the_creator_can_change_their_petition(stored: dict[str, Any]) -> None:
    creator = phone_proof.Proof(PHONE, Channel.WHATSAPP, NOW + timedelta(hours=1))
    stranger = phone_proof.Proof("+233207654321", Channel.WHATSAPP, NOW + timedelta(hours=1))
    with pytest.raises(petitions.PetitionNotFound):
        petitions.withdraw("482913", stranger, NOW)
    assert petitions.withdraw("482913", creator, NOW)["status"] == PetitionStatus.WITHDRAWN



def test_the_public_timeline_shows_the_mce_decided_never_who_nor_the_note() -> None:
    trail = [{"action": "submitted", "at": "t1"}, {"action": "refused", "at": "t2", "reason": "private_individual", "note": "Take out Kofi"},
             {"action": "resubmitted", "at": "t3"}, {"action": "published", "at": "t4", "actorName": "The MCE"},
             {"action": "made_anonymous", "at": "t5"}]
    shown = present.timeline(trail)
    assert [e.action for e in shown] == ["submitted", "refused", "resubmitted", "published"]
    assert shown[1].reason == "Names a private individual" and "Kofi" not in str(shown) and "The MCE" not in str(shown)


def test_a_petition_that_was_never_published_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(petitions, "find", lambda code: _petition())
    assert TestClient(app).get("/api/petitions/482913").status_code == 404


def test_sending_a_petition_needs_a_confirmed_phone_and_is_checked_again(monkeypatch: pytest.MonkeyPatch) -> None:
    client, body = TestClient(app), {"title": DRAFT.title, "body": DRAFT.body, "topic": "drainage", "scope": "metro"}
    assert client.post("/api/petitions", json=body).status_code == 401
    proof = phone_proof.issue_proof(PHONE, Channel.USSD, datetime.now(UTC))
    response = client.post("/api/petitions", json={**body, "body": f"{DRAFT.body} Call 0241234567."}, headers={"X-Phone-Proof": proof})
    assert response.status_code == 422 and "phone number" in response.json()["detail"]


def test_a_ledger_search_the_index_cannot_answer_says_so_plainly(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg
    from sqlalchemy.exc import OperationalError

    client = TestClient(app, raise_server_exceptions=False)
    words = {"title": DRAFT.title, "body": DRAFT.body, "topic": "drainage"}
    for failure in (psycopg.OperationalError("auth failed"), OperationalError("connect", {}, Exception("auth failed"))):
        def unreachable(query: str, failure: Exception = failure) -> list[Any]:
            raise failure
        monkeypatch.setattr(petition_ledger, "cached_search", unreachable)
        response = client.post("/api/petitions/ledger", json=words)
        assert response.status_code == 503 and response.json()["detail"] == "The Ledger can't be searched right now. Try again shortly."


def test_a_passage_from_the_ledger_reads_as_words_and_the_same_text_shows_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.retrieval import Chunk

    assert petition_ledger.passage("preventing \uf002ooding, signi\uf001cant, \ufb01re \uf0b7 one \ufffd") == \
        "preventing flooding, significant, fire • one"
    plan = "FLOOD MITIGATION AND PREPAREDNESS MEASURES Identification of flood hotspots in the Accra Metropolis " * 3
    chunks = [Chunk(1, "plan", 0, plan), Chunk(2, "copy", 0, plan), Chunk(3, "budget", 4, "Desilting of drains, 2024 budget line.")]
    monkeypatch.setattr(petition_ledger, "ranked_lists", lambda queries: ([chunks], []))
    docs = {d: {"$id": d, "title": d.title(), "status": "published", "department": "dept-disaster-management"} for d in ("plan", "copy", "budget")}
    monkeypatch.setattr(petition_ledger.ledger_documents, "get_documents", lambda ids: docs)
    assert [m.id for m in petition_ledger.search("drainage")] == ["plan", "budget"]


def test_the_tabs_are_told_how_many_petitions_stand_in_each_group(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tab that only says "Open" leaves the reader counting cards to learn whether anything is happening."""
    stored = [{"status": "open"}, {"status": "open"}, {"status": "awaiting_response"}, {"status": "responded"},
              {"status": "closed"}, {"status": "withdrawn"}, {"status": "in_review"}]
    monkeypatch.setattr(petitions, "every_record", lambda collection, queries: stored)
    assert petitions.public_counts() == {"open": 2, "awaiting": 1, "responded": 1, "closed": 2}
