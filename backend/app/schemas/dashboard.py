"""The public dashboard's figures. Personal safety is in none of them."""

from pydantic import BaseModel


class MonthFigures(BaseModel):
    month: str  # "2026-09"
    received: int  # reports filed that month
    resolved: int  # reports resolved that month (and still standing resolved)


class TopicFigures(BaseModel):
    label: str
    count: int


class SubMetroFigures(BaseModel):
    name: str
    reports: int
    resolved: int
    median_days: float | None  # None until five of its reports have been resolved


class RecentDocument(BaseModel):
    id: str
    title: str
    department_name: str | None
    published_at: str | None


class Dashboard(BaseModel):
    generated_at: str
    period_start: str  # the twelve months run from here to generated_at
    received: int
    resolved: int
    median_days: float | None  # None until five reports have been resolved
    months: list[MonthFigures]
    topics: list[TopicFigures]  # most reported first; topics with no reports are left out
    sub_metros: list[SubMetroFigures]
    documents_published: int
    departments_publishing: int
    recent_documents: list[RecentDocument]
