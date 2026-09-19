"""Stage E: what residents say under a petition — who may write a comment, what the screen refuses, what a
contributor can take down, and what goes down with the petition itself."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.dependencies import current_principal
from app.main import app
from app.services import (
    channel_limits,
    channel_sessions,
    ledger_documents,
    petition_comments,
    petition_departments,
    petition_removals,
    petition_reports,
    petition_screen,
    petition_signatures,
    petition_versions,
    petitions,
    phone_proof,
    rate_limit,
    redis_store,
)
from app.services.appwrite_client import as_record
from app.services.auth import Principal, Role
from app.services.petition_comments import COMMENT_MAX
from app.services.petition_grounds import Dismissal, Ground, in_plain_words
from app.services.petition_reports import ReportState
from app.services.petition_rules import Draft, InvalidPetition, PetitionStatus, Scope, WrongState
from app.services.phone_proof import Channel

NOW = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
PHONE, OTHER_PHONE, CONTRIBUTOR_PHONE = "+233241234567", "+233209876543", "+233207654321"
KOFI = Principal("u-c", "Kofi Asante", "k@x.org", Role.CONTRIBUTOR)
DRAFT = Draft("Desilt the Odaw drain before the rains", "The drain at Kaneshie floods every June and the market has to close.",
              "drainage", Scope.AREA, "kaneshie", None, ())
SAID = "The drain by the lorry park has not been cleared since May."
LIMITS = ("PETITION_COMMENTS", "PETITION_COMMENTS_ON_ONE", "PETITION_CHANGES", "PETITION_REPORTS",
          "PETITION_REPORTS_ABOUT_ONE")


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


def proof_header(number: str) -> dict[str, str]:
    """A sealed proof as the page sends it, issued now because the route opens it against the real clock."""
    return {"X-Phone-Proof": phone_proof.issue_proof(number, Channel.WHATSAPP, datetime.now(UTC))}


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    fake = fakeredis.FakeRedis(decode_responses=True)
    for module in (redis_store, channel_limits, channel_sessions, phone_proof):
        monkeypatch.setattr(module, "get_redis", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test counts from nothing, at the limits that ship: the counts live in this process, and one test must
    not spend another's."""
    for name in LIMITS:
        shipped = getattr(rate_limit, name)
        monkeypatch.setattr(rate_limit, name, rate_limit.RateLimit(shipped.limit, shipped.window))


@dataclass
class Fake:
    """One petition, and everything written under it in dicts: its trail, its versions and its rows."""

    petition: dict[str, Any] = field(default_factory=_petition)
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    trail: list[tuple[Any, ...]] = field(default_factory=list)
    versions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def comments(self) -> list[dict[str, Any]]:
        return self.rows.setdefault(petition_comments.COMMENTS_COLLECTION, [])

    @property
    def comment_reports(self) -> list[dict[str, Any]]:
        return self.rows.setdefault(petition_comments.COMMENT_REPORTS_COLLECTION, [])


class _Written:
    """What an Appwrite write returns, as much of it as as_record() reads."""

    def __init__(self, row: dict[str, Any]) -> None:
        self.data, self.id, self.createdat, self.updatedat = row, row["$id"], row.get("createdAt", ""), ""


class _Listing:
    def __init__(self, page: list[dict[str, Any]], total: int) -> None:
        self.documents, self.total = [_Written(row) for row in page], total


def _asked(queries: list[str], method: str) -> list[dict[str, Any]]:
    return [asked for query in queries if (asked := json.loads(query))["method"] == method]


def _matches(row: dict[str, Any], queries: list[str]) -> bool:
    return all(row.get(asked["attribute"]) in asked["values"] for asked in _asked(queries, "equal"))


def _how_many(queries: list[str], method: str, otherwise: int) -> int:
    asked = _asked(queries, method)
    return int(asked[0]["values"][0]) if asked else otherwise


class _FakeDatabases:
    """As much of Appwrite as these routes ask of it: writing a row, changing one, and a listing that knows
    equality, newest first and a page."""

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

    def list_documents(self, _database: str, collection: str, queries: list[str]) -> _Listing:
        kept = [row for row in self.rows.get(collection, []) if _matches(row, queries)]
        ordered = list(reversed(kept)) if _asked(queries, "orderDesc") else kept
        first = _how_many(queries, "offset", 0)
        return _Listing(ordered[first:first + _how_many(queries, "limit", len(ordered))], len(kept))


def _every_record(database: _FakeDatabases) -> Any:
    def every(collection: str, queries: list[str]) -> list[dict[str, Any]]:
        return [as_record(document) for document in database.list_documents("", collection, queries).documents]

    return every


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch, server: fakeredis.FakeRedis) -> Fake:
    state = Fake()
    database = _FakeDatabases(state.rows)

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
    monkeypatch.setattr(petitions, "history", lambda petition_id: [])
    monkeypatch.setattr(petitions, "list_petitions", lambda queries: ([dict(state.petition)], 1))
    monkeypatch.setattr(petition_versions, "record_version",
                        lambda pid, fields, number, at: state.versions.append({**fields, "version": number, "at": at.isoformat()}))
    monkeypatch.setattr(petition_versions, "versions_of", lambda pid: list(state.versions))
    monkeypatch.setattr(petition_signatures, "has_signed", lambda pid, number: False)
    monkeypatch.setattr(petition_signatures, "on_earlier_versions", lambda petition: 0)
    monkeypatch.setattr(ledger_documents, "get_documents", lambda ids: {})
    for module in (petition_comments, petition_departments, petition_removals, petition_reports):
        monkeypatch.setattr(module, "get_databases", lambda: database)
        monkeypatch.setattr(module, "every_record", _every_record(database))
    # The model that reads words written under a petition for the name of a private person is advisory and fails
    # open; a test about that check stubs it the other way.
    monkeypatch.setattr(petition_screen, "private_person", lambda text: None)
    return state


def _publish(stored: Fake) -> dict[str, Any]:
    return petitions.submit(proof_of(PHONE), DRAFT, False, None, NOW)


def _comment(stored: Fake, number: str = PHONE, name: str | None = None, text: str = SAID) -> petition_comments.Seen:
    return petition_comments.add("482913", proof_of(number), name, text, NOW)


def test_a_comment_needs_the_same_confirmed_number_a_signature_does(stored: Fake) -> None:
    _publish(stored)
    client, said = TestClient(app), {"text": SAID}
    assert client.post("/api/petitions/482913/comments", json=said).status_code == 401
    assert client.post("/api/petitions/482913/comments", json=said, headers={"X-Phone-Proof": "not-a-proof"}).status_code == 401
    written = client.post("/api/petitions/482913/comments", json=said, headers=proof_header(PHONE))
    assert written.status_code == 201 and written.json()["text"] == SAID and written.json()["removed"] is False
    assert len(stored.comments) == 1


def test_a_comment_carries_the_name_its_writer_chose_and_never_their_number(stored: Fake) -> None:
    _publish(stored)
    named, unnamed = _comment(stored, PHONE, "Ama Mensah"), _comment(stored, OTHER_PHONE, "  ", "Buses can't pass at all.")
    assert (named.name, unnamed.name) == ("Ama Mensah", "Resident")
    written = str(stored.comments)
    assert "241234567" not in written and "209876543" not in written and "creatorPhone" not in written
    keys = {row["commenterKey"] for row in stored.comments}
    assert len(keys) == 2 and petition_signatures.signer_key("p1", PHONE) not in keys  # unrelated to what it signs
    with pytest.raises(InvalidPetition, match="letters"):
        _comment(stored, PHONE, "Kofi 0241234567")


def test_a_comment_over_five_hundred_characters_is_refused(stored: Fake) -> None:
    _publish(stored)
    assert len(_comment(stored, text="e" * COMMENT_MAX).text) == COMMENT_MAX
    with pytest.raises(InvalidPetition, match="500 characters"):
        _comment(stored, text="e" * (COMMENT_MAX + 1))
    with pytest.raises(InvalidPetition, match="Write your comment"):
        _comment(stored, text="   ")
    assert len(stored.comments) == 1


def test_personal_data_and_the_naming_of_a_private_person_refuse_a_comment_with_the_reason(
        stored: Fake, monkeypatch: pytest.MonkeyPatch) -> None:
    """Refused as written, and never quietly mended: whoever wrote it decides how to say it instead."""
    _publish(stored)
    for text in ("Call me on 024 123 4567", "Write to ama@example.com", "My card is GHA-123456789-0"):
        with pytest.raises(InvalidPetition, match="personal data"):
            _comment(stored, text=text)
    monkeypatch.setattr(petition_screen, "private_person", lambda text: "Auntie Esi")
    with pytest.raises(InvalidPetition, match="private person"):
        _comment(stored, text="Auntie Esi at number 12 tips her rubbish in the drain.")
    assert stored.comments == []


def test_a_number_and_a_petition_each_take_only_so_many_comments_in_an_hour(stored: Fake) -> None:
    """Two counts, neither of which hides anything: one number can't flood the petitions, and one petition can't
    be buried under comments."""
    _publish(stored)
    client = TestClient(app)

    def written(number: str) -> int:
        return client.post("/api/petitions/482913/comments", json={"text": SAID}, headers=proof_header(number)).status_code

    assert {written(PHONE) for _ in range(rate_limit.PETITION_COMMENTS.limit + 1)} == {201, 429}
    others = [written(f"+23324{n:07d}") for n in range(rate_limit.PETITION_COMMENTS_ON_ONE.limit)]
    assert others[0] == 201 and others[-1] == 429  # a fresh number, and the petition's own count is spent


def test_a_contributor_takes_one_comment_down_and_the_petition_and_the_others_stand(stored: Fake) -> None:
    _publish(stored)
    kept, struck = _comment(stored), _comment(stored, OTHER_PHONE, "Ama", "Auntie Esi at number 12 tips hers in it.")
    filed = petition_comments.file_report("482913", struck.id, Ground.PRIVATE_INDIVIDUAL, None, NOW)
    removed = petition_comments.remove(KOFI, "482913", struck.id, Ground.PRIVATE_INDIVIDUAL, NOW)
    assert removed.removed and removed.name is None
    assert removed.text == f"Comment removed by a verified contributor: {in_plain_words(Ground.PRIVATE_INDIVIDUAL)}"
    assert "Auntie Esi" not in str(removed) and "Ama" not in str(removed)
    page, total = petition_comments.on_petition("482913", 20, 0)
    assert [said.text for said in page] == [removed.text, kept.text] and total == 2  # newest first, the other as it was
    assert petitions.public("482913")["status"] == PetitionStatus.OPEN
    assert stored.comment_reports[0]["state"] == ReportState.ACTED_ON  # the report was answered by the removal
    assert stored.comments[1]["removedByName"] == "Kofi Asante" and filed["state"] == ReportState.OPEN
    with pytest.raises(WrongState, match="already been removed"):
        petition_comments.remove(KOFI, "482913", struck.id, Ground.INCITES_VIOLENCE, NOW)


def test_a_reported_comment_reaches_the_same_queue_and_a_dismissal_leaves_it_up(stored: Fake) -> None:
    _publish(stored)
    said = _comment(stored, PHONE, "Ama")
    filed = petition_comments.file_report("482913", said.id, Ground.PERSONAL_DATA, "  There is an address in it.  ", NOW)
    assert filed["note"] == "There is an address in it." and filed["code"] == "482913"
    with pytest.raises(InvalidPetition, match="personal data"):
        petition_comments.file_report("482913", said.id, Ground.PERSONAL_DATA, "Ring the writer on 024 123 4567.", NOW)
    with pytest.raises(petition_comments.CommentNotFound):
        petition_comments.file_report("482913", "petition_comments-9", Ground.PERSONAL_DATA, None, NOW)
    client = TestClient(app)
    app.dependency_overrides[current_principal] = lambda: KOFI
    try:
        queue = client.get("/api/petitions/reports").json()
        assert [item["comment"]["text"] for item in queue["comments"]] == [SAID]
        assert queue["comments"][0]["code"] == "482913" and queue["comments"][0]["reports_on_this_comment"] == 1
        assert queue["comments"][0]["ground_words"] == in_plain_words(Ground.PERSONAL_DATA)
        settled = client.post(f"/api/petitions/comment-reports/{filed['$id']}/dismiss", json={"reason": "not_the_ground"})
        assert settled.status_code == 200 and settled.json()["comments"] == []
    finally:
        app.dependency_overrides.clear()
    assert stored.comment_reports[0]["dismissedReason"] == Dismissal.NOT_THE_GROUND
    assert petition_comments.on_petition("482913", 20, 0)[1] == 1  # the comment stayed up throughout


def test_comments_go_down_with_the_petition_and_are_back_when_it_is_published_again(stored: Fake) -> None:
    """By the same door the tombstone closed: nothing of a removed petition is read, its comments included."""
    _publish(stored)
    _comment(stored)
    client = TestClient(app)
    assert client.get("/api/petitions/482913/comments").json()["total"] == 1
    petition_removals.remove(KOFI, proof_of(CONTRIBUTOR_PHONE), "482913", Ground.PERSONAL_DATA, None, None, NOW)
    gone = client.get("/api/petitions/482913/comments")
    assert gone.status_code == 404 and gone.json()["detail"] == "No petition has that number."
    with pytest.raises(petitions.PetitionNotFound):
        _comment(stored, OTHER_PHONE, None, "Anything at all.")
    mended = Draft(**{**DRAFT.__dict__, "body": f"{DRAFT.body} The market association has written twice."})
    petitions.edit("482913", proof_of(PHONE), mended, NOW + timedelta(days=1))
    back = client.get("/api/petitions/482913/comments").json()
    assert back["total"] == 1 and back["comments"][0]["text"] == SAID
    assert all(row.get("removalGround") is None for row in stored.comments)  # they were never touched, only unreachable


def test_the_petition_says_how_many_comments_stand_under_it(stored: Fake) -> None:
    """USSD and WhatsApp read the count from the petition's own answer, so they can say it without a second call."""
    _publish(stored)
    for text in (SAID, "The market floods to the knee.", "Nothing was done last year either."):
        _comment(stored, f"+2332012345{len(stored.comments):02d}", None, text)
    petition_comments.remove(KOFI, "482913", stored.comments[0]["$id"], Ground.INCITES_VIOLENCE, NOW)
    page = TestClient(app).get("/api/petitions/482913").json()
    assert page["state"] == "published" and page["comments"] == 3  # a removed one still holds its place
