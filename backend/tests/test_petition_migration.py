"""Moving the petitions that were already in the database to Stage A: the mapping in docs/petition-migration.md,
and the rule that nothing is deleted and nothing unrecognised is touched."""

from datetime import UTC, datetime, timedelta
from typing import Any

import migrate_petitions as migration
import pytest

from app.services import petition_screen, petition_versions, petitions
from app.services.petition_rules import PetitionAction, PetitionStatus

NOW = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)
WRITTEN = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)
WAITING = {"$id": "p1", "code": "504162", "title": "The Assembly has not posted its financials",
           "body": "The last budget on the Assembly's site is from 2023, and the tariffs page is empty.",
           "topic": "drainage", "scope": "metro", "wardLocation": None, "imageIds": [],
           "status": "in_review", "submittedAt": WRITTEN.isoformat(), "createdAt": WRITTEN.isoformat()}


def test_every_old_status_has_somewhere_to_go_and_anything_else_is_left_alone() -> None:
    for status in ("open", "awaiting_response", "responded", "closed"):
        assert migration.move_for(status, None) == migration.Move(PetitionStatus(status), status, None)
    assert migration.move_for("someday_maybe", None) is None  # no rule fits it, so nothing is written to it


def test_a_refusal_is_closed_and_still_named_as_what_it_was() -> None:
    """Never as a contributor's removal: no contributor removed it, and saying so would be untrue."""
    move = migration.move_for("refused", None)
    assert move == migration.Move(PetitionStatus.CLOSED, "refused", "Refused under the earlier review process")
    assert migration.move_for("withdrawn", None).label == "Withdrawn by the person who started it"


def test_a_petition_that_was_waiting_for_the_mce_is_published_unless_the_screen_now_stops_it() -> None:
    assert migration.move_for("in_review", None) == migration.Move(PetitionStatus.OPEN, "in_review", None)
    stopped = migration.move_for("in_review", "It contains a phone number.")
    assert stopped is not None and stopped.status == PetitionStatus.CLOSED and stopped.legacy_status == "in_review"
    assert stopped.label == "Closed during the move to the new petition process"
    assert stopped.note == "Closed during the move to the new petition process: It contains a phone number."


def test_only_a_petition_that_was_waiting_is_screened_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-screening what is already public would take down words nobody is about to publish."""
    monkeypatch.setattr(petition_screen, "hard_stop", lambda title, body: "It contains a phone number.")
    assert migration.screen_stop_for(WAITING) == "It contains a phone number."
    assert migration.screen_stop_for({**WAITING, "status": "open"}) is None


def test_a_published_petition_keeps_the_date_it_was_written_and_its_own_ninety_days() -> None:
    changes = migration.changes_for(WAITING, migration.move_for("in_review", None), NOW)
    assert changes["publishedAt"] == WRITTEN.isoformat() and changes["legacyStatus"] == "in_review"
    assert changes["closesAt"] == (WRITTEN + timedelta(days=90)).isoformat() and changes["threshold"] == 500
    assert changes["version"] == 1 and changes["removalCount"] == 0 and changes["status"] == "open"


def test_a_petition_the_old_process_ended_is_closed_and_never_becomes_public() -> None:
    refused = {**WAITING, "status": "refused"}
    changes = migration.changes_for(refused, migration.move_for("refused", None), NOW)
    assert changes["status"] == "closed" and changes["legacyStatus"] == "refused" and changes["closedAt"] == NOW.isoformat()
    assert "publishedAt" not in changes  # it was never published, and the move doesn't publish it
    assert not petitions.is_public({**refused, **changes})


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"petition": dict(WAITING), "trail": [], "versions": [], "signatures": [{"$id": "s1"}]}
    monkeypatch.setattr(migration, "every_petition", lambda: [dict(state["petition"])])
    monkeypatch.setattr(petitions, "update_petition",
                        lambda pid, changes: state.update(petition={**state["petition"], **changes}) or dict(state["petition"]))
    monkeypatch.setattr(petitions, "record_history", lambda p, action, actor, from_status, reason=None, note=None:
                        state["trail"].append((action, actor.role, from_status, reason, note)))
    monkeypatch.setattr(petition_versions, "versions_of", lambda pid: list(state["versions"]))
    monkeypatch.setattr(petition_versions, "record_version",
                        lambda pid, fields, number, at: state["versions"].append({**fields, "version": number, "at": at}))
    monkeypatch.setattr(migration, "every_record", lambda collection, queries: list(state["signatures"]))
    monkeypatch.setattr(migration, "get_databases",
                        lambda: type("Db", (), {"update_document": lambda self, *a: state.update(signed=a[-1])})())
    monkeypatch.setattr(petition_screen, "hard_stop", lambda title, body: None)
    return state


def test_a_dry_run_writes_nothing(stored: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    migration.run(False, NOW)
    assert stored["petition"] == WAITING and stored["trail"] == [] and stored["versions"] == []
    printed = capsys.readouterr().out
    assert "[dry run] 504162: in_review -> open" in printed and "1 to move" in printed


def test_the_move_publishes_it_keeps_what_it_was_and_starts_its_history(stored: dict[str, Any]) -> None:
    migration.run(True, NOW)
    petition = stored["petition"]
    assert petition["status"] == "open" and petition["legacyStatus"] == "in_review"
    assert petition["title"] == WAITING["title"] and petition["body"] == WAITING["body"]  # nothing is deleted
    assert stored["trail"] == [(PetitionAction.PUBLISHED, "system", "in_review", "in_review", None)]
    assert [(v["version"], v["title"]) for v in stored["versions"]] == [(1, WAITING["title"])]
    assert stored["signed"] == {"version": 1}  # the signatures it already had were given to version 1


def test_the_move_closes_a_petition_the_screen_now_stops(stored: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(petition_screen, "hard_stop", lambda title, body: "It contains a phone number.")
    migration.run(True, NOW)
    assert stored["petition"]["status"] == "closed" and stored["petition"]["legacyStatus"] == "in_review"
    assert stored["trail"][0][0] == PetitionAction.CLOSED
    assert stored["trail"][0][4] == "Closed during the move to the new petition process: It contains a phone number."


def test_a_row_no_rule_fits_is_reported_and_left_exactly_as_it_was(stored: dict[str, Any],
                                                                   capsys: pytest.CaptureFixture[str]) -> None:
    stored["petition"]["status"] = "half_written"
    migration.run(True, NOW)
    assert stored["petition"]["status"] == "half_written" and stored["trail"] == []
    assert "untouched 504162: half_written fits no rule" in capsys.readouterr().out
