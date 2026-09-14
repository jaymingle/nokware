"""Request and response models for Ask: POST /api/ask, POST /api/ask/stream and POST /api/ask/export."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel, StringConstraints

from app.services.ledger_documents import Provenance

MAX_QUESTION_LENGTH = 1000

Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH)
]
AnswerStatus = Literal["answered", "no_information"]


class AskRequest(BaseModel):
    question: Question


class AskSource(BaseModel):
    """One retrieved chunk; a document's chunks share its label."""

    label: str  # "S1": the citation label used in the answer text
    cited: bool  # whether the answer cites this source's label
    document_id: str
    title: str | None
    chunk_text: str
    department: str | None
    department_name: str | None
    source_type: str | None
    provenance: Provenance | None  # how the document entered the Ledger; None if the record doesn't say
    source_url: str | None
    published_at: str | None  # when it was added to the Ledger
    document_year: int | None  # the year of the document itself


class FigureRow(BaseModel):
    name: str
    value: str


class AskFigure(BaseModel):
    """A live count of reports residents filed with Nokware: a source, but not a document."""

    label: str  # "R1": the citation label used in the answer text
    cited: bool
    description: str  # what was counted, e.g. "Open reports · Solid waste and dumping · Kinka · this month"
    value: str  # as it may be shown: "12", "fewer than 5", "none"
    rows: list[FigureRow]  # a breakdown by topic, sub-metro or month, if asked for
    counted_at: str
    grouped_by: Literal["none", "topic", "sub_metro", "month"] = "none"  # month: rows run oldest first


class ChartValue(BaseModel):
    shown: str  # as the public may see it: "12", "fewer than 5", "none"
    low: int
    high: int  # low == high for an exact count; "fewer than 5" is 1 to 4, drawn as a range, never a value


class ChartSeries(BaseModel):
    name: str
    values: list[ChartValue]  # one per category


class AskChart(BaseModel):
    """A chart the question asked for, of the answer's cited live report figures (ask_charts decides; clients draw)."""

    kind: Literal["bar", "stacked_bar", "line", "pie", "donut"]  # bar: side by side when there are several series
    horizontal: bool  # bars lie flat (long category names)
    title: str
    categories: list[str]  # oldest first when over_time
    series: list[ChartSeries]
    over_time: bool
    figures: list[str]  # the R labels charted
    counted_at: str
    axis_max: int  # 0 for a pie or donut
    ticks: list[int]
    note: str | None  # why this isn't the kind asked for, in one line


class ExportSource(BaseModel):
    """A cited document as an export lists it."""

    label: str  # "S1": the answer's citation label
    title: str
    department_name: str | None
    provenance: Provenance | None
    source_url: str | None
    document_year: int | None
    published_at: str | None
    ledger_url: str | None  # Nokware's copy, when the API has a public address


class ExportView(BaseModel):
    """Everything an export of one answer carries, signed by the API: the export route renders only answers it gave."""

    question: str
    answered_at: str
    answer: str
    status: AnswerStatus
    sources: list[ExportSource]  # cited only
    figures: list[AskFigure]  # cited only
    chart: AskChart | None
    chart_note: str | None
    token: str


class AskResponse(BaseModel):
    answer: str
    status: AnswerStatus
    sources: list[AskSource]
    figures: list[AskFigure]
    chart: AskChart | None = None
    chart_note: str | None = None  # why the chart isn't the kind asked for, or why there is none
    export: ExportView


class AskExportRequest(BaseModel):
    view: ExportView
    format: Literal["pdf", "docx", "csv"]


class StageEvent(BaseModel):
    type: Literal["stage"]
    stage: Literal["searching", "counting", "writing"]  # counting: searching and counting live report data


class SourcesEvent(BaseModel):
    """Every source retrieved, before the answer is written; none is marked cited yet."""

    type: Literal["sources"]
    sources: list[AskSource]
    figures: list[AskFigure] = []


class DeltaEvent(BaseModel):
    """The next piece of the model's raw answer text."""

    type: Literal["delta"]
    text: str


class DoneEvent(BaseModel):
    """The checked answer, which replaces the streamed text, and the labels it cites."""

    type: Literal["done"]
    answer: str
    status: AnswerStatus
    cited: list[str]
    chart: AskChart | None = None
    chart_note: str | None = None
    export: ExportView | None = None  # what POST /api/ask/export takes back, signed


class ErrorEvent(BaseModel):
    type: Literal["error"]
    message: str


AnyStreamEvent = Annotated[StageEvent | SourcesEvent | DeltaEvent | DoneEvent | ErrorEvent, Field(discriminator="type")]


class AskStreamEvent(RootModel[AnyStreamEvent]):
    """One line of POST /api/ask/stream's newline-delimited JSON."""
