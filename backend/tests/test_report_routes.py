"""The public report routes: form options, errors as the citizen sees them, and rate limits."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import reports as routes
from app.services import rate_limit
from app.services.report_rules import InvalidReport


@pytest.fixture(autouse=True)
def fresh_limits() -> None:
    for limit in (rate_limit.SUBMISSIONS, rate_limit.LOOKUPS, rate_limit.ESCALATIONS):
        limit._hits.clear()


client = TestClient(app)


def test_the_form_gets_wards_by_sub_metro_and_the_safety_types() -> None:
    body = client.get("/api/reports/options").json()
    assert [sm["name"] for sm in body["sub_metros"]] == ["Ashiedu Keteke", "Okaikoi South", "Ablekuma South"]
    assert sum(len(sm["wards"]) for sm in body["sub_metros"]) == 20
    assert {t["id"] for t in body["safety_types"]} >= {"abuse", "child_at_risk", "threat_to_life"}
    assert body["max_photos"] == 10
    abuse = next(t for t in body["safety_types"] if t["id"] == "abuse")
    assert abuse["recipients"] == ["Ghana Police Service", "Social Welfare"]  # plain names, for someone in danger


def test_an_invalid_report_is_a_422_with_a_message_to_show(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object) -> None:
        raise InvalidReport("Choose the electoral area where this is.")

    monkeypatch.setattr(routes.report_intake, "submit", refuse)
    response = client.post("/api/reports", data={"description": "A choked drain by the school."})
    assert response.status_code == 422 and response.json() == {"detail": "Choose the electoral area where this is."}


def test_an_unknown_reference_is_a_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes.report_store, "find_by_reference", lambda reference: None)
    response = client.get("/api/reports/K7QM-4TXP")
    assert response.status_code == 404 and "reference" in response.json()["detail"]


def test_filing_is_rate_limited_per_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes.report_intake, "submit", lambda *args: (_ for _ in ()).throw(InvalidReport("no")))
    codes = [client.post("/api/reports", data={"description": "x"}).status_code for _ in range(6)]
    assert codes == [422] * 5 + [429]


def test_the_messages_question_needs_the_receipt_token() -> None:
    response = client.post("/api/reports/K7QM-4TXP/preferences", json={"notify": True, "callback_consent": False})
    assert response.status_code == 422
