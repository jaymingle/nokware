"""The public dashboard's figures: personal safety counted nowhere, medians only from five cases."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import report_dashboard
from app.services.report_dashboard import aggregate, month_keys, period_start

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def case(topic: str = "drainage", *, days_ago: float = 10, resolved_after: float | None = None, **fields: Any) -> dict[str, Any]:
    created = NOW - timedelta(days=days_ago)
    resolved = created + timedelta(days=resolved_after) if resolved_after is not None else None
    return {
        "category": "civic_service", "isSensitive": False, "topic": topic, "subMetro": "ashiedu-keteke",
        "status": "resolved" if resolved else "assigned", "createdAt": created.isoformat(),
        "resolvedAt": resolved.isoformat() if resolved else None, **fields,
    }


SAFETY = case("abuse", category="personal_safety", isSensitive=True, subMetro="ablekuma-south", resolved_after=1)


def test_the_period_is_twelve_calendar_months_ending_this_one() -> None:
    assert period_start(NOW) == datetime(2025, 10, 1, tzinfo=timezone.utc)
    assert month_keys(NOW)[0] == "2025-10" and month_keys(NOW)[-1] == "2026-09" and len(month_keys(NOW)) == 12
    assert month_keys(datetime(2026, 1, 5, tzinfo=timezone.utc))[0] == "2025-02"


def test_personal_safety_is_in_no_figure_not_even_the_totals() -> None:
    with_safety = aggregate([case(), SAFETY, {**SAFETY, "category": "civic_service"}], NOW)  # flagged private: out too
    without = aggregate([case()], NOW)
    assert with_safety == without
    assert with_safety["received"] is None and "Abuse" not in str(with_safety)  # 1 reads "fewer than 5"


def test_totals_trend_topics_and_sub_metros() -> None:
    cases = [
        *[case("drainage", days_ago=3, resolved_after=1) for _ in range(5)],
        *[case("drainage", days_ago=40) for _ in range(5)],
        *[case("roads", days_ago=5, subMetro="okaikoi-south") for _ in range(6)],
        case("roads", days_ago=400, resolved_after=380),  # filed before the period, resolved within it
    ]
    figures = aggregate(cases, NOW)
    assert (figures["received"], figures["resolved"]) == (16, 5)
    assert figures["topics"] == [{"label": "Drainage and flooding", "count": 10}, {"label": "Roads and potholes", "count": 6}]
    assert figures["months"][-1] == {"month": "2026-09", "received": 11, "resolved": 5}
    rows = {r["name"]: r for r in figures["sub_metros"]}
    assert set(rows) == {"Ashiedu Keteke", "Okaikoi South", "Ablekuma South"}  # every sub-metro, even with none
    assert (rows["Ashiedu Keteke"]["reports"], rows["Okaikoi South"]["reports"], rows["Ablekuma South"]["reports"]) == (10, 6, 0)


def test_counts_from_one_to_four_read_fewer_than_five_everywhere() -> None:
    figures = aggregate([case("drainage", resolved_after=1), case("roads"), case("roads"), *[case("schools") for _ in range(5)]], NOW)
    assert (figures["received"], figures["resolved"]) == (8, None)
    assert figures["topics"] == [
        {"label": "Schools", "count": 5},
        {"label": "Drainage and flooding", "count": None},  # suppressed topics by name, not by size
        {"label": "Roads and potholes", "count": None},
    ]
    assert figures["months"][-1]["resolved"] is None and figures["months"][0] == {"month": "2025-10", "received": 0, "resolved": 0}


def test_a_median_needs_five_resolved_cases() -> None:
    four = [case(days_ago=20, resolved_after=d) for d in (1, 2, 3, 4)]
    assert aggregate(four, NOW)["median_days"] is None
    five = [*four, case(days_ago=20, resolved_after=10)]
    assert aggregate(five, NOW)["median_days"] == 3.0
    assert aggregate(five, NOW)["sub_metros"][0]["median_days"] == 3.0


def test_a_reopened_case_is_not_counted_resolved() -> None:
    reopened = {**case(resolved_after=1), "status": "assigned"}  # keeps its old resolvedAt
    figures = aggregate([reopened], NOW)
    assert figures["resolved"] == 0 and sum(m["resolved"] for m in figures["months"]) == 0


def test_the_route_serves_the_cached_figures(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[datetime] = []

    def build(now: datetime) -> dict[str, Any]:
        calls.append(now)
        return {
            "generated_at": now.isoformat(), **aggregate([case() for _ in range(6)], now),
            "documents_published": 164, "departments_publishing": 9, "recent_documents": [],
        }

    monkeypatch.setattr(report_dashboard, "build", build)
    report_dashboard.CACHE.clear()
    client = TestClient(app)
    first = client.get("/api/dashboard").json()
    client.get("/api/dashboard")
    assert first["received"] == 6 and first["documents_published"] == 164 and len(calls) == 1
    report_dashboard.CACHE.clear()
