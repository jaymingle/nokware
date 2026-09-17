"""Add your voice: civic issues only, one voice per browser, names for the handling department alone."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import case_presenters
from app.routes import issues as issue_routes
from app.services import issue_voices, rate_limit, report_followups
from app.services.auth import Principal, Role
from app.services.issue_voices import InvalidVoice, add_voice, device_hash, is_public_issue
from app.services.report_followups import public_status
from app.services.report_intake import _drawn_ids

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
TOKEN = "b" * 32
ISSUE = {"$id": "c1", "publicId": "k7qm4txp2a", "category": "civic_service", "isSensitive": False, "status": "assigned",
         "topic": "roads", "wardLocation": "kaneshie", "subMetro": "okaikoi-south", "recipients": ["dept-urban-roads"],
         "createdAt": "2026-09-10T09:00:00+00:00", "voiceCount": 3, "reference": "46EC-TCPR", "severity": 3,
         "description": "The pothole by the footbridge.", "classifiedBy": "ai"}
ROADS = Principal("u-r", "Urban Roads", "r@x.org", Role.DEPARTMENT, "dept-urban-roads")
MCE = Principal("u-m", "MCE", "m@x.org", Role.MCE)
ASSIGNED = [{"$id": "a1", "caseId": "c1", "recipient": "dept-urban-roads", "status": "assigned", "active": True}]


def test_only_open_civic_service_issues_take_voices() -> None:
    assert is_public_issue(ISSUE)
    for other in ({"category": "public_safety"}, {"category": "personal_safety"}, {"isSensitive": True},
                  {"status": "resolved"}, {"publicId": None}):
        assert not is_public_issue({**ISSUE, **other}), other


def test_only_civic_reports_are_given_a_public_id() -> None:
    assert len(_drawn_ids({"category": "civic_service"})["publicId"]) == 10
    assert "publicId" not in _drawn_ids({"category": "public_safety"}) and "publicId" not in _drawn_ids({"category": "personal_safety"})


def test_a_voice_is_anonymous_unless_named_and_counted_once_per_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    stored: dict[str, dict[str, Any]] = {}

    def record(case_id: str, token: str, name: str | None, now: datetime) -> bool:
        key = device_hash(case_id, token)
        if key in stored:
            return False
        stored[key] = {"named": name is not None, "name": name}
        return True

    updates: list[dict[str, Any]] = []
    monkeypatch.setattr(issue_voices, "find_issue", lambda public_id: ISSUE)
    monkeypatch.setattr(issue_voices, "_record_voice", record)
    monkeypatch.setattr(issue_voices, "voices_total", lambda case_id: len(stored))
    monkeypatch.setattr(issue_voices.report_store, "update_case", lambda case_id, changes: updates.append(changes))
    assert add_voice("k7qm4txp2a", TOKEN, "  ", NOW) == (1, True)  # a blank name is anonymous
    assert add_voice("k7qm4txp2a", TOKEN, "Ama", NOW) == (1, False)  # the same browser again
    assert add_voice("k7qm4txp2a", "c" * 32, "Kofi Mensah", NOW) == (2, True)
    assert [v["named"] for v in stored.values()] == [False, True] and updates[-1] == {"voiceCount": 2}
    with pytest.raises(InvalidVoice):
        add_voice("k7qm4txp2a", "short", None, NOW)
    with pytest.raises(InvalidVoice):
        add_voice("k7qm4txp2a", TOKEN, "x" * 81, NOW)


def test_names_reach_the_handling_department_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(issue_voices, "named_voices", lambda case_id: ["Kofi Mensah"])
    assert case_presenters._voice_names(ROADS, ISSUE, ASSIGNED) == ["Kofi Mensah"]
    assert case_presenters._voice_names(MCE, ISSUE, ASSIGNED) is None
    assert case_presenters._voice_names(ROADS, {**ISSUE, "category": "public_safety"}, ASSIGNED) is None
    summary = case_presenters.summary(MCE, ISSUE, ASSIGNED)
    assert summary.voices == 3  # the MCE sees the count


def test_the_reporter_sees_the_count_and_a_safety_case_shows_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_followups.report_locations, "views", lambda case_id: [])
    assert public_status(ISSUE, [], NOW)["voices"] == 3
    private = {**ISSUE, "category": "personal_safety", "isSensitive": True, "topic": "abuse"}
    assert "voices" not in public_status(private, [], NOW)


def test_the_routes_list_issues_without_content_and_limit_voices(monkeypatch: pytest.MonkeyPatch) -> None:
    rate_limit.VOICES._hits.clear()
    monkeypatch.setattr(issue_routes.issue_voices, "list_issues", lambda *args: ([ISSUE, {**ISSUE, "status": "resolved"}], 2))
    client = TestClient(app)
    page = client.get("/api/issues").json()
    assert [i["public_id"] for i in page["issues"]] == ["k7qm4txp2a"]
    issue = page["issues"][0]
    assert (issue["topic"], issue["ward"], issue["departments"], issue["voices"]) == ("Roads and potholes", "Kaneshie", ["Urban Roads"], 3)
    assert "footbridge" not in str(page) and "46EC" not in str(page)  # never the words, never the reference
    monkeypatch.setattr(issue_routes.issue_voices, "add_voice", lambda *args: (4, True))
    codes = [client.post("/api/issues/k7qm4txp2a/voices", json={"device_token": TOKEN}).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429
    rate_limit.VOICES._hits.clear()
    assert client.post("/api/issues/k7qm4txp2a/voices", json={"device_token": "short"}).status_code == 422


def test_one_open_issue_reads_as_the_list_shows_it_and_a_closed_one_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(issue_voices, "civic_issue", lambda public_id: ISSUE)
    shown = client.get("/api/issues/k7qm4txp2a").json()
    assert (shown["topic"], shown["ward"], shown["voices"]) == ("Roads and potholes", "Kaneshie", 3) and "description" not in shown
    monkeypatch.setattr(issue_voices, "civic_issue", lambda public_id: {**ISSUE, "status": "resolved"})
    assert client.get("/api/issues/k7qm4txp2a").status_code == 409
