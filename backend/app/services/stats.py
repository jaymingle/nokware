"""Counts over citizen reports for the public: Ask's live figures and the dashboard. Aggregates only.

The rules are enforced here, so no caller can skip them:

- Personal safety is never counted. It is not a filter, and it is left out of
  every count and total; otherwise a total less the visible topics would give
  its number away.
- A count from 1 to 4 is shown as "fewer than 5" (``shown``). Zero is shown.
- Callers get numbers only, never a case's content.

Known limit: any system that answers counts allows differencing. Comparing the
count for one electoral area with its sub-metro's, or a total with its parts,
can narrow a suppressed cell. Leaving personal safety out entirely is the
protection that matters; for civic and public-safety counts, the residual risk
is accepted and documented.

The case list is read from Appwrite at most once a minute and shared.
"""

import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from appwrite.query import Query

from app.services.appwrite_client import every_record
from app.services.case_workflow import CaseStatus
from app.services.citizen_reports import REPORTS_COLLECTION
from app.services.ledger_documents import parse_datetime
from app.services.report_taxonomy import TOPICS_BY_ID, Category

SMALL = 5  # counts below this (other than zero) are never shown as numbers
FEWER_THAN_SMALL = "fewer than 5"
CACHE_SECONDS = 60
CASE_FIELDS = ["category", "isSensitive", "topic", "wardLocation", "subMetro", "recipients", "status", "createdAt", "resolvedAt"]
OPEN = (CaseStatus.SUBMITTED, CaseStatus.ASSIGNED, CaseStatus.IN_PROGRESS, CaseStatus.ESCALATED)


class Period(StrEnum):
    TODAY = "today"
    THIS_WEEK = "this_week"
    THIS_MONTH = "this_month"
    LAST_30_DAYS = "last_30_days"
    THIS_YEAR = "this_year"
    ALL_TIME = "all_time"


class StatusGroup(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    ANY = "any"


def shown(count: int) -> int | None:
    """A count as the public may see it: None ("fewer than 5") from 1 to 4."""
    return None if 0 < count < SMALL else count


def display(count: int) -> str:
    value = shown(count)
    return FEWER_THAN_SMALL if value is None else "none" if value == 0 else f"{value:,}"


def is_public(case: dict[str, Any]) -> bool:
    """Everyday and public-safety reports only. Checked twice over: by category and by the private flag."""
    return case.get("category") != Category.PERSONAL_SAFETY and not case.get("isSensitive")


def period_start(period: Period, now: datetime) -> datetime | None:
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)  # Accra keeps GMT all year
    starts = {
        Period.TODAY: midnight,
        Period.THIS_WEEK: midnight - timedelta(days=now.weekday()),
        Period.THIS_MONTH: midnight.replace(day=1),
        Period.LAST_30_DAYS: now - timedelta(days=30),
        Period.THIS_YEAR: midnight.replace(month=1, day=1),
    }
    return starts.get(period)


@dataclass(frozen=True)
class ReportFilter:
    """Which reports to count. A None field doesn't filter."""

    topic: str | None = None
    category: Category | None = None  # civic service or public safety; personal safety is never counted
    status: StatusGroup = StatusGroup.ANY
    ward: str | None = None  # a ward ID
    sub_metro: str | None = None
    recipient: str | None = None  # a department or agency team
    period: Period = Period.ALL_TIME


def _status_matches(status: str | None, group: StatusGroup) -> bool:
    if group == StatusGroup.OPEN:
        return status in OPEN
    return group == StatusGroup.ANY or status == group.value


def matches(case: dict[str, Any], wanted: ReportFilter, now: datetime) -> bool:
    start = period_start(wanted.period, now)
    created = parse_datetime(case.get("createdAt"))
    checks = (
        is_public(case),
        wanted.topic is None or case.get("topic") == wanted.topic,
        wanted.category is None or case.get("category") == wanted.category,
        _status_matches(case.get("status"), wanted.status),
        wanted.ward is None or case.get("wardLocation") == wanted.ward,
        wanted.sub_metro is None or case.get("subMetro") == wanted.sub_metro,
        wanted.recipient is None or wanted.recipient in (case.get("recipients") or []),
        start is None or (created is not None and created >= start),
    )
    return all(checks)


def count(cases: list[dict[str, Any]], wanted: ReportFilter, now: datetime) -> int:
    return sum(1 for case in cases if matches(case, wanted, now))


def breakdown(cases: list[dict[str, Any]], wanted: ReportFilter, by: str, now: datetime) -> list[tuple[str, int]]:
    """Counts per topic or sub-metro ID, largest first. Personal safety never appears."""
    field = {"topic": "topic", "sub_metro": "subMetro"}[by]
    counts = Counter(case.get(field) for case in cases if matches(case, wanted, now) and case.get(field))
    return counts.most_common()


def topic_label(topic: str) -> str:
    return TOPICS_BY_ID[topic].label if topic in TOPICS_BY_ID else topic


def _fetch_public_cases() -> list[dict[str, Any]]:
    return every_record(
        REPORTS_COLLECTION,
        [Query.not_equal("category", Category.PERSONAL_SAFETY.value), Query.select(CASE_FIELDS)],
    )


class _Cache:
    def __init__(self, seconds: float, make: Callable[[], list[dict[str, Any]]]) -> None:
        self.seconds, self.make = seconds, make
        self._value: tuple[float, list[dict[str, Any]]] | None = None
        self._lock = threading.Lock()

    def get(self) -> tuple[float, list[dict[str, Any]]]:
        """(when it was read, as time.time(); the cases)."""
        with self._lock:
            if self._value is None or time.time() - self._value[0] > self.seconds:
                self._value = (time.time(), self.make())
            return self._value

    def clear(self) -> None:
        self._value = None


CASES = _Cache(CACHE_SECONDS, lambda: _fetch_public_cases())


def public_cases() -> list[dict[str, Any]]:
    """Every report but personal safety, with only the fields counts need; at most a minute old."""
    return CASES.get()[1]


def counted_at() -> float:
    """When the shared case list was read (time.time())."""
    return CASES.get()[0]
