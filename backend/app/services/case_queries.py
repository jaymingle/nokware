"""The lists staff work from: a recipient's queue, and the MCE's view across every case."""

from datetime import datetime, timedelta
from typing import Any

from appwrite.query import Query

from app.services import ledger_documents, report_store
from app.services.appwrite_client import DATABASE_ID, as_record, get_databases
from app.services.case_workflow import AssignmentStatus, CaseStatus, shown_count
from app.services.citizen_reports import ASSIGNMENTS_COLLECTION, REPORTS_COLLECTION
from app.services.report_taxonomy import Category

QUEUE_LIMIT = 200
RECENTLY_RESOLVED = timedelta(days=30)
OPEN = (CaseStatus.SUBMITTED, CaseStatus.ASSIGNED, CaseStatus.IN_PROGRESS, CaseStatus.ESCALATED)


def _assignments(queries: list[str]) -> list[dict[str, Any]]:
    listing = get_databases().list_documents(DATABASE_ID, ASSIGNMENTS_COLLECTION, queries=[*queries, Query.limit(QUEUE_LIMIT)])
    return [as_record(d) for d in listing.documents]


def _cases(case_ids: list[str]) -> dict[str, dict[str, Any]]:
    ids = list(dict.fromkeys(case_ids))
    if not ids:
        return {}
    listing = get_databases().list_documents(
        DATABASE_ID, REPORTS_COLLECTION, queries=[Query.equal("$id", ids), Query.limit(len(ids))]
    )
    return {d.id: as_record(d) for d in listing.documents}


def _queue_order(pair: tuple[dict[str, Any], dict[str, Any]]) -> tuple[int, int, str]:
    case, mine = pair
    done = mine["status"] == AssignmentStatus.RESOLVED or case["status"] == CaseStatus.ESCALATED
    return (1 if done else 0, -case["severity"], mine["assignedAt"])


def queue(recipient: str, now: datetime) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """(case, this recipient's assignment): open work most severe and oldest first, then the last 30 days' resolved."""
    mine = _assignments([Query.equal("recipient", recipient), Query.equal("active", True)])
    cutoff = now - RECENTLY_RESOLVED
    recent = [
        a for a in mine
        if a["status"] != AssignmentStatus.RESOLVED or (ledger_documents.parse_datetime(a.get("resolvedAt")) or now) >= cutoff
    ]
    cases = _cases([a["caseId"] for a in recent])
    pairs = [(cases[a["caseId"]], a) for a in recent if a["caseId"] in cases]
    return sorted(pairs, key=_queue_order)


def all_cases() -> list[dict[str, Any]]:
    """Every case, newest first, for the MCE's oversight (each shown as its view allows)."""
    listing = get_databases().list_documents(
        DATABASE_ID, REPORTS_COLLECTION, queries=[Query.order_desc("createdAt"), Query.limit(QUEUE_LIMIT)]
    )
    return [as_record(d) for d in listing.documents]


def oversight_stats(cases: list[dict[str, Any]], now: datetime) -> dict[str, int | None]:
    """The MCE's headline counts. Personal safety only metro-wide, and never as a number below 5."""
    cutoff = now - RECENTLY_RESOLVED
    everyday = [c for c in cases if c["category"] != Category.PERSONAL_SAFETY]
    safety_open = sum(1 for c in cases if c["category"] == Category.PERSONAL_SAFETY and c["status"] in OPEN)
    return {
        "open": sum(1 for c in everyday if c["status"] in OPEN),
        # Every escalation, safety included: the MCE must act on each, and sees each one in outline anyway.
        "escalated": sum(1 for c in cases if c["status"] == CaseStatus.ESCALATED),
        "resolved_30_days": sum(
            1 for c in everyday
            if c["status"] == CaseStatus.RESOLVED and (ledger_documents.parse_datetime(c.get("resolvedAt")) or now) >= cutoff
        ),
        "personal_safety_open": shown_count(safety_open),
    }


def load(case_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    case = report_store.find_case(case_id)
    return (case, report_store.assignments_for(case_id)) if case else None
