"""The numbers a citizen is shown: each with its source, and the right ones for where the report went."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import contacts
from app.main import app
from app.routes import reports as routes
from app.services import rate_limit
from app.services.report_taxonomy import TOPICS, Category

client = TestClient(app)


def ids(found: list[contacts.PublicContact]) -> list[str]:
    return [c.id for c in found]


def test_a_safety_report_gets_emergency_lines_the_helpline_and_its_sub_metros_welfare_desk() -> None:
    assert ids(contacts.for_report("abuse", "ablekuma-south")) == [
        "emergency-112", "police-191", "police-18555", "helpline-of-hope", "sw-ablekuma-south"]
    assert ids(contacts.for_report("child_at_risk", None))[-1] == "sw-head-office"  # no sub-metro given


def test_other_reports_get_the_numbers_for_where_they_went() -> None:
    assert ids(contacts.for_report("fire", "kinka")) == ["emergency-112", "fire-192", "gnfs"]
    assert ids(contacts.for_report("disaster", None)) == ["emergency-112", "nadmo-emergency"]
    assert ids(contacts.for_report("public_crime", None)) == ["emergency-112", "police-191"]
    assert ids(contacts.for_report("structural_danger", None)) == ["emergency-112", "ama-general"]
    assert ids(contacts.for_report("solid_waste", None)) == ["ama-sanitation-whatsapp", "ama-general"]
    assert ids(contacts.for_report("roads", None)) == ids(contacts.for_report("revenue", None)) == ["ama-general"]


def test_every_danger_to_the_public_starts_with_112_and_every_agency_report_gets_its_line() -> None:
    for topic in TOPICS:
        shown = ids(contacts.for_report(topic.id, None))
        if topic.category != Category.CIVIC_SERVICE:
            assert shown[0] == "emergency-112", topic.id
        for recipient, line in contacts.AGENCY_LINES.items():
            assert recipient not in topic.recipients or line in shown, topic.id


def test_a_number_given_to_nokware_that_differs_is_shown_beside_the_current_one() -> None:
    police = contacts.contacts()["police-main"].numbers
    assert [(n.number, n.current) for n in police] == [("0302 779 300", True), ("0302 773 900", False)]
    assert all(n.note for c in contacts.contacts().values() for n in c.numbers if not n.current)


def test_every_official_number_is_cited_and_only_those_are() -> None:
    for c in contacts.contacts().values():
        assert (c.tier == 2) == (c.source is not None and c.source.url.startswith("https://") and bool(c.source.checked)), c.id
        assert c.tier == 3 or (c.reported_via is None and c.press_url is None), c.id


def test_numbers_whose_source_did_not_hold_up_are_never_shown() -> None:
    held = {h["number"] for h in json.loads(contacts.CONTACTS_FILE.read_text())["held"]}
    shown = {n.number for c in contacts.contacts().values() for n in c.numbers}
    assert held and not held & shown


def test_the_directory_groups_every_contact_by_service() -> None:
    body = client.get("/api/contacts").json()
    assert body["services"][0]["name"] == "Emergency lines"
    assert sum(len(s["contacts"]) for s in body["services"]) == len(contacts.contacts())


@pytest.fixture
def lookup(monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[str, Any]], None]:
    rate_limit.LOOKUPS._hits.clear()
    monkeypatch.setattr(routes.report_store, "assignments_for", lambda case_id: [])

    def found(case: dict[str, Any]) -> None:
        monkeypatch.setattr(routes.report_followups, "find", lambda reference: case)
    return found


def test_an_everyday_status_shows_its_numbers_and_a_safety_status_shows_none(lookup: Callable[[dict[str, Any]], None]) -> None:
    base = {"$id": "c1", "reference": "K7QM-4TXP", "createdAt": "2026-09-01T10:00:00+00:00", "status": "assigned",
            "recipients": ["dept-waste-management"], "wardLocation": "kinka", "subMetro": "ashiedu-keteke"}
    lookup({**base, "topic": "solid_waste", "category": "civic_service", "isSensitive": False})
    assert [c["id"] for c in client.get("/api/reports/K7QM-4TXP").json()["contacts"]] == ["ama-sanitation-whatsapp", "ama-general"]
    lookup({**base, "topic": "abuse", "category": "personal_safety", "isSensitive": True, "recipients": ["agency-police"]})
    assert client.get("/api/reports/K7QM-4TXP").json()["contacts"] == []
