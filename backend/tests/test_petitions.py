"""Petitions in Stage A: the rules, confirming a phone, the checks on a draft, publishing without anyone's leave,
a contributor's removal and the tombstone it leaves, reading a report, and what the public sees."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.dependencies import current_principal
from app.main import app
from app.routes import petition_presenters as present
from app.services import (
    channel_limits,
    channel_sessions,
    petition_clock,
    petition_ledger,
    petition_removals,
    petition_reports,
    petition_rules,
    petition_screen,
    petition_signatures,
    petition_versions,
    petitions,
    phone_proof,
    rate_limit,
    redis_store,
    ussd,
    whatsapp_conversation,
    whatsapp_reply,
)
from app.services.auth import Principal, Role
from app.services.petition_grounds import Dismissal, Ground, in_plain_words
from app.services.petition_reports import ReportState
from app.services.petition_rules import (
    Draft,
    InvalidPetition,
    NotAllowed,
    PetitionAction,
    PetitionStatus,
    Scope,
    WrongState,
    check_editable,
    check_withdraw,
    clean_draft,
    clean_name,
    creator_actions,
    normalise_code,
    publish_fields,
)
from app.services.phone_proof import Channel, Claim, ProofError
from app.services.whatsapp_conversation import Inbound

NOW = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
PHONE, CONTRIBUTOR_PHONE = "+233241234567", "+233207654321"
MCE = Principal("u-m", "The MCE", "m@x.org", Role.MCE)
KOFI = Principal("u-c", "Kofi Asante", "k@x.org", Role.CONTRIBUTOR)
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
            "status": "open", "submittedAt": NOW.isoformat(), "publishedAt": NOW.isoformat(),
            "closesAt": (NOW + timedelta(days=90)).isoformat(), "threshold": 150, "signatureCount": 0,
            "version": 1, "versionedAt": NOW.isoformat(), "removalCount": 0,
            "creatorKey": phone_proof.phone_key(PHONE), "creatorPhone": PHONE, "creatorName": None,
            "issueId": None, "documentIds": [], "imageIds": []}
    return {**base, **changes}


def proof_of(number: str) -> phone_proof.Proof:
    return phone_proof.Proof(number, Channel.WHATSAPP, NOW + timedelta(hours=1))


def test_a_petition_is_about_something_the_assembly_handles_and_never_personal_safety() -> None:
    topics = {t.id for t in petition_rules.petition_topics()}
    assert {"drainage", "roads", "disaster", "structural_danger"} <= topics
    assert not topics & {"abuse", "child_at_risk", "public_crime", "fire", "road_accident"}
    with pytest.raises(InvalidPetition):
        clean_draft(Draft(**{**DRAFT.__dict__, "topic": "abuse"}))


def test_a_draft_is_tidied_and_checked() -> None:
    tidy = clean_draft(Draft("  Desilt   the Odaw drain before the rains ", DRAFT.body, "drainage", Scope.METRO, "kaneshie", " ", ("d1", "d1")))
    assert (tidy.title, tidy.ward, tidy.issue, tidy.documents) == ("Desilt the Odaw drain before the rains", None, None, ("d1",))
    for bad in ({"title": "Fix it"}, {"body": "Too short."}, {"ward": None}, {"ward": "nowhere"},
                {"documents": ("a", "b", "c", "d")}, {"images": ("a", "b", "c", "d")}):
        with pytest.raises(InvalidPetition):
            clean_draft(Draft(**{**DRAFT.__dict__, **bad}))


def test_a_name_is_shown_only_when_chosen() -> None:
    assert clean_name(False, "Ama Mensah") is None
    assert clean_name(True, "  Ama   Mensah ") == "Ama Mensah"
    with pytest.raises(InvalidPetition):
        clean_name(True, " ")


def test_publishing_fixes_the_ninety_days_and_the_threshold_of_the_moment() -> None:
    opened = publish_fields(NOW, 150)
    assert opened["status"] == "open" and opened["threshold"] == 150 and opened["version"] == 1
    assert opened["closesAt"] == (NOW + timedelta(days=90)).isoformat()
    assert opened["publishedAt"] == NOW.isoformat() and opened["removalCount"] == 0


def test_what_a_creator_can_do_depends_only_on_where_their_petition_stands() -> None:
    assert creator_actions(_petition()) == ["edit", "withdraw"]
    assert creator_actions(_petition(status="removed")) == ["edit"]
    assert creator_actions(_petition(status="awaiting_response", creatorName="Ama")) == ["edit", "make_anonymous"]
    assert creator_actions(_petition(status="closed")) == []
    for status in ("responded", "closed"):
        with pytest.raises(WrongState, match="can't be edited"):
            check_editable(_petition(status=status))
    with pytest.raises(WrongState, match="gone to the MCE"):
        check_withdraw(_petition(status="awaiting_response"))


def test_a_petition_number_is_six_digits_however_it_is_typed() -> None:
    assert [normalise_code(t) for t in ("482 913", "482-913", "482913", "48291", "4829134", "48a913")] == [
        "482913", "482913", "482913", None, None, None]
    assert normalise_code(petition_rules.new_code()) is not None


def test_a_whatsapp_code_confirms_the_number_once_and_redis_never_holds_it(server: fakeredis.FakeRedis) -> None:
    challenge = phone_proof.new_challenge()
    assert phone_proof.state(challenge.secret).state == "waiting"
    assert phone_proof.claim(f"Nokware code {challenge.code}", PHONE, Channel.WHATSAPP, NOW) == Claim.PROVEN
    assert phone_proof.claim(challenge.code, CONTRIBUTOR_PHONE, Channel.WHATSAPP, NOW) == Claim.UNKNOWN  # used
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
    monkeypatch.setattr(petition_screen, "private_person", lambda text: None)
    assert petition_screen.screen("Stop the landlord who beats his wife", DRAFT.body).stop == petition_screen.SAFETY_STOP
    for text in ("Call me on 024 123 4567", "Write to ama@example.com", "Card GHA-123456789-0", "Ring +233 20 765 4321"):
        assert "Take it out" in (petition_screen.screen(DRAFT.title, f"{DRAFT.body} {text}").stop or ""), text
    assert petition_screen.screen(DRAFT.title, f"{DRAFT.body} The 2024 budget set aside GH¢ 250,000.").stop is None


def test_a_private_person_only_warns_and_a_missing_model_lets_it_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(petition_screen, "private_person", lambda text: "Auntie Esi")
    screened = petition_screen.screen(DRAFT.title, DRAFT.body)
    assert screened.stop is None and "Auntie Esi" in (screened.warning or "")
    monkeypatch.setattr(petition_screen, "private_person", lambda text: None)
    assert petition_screen.screen(DRAFT.title, DRAFT.body) == petition_screen.Screening(None, None)


@dataclass
class Fake:
    """One petition and everything written about it, in dicts: the trail, its versions, removals and reports."""

    petition: dict[str, Any] = field(default_factory=_petition)
    trail: list[tuple[Any, ...]] = field(default_factory=list)
    versions: list[dict[str, Any]] = field(default_factory=list)
    removals: list[dict[str, Any]] = field(default_factory=list)
    reports: list[dict[str, Any]] = field(default_factory=list)
    signers: set[str] = field(default_factory=set)


class _Written:
    """What an Appwrite write returns, as much of it as as_record() reads."""

    def __init__(self, row: dict[str, Any]) -> None:
        self.data, self.id, self.createdat, self.updatedat = row, row["$id"], row.get("createdAt", ""), ""


class _FakeDatabases:
    def __init__(self, rows: dict[str, list[dict[str, Any]]]) -> None:
        self.rows = rows

    def create_document(self, _database: str, collection: str, _id: str, data: dict[str, Any]) -> _Written:
        kept = self.rows.setdefault(collection, [])
        row = {**data, "$id": f"{collection}-{len(kept) + 1}"}
        kept.append(row)
        return _Written(row)

    def update_document(self, _database: str, collection: str, row_id: str, changes: dict[str, Any]) -> _Written:
        row = next(r for r in self.rows[collection] if r["$id"] == row_id)
        row.update(changes)
        return _Written(row)


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch, server: fakeredis.FakeRedis) -> Fake:
    state = Fake()
    rows = {petition_removals.REMOVALS_COLLECTION: state.removals, petition_reports.REPORTS_COLLECTION: state.reports}
    database = _FakeDatabases(rows)

    def find(code: str) -> dict[str, Any]:
        if code != state.petition["code"]:
            raise petitions.PetitionNotFound(code)
        return dict(state.petition)

    def create(fields: dict[str, Any]) -> dict[str, Any]:
        state.petition = {**fields, "$id": "p1", "code": "482913"}
        return dict(state.petition)

    monkeypatch.setattr(petitions, "find", find)
    monkeypatch.setattr(petitions, "_create", create)
    monkeypatch.setattr(petitions, "update_petition",
                        lambda pid, changes: state.__setattr__("petition", {**state.petition, **changes}) or dict(state.petition))
    monkeypatch.setattr(petitions, "record_history", lambda p, action, actor, from_status, reason=None, note=None:
                        state.trail.append((action, actor.role, from_status, reason, note)))
    monkeypatch.setattr(petitions, "list_petitions", lambda queries: ([dict(state.petition)], 1))
    monkeypatch.setattr(petitions, "test_petition_ids", set)
    monkeypatch.setattr(petition_versions, "record_version",
                        lambda pid, fields, number, at: state.versions.append({**fields, "petitionId": pid, "version": number,
                                                                              "at": at.isoformat()}))
    monkeypatch.setattr(petition_versions, "versions_of", lambda pid: list(state.versions))
    monkeypatch.setattr(petition_signatures, "has_signed", lambda pid, number: number in state.signers)
    monkeypatch.setattr(petition_signatures, "on_earlier_versions",
                        lambda petition: sum(1 for _ in state.signers) if (petition.get("version") or 1) > 1 else 0)
    monkeypatch.setattr(petition_removals, "get_databases", lambda: database)
    monkeypatch.setattr(petition_removals, "latest_removal", lambda pid: dict(state.removals[-1]) if state.removals else None)
    monkeypatch.setattr(petition_removals, "every_record", lambda collection, queries: list(state.removals))
    monkeypatch.setattr(petition_reports, "get_databases", lambda: database)
    monkeypatch.setattr(petition_reports, "every_record", _reports_matching(state))
    return state


def _reports_matching(state: Fake) -> Any:
    """The fake index over the reports: a query naming a row finds that row, one asking for open reports finds
    those, and orderDesc turns them newest first, as Appwrite would."""

    def matching(_collection: str, queries: list[str]) -> list[dict[str, Any]]:
        asked = " ".join(queries)
        found = [dict(report) for report in state.reports
                 if report["$id"] in asked or (ReportState.OPEN.value in asked and report["state"] == ReportState.OPEN)]
        return list(reversed(found)) if "orderDesc" in asked else found

    return matching


def _publish(state: Fake) -> dict[str, Any]:
    return petitions.submit(proof_of(PHONE), DRAFT, False, None, NOW)


def test_a_petition_is_public_the_moment_its_words_pass_the_screen(stored: Fake) -> None:
    """Nobody publishes it but the person who wrote it: there is no queue, no reviewer and no waiting."""
    published = _publish(stored)
    assert published["status"] == PetitionStatus.OPEN and published["publishedAt"] == NOW.isoformat()
    assert published["threshold"] == 150 and published["version"] == 1  # an electoral area
    assert petitions.public("482913")["code"] == "482913"
    assert stored.trail == [(PetitionAction.PUBLISHED, "creator", None, None, None)]
    assert [(v["version"], v["title"]) for v in stored.versions] == [(1, DRAFT.title)]


def test_words_the_screen_stops_never_become_a_petition(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[dict[str, Any]] = []
    monkeypatch.setattr(petitions, "_create", lambda fields: created.append(fields) or fields)
    client = TestClient(app)
    form = {"title": DRAFT.title, "body": f"{DRAFT.body} Call 0241234567.", "topic": "drainage", "scope": "metro"}
    assert client.post("/api/petitions", data=form).status_code == 401
    proof = phone_proof.issue_proof(PHONE, Channel.USSD, datetime.now(UTC))
    response = client.post("/api/petitions", data=form, headers={"X-Phone-Proof": proof})
    assert response.status_code == 422 and "phone number" in response.json()["detail"]
    assert created == []


def _remove(stored: Fake, ground: Ground = Ground.PRIVATE_INDIVIDUAL, duplicate: str | None = None,
            note: str | None = None) -> petition_removals.Removed:
    return petition_removals.remove(KOFI, proof_of(CONTRIBUTOR_PHONE), "482913", ground, duplicate, note, NOW)


def test_a_contributor_removes_a_petition_on_a_ground_but_never_their_own_nor_one_they_signed(stored: Fake) -> None:
    _publish(stored)
    with pytest.raises(NotAllowed, match="You started this petition"):
        petition_removals.remove(KOFI, proof_of(PHONE), "482913", Ground.PERSONAL_DATA, None, None, NOW)
    stored.signers.add(CONTRIBUTOR_PHONE)
    with pytest.raises(NotAllowed, match="You signed this petition"):
        _remove(stored)
    stored.signers.clear()
    removed = _remove(stored, Ground.INCITES_VIOLENCE, note="Third paragraph names a neighbour.")
    assert stored.petition["status"] == PetitionStatus.REMOVED and stored.petition["removalCount"] == 1
    assert stored.petition["removedFromStatus"] == "open"  # where a republication puts it back
    assert removed.record["ground"] == "incites_violence" and removed.record["removedByName"] == "Kofi Asante"
    assert stored.trail[-1] == (PetitionAction.REMOVED, "contributor", "open", "incites_violence",
                                "Third paragraph names a neighbour.")
    with pytest.raises(WrongState, match="already been removed"):
        _remove(stored)


def test_the_mce_cannot_remove_a_petition_and_nor_can_a_stranger(stored: Fake, monkeypatch: pytest.MonkeyPatch) -> None:
    """The MCE is usually what a petition is about, so it never holds the button that takes one down."""
    client, body = TestClient(app), {"ground": "personal_data"}
    assert client.post("/api/petitions/482913/removal", json=body).status_code == 401
    for principal, expected in ((MCE, 403), (KOFI, 401)):  # a contributor still has to confirm their own number
        app.dependency_overrides[current_principal] = lambda principal=principal: principal
        assert client.post("/api/petitions/482913/removal", json=body).status_code == expected
        app.dependency_overrides.clear()


def test_only_the_four_grounds_remove_a_petition_and_a_duplicate_must_name_a_public_one(stored: Fake) -> None:
    _publish(stored)
    assert [g.value for g in Ground] == ["private_individual", "incites_violence", "personal_data", "duplicate"]
    with pytest.raises(ValueError, match="not a valid Ground"):
        Ground("i_dont_like_it")
    with pytest.raises(InvalidPetition, match="number of the open petition"):
        _remove(stored, Ground.DUPLICATE)
    with pytest.raises(InvalidPetition, match="No public petition"):
        _remove(stored, Ground.DUPLICATE, "111111")
    with pytest.raises(InvalidPetition, match="No public petition"):
        _remove(stored, Ground.DUPLICATE, "482913")  # itself


def test_a_note_on_a_removal_is_kept_for_the_record_and_refused_if_it_holds_personal_data(stored: Fake) -> None:
    _publish(stored)
    with pytest.raises(InvalidPetition, match="personal data"):
        _remove(stored, note="Reported by Ama on 024 123 4567.")
    assert stored.petition["status"] == PetitionStatus.OPEN  # nothing happened
    assert petition_removals.clean_note("  ") is None


def test_the_tombstone_carries_the_ground_the_date_and_nothing_of_the_petition(stored: Fake) -> None:
    _publish(stored)
    petitions.update_petition("p1", {"signatureCount": 412, "creatorName": "Ama Mensah"})
    removed = _remove(stored, Ground.PRIVATE_INDIVIDUAL, note="Names the landlord at number 12.")
    stone = present.tombstone(petition_removals.tombstone(removed.record)).model_dump()
    assert stone == {"state": "removed", "code": "482913", "ground": "private_individual",
                     "ground_words": in_plain_words(Ground.PRIVATE_INDIVIDUAL), "removed_at": NOW.isoformat(),
                     "duplicate_of": None, "previous_removals": 0}
    written = str(stone)
    assert all(word not in written for word in (DRAFT.title, DRAFT.body, "Ama Mensah", "412", "landlord"))
    with pytest.raises(petitions.PetitionNotFound):
        petitions.public("482913")  # every public read goes through this, so nothing else can reach a reader


def test_a_removed_petitions_page_is_the_tombstone_and_an_unknown_number_is_still_not_found(stored: Fake) -> None:
    _publish(stored)
    _remove(stored, Ground.PERSONAL_DATA)
    client = TestClient(app)
    page = client.get("/api/petitions/482913")
    assert page.status_code == 200 and page.json()["state"] == "removed"
    assert set(page.json()) == {"state", "code", "ground", "ground_words", "removed_at", "duplicate_of", "previous_removals"}
    assert client.get("/api/petitions/111111").status_code == 404


def test_a_report_hides_nothing_and_its_note_is_screened(stored: Fake) -> None:
    _publish(stored)
    filed = petition_reports.file_report("482913", Ground.PERSONAL_DATA, None, "  There is a home address in it.  ", NOW)
    assert filed["state"] == ReportState.OPEN and filed["note"] == "There is a home address in it."
    assert stored.petition["status"] == PetitionStatus.OPEN and petitions.public("482913")["title"] == DRAFT.title
    assert present.card(petitions.public("482913")).signatures == 0  # still countable, still signable
    with pytest.raises(InvalidPetition, match="personal data"):
        petition_reports.file_report("482913", Ground.PERSONAL_DATA, None, "Ring the writer on 024 123 4567.", NOW)
    with pytest.raises(InvalidPetition, match="number of the open petition"):
        petition_reports.file_report("482913", Ground.DUPLICATE, None, None, NOW)


def test_the_queue_gathers_what_was_reported_and_a_removal_settles_all_of_it(stored: Fake) -> None:
    _publish(stored)
    for ground in (Ground.PERSONAL_DATA, Ground.INCITES_VIOLENCE):
        petition_reports.file_report("482913", ground, None, f"About {ground.value}.", NOW)
    queue = petition_reports.queue()
    assert [item.report["ground"] for item in queue] == ["incites_violence", "personal_data"]  # newest first
    assert queue[0].reports_on_this_petition == 2 and queue[0].petition["code"] == "482913"
    shown = present.reported(queue[0])
    assert shown.ground_words == in_plain_words(Ground.INCITES_VIOLENCE) and shown.petition.title == DRAFT.title
    petition_reports.dismiss(KOFI, queue[0].report["$id"], Dismissal.NOT_THE_GROUND, NOW)
    assert stored.reports[1]["state"] == ReportState.DISMISSED and stored.reports[1]["dismissedReason"] == "not_the_ground"
    with pytest.raises(petition_reports.ReportNotFound):  # settled once; a second contributor is told, not obeyed
        petition_reports.dismiss(KOFI, queue[0].report["$id"], Dismissal.ALREADY_HANDLED, NOW)
    _remove(stored, Ground.INCITES_VIOLENCE)
    assert stored.reports[0]["state"] == ReportState.ACTED_ON  # the one still open was answered by the removal


def test_a_republished_petition_is_a_new_version_that_keeps_its_signatures(stored: Fake) -> None:
    """The signatures stand: they were given to the petition, and the page says how many were given to older words."""
    _publish(stored)
    petitions.update_petition("p1", {"signatureCount": 412})
    stored.signers.update({f"+23324123456{n}" for n in range(7)})
    _remove(stored, Ground.PERSONAL_DATA)
    mended = Draft(**{**DRAFT.__dict__, "body": f"{DRAFT.body} The market association has written twice."})
    republished = petitions.edit("482913", proof_of(PHONE), mended, NOW + timedelta(days=1))
    assert republished["status"] == PetitionStatus.OPEN and republished["version"] == 2
    assert republished["signatureCount"] == 412 and republished["removalCount"] == 1
    assert republished["removedAt"] is None and republished["removalGround"] is None
    assert republished["closesAt"] == _petition()["closesAt"]  # time spent down is not time won
    assert stored.trail[-1][:3] == (PetitionAction.REPUBLISHED, "creator", "removed")
    assert [v["version"] for v in stored.versions] == [1, 2]
    assert present.card(republished).removals == 1
    assert present.versions("p1")[1].changed == ["body"]


def test_a_signature_records_the_version_it_was_given_to(stored: Fake, monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[dict[str, Any]] = []
    monkeypatch.setattr(petitions, "public", lambda code: dict(stored.petition))
    monkeypatch.setattr(petition_signatures, "_store",
                        lambda pid, key, name, channel, version, now: bool(written.append({"version": version})) or True)
    monkeypatch.setattr(petition_signatures, "total", lambda pid: 1)
    _publish(stored)
    petitions.update_petition("p1", {"version": 3})
    petition_signatures.sign("482913", PHONE, Channel.USSD, False, None, NOW)
    assert written == [{"version": 3}]


def test_the_public_timeline_says_what_happened_never_who_did_it() -> None:
    trail = [{"action": "published", "at": "t1"},
             {"action": "removed", "at": "t2", "reason": "private_individual", "note": "Names Kofi at number 12"},
             {"action": "republished", "at": "t3"}, {"action": "made_anonymous", "at": "t4"},
             {"action": "closed", "at": "t5", "reason": "refused"}]
    shown = present.timeline(trail)
    assert [e.action for e in shown] == ["published", "removed", "republished", "closed"]
    assert shown[1].reason == in_plain_words(Ground.PRIVATE_INDIVIDUAL) and "Kofi" not in str(shown)
    assert shown[3].reason == "Refused under the earlier review process"  # a petition the old process ended


def test_a_petition_page_is_refused_after_too_many_reports_about_it(stored: Fake) -> None:
    """One petition can't be buried under reports, and no report ever hides it: the limit only keeps the queue readable."""
    _publish(stored)
    client, body = TestClient(app), {"ground": "personal_data"}
    codes = {client.post("/api/petitions/482913/report", json=body).status_code
             for _ in range(rate_limit.PETITION_REPORTS.limit + 1)}
    assert codes == {201, 429}
    assert petitions.public("482913")["status"] == PetitionStatus.OPEN


def test_the_clock_closes_a_petition_at_ninety_days_and_publishes_nothing(stored: Fake, monkeypatch: pytest.MonkeyPatch) -> None:
    _publish(stored)
    monkeypatch.setattr(petition_clock, "_due", lambda queries: [dict(stored.petition)] if "open" in str(queries) else [])
    told: list[str] = []
    monkeypatch.setattr(petition_clock.petition_updates, "notify_quietly", lambda petition, update: told.append(update.value))
    assert petition_clock.run_clock(NOW + timedelta(days=89)) == {"closed": [], "unanswered": []}
    assert petition_clock.run_clock(NOW + timedelta(days=90))["closed"] == ["482913"]
    assert stored.petition["status"] == PetitionStatus.CLOSED and told == ["closed"]


def test_only_the_creator_can_change_their_petition(stored: Fake) -> None:
    _publish(stored)
    with pytest.raises(petitions.PetitionNotFound):
        petitions.withdraw("482913", proof_of(CONTRIBUTOR_PHONE), NOW)
    closed = petitions.withdraw("482913", proof_of(PHONE), NOW)
    assert closed["status"] == PetitionStatus.CLOSED and stored.trail[-1][0] == PetitionAction.WITHDRAWN


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

    assert petition_ledger.passage("preventing ooding, signicant, ﬁre  one �") == \
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
              {"status": "closed"}, {"status": "removed"}]
    monkeypatch.setattr(petitions, "every_record", lambda collection, queries: stored)
    assert petitions.public_counts() == {"open": 2, "awaiting": 1, "responded": 1, "closed": 1}
