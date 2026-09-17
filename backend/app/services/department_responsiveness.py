"""How each Assembly department responds: to residents' reports, and to documents contributors send it.

The platform publishing evidence about the institution's own behaviour, with the
same rules as every public figure (stats.py): personal safety is left out
entirely (not counted, and not in which departments appear), a count from 1 to 4
reads "fewer than 5" (None here), a median needs five cases, and nothing about a
case's content appears. Where two counts add up to one that is shown (resolved and
still open make up received), hiding one hides the other, or subtraction would
reveal it. Over the last twelve months, as the dashboard.

Reports are counted per department: a report sent to two departments counts for
both, and one the MCE moved counts for the department that has it now. Reports
don't expire, so the nearest measure of "unactioned" is still waiting to be
started 7 days after it arrived: the measure chosen here, not a statutory
deadline. What does expire is a review clock: a contributor's document the
department doesn't review within 72 hours publishes automatically, and so does an
escalated dispute the MCE doesn't rule on in time. Departments are listed by
name, never ranked. Police and GNFS are national agencies, not Assembly
departments, so they are not held to this scorecard.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from appwrite.query import Query

from app.services import petition_figures
from app.services.appwrite_client import every_record
from app.services.case_history import COLLECTION_ID as CASE_HISTORY
from app.services.case_history import CaseHistoryAction
from app.services.citizen_reports import ASSIGNMENTS_COLLECTION
from app.services.document_history import COLLECTION_ID as DOCUMENT_HISTORY
from app.services.document_history import HistoryAction
from app.services.ledger_documents import LedgerStatus, parse_datetime
from app.services.report_dashboard import MEDIAN_MIN, _Cache, period_start
from app.services.stats import is_public, public_cases, shown
from app.teams import DEPARTMENT_NAMES

WAITING_DAYS = 7
DAY, HOUR = 86_400, 3_600
CACHE = _Cache(60)
REVIEWS = (HistoryAction.ACCEPTED.value, HistoryAction.DISPUTED.value, HistoryAction.AUTO_PUBLISHED.value)
RULINGS = (HistoryAction.UPHELD.value, HistoryAction.OVERRULED.value, HistoryAction.AUTO_PUBLISHED.value)


def median(values: list[float], unit: float) -> float | None:
    """A median in days or hours, to one decimal; None below five cases."""
    return round(statistics.median(values) / unit, 1) if len(values) >= MEDIAN_MIN else None


@dataclass(frozen=True)
class _Part:
    """One department's part in one public report."""

    assigned: datetime
    started: datetime | None  # work started, or resolved without a separate start
    resolved: datetime | None
    case_id: str


def _parts(cases: dict[str, dict[str, Any]], assignments: list[dict[str, Any]]) -> dict[str, list[_Part]]:
    parts: dict[str, list[_Part]] = defaultdict(list)
    for a in assignments:
        assigned = parse_datetime(a.get("assignedAt"))
        if a["caseId"] not in cases or a["recipient"] not in DEPARTMENT_NAMES or assigned is None:
            continue
        resolved = parse_datetime(a.get("resolvedAt")) if a.get("status") == "resolved" else None
        started = parse_datetime(a.get("acknowledgedAt")) or resolved
        parts[a["recipient"]].append(_Part(assigned, started, resolved, a["caseId"]))
    return parts


def _disputes(history: list[dict[str, Any]], cases: set[str]) -> dict[str, dict[str, int]]:
    """Per case, whether residents disputed its resolution and how the MCE ruled: confirmed, or reopened."""
    found: dict[str, dict[str, int]] = defaultdict(lambda: {"disputed": 0, "confirmed": 0, "reopened": 0})
    for entry in history:
        if entry["caseId"] not in cases:
            continue
        action = entry["action"]
        if action == CaseHistoryAction.ESCALATED:
            found[entry["caseId"]]["disputed"] += 1
        elif action == CaseHistoryAction.ESCALATION_CONFIRMED:
            found[entry["caseId"]]["confirmed"] += 1
        elif action == CaseHistoryAction.REASSIGNED and entry.get("fromStatus") == "escalated" and not entry.get("fromDept"):
            found[entry["caseId"]]["reopened"] += 1  # reopen() sends the case back to the same departments
    return found


def complement(total: int | None, part: int | None, rest: int | None) -> tuple[int | None, int | None]:
    """Two counts that add up to a shown total: if one reads "fewer than 5", so must the other, or the total less
    the one shown would give it away."""
    if total is not None and (part is None) != (rest is None):
        return None, None
    return part, rest


def _reports(parts: list[_Part], disputes: dict[str, dict[str, int]], now: datetime) -> dict[str, Any]:
    waiting_since = now - timedelta(days=WAITING_DAYS)
    own = [disputes[p.case_id] for p in parts if p.case_id in disputes]
    resolved, still_open = complement(shown(len(parts)), shown(sum(1 for p in parts if p.resolved)),
                                      shown(sum(1 for p in parts if not p.resolved)))
    return {
        "received": shown(len(parts)),
        "resolved": resolved,
        "open": still_open,
        "waiting": shown(sum(1 for p in parts if not p.resolved and not p.started and p.assigned <= waiting_since)),
        "median_days_to_start": median([(p.started - p.assigned).total_seconds() for p in parts if p.started], DAY),
        "median_days_to_resolve": median([(p.resolved - p.assigned).total_seconds() for p in parts if p.resolved], DAY),
        "disputed": shown(sum(d["disputed"] for d in own)),
        "confirmed": shown(sum(d["confirmed"] for d in own)),
        "reopened": shown(sum(d["reopened"] for d in own)),
    }


def _outcomes(history: list[dict[str, Any]], opened: tuple[str, ...], closing: tuple[str, ...], from_status: str) -> list[tuple[str, str, float]]:
    """Each review, in order per document: (department, how it ended, hours taken). A clock that ran out ends
    it as auto_published; hours are kept only for a decision someone made."""
    by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in history:
        by_document[entry["documentId"]].append(entry)
    ended = []
    for entries in by_document.values():
        entries.sort(key=lambda e: e["at"])
        pending: dict[str, Any] | None = None
        for entry in entries:
            if entry["action"] in opened:
                pending = entry
            elif pending and entry["action"] in closing and (entry["action"] != HistoryAction.AUTO_PUBLISHED or entry.get("fromStatus") == from_status):
                hours = (parse_datetime(entry["at"]) - parse_datetime(pending["at"])).total_seconds() / HOUR
                ended.append((entry["department"], entry["action"], hours))
                pending = None
    return ended


def _documents(reviews: list[tuple[str, str, float]]) -> dict[str, Any]:
    decided = [hours for _, action, hours in reviews if action != HistoryAction.AUTO_PUBLISHED]
    return {
        "accepted": shown(sum(1 for _, a, _ in reviews if a == HistoryAction.ACCEPTED)),
        "disputed": shown(sum(1 for _, a, _ in reviews if a == HistoryAction.DISPUTED)),
        "auto_published": shown(sum(1 for _, a, _ in reviews if a == HistoryAction.AUTO_PUBLISHED)),
        "median_hours_to_review": median([h * HOUR for h in decided], HOUR),
    }


def _mce(rulings: list[tuple[str, str, float]], disputes: dict[str, dict[str, int]]) -> dict[str, Any]:
    return {
        "documents_ruled": shown(sum(1 for _, a, _ in rulings if a != HistoryAction.AUTO_PUBLISHED)),
        "documents_run_out": shown(sum(1 for _, a, _ in rulings if a == HistoryAction.AUTO_PUBLISHED)),
        "reports_confirmed": shown(sum(d["confirmed"] for d in disputes.values())),
        "reports_reopened": shown(sum(d["reopened"] for d in disputes.values())),
    }


def build(cases: list[dict[str, Any]], assignments: list[dict[str, Any]], case_history: list[dict[str, Any]],
          document_history: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    start = period_start(now)
    in_period = {c["$id"]: c for c in cases if is_public(c) and (parse_datetime(c.get("createdAt")) or start) >= start}
    parts = _parts(in_period, assignments)
    disputes = _disputes(case_history, set(in_period))
    recent = [e for e in document_history if (parse_datetime(e.get("at")) or start) >= start]
    reviews = _outcomes(recent, (HistoryAction.SUBMITTED.value, HistoryAction.RESUBMITTED.value), REVIEWS, LedgerStatus.HELD.value)
    rulings = _outcomes(recent, (HistoryAction.ESCALATED.value,), RULINGS, LedgerStatus.DISPUTED.value)
    departments = [
        {"id": team, "name": name, "reports": _reports(parts.get(team, []), disputes, now),
         "documents": _documents([r for r in reviews if r[0] == team])}
        for team, name in sorted(DEPARTMENT_NAMES.items(), key=lambda item: item[1].lower())
    ]
    return {"generated_at": now.isoformat(), "period_start": start.isoformat(), "waiting_days": WAITING_DAYS,
            "departments": departments, "mce": _mce(rulings, disputes)}


def _history(collection: str, actions: list[str]) -> list[dict[str, Any]]:
    return every_record(collection, [Query.equal("action", actions)])


def responsiveness(now: datetime) -> dict[str, Any]:
    """The figures, at most a minute old."""

    def make() -> dict[str, Any]:
        case_actions = [CaseHistoryAction.ESCALATED.value, CaseHistoryAction.ESCALATION_CONFIRMED.value, CaseHistoryAction.REASSIGNED.value]
        document_actions = [a.value for a in HistoryAction]
        figures = build(public_cases(), every_record(ASSIGNMENTS_COLLECTION, [Query.equal("active", True)]),
                        _history(CASE_HISTORY, case_actions), _history(DOCUMENT_HISTORY, document_actions), now)
        return {**figures, "petitions": petition_figures.figures(period_start(now), now)}

    return CACHE.get(make)
