"""The public dashboard: what residents reported over the last twelve months, and what the Assembly resolved.

Personal safety is left out entirely, totals included: were it counted anywhere,
the total less the visible topics would give its number away. The finest place a
count is broken down to is the electoral area a civic report names — a
personal-safety report is never located finer than its sub-metro, and is not
counted here at all — and no case, address or reporter appears. Every count from
1 to 4 reads "fewer than 5" (None here), as in Ask, so the two never give
different numbers for the same thing. A median is shown only once five cases
have been resolved; below that it says little and could single a case out, and
for that reason no median is given per electoral area at all: twenty areas would
almost never reach five, and the few that did would stand out.

Figures are cached for a minute, so a busy public page reads Appwrite at most
once a minute.
"""

import statistics
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from appwrite.query import Query

from app.services import ledger_documents
from app.services.appwrite_client import every_record
from app.services.case_workflow import CaseStatus
from app.services.ledger_documents import LedgerStatus, parse_datetime
from app.services.report_taxonomy import TOPICS_BY_ID
from app.services.stats import is_public, public_cases, shown
from app.teams import DEPARTMENT_NAMES
from app.wards import sub_metros, wards

PERIOD_MONTHS = 12
MEDIAN_MIN = 5  # resolved cases needed before a median is shown
RECENT_DOCUMENTS = 4
CACHE_SECONDS = 60
DAY_SECONDS = 86_400


def period_start(now: datetime) -> datetime:
    """The first day of the month eleven months back: twelve calendar months, this one included."""
    months = now.year * 12 + now.month - 1 - (PERIOD_MONTHS - 1)
    return now.replace(year=months // 12, month=months % 12 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def month_keys(now: datetime) -> list[str]:
    start = period_start(now)
    first = start.year * 12 + start.month - 1
    return [f"{(first + i) // 12}-{(first + i) % 12 + 1:02d}" for i in range(PERIOD_MONTHS)]


@dataclass(frozen=True)
class Dated:
    case: dict[str, Any]
    created: datetime
    resolved: datetime | None  # set only while the case stands resolved


def _dated(case: dict[str, Any]) -> Dated | None:
    created = parse_datetime(case.get("createdAt"))
    if created is None:
        return None
    resolved = parse_datetime(case.get("resolvedAt")) if case.get("status") == CaseStatus.RESOLVED else None
    return Dated(case, created, resolved)


def median_days(cases: list[Dated]) -> float | None:
    """Median days from report to resolution; None below MEDIAN_MIN resolved cases."""
    spans = [(c.resolved - c.created).total_seconds() / DAY_SECONDS for c in cases if c.resolved]
    return round(statistics.median(spans), 1) if len(spans) >= MEDIAN_MIN else None


def _months(dated: list[Dated], now: datetime) -> list[dict[str, Any]]:
    received = Counter(f"{c.created:%Y-%m}" for c in dated)
    resolved = Counter(f"{c.resolved:%Y-%m}" for c in dated if c.resolved)
    return [{"month": key, "received": shown(received[key]), "resolved": shown(resolved[key])} for key in month_keys(now)]


def _topics(in_period: list[Dated]) -> list[dict[str, Any]]:
    counts = Counter(c.case["topic"] for c in in_period if c.case.get("topic") in TOPICS_BY_ID)
    rows = [{"label": TOPICS_BY_ID[topic].label, "count": shown(n)} for topic, n in counts.items()]
    # Shown counts largest first; the "fewer than 5" topics after them, by name, so their order says nothing.
    return sorted(rows, key=lambda r: (r["count"] is None, -(r["count"] or 0), r["label"]))


def _sub_metro_rows(in_period: list[Dated]) -> list[dict[str, Any]]:
    rows = []
    for sub_metro in sub_metros().values():
        here = [c for c in in_period if c.case.get("subMetro") == sub_metro.id]
        rows.append(
            {
                "id": sub_metro.id,
                "name": sub_metro.name,
                "reports": shown(len(here)),
                "resolved": shown(sum(1 for c in here if c.resolved)),
                "median_days": median_days(here),
            }
        )
    return rows


def _electoral_area_rows(in_period: list[Dated]) -> list[dict[str, Any]]:
    """Every electoral area, in the order the sub-metros list them, whether or not it has reports.

    An area with none is listed with a count of 0 rather than left out: a missing
    area reads as somewhere nobody reports from, when it may be somewhere nobody
    has told about Nokware. No median is given here — see the note above."""
    rows = []
    for ward in wards().values():
        here = [c for c in in_period if c.case.get("wardLocation") == ward.id]
        rows.append({
            "id": ward.id,
            "name": ward.name,
            "sub_metro": ward.sub_metro,
            "reports": shown(len(here)),
            "resolved": shown(sum(1 for c in here if c.resolved)),
        })
    return rows


def aggregate(cases: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """The report figures: totals, monthly trend, topics and sub-metros, for the last twelve months."""
    start = period_start(now)
    dated = [d for d in (_dated(c) for c in cases if is_public(c)) if d is not None]
    in_period = [d for d in dated if d.created >= start]
    return {
        "period_start": start.isoformat(),
        "received": shown(len(in_period)),
        "resolved": shown(sum(1 for c in in_period if c.resolved)),
        "median_days": median_days(in_period),
        "months": _months(dated, now),  # a month outside the period is simply not listed
        "topics": _topics(in_period),
        "sub_metros": _sub_metro_rows(in_period),
        "electoral_areas": _electoral_area_rows(in_period),
    }


def ledger_figures() -> dict[str, Any]:
    """How many documents the Ledger has published, from how many departments, and the latest few."""
    published = Query.equal("status", LedgerStatus.PUBLISHED.value)
    latest, total = ledger_documents.list_documents(
        [published, Query.order_desc("publishedAt"), Query.limit(RECENT_DOCUMENTS)]
    )
    every = every_record(ledger_documents.COLLECTION_ID, [published, Query.select(["department"])])
    departments = {d.get("department") for d in every}
    recent = [
        {
            "id": d["$id"],
            "title": d["title"],
            "department_name": DEPARTMENT_NAMES.get(d.get("department") or ""),
            "published_at": d.get("publishedAt"),
        }
        for d in latest
    ]
    return {"documents_published": total, "departments_publishing": len(departments - {None}), "recent_documents": recent}


def build(now: datetime) -> dict[str, Any]:
    return {"generated_at": now.isoformat(), **aggregate(public_cases(), now), **ledger_figures()}


class _Cache:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._value: tuple[float, dict[str, Any]] | None = None
        self._lock = threading.Lock()

    def get(self, make: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            if self._value is None or time.monotonic() - self._value[0] > self.seconds:
                self._value = (time.monotonic(), make())
            return self._value[1]

    def clear(self) -> None:
        self._value = None


CACHE = _Cache(CACHE_SECONDS)


def dashboard(now: datetime) -> dict[str, Any]:
    """The dashboard's figures, at most a minute old."""
    return CACHE.get(lambda: build(now))
