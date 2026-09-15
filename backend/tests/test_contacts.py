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
from app.services.channel_contacts import medical_text, numbers_text
from app.services.report_taxonomy import TOPICS, TOPICS_BY_ID, Category

client = TestClient(app)


def ids(found: list[contacts.PublicContact]) -> list[str]:
    return [c.id for c in found]


POLICE = ["police-191", "police-18555", "police-main"]
AMBULANCE = ["ambulance-193", "nas"]


def test_a_safety_report_gets_every_number_to_try_and_its_sub_metros_welfare_desk() -> None:
    assert ids(contacts.for_report("abuse", "ablekuma-south")) == [
        "emergency-112", *POLICE, "dovvsu", "police-mobile", "police-whatsapp", "helpline-of-hope",
        "sw-ablekuma-south", "sw-head-office", *AMBULANCE]
    unknown = ids(contacts.for_report("child_at_risk", None))  # no sub-metro given: every desk, then the head office
    assert unknown[unknown.index("helpline-of-hope") + 1:unknown.index("ambulance-193")] == [
        "sw-ashiedu-keteke", "sw-ablekuma-south", "sw-okaikoi-south", "sw-head-office"]
    assert contacts.safety_contacts(None) == contacts.for_report("abuse", None)


def test_other_emergencies_get_every_number_for_each_service_they_need() -> None:
    assert ids(contacts.for_report("fire", None)) == ["emergency-112", "fire-192", "gnfs", *AMBULANCE]
    assert ids(contacts.for_report("disaster", None)) == ["emergency-112", "nadmo-emergency", "nadmo-whatsapp", *AMBULANCE]
    assert ids(contacts.for_report("public_crime", None)) == ["emergency-112", *POLICE, *AMBULANCE]  # no unverified lines
    assert ids(contacts.for_report("structural_danger", None)) == ["emergency-112", "fire-192", "gnfs", *AMBULANCE, "ama-general"]
    assert ids(contacts.for_report("solid_waste", None)) == ["ama-sanitation-whatsapp", "ama-general"]
    assert ids(contacts.for_report("roads", None)) == ids(contacts.for_report("revenue", None)) == ["ama-general"]


def test_where_a_screen_cannot_hold_them_two_numbers_per_service() -> None:
    assert contacts.short_line("fire", None) == "Fire: 112, 192. Ambulance: 193, 0501 614 877."
    assert contacts.short_line("public_crime", None) == "Police: 112, 191. Ambulance: 193, 0501 614 877."
    assert contacts.short_line("abuse", "okaikoi-south") == (
        "Police: 112, 191. DOVVSU (domestic violence): 0551 000 900. Helpline: 0800 800 800, 0800 900 900. "
        "Social Welfare: 0303 935 397. Ambulance: 193, 0501 614 877.")
    assert "Social Welfare: 0550 006 688." in contacts.short_line("abuse", None)  # the head office when unknown
    assert contacts.short_line("roads", None) == ""


def test_the_chat_list_keeps_every_number_and_its_source_label() -> None:
    text = numbers_text("abuse", None)
    listed = {n.number for c in contacts.for_report("abuse", None) for n in c.numbers}
    assert all(number in text for number in listed)
    assert "*Police reporting lines* (reported via X by the Ghana Police Service, not independently verified)" in text
    assert "0302 773 900 (Police HQ, Accra; an earlier listing, may not connect)" in text
    assert "Assembly" not in text and numbers_text("roads", None) == ""


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


def test_an_everyday_status_shows_its_numbers_and_a_safety_status_shows_none(
    lookup: Callable[[dict[str, Any]], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes.report_followups.report_locations, "views", lambda case_id: [])
    base = {"$id": "c1", "reference": "K7QM-4TXP", "createdAt": "2026-09-01T10:00:00+00:00", "status": "assigned",
            "recipients": ["dept-waste-management"], "wardLocation": "kinka", "subMetro": "ashiedu-keteke"}
    lookup({**base, "topic": "solid_waste", "category": "civic_service", "isSensitive": False})
    assert [c["id"] for c in client.get("/api/reports/K7QM-4TXP").json()["contacts"]] == ["ama-sanitation-whatsapp", "ama-general"]
    lookup({**base, "topic": "abuse", "category": "personal_safety", "isSensitive": True, "recipients": ["agency-police"]})
    assert client.get("/api/reports/K7QM-4TXP").json()["contacts"] == []


def test_a_road_accident_goes_to_the_police_with_police_and_ambulance_numbers() -> None:
    assert TOPICS_BY_ID["road_accident"].recipients == ("agency-police",)
    assert ids(contacts.for_report("road_accident", None)) == ["emergency-112", *POLICE, *AMBULANCE]


def test_a_medical_emergency_gets_the_ambulance_and_is_told_plainly_it_isnt_the_assemblys() -> None:
    text = medical_text()
    assert text.startswith("This isn't something the Assembly can act on, so Nokware won't file it.")
    assert all(number in text for number in ("112", "193", "0501 614 877", "0505 982 870"))


def test_dovvsu_is_the_line_the_police_publish_checked_on_its_own_date() -> None:
    dovvsu = contacts.contacts()["dovvsu"]
    assert dovvsu.tier == 2 and [n.number for n in dovvsu.numbers] == ["0551 000 900"]
    assert dovvsu.source and dovvsu.source.label == "police.gov.gh" and dovvsu.source.checked == "2026-09-15"
    assert contacts.contacts()["police-main"].source.checked == contacts.directory().checked  # the file's date otherwise
