"""The staff case routes: role gates, and no hint that a case exists to someone with no view of it."""

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from app import dependencies
from app.main import app
from app.routes import cases as routes
from app.schemas.cases import OptionalNoteRequest
from app.services.auth import Principal, Role
from app.services.case_actions import Outcome
from app.services.citizen_reports import NotificationEvent

FINANCE = Principal("u-f", "Finance", "f@x.org", Role.DEPARTMENT, "dept-finance")
MCE = Principal("u-m", "MCE", "m@x.org", Role.MCE)
CONTRIBUTOR = Principal("u-c", "Contributor", "c@x.org", Role.CONTRIBUTOR)
BEARER = {"Authorization": "Bearer t"}
SAFETY_CASE = {"$id": "c1", "category": "personal_safety", "recipients": ["agency-police", "dept-social-welfare"]}


def as_user(principal: Principal, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(dependencies, "authenticate", lambda jwt: principal)
    return TestClient(app)


def test_a_department_with_no_part_in_a_case_gets_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes.case_queries, "load", lambda case_id: (SAFETY_CASE, []))
    response = as_user(FINANCE, monkeypatch).get("/api/cases/c1", headers=BEARER)
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (Outcome({"$id": "c1"}, resolved=False, started=True), [NotificationEvent.STARTED]),
        (Outcome({"$id": "c1"}, resolved=False), []),
        (Outcome({"$id": "c1"}, resolved=True), [NotificationEvent.RESOLVED]),
        (Outcome({"$id": "c1"}, resolved=False, reassigned=True), [NotificationEvent.REASSIGNED]),
        (Outcome({"$id": "c1"}, resolved=False, reopened=True), [NotificationEvent.REOPENED]),
    ],
)
def test_the_citizen_is_told_after_the_response_and_never_inside_the_request(
    monkeypatch: pytest.MonkeyPatch, outcome: Outcome, expected: list[NotificationEvent]
) -> None:
    """A department's "Start work" must not wait on a provider, and a provider failing must not fail the action."""
    monkeypatch.setattr(routes, "_visible", lambda principal, case_id: case_id)
    tasks = BackgroundTasks()

    routes._after(FINANCE, outcome, tasks)

    assert [task.args for task in tasks.tasks] == [(outcome.case, event) for event in expected]
    assert all(task.func is routes.notify_quietly for task in tasks.tasks)


def test_only_the_mce_oversees_and_contributors_have_no_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    assert as_user(FINANCE, monkeypatch).get("/api/cases/oversight", headers=BEARER).status_code == 403
    assert as_user(CONTRIBUTOR, monkeypatch).get("/api/cases/queue", headers=BEARER).status_code == 403
    assert as_user(FINANCE, monkeypatch).post("/api/cases/c1/reassign", headers=BEARER,
                                              json={"from_recipient": "a", "to_recipient": "b", "reason": "r"}).status_code == 403


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("Reach the supervisor on 0241234567.", "contains a phone number"),
        ("Write to kofi@example.com.", "contains an email address"),
        ("a" * 501, "at most 500 characters"),
    ],
)
def test_a_note_that_cannot_be_shown_to_a_resident_is_refused_before_anything_is_saved(
    monkeypatch: pytest.MonkeyPatch, note: str, expected: str
) -> None:
    """Nothing is stubbed but who is signed in: the note is screened before the case is so much as read."""
    response = as_user(FINANCE, monkeypatch).post("/api/cases/c1/resolve", headers=BEARER, json={"note": note})

    assert response.status_code == 422 and expected in str(response.json())


def _body_required(path: str) -> bool:
    post = app.openapi()["paths"][f"/api/cases/{{case_id}}/{path}"]["post"]
    return bool(post.get("requestBody", {}).get("required"))


def test_the_stages_that_offer_a_note_take_no_body_at_all_and_the_two_that_need_one_insist() -> None:
    """What the web has to know to build the buttons: which stages may be posted with nothing in them."""
    assert not _body_required("acknowledge") and not _body_required("reopen")
    assert not _body_required("confirm-resolution")
    assert _body_required("resolve") and _body_required("reassign")


def test_a_note_reaches_the_stage_it_was_written_at(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(routes, "_visible", lambda principal, case_id: case_id)
    monkeypatch.setattr(routes.case_actions, "acknowledge",
                        lambda principal, case_id, note, now: seen.append(note) or Outcome({"$id": case_id}, resolved=False))

    routes.acknowledge(FINANCE, "c1", BackgroundTasks(), OptionalNoteRequest())
    routes.acknowledge(FINANCE, "c1", BackgroundTasks(), OptionalNoteRequest(note="A crew comes Monday."))

    assert seen == ["", "A crew comes Monday."]
