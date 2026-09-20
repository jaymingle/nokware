"""Stage C: the MCE shares a petition with a department, the department answers under its own name, and the
person who started it replies to the MCE once — all of it public, all of it in the trail, none of it on a
tombstone."""

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
    petition_responses,
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
from app.services.petition_grounds import Ground
from app.services.petition_rules import (
    DEPARTMENT_NOTE_MAX,
    REPLY_MAX,
    Draft,
    InvalidPetition,
    NotAllowed,
    PetitionAction,
    Scope,
    WrongState,
)
from app.services.phone_proof import Channel

NOW = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
PHONE, OTHER_PHONE, CONTRIBUTOR_PHONE = "+233241234567", "+233209876543", "+233207654321"
MCE = Principal("u-m", "Hon. Test MCE", "m@x.org", Role.MCE)
KOFI = Principal("u-c", "Kofi Asante", "k@x.org", Role.CONTRIBUTOR)
WORKS = Principal("u-w", "Yaw Boateng", "w@x.org", Role.DEPARTMENT, department="dept-works")
WASTE = Principal("u-s", "Adwoa Nyarko", "s@x.org", Role.DEPARTMENT, department="dept-waste-management")
DRAFT = Draft("Desilt the Odaw drain before the rains", "The drain at Kaneshie floods every June and the market has to close.",
              "drainage", Scope.AREA, "kaneshie", None, ())
ANSWER = "The Assembly will desilt the Kaneshie market drain and publish the schedule on this page."
NOTE = "Works surveyed the drain on 12 September. The desilting contract goes to tender on 2 October."
REPLY = "The market association has heard nothing since the survey, and the rains begin in May."
LIMITS = ("PETITION_CHANGES",)


def _petition(**changes: Any) -> dict[str, Any]:
    """A petition the MCE has answered: the point at which a department can be asked and the creator can reply."""
    base = {"$id": "p1", "code": "482913", "title": DRAFT.title, "body": DRAFT.body, "topic": "drainage",
            "recipients": ["dept-works"], "scope": "area", "wardLocation": "kaneshie", "subMetro": "okaikoi-south",
            "status": "responded", "submittedAt": NOW.isoformat(), "publishedAt": NOW.isoformat(),
            "closesAt": (NOW + timedelta(days=90)).isoformat(), "threshold": 150, "signatureCount": 151,
            "thresholdReachedAt": NOW.isoformat(), "responseDue": (NOW + timedelta(days=30)).isoformat(),
            "respondedAt": NOW.isoformat(), "responseKind": "will_act", "responseText": ANSWER,
            "responseDepartment": None, "responseDocumentIds": [], "respondedByName": MCE.name,
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
    """Every test counts from nothing: the counts live in this process, and one test must not spend another's."""
    for name in LIMITS:
        shipped = getattr(rate_limit, name)
        monkeypatch.setattr(rate_limit, name, rate_limit.RateLimit(shipped.limit, shipped.window))


@dataclass
class Fake:
    """Every collection these routes touch, as rows in dicts."""

    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def petition(self) -> dict[str, Any]:
        return self.rows[petitions.PETITIONS_COLLECTION][0]

    @property
    def shares(self) -> list[dict[str, Any]]:
        return self.rows.setdefault(petition_departments.SHARES_COLLECTION, [])

    @property
    def trail(self) -> list[dict[str, Any]]:
        return self.rows.setdefault(petitions.HISTORY_COLLECTION, [])


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


def _ordered(rows: list[dict[str, Any]], queries: list[str]) -> list[dict[str, Any]]:
    for method, backwards in (("orderAsc", False), ("orderDesc", True)):
        asked = _asked(queries, method)
        if asked:
            return sorted(rows, key=lambda row: str(row.get(asked[0]["attribute"]) or ""), reverse=backwards)
    return rows


class _FakeDatabases:
    """As much of Appwrite as these routes ask of it: writing a row, changing one, and a listing that knows
    equality, an order and a page."""

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
        ordered = _ordered(kept, queries)
        first = _how_many(queries, "offset", 0)
        return _Listing(ordered[first:first + _how_many(queries, "limit", len(ordered))], len(kept))


def _every_record(database: _FakeDatabases) -> Any:
    def every(collection: str, queries: list[str]) -> list[dict[str, Any]]:
        return [as_record(document) for document in database.list_documents("", collection, queries).documents]

    return every


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch, server: fakeredis.FakeRedis) -> Fake:
    """One answered petition in a fake Appwrite, with the real trail, so a timeline is read as a reader reads it."""
    state = Fake(rows={petitions.PETITIONS_COLLECTION: [_petition()]})
    database = _FakeDatabases(state.rows)
    for module in (petitions, petition_comments, petition_departments, petition_removals, petition_reports,
                   petition_signatures, petition_versions):
        monkeypatch.setattr(module, "get_databases", lambda: database)
        if hasattr(module, "every_record"):
            monkeypatch.setattr(module, "every_record", _every_record(database))
    monkeypatch.setattr(ledger_documents, "get_documents", lambda ids: {})
    # The model that reads words for the name of a private person is advisory and fails open; the test about that
    # check stubs it the other way.
    monkeypatch.setattr(petition_screen, "private_person", lambda text: None)
    return state


@pytest.fixture
def client() -> Any:
    portal = TestClient(app)
    yield portal
    app.dependency_overrides.clear()


def _as(principal: Principal) -> None:
    app.dependency_overrides[current_principal] = lambda: principal


def _share(stored: Fake, department: str = "dept-works") -> dict[str, Any]:
    return petition_departments.share(MCE, "482913", department, NOW)


def _answered(stored: Fake) -> None:
    """The department writes its note and the creator replies: the page as both tests below expect to find it."""
    _share(stored)
    petition_departments.add_note(WORKS, "482913", NOTE, NOW + timedelta(days=1))
    petition_responses.reply("482913", proof_of(PHONE), REPLY, NOW + timedelta(days=2))


def test_only_the_mce_shares_a_petition_and_only_with_a_department_of_the_assembly(stored: Fake, client: TestClient) -> None:
    sent = {"department": "dept-works"}
    assert client.post("/api/petitions/482913/share", json=sent).status_code == 401
    for other in (KOFI, WORKS):
        _as(other)
        assert client.post("/api/petitions/482913/share", json=sent).status_code == 403
    _as(MCE)
    shared = client.post("/api/petitions/482913/share", json=sent)
    assert shared.status_code == 200 and [s["department"] for s in shared.json()["shared_with"]] == ["Works Department"]
    assert stored.shares[0]["sharedByName"] == "Hon. Test MCE" and not stored.shares[0].get("note")
    with pytest.raises(WrongState, match="already been shared"):
        _share(stored)
    for not_a_department in ("agency-police", "contributor", "mce", ""):
        with pytest.raises(InvalidPetition, match="department"):
            _share(stored, not_a_department)
    assert len(stored.shares) == 1


def test_a_department_answers_only_a_petition_shared_with_it_and_answers_once(stored: Fake, client: TestClient) -> None:
    _share(stored)
    with pytest.raises(NotAllowed, match="wasn't shared with your department"):
        petition_departments.add_note(WASTE, "482913", NOTE, NOW)
    _as(MCE)
    assert client.post("/api/petitions/482913/note", json={"text": NOTE}).status_code == 403
    _as(WORKS)
    written = client.post("/api/petitions/482913/note", json={"text": NOTE})
    assert written.status_code == 200 and written.json()["note"] == NOTE
    assert written.json()["petition"]["code"] == "482913" and written.json()["note_at"]
    assert stored.shares[0]["notedByName"] == "Yaw Boateng"  # kept for the record; the page shows the department
    with pytest.raises(WrongState, match="already written its note"):
        petition_departments.add_note(WORKS, "482913", "The tender closed on 2 October.", NOW + timedelta(days=30))
    assert stored.shares[0]["note"] == NOTE  # the first answer stands; it was not replaced


def test_a_department_sees_the_petitions_shared_with_it_and_no_others(stored: Fake, client: TestClient) -> None:
    _share(stored)
    _as(WASTE)
    assert client.get("/api/petitions/shared").json() == []
    _as(WORKS)
    queue = client.get("/api/petitions/shared").json()
    assert [item["petition"]["code"] for item in queue] == ["482913"] and queue[0]["note"] is None
    _as(MCE)
    assert client.get("/api/petitions/shared").status_code == 403


def test_a_note_holding_a_number_or_naming_a_private_person_is_refused_with_the_reason(
        stored: Fake, monkeypatch: pytest.MonkeyPatch) -> None:
    """Refused as written, never quietly mended: the note is published, and whoever wrote it decides how to say it."""
    _share(stored)
    for text in ("Call the foreman on 024 123 4567", "Write to works@example.com", "His card is GHA-123456789-0"):
        with pytest.raises(InvalidPetition, match="personal data"):
            petition_departments.add_note(WORKS, "482913", text, NOW)
    with pytest.raises(InvalidPetition, match=f"{DEPARTMENT_NOTE_MAX} characters"):
        petition_departments.add_note(WORKS, "482913", "e" * (DEPARTMENT_NOTE_MAX + 1), NOW)
    with pytest.raises(InvalidPetition, match="Write your department's note"):
        petition_departments.add_note(WORKS, "482913", "   ", NOW)
    monkeypatch.setattr(petition_screen, "private_person", lambda text: "Auntie Esi")
    with pytest.raises(InvalidPetition, match="private person"):
        petition_departments.add_note(WORKS, "482913", "Auntie Esi at number 12 blocks the drain.", NOW)
    assert not stored.shares[0].get("note")


def test_only_the_creator_replies_to_the_response_and_only_once(stored: Fake, client: TestClient) -> None:
    said = {"text": REPLY}
    assert client.post("/api/petitions/482913/reply", json=said).status_code == 401
    assert client.post("/api/petitions/482913/reply", json=said, headers={"X-Phone-Proof": "not-a-proof"}).status_code == 401
    stranger = client.post("/api/petitions/482913/reply", json=said, headers=proof_header(OTHER_PHONE))
    assert stranger.status_code == 404  # anyone else's petition is simply not found, as it is for an edit
    answered = client.post("/api/petitions/482913/reply", json=said, headers=proof_header(PHONE))
    assert answered.status_code == 200 and answered.json()["response"]["reply"]["text"] == REPLY
    with pytest.raises(WrongState, match="already replied"):
        petition_responses.reply("482913", proof_of(PHONE), "And the rains have started.", NOW + timedelta(days=3))
    assert stored.petition["replyText"] == REPLY


def test_there_is_nothing_to_reply_to_until_the_mce_has_answered(stored: Fake) -> None:
    for waiting in ({"status": "open", "respondedAt": None}, {"status": "awaiting_response", "respondedAt": None}):
        stored.petition.update(waiting)
        with pytest.raises(WrongState, match="no response"):
            petition_responses.reply("482913", proof_of(PHONE), REPLY, NOW)
    assert stored.petition.get("replyText") is None


def test_a_reply_over_a_thousand_characters_is_refused(stored: Fake) -> None:
    longest = petition_responses.reply("482913", proof_of(PHONE), "e" * REPLY_MAX, NOW)
    assert len(longest["replyText"]) == REPLY_MAX
    stored.petition.update(replyText=None, replyAt=None)
    with pytest.raises(InvalidPetition, match="1,000 characters"):
        petition_responses.reply("482913", proof_of(PHONE), "e" * (REPLY_MAX + 1), NOW)
    with pytest.raises(InvalidPetition, match="Write your reply"):
        petition_responses.reply("482913", proof_of(PHONE), " ", NOW)
    assert stored.petition["replyText"] is None


def test_the_note_and_the_reply_stand_on_the_public_page_and_in_its_timeline(stored: Fake, client: TestClient) -> None:
    _answered(stored)
    page = client.get("/api/petitions/482913").json()
    assert page["state"] == "published"
    assert page["shared_with"] == [{"department": "Works Department", "shared_at": NOW.isoformat(),
                                    "note": NOTE, "note_at": (NOW + timedelta(days=1)).isoformat()}]
    assert page["response"]["reply"] == {"text": REPLY, "at": (NOW + timedelta(days=2)).isoformat()}
    timeline = [(entry["action"], entry["reason"]) for entry in page["timeline"]]
    assert timeline == [("shared", "Works Department"), ("department_note", "Works Department"),
                        ("creator_replied", None)]  # the response itself was answered before this petition was seeded
    assert [row["actorRole"] for row in stored.trail] == ["mce", "department", "creator"]
    assert "Yaw Boateng" not in json.dumps(page)  # the department answers, not the officer who typed it


def test_a_removed_petition_carries_neither_its_departments_nor_its_reply(stored: Fake, client: TestClient) -> None:
    """The tombstone is built from the removal record alone; what is not deleted is only unreachable, and comes
    back with the petition when its creator publishes it again."""
    _answered(stored)
    petition_removals.remove(KOFI, proof_of(CONTRIBUTOR_PHONE), "482913", Ground.PERSONAL_DATA, None, None,
                             NOW + timedelta(days=3))
    stone = client.get("/api/petitions/482913")
    assert stone.status_code == 200 and stone.json()["state"] == "removed"
    written = json.dumps(stone.json())
    assert NOTE not in written and REPLY not in written and ANSWER not in written
    assert "Works Department" not in written and "shared_with" not in written and "response" not in written
    with pytest.raises(petitions.PetitionNotFound):
        petition_departments.add_note(WASTE, "482913", NOTE, NOW + timedelta(days=4))
    with pytest.raises(WrongState, match="no response"):
        petition_responses.reply("482913", proof_of(PHONE), REPLY, NOW + timedelta(days=4))
    _as(WORKS)
    assert client.get("/api/petitions/shared").json() == []  # a department answers what the public can read
    petitions.edit("482913", proof_of(PHONE), DRAFT, NOW + timedelta(days=5))
    back = client.get("/api/petitions/482913").json()
    assert back["shared_with"][0]["note"] == NOTE and back["response"]["reply"]["text"] == REPLY
    assert [entry["action"] for entry in back["timeline"]][-1] == PetitionAction.REPUBLISHED
