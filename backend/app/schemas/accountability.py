"""Response models for the accountability pages: GET /api/publishing-record and GET /api/responsiveness."""

from typing import Literal

from pydantic import BaseModel

Count = int | None  # None: fewer than 5


class RecordDocument(BaseModel):
    id: str  # the Ledger document; its PDF is at /api/ledger/{id}/file
    title: str
    year: int | None
    year_source: Literal["confirmed", "cover", "title", "ledger"] | None  # ledger: from the Ledger's record, not the document
    department_name: str | None
    note: str | None  # why it counts as what it does, when its first page decided


class RecordPeriod(BaseModel):
    """One year, quarter or plan period of a required document."""

    label: str  # "2024", "Q2 2024", "2022–2025"
    year: int
    quarter: int | None
    # held: the document itself; related: documents about the same thing, not it; missing: neither, once
    # expected; not_due: not yet expected, by our assumption (not a statutory deadline)
    state: Literal["held", "related", "missing", "not_due"]
    expected_from: str | None  # the date it counts as expected, by our assumption
    documents: list[RecordDocument]
    related: list[RecordDocument]
    nearby: list[RecordDocument]  # what the Ledger holds that year from the same departments or categories
    nearby_total: int


class Requirement(BaseModel):
    id: str
    name: str
    cadence: Literal["annual", "quarterly", "plan_period", "as_issued"]
    issued_by: str | None  # when the Assembly isn't the one that issues it
    expected_note: str | None  # "Expected 6 months after the year ends": our assumption, not a statutory deadline
    nearby_scope: str  # where "what the Ledger holds" looks: departments and categories
    periods: list[RecordPeriod]  # empty for a document issued on no fixed schedule
    undated: list[RecordDocument]  # held, but its year isn't stated
    held: list[RecordDocument]  # for a document issued on no fixed schedule: every one held


class RequirementGroup(BaseModel):
    id: str
    name: str
    requirements: list[Requirement]


class RecordSummary(BaseModel):
    due: int
    held: int
    related: int
    missing: int
    not_due: int


class ReportingGap(BaseModel):
    """A figure the Assembly's documents once reported and haven't since: Nokware's reading, with its evidence."""

    id: str
    subject: str
    latest_year: int
    years_since: int
    figures: str  # the figures as the document gives them
    quote: str  # the passage they come from
    document_id: str  # its PDF is at /api/ledger/{id}/file
    document_title: str
    searched: list[str]  # the words the Ledger was searched for
    checked: str  # the date it was searched
    why: str


class PublishingRecord(BaseModel):
    generated_at: str
    documents_centre: str
    documents_centre_checked: str  # the date ama.gov.gh's Documents Centre was last checked
    first_year: int
    last_year: int
    groups: list[RequirementGroup]
    summary: RecordSummary
    gaps: list[ReportingGap]  # figures the documents once reported and haven't since
    gaps_about: str


class DepartmentReports(BaseModel):
    received: Count
    resolved: Count
    open: Count
    waiting: Count  # still not started this many days after it arrived (Responsiveness.waiting_days)
    median_days_to_start: float | None  # None until five
    median_days_to_resolve: float | None
    disputed: Count  # resolutions residents said weren't fixed
    confirmed: Count  # of those, the MCE confirmed the resolution
    reopened: Count  # or sent it back to be finished


class DepartmentDocuments(BaseModel):
    """Contributors' documents the department had 72 hours to review."""

    accepted: Count
    disputed: Count
    auto_published: Count  # the review clock ran out
    median_hours_to_review: float | None


class DepartmentFigures(BaseModel):
    id: str
    name: str
    reports: DepartmentReports
    documents: DepartmentDocuments


class MceFigures(BaseModel):
    documents_ruled: Count  # escalated disputes the MCE ruled on
    documents_run_out: Count  # or let the clock run out on
    reports_confirmed: Count
    reports_reopened: Count


class PetitionRefusals(BaseModel):
    reason: str
    label: str
    count: int


class PetitionFigures(BaseModel):
    """The MCE's handling of petitions: exact counts, since they count decisions on public petitions, not residents."""

    sent: int
    published_by_mce: int
    published_automatically: int  # the MCE let the 72 hours pass
    refused: int
    refusals: list[PetitionRefusals]
    reached_threshold: int  # the four below add up to this
    answered_in_time: int
    answered_late: int
    unanswered: int  # 30 days passed, no response yet
    waiting: int  # still within the 30 days


class Responsiveness(BaseModel):
    generated_at: str
    period_start: str
    waiting_days: int
    departments: list[DepartmentFigures]  # by name, never ranked; Assembly departments only
    mce: MceFigures
    petitions: PetitionFigures
