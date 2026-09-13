"""The staff case routes: role gates, and no hint that a case exists to someone with no view of it."""

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.main import app
from app.routes import cases as routes
from app.services.auth import Principal, Role

FINANCE = Principal("u-f", "Finance", "f@x.org", Role.DEPARTMENT, "dept-finance")
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


def test_only_the_mce_oversees_and_contributors_have_no_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    assert as_user(FINANCE, monkeypatch).get("/api/cases/oversight", headers=BEARER).status_code == 403
    assert as_user(CONTRIBUTOR, monkeypatch).get("/api/cases/queue", headers=BEARER).status_code == 403
    assert as_user(FINANCE, monkeypatch).post("/api/cases/c1/reassign", headers=BEARER,
                                              json={"from_recipient": "a", "to_recipient": "b", "reason": "r"}).status_code == 403
