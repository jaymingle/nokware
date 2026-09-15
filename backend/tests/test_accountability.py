"""Accountability: the publishing record (required against held, careful about what a gap means) and departmental
responsiveness (personal safety out, "fewer than 5", no ranking, no leak by subtraction)."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import department_responsiveness, publishing_record
from app.services.department_responsiveness import build as build_responsiveness, complement
from app.services.publishing_record import build as build_record, document_year, quarter_of

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def doc(doc_id: str, title: str, year: int | None = None, department: str = "dept-budget-rating", category: str = "Budget And Fee Fixing") -> dict[str, Any]:
    return {"$id": doc_id, "title": title, "documentYear": year, "department": department, "category": category, "status": "published"}


LEDGER = [
    doc("fee26", "2026 Fee-Fixing Resolution - Accra Metropolitan Assembly.", 2026),
    doc("bud21a", "AMA BUDGET 2021 - INVESTMENT", 2021),
    doc("comp22", "2022 Composite Budget", 2022),
    doc("bud26", "2026 AMA Budget", 2026),
    doc("proc24", "AMA PROCUREMENT PLAN 2024", 2024, "dept-finance", "Procurement Reports"),
    doc("energy24", "AMA Energy Report", 2024, "dept-finance", "Annual Reports"),
    doc("mtdp26", "MEDIUM TERM DEVELOPMENT PLAN, 2026-2029", 2026, "dept-central-administration", "Annual Action Plan"),
    doc("apr19", "AMA ANNUAL PROGRESS REPORT 2019", 2021, "dept-central-administration", "Annual Reports"),
    doc("me22", "MONITORING AND EVALUATION REPORT 2022", 2022, "dept-central-administration", "Annual Reports"),
    doc("rti", "RTI Manual-AMA", None, "dept-central-administration", "Policy Documents"),
    doc("ia24", "Internal Audit Report, Second Quarter 2024", 2024, "dept-finance", "Annual Reports"),
    doc("ia24x", "Internal Audit Report 2024", 2024, "dept-finance", "Annual Reports"),
]


def requirement(record: dict[str, Any], requirement_id: str) -> dict[str, Any]:
    return next(r for g in record["groups"] for r in g["requirements"] if r["id"] == requirement_id)


def period(row: dict[str, Any], label: str) -> dict[str, Any]:
    return next(p for p in row["periods"] if p["label"] == label)


@pytest.fixture(autouse=True)
def no_confirmations(monkeypatch: pytest.MonkeyPatch) -> None:
    rules = {**publishing_record.rules(), "confirmed": {}}
    monkeypatch.setattr(publishing_record, "rules", lambda: rules)


def test_a_gap_sits_beside_what_the_ledger_does_hold_that_year() -> None:
    fees = requirement(build_record(LEDGER, NOW), "fee_fixing")
    assert [p["label"] for p in fees["periods"]] == ["2021", "2022", "2023", "2024", "2025", "2026"]
    assert period(fees, "2026")["state"] == "held" and period(fees, "2026")["documents"][0]["id"] == "fee26"
    gap = period(fees, "2024")
    assert gap["state"] == "missing" and gap["documents"] == [] and gap["expected_from"] == "2024-01-01"
    assert {d["id"] for d in gap["nearby"]} == {"proc24", "energy24", "ia24", "ia24x"} and gap["nearby_total"] == 4  # Finance's 2024
    assert fees["nearby_scope"] == "Budget & Rating, Finance or Budget And Fee Fixing"


def test_related_documents_are_never_counted_as_the_document_itself() -> None:
    record = build_record(LEDGER, NOW)
    budget = requirement(record, "composite_budget")
    assert period(budget, "2021")["state"] == "related" and [d["id"] for d in period(budget, "2021")["related"]] == ["bud21a"]
    assert period(budget, "2022")["state"] == "held" and period(budget, "2026")["documents"][0]["id"] == "bud26"
    progress = requirement(record, "annual_progress")
    assert period(progress, "2022")["state"] == "related"  # an M&E report is not an Annual Progress Report


def test_nothing_is_called_missing_before_it_is_expected() -> None:
    record = build_record(LEDGER, NOW)
    statements = requirement(record, "financial_statements")
    assert period(statements, "2025")["state"] == "missing" and period(statements, "2026")["state"] == "not_due"
    assert period(statements, "2025")["expected_from"] == "2026-07-01" and statements["expected_note"] == "Expected 6 months after the year ends"
    audit = requirement(record, "internal_audit")
    assert period(audit, "Q1 2026")["state"] == "missing" and period(audit, "Q2 2026")["state"] == "not_due"  # due 1 Oct
    general = requirement(record, "auditor_general")
    assert general["issued_by"] == "the Auditor-General (Ghana Audit Service)" and period(general, "2025")["state"] == "not_due"


def test_quarters_plan_periods_and_undated_documents() -> None:
    record = build_record(LEDGER, NOW)
    audit = requirement(record, "internal_audit")
    assert period(audit, "Q2 2024")["state"] == "held"
    assert period(audit, "Q3 2024")["state"] == "related"  # a 2024 report with no quarter stated
    plan = requirement(record, "mtdp")
    assert [(p["label"], p["state"]) for p in plan["periods"]] == [("2018–2021", "missing"), ("2022–2025", "missing"), ("2026–2029", "held")]
    manual = requirement(record, "rti_manual")
    assert [d["id"] for d in manual["undated"]] == ["rti"] and all(p["state"] != "held" for p in manual["periods"])


def test_a_pac_report_is_never_called_missing_and_says_who_issues_it() -> None:
    pac = requirement(build_record(LEDGER, NOW), "pac")
    assert pac["periods"] == [] and pac["held"] == [] and pac["issued_by"] == "Parliament's Public Accounts Committee"
    held = requirement(build_record([*LEDGER, doc("pac1", "Report of the Public Accounts Committee on MMDAs 2023", 2023)], NOW), "pac")
    assert [d["id"] for d in held["held"]] == ["pac1"]


def test_a_title_year_wins_and_a_person_can_confirm_or_set_aside_a_match(monkeypatch: pytest.MonkeyPatch) -> None:
    assert document_year(LEDGER[7]) == 2019  # filed in 2021, covers 2019
    assert [quarter_of(t) for t in ("First Quarter 2024", "JULY - SEPT 2023", "Q4 report", "annual")] == [1, 3, 4, None]
    rules = {**publishing_record.rules(), "confirmed": {"energy24": ["financial_statements", 2024], "bud26": None}}
    monkeypatch.setattr(publishing_record, "rules", lambda: rules)
    record = build_record(LEDGER, NOW)
    assert period(requirement(record, "financial_statements"), "2024")["documents"][0]["id"] == "energy24"
    assert period(requirement(record, "composite_budget"), "2026")["documents"] == []  # set aside by a person


def test_the_summary_counts_what_was_due(monkeypatch: pytest.MonkeyPatch) -> None:
    summary = build_record(LEDGER, NOW)["summary"]
    assert summary["due"] == summary["held"] + summary["related"] + summary["missing"] and summary["not_due"] > 0


def test_test_documents_are_left_out_of_the_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publishing_record, "every_record", lambda collection, queries: [*LEDGER, doc("t", "[TEST] 2024 Fee-Fixing Resolution", 2024)])
    assert "t" not in {d["$id"] for d in publishing_record.published_documents()}


# Responsiveness.

def case(case_id: str, created: datetime, category: str = "civic_service", sensitive: bool = False) -> dict[str, Any]:
    return {"$id": case_id, "category": category, "isSensitive": sensitive, "createdAt": created.isoformat()}


def assignment(case_id: str, recipient: str, assigned: datetime, started: datetime | None = None, resolved: datetime | None = None) -> dict[str, Any]:
    return {"caseId": case_id, "recipient": recipient, "active": True, "assignedAt": assigned.isoformat(),
            "acknowledgedAt": started.isoformat() if started else None, "resolvedAt": resolved.isoformat() if resolved else None,
            "status": "resolved" if resolved else "assigned"}


def days_ago(n: float) -> datetime:
    return NOW - timedelta(days=n)


def works_cases(count: int, resolved: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = [case(f"w{i}", days_ago(30)) for i in range(count)]
    parts = [assignment(f"w{i}", "dept-works", days_ago(30), days_ago(29), days_ago(30 - 2 - i) if i < resolved else None) for i in range(count)]
    return cases, parts


def department(result: dict[str, Any], name: str) -> dict[str, Any]:
    return next(d for d in result["departments"] if d["name"] == name)


def test_personal_safety_and_national_agencies_are_left_out_entirely() -> None:
    cases, parts = works_cases(6, 6)
    cases += [case("s1", days_ago(5), "personal_safety", True)] * 1
    parts += [assignment("s1", "dept-social-welfare", days_ago(5)), assignment("s1", "agency-police", days_ago(5)),
              assignment("w0", "agency-police", days_ago(30))]
    result = build_responsiveness(cases, parts, [], [], NOW)
    assert department(result, "Social Welfare & Community Development")["reports"]["received"] == 0
    assert all(d["id"].startswith("dept-") for d in result["departments"])
    names = [d["name"] for d in result["departments"]]
    assert names == sorted(names, key=str.lower)  # by name, never ranked


def test_small_counts_read_fewer_than_5_and_hiding_one_of_a_pair_hides_the_other() -> None:
    cases, parts = works_cases(6, 5)  # resolved 5 would give away open = 1
    works = department(build_responsiveness(cases, parts, [], [], NOW), "Works Department")["reports"]
    assert (works["received"], works["resolved"], works["open"]) == (6, None, None)
    assert complement(10, 5, 5) == (5, 5) and complement(None, None, 7) == (None, 7)
    cases, parts = works_cases(10, 5)
    works = department(build_responsiveness(cases, parts, [], [], NOW), "Works Department")["reports"]
    assert (works["received"], works["resolved"], works["open"]) == (10, 5, 5)


def test_medians_need_five_and_waiting_counts_reports_not_started_after_7_days() -> None:
    cases, parts = works_cases(10, 5)
    cases += [case(f"n{i}", days_ago(9)) for i in range(5)] + [case("new", days_ago(2))]
    parts += [assignment(f"n{i}", "dept-works", days_ago(9)) for i in range(5)] + [assignment("new", "dept-works", days_ago(2))]
    works = department(build_responsiveness(cases, parts, [], [], NOW), "Works Department")["reports"]
    assert works["waiting"] == 5  # the report from 2 days ago isn't waiting yet
    assert works["median_days_to_start"] == 1.0 and works["median_days_to_resolve"] == 4.0
    few_cases, few_parts = works_cases(6, 4)
    assert department(build_responsiveness(few_cases, few_parts, [], [], NOW), "Works Department")["reports"]["median_days_to_resolve"] is None


def test_residents_disputes_and_how_the_mce_ruled() -> None:
    cases, parts = works_cases(10, 10)
    history = ([{"caseId": f"w{i}", "action": "escalated"} for i in range(7)]
               + [{"caseId": f"w{i}", "action": "escalation_confirmed"} for i in range(5)]
               + [{"caseId": "w5", "action": "reassigned", "fromStatus": "escalated", "fromDept": None},
                  {"caseId": "w6", "action": "reassigned", "fromStatus": "assigned", "fromDept": "dept-works"}])  # a move, not a reopen
    result = build_responsiveness(cases, parts, history, [], NOW)
    works = department(result, "Works Department")["reports"]
    assert (works["disputed"], works["confirmed"], works["reopened"]) == (7, 5, None)
    assert (result["mce"]["reports_confirmed"], result["mce"]["reports_reopened"]) == (5, None)


def entry(document: str, action: str, hours: float, from_status: str | None = None, department: str = "dept-finance") -> dict[str, Any]:
    return {"documentId": document, "action": action, "at": (days_ago(20) + timedelta(hours=hours)).isoformat(), "fromStatus": from_status,
            "department": department}


def test_contributor_documents_accepted_disputed_or_left_to_publish_themselves() -> None:
    history = []
    for i in range(5):
        history += [entry(f"a{i}", "submitted", 0), entry(f"a{i}", "accepted", 10 + i)]
    for i in range(5):
        history += [entry(f"x{i}", "submitted", 0), entry(f"x{i}", "auto_published", 72, "held")]
    history += [entry("d1", "submitted", 0), entry("d1", "disputed", 5), entry("d1", "escalated", 20),
                entry("d1", "auto_published", 92, "disputed")]  # the MCE's clock ran out, not the department's
    result = build_responsiveness([], [], [], history, NOW)
    finance = department(result, "Finance")["documents"]
    assert (finance["accepted"], finance["disputed"], finance["auto_published"], finance["median_hours_to_review"]) == (5, None, 5, 11.5)  # the dispute took 5 hours
    assert (result["mce"]["documents_ruled"], result["mce"]["documents_run_out"]) == (0, None)


def test_only_the_last_twelve_months_count() -> None:
    cases, parts = works_cases(6, 0)
    old = [case("old", days_ago(400))]
    result = build_responsiveness([*cases, *old], [*parts, assignment("old", "dept-works", days_ago(400))], [], [], NOW)
    assert department(result, "Works Department")["reports"]["received"] == 6


def test_both_routes_answer_publicly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publishing_record, "published_documents", lambda: LEDGER)
    monkeypatch.setattr(publishing_record.CACHE, "_value", None)
    monkeypatch.setattr(department_responsiveness, "public_cases", lambda: works_cases(6, 6)[0])
    monkeypatch.setattr(department_responsiveness, "every_record", lambda collection, queries: works_cases(6, 6)[1] if "assign" in collection else [])
    monkeypatch.setattr(department_responsiveness.CACHE, "_value", None)
    client = TestClient(app)
    record = client.get("/api/publishing-record").json()
    assert record["documents_centre_checked"] == "2026-09-12" and [g["name"] for g in record["groups"]] == [
        "Vision and plans", "Budget and tariffs", "Financial and audit", "Oversight and RTI"]
    response = client.get("/api/responsiveness").json()
    assert response["waiting_days"] == 7 and department(response, "Works Department")["reports"]["received"] == 6
