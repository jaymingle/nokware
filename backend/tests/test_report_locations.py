"""A shared precise location: kept apart, opened only by the Police or Social Welfare on the case, every view told."""

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.dependencies import current_principal
from app.main import app
from app.routes import case_presenters, cases
from app.services import report_followups, report_locations
from app.services.auth import Principal, Role
from app.services.case_history import CaseHistoryAction
from app.services.workflow import NotAllowed

NOW = datetime(2026, 9, 14, 20, 0, tzinfo=UTC)
CASE = {"$id": "c2", "reference": "M3RD-8WQA", "category": "personal_safety", "isSensitive": True, "topic": "abuse",
        "status": "assigned", "severity": 5, "description": "[TEST] He hits me.", "classificationNote": "Classified.", "createdAt": "2026-09-14T19:00:00+00:00", "subMetro": "okaikoi-south",
        "recipients": ["agency-police", "dept-social-welfare"]}
ACTIVE = [{"$id": "a1", "recipient": "agency-police", "status": "assigned", "active": True},
          {"$id": "a2", "recipient": "dept-social-welfare", "status": "assigned", "active": True}]
POLICE = Principal("u-p", "Officer Mensah", "p@x.org", Role.AGENCY, agency="agency-police")
WELFARE = Principal("u-w", "Social Welfare", "w@x.org", Role.DEPARTMENT, department="dept-social-welfare")
WORKS = Principal("u-k", "Works Department", "k@x.org", Role.DEPARTMENT, department="dept-works")
MCE = Principal("u-m", "MCE", "m@x.org", Role.MCE)
PLACE = {"address": "House 12, behind the Kaneshie market clinic", "latitude": 5.567, "longitude": -0.235}


@pytest.fixture
def records(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The contact record and the audit trail, in memory."""
    store: dict[str, Any] = {"contact": {"caseId": "c2", "whatsapp": "+233507387216"}, "history": []}

    def update(case_id: str, changes: dict[str, Any]) -> None:
        store["contact"].update(changes)

    def record(case_id: str, entry: Any) -> None:
        store["history"].append({"action": entry.action.value, "toDept": entry.to_recipient, "note": entry.note,
                                 "actorName": entry.actor.name, "actorRole": entry.actor.role.value, "timestamp": NOW.isoformat()})

    monkeypatch.setattr(report_locations, "update_contact", update)
    monkeypatch.setattr(report_locations, "contact_for", lambda case_id: store["contact"])
    monkeypatch.setattr(report_locations.case_history, "record", record)
    monkeypatch.setattr(report_locations.case_history, "entries_for", lambda case_id: store["history"])
    return store


def test_a_shared_location_is_stored_apart_and_the_trail_never_says_where(records: dict[str, Any]) -> None:
    report_locations.share("c2", PLACE["address"], PLACE["latitude"], PLACE["longitude"], NOW)
    assert json.loads(records["contact"]["exactLocation"]) == PLACE and records["contact"]["exactLocationAt"] == NOW.isoformat()
    assert records["history"][0]["action"] == CaseHistoryAction.LOCATION_SHARED
    assert "Kaneshie" not in str(records["history"]) and "5.567" not in str(records["history"])
    with pytest.raises(ValueError):
        report_locations.share("c2", "  ", None, None, NOW)


@pytest.mark.parametrize("principal", [POLICE, WELFARE])
def test_the_police_or_social_welfare_on_the_case_can_open_it_and_each_view_is_recorded(records: dict[str, Any], principal: Principal) -> None:
    report_locations.share("c2", PLACE["address"], PLACE["latitude"], PLACE["longitude"], NOW)
    assert report_locations.shared_at(principal, CASE, ACTIVE) == NOW.isoformat()
    opened = report_locations.open_location(principal, CASE, ACTIVE)
    assert (opened.address, opened.latitude, opened.longitude) == (PLACE["address"], 5.567, -0.235)
    viewed = records["history"][-1]
    assert viewed["action"] == CaseHistoryAction.LOCATION_VIEWED and viewed["toDept"] == principal.recipient
    assert "Kaneshie" not in str(viewed)


@pytest.mark.parametrize(("principal", "assignments", "case"), [
    (MCE, ACTIVE, CASE),
    (WORKS, [*ACTIVE, {"$id": "a3", "recipient": "dept-works", "status": "assigned", "active": True}], CASE),  # not a responder
    (POLICE, [{**ACTIVE[0], "active": False}, ACTIVE[1]], CASE),  # the MCE moved the Police off the case
    (POLICE, ACTIVE, {**CASE, "category": "civic_service", "isSensitive": False}),
])
def test_no_one_else_can_see_or_open_it(records: dict[str, Any], principal: Principal, assignments: list[dict[str, Any]], case: dict[str, Any]) -> None:
    report_locations.share("c2", PLACE["address"], None, None, NOW)
    assert report_locations.shared_at(principal, case, assignments) is None
    with pytest.raises(NotAllowed):
        report_locations.open_location(principal, case, assignments)
    assert not any(e["action"] == CaseHistoryAction.LOCATION_VIEWED for e in records["history"])


def test_the_citizen_sees_each_view_by_service_never_by_person(records: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    report_locations.share("c2", PLACE["address"], None, None, NOW)
    report_locations.open_location(POLICE, CASE, ACTIVE)
    assert report_locations.views("c2") == [{"by": "Ghana Police Service", "at": NOW.isoformat()}]
    status = report_followups.public_status(CASE, ACTIVE, NOW)
    assert status["location_views"] == [{"by": "Ghana Police Service", "at": NOW.isoformat()}]
    assert "Mensah" not in str(status) and "abuse" not in str(status).lower()


def test_remove_deletes_it_and_says_so_only_once_it_is_gone(records: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    report_locations.share("c2", PLACE["address"], None, None, NOW)
    assert report_locations.remove("c2")
    assert records["contact"]["exactLocation"] is None and records["history"][-1]["action"] == CaseHistoryAction.LOCATION_REMOVED
    with pytest.raises(report_locations.NoLocation):
        report_locations.open_location(POLICE, CASE, ACTIVE)
    monkeypatch.setattr(report_locations, "update_contact", lambda case_id, changes: None)  # the delete didn't happen
    records["contact"]["exactLocation"] = "{}"
    assert not report_locations.remove("c2")


def test_the_case_detail_tells_only_a_responder_that_there_is_one_and_never_carries_it(records: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    report_locations.share("c2", PLACE["address"], None, None, NOW)
    monkeypatch.setattr(case_presenters, "contact_for", lambda case_id: records["contact"])
    monkeypatch.setattr(case_presenters.case_history, "entries_for", lambda case_id: records["history"])
    for principal, expected in ((POLICE, NOW.isoformat()), (MCE, None)):
        shown = case_presenters.detail(principal, CASE, ACTIVE).model_dump_json()
        assert json.loads(shown)["location_shared_at"] == expected
        assert "Kaneshie" not in shown and "exactLocation" not in shown


def test_the_route_opens_it_for_a_responder_and_is_closed_to_the_mce(records: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    report_locations.share("c2", PLACE["address"], PLACE["latitude"], PLACE["longitude"], NOW)
    monkeypatch.setattr(cases.case_queries, "load", lambda case_id: (CASE, ACTIVE) if case_id == "c2" else None)
    client = TestClient(app)
    try:
        app.dependency_overrides[current_principal] = lambda: POLICE
        body = client.get("/api/cases/c2/location").json()
        assert body == {**PLACE, "shared_at": NOW.isoformat()}
        app.dependency_overrides[current_principal] = lambda: MCE
        assert client.get("/api/cases/c2/location").status_code == 403
        app.dependency_overrides[current_principal] = lambda: POLICE
        report_locations.remove("c2")
        assert client.get("/api/cases/c2/location").status_code == 404
    finally:
        app.dependency_overrides.clear()
