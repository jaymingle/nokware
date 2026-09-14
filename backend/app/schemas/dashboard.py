"""The public dashboard's figures. Personal safety is in none of them; a report count of None means "fewer than 5"."""

from pydantic import BaseModel


class MonthFigures(BaseModel):
    month: str  # "2026-09"
    received: int | None  # reports filed that month; None: fewer than 5
    resolved: int | None  # reports resolved that month (and still standing resolved); None: fewer than 5


class TopicFigures(BaseModel):
    label: str
    count: int | None  # None: fewer than 5


class SubMetroFigures(BaseModel):
    name: str
    reports: int | None  # None: fewer than 5
    resolved: int | None
    median_days: float | None  # None until five of its reports have been resolved


class RecentDocument(BaseModel):
    id: str
    title: str
    department_name: str | None
    published_at: str | None


class Dashboard(BaseModel):
    generated_at: str
    period_start: str  # the twelve months run from here to generated_at
    received: int | None  # None: fewer than 5
    resolved: int | None
    median_days: float | None  # None until five reports have been resolved
    months: list[MonthFigures]
    topics: list[TopicFigures]  # most reported first; topics with no reports are left out
    sub_metros: list[SubMetroFigures]
    documents_published: int
    departments_publishing: int
    recent_documents: list[RecentDocument]
