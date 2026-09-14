"""Staff changes to cases and what each caller sees, with storage replaced by an in-memory fake."""

import itertools
from datetime import datetime, timezone
from typing import Any

import pytest

from app.routes import case_presenters
from app.services import case_actions
from app.services.auth import Principal, Role
from app.services.case_workflow import Reassignment
from app.services.workflow import NotAllowed, WrongState

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
WORKS = Principal("u-w", "Kofi (Works)", "w@x.org", Role.DEPARTMENT, "dept-works")
POLICE = Principal("u-p", "Police liaison", "p@x.org", Role.AGENCY, agency="agency-police")
WELFARE = Principal("u-s", "Social Welfare", "s@x.org", Role.DEPARTMENT, "dept-social-welfare")
MCE = Principal("u-m", "MCE", "m@x.org", Role.MCE)


class Fake:
    def __init__(self) -> None:
        self.cases: dict[str, dict[str, Any]] = {}
        self.assignments: dict[str, dict[str, Any]] = {}
        self.trail: list[Any] = []
        self.ids = itertools.count(1)

    def add_case(self, case_id: str, recipients: list[str], **fields: Any) -> None:
        self.cases[case_id] = {"$id": case_id, "reference": "K7QM-4TXP", "status": "assigned", "category": "civic_service",
                               "isSensitive": False, "severity": 3, "recipients": recipients, "topic": "drainage",
                               "description": "The drain is choked.", "createdAt": NOW.isoformat(), "wardLocation": "mudor",
                               "subMetro": "ashiedu-keteke", "photoIds": ["reports/x/01.jpg"], "classificationNote": "Classified.",
                               **fields}
        for recipient in recipients:
            self.create_assignment({"caseId": case_id, "recipient": recipient, "status": "assigned", "active": True,
                                    "assignedAt": NOW.isoformat()})

    def create_assignment(self, data: dict[str, Any]) -> dict[str, Any]:
        record = {**data, "$id": f"a{next(self.ids)}"}
        self.assignments[record["$id"]] = record
        return record

    def update_assignment(self, assignment_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        self.assignments[assignment_id].update(changes)
        return dict(self.assignments[assignment_id])

    def update_case(self, case_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        self.cases[case_id].update(changes)
        return dict(self.cases[case_id])

    def assignments_for(self, case_id: str) -> list[dict[str, Any]]:
        return [dict(a) for a in self.assignments.values() if a["caseId"] == case_id]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Fake:
    f = Fake()
    store = case_actions.report_store
    monkeypatch.setattr(store, "find_case", lambda case_id: dict(f.cases[case_id]) if case_id in f.cases else None)
    for name in ("assignments_for", "create_assignment", "update_assignment", "update_case"):
        monkeypatch.setattr(store, name, getattr(f, name))
    monkeypatch.setattr(case_actions.case_history, "record", lambda case_id, entry: f.trail.append(entry))
    monkeypatch.setattr(case_actions, "sync_contact_retention", lambda case: None)
    return f


def test_a_department_starts_and_finishes_a_case_and_the_citizen_is_told(fake: Fake) -> None:
    fake.add_case("c1", ["dept-works"])
    assert case_actions.acknowledge(WORKS, "c1", NOW).case["status"] == "in_progress"
    outcome = case_actions.resolve(WORKS, "c1", "Drain desilted on 12 September.", NOW)
    assert outcome.resolved and outcome.case["status"] == "resolved" and outcome.case["resolvedAt"]
    assert [e.action for e in fake.trail] == ["acknowledged", "resolved"]
    assert fake.trail[1].note == "Resolved by Works Department. Drain desilted on 12 September." and fake.trail[1].actor.name == "Kofi (Works)"


def test_a_two_recipient_case_waits_for_both_and_its_trail_never_quotes_them(fake: Fake) -> None:
    fake.add_case("c2", ["agency-police", "dept-social-welfare"], category="personal_safety", isSensitive=True)
    first = case_actions.resolve(POLICE, "c2", "Arrested the suspect; statement taken.", NOW)
    assert not first.resolved and first.case["status"] == "in_progress"
    assert case_actions.resolve(WELFARE, "c2", "Family moved to a shelter.", NOW).resolved
    assert all("suspect" not in (e.note or "") and "shelter" not in (e.note or "") for e in fake.trail)


def test_an_escalated_case_waits_for_the_mce(fake: Fake) -> None:
    fake.add_case("c3", ["dept-works"], status="escalated", escalatedAt=NOW.isoformat())
    with pytest.raises(WrongState):
        case_actions.resolve(WORKS, "c3", "Done again", NOW)
    with pytest.raises(NotAllowed):
        case_actions.acknowledge(POLICE, "c3", NOW)


def test_the_mce_reassigns_one_part_and_the_trail_gives_the_reason(fake: Fake) -> None:
    fake.add_case("c4", ["dept-works"])
    outcome = case_actions.reassign(MCE, "c4", Reassignment("dept-works", "dept-waste-management"), "Refuse, not drains.", NOW)
    active = [a["recipient"] for a in fake.assignments_for("c4") if a["active"]]
    assert active == ["dept-waste-management"] and outcome.case["recipients"] == ["dept-waste-management"]
    assert fake.trail[-1].note == "Moved from Works Department to Waste Management: Refuse, not drains."


def test_the_mce_reopens_or_confirms_an_escalated_case(fake: Fake) -> None:
    fake.add_case("c5", ["dept-works"], status="escalated", escalatedAt=NOW.isoformat(), resolvedAt=NOW.isoformat())
    for a in fake.assignments.values():
        a.update(status="resolved", resolutionNote="Done.")
    reopened = case_actions.reopen(MCE, "c5", "Water still stands at the gate.", NOW)
    assert reopened.case["status"] == "assigned" and fake.assignments_for("c5")[0]["resolutionNote"] is None
    fake.add_case("c6", ["dept-works"], status="escalated", escalatedAt=NOW.isoformat(), resolvedAt=NOW.isoformat())
    assert case_actions.confirm_resolution(MCE, "c6", "Photos show the drain clear.", NOW).resolved


def test_recipients_see_everything_and_the_mce_sees_a_safety_case_only_in_outline(
    fake: Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(case_presenters.report_locations, "contact_for", lambda case_id: None)  # no location shared
    monkeypatch.setattr(case_presenters.case_history, "entries_for", lambda case_id: [
        {"action": "classified", "actorName": "Nokware", "actorRole": "system", "note": "Filed by the citizen as personal safety: Sexual violence.", "timestamp": NOW.isoformat()},
    ])
    monkeypatch.setattr(case_presenters, "photo_link", lambda name: f"https://photos.test/{name}")
    monkeypatch.setattr(case_presenters, "contact_for", lambda case_id: {"phone": "+233241234567", "whatsapp": None, "callbackConsent": True})
    fake.add_case("c7", ["agency-police", "dept-social-welfare"], category="personal_safety", isSensitive=True,
                  topic="sexual_violence", wardLocation=None, subMetro="okaikoi-south")
    case = fake.cases["c7"]
    police = case_presenters.detail(POLICE, case, fake.assignments_for("c7"))
    assert police.view == "full" and police.description and police.photos and police.contact and police.contact.phone
    assert police.topic == "Sexual violence" and police.place == "Okaikoi South" and police.allowed_actions == ["acknowledge", "resolve"]
    mce = case_presenters.detail(MCE, case, fake.assignments_for("c7"))
    assert mce.view == "oversight" and mce.topic == "Personal safety"
    assert (mce.description, mce.photos, mce.place, mce.contact, mce.excerpt, mce.classification_note) == (None, [], None, None, None, None)
    assert mce.history[0].note == "Filed as personal safety." and mce.recipients == ["Ghana Police Service", "Social Welfare & Community Development"]  # staff see full names
