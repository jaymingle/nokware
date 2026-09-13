"""Role resolution from team membership, and the auth dependencies' responses."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import dependencies
from app.dependencies import CurrentPrincipal, require_roles
from app.services.auth import InvalidTokenError, NoRoleError, Principal, Role, resolve_role

FINANCE = Principal(user_id="u1", name="Finance", email="f@example.org", role=Role.DEPARTMENT, department="dept-finance")


def test_department_team_gives_its_department() -> None:
    assert resolve_role(["dept-finance"]) == (Role.DEPARTMENT, "dept-finance")
    assert resolve_role(["dept-press"]) == (Role.DEPARTMENT, "dept-press")


def test_contributor_and_mce_have_no_department() -> None:
    assert resolve_role(["contributor"]) == (Role.CONTRIBUTOR, None)
    assert resolve_role(["mce"]) == (Role.MCE, None)


def test_teams_outside_nokware_are_ignored() -> None:
    assert resolve_role(["newsletter", "dept-works"]) == (Role.DEPARTMENT, "dept-works")


@pytest.mark.parametrize("teams", [[], ["newsletter"], ["dept-finance", "dept-works"], ["contributor", "mce"]])
def test_no_role_or_an_ambiguous_one_is_refused(teams: list[str]) -> None:
    with pytest.raises(NoRoleError):
        resolve_role(teams)


def client_for(outcome: Principal | Exception, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def fake_authenticate(jwt: str) -> Principal:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(dependencies, "authenticate", fake_authenticate)
    app = FastAPI()

    @app.get("/any")
    def any_role(principal: CurrentPrincipal) -> dict[str, str]:
        return {"role": principal.role}

    @app.get("/mce-only")
    def mce_only(principal: Principal = Depends(require_roles(Role.MCE))) -> dict[str, str]:
        return {"role": principal.role}

    return TestClient(app)


BEARER = {"Authorization": "Bearer token"}


def test_missing_token_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    response = client_for(FINANCE, monkeypatch).get("/any")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    assert client_for(InvalidTokenError("expired"), monkeypatch).get("/any", headers=BEARER).status_code == 401


def test_account_without_a_role_is_403(monkeypatch: pytest.MonkeyPatch) -> None:
    assert client_for(NoRoleError("none"), monkeypatch).get("/any", headers=BEARER).status_code == 403


def test_role_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_for(FINANCE, monkeypatch)
    assert client.get("/any", headers=BEARER).json() == {"role": "department"}
    assert client.get("/mce-only", headers=BEARER).status_code == 403
