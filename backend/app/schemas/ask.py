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


class AskHeard(BaseModel):
    """A spoken question in words, shown to the person to check before anything is asked."""

    question: str  # what is put to Ask once they confirm it: the English, clipped to the question limit
    language: str  # the language spoken, named in English
    understood: str  # 'I understood: "…"', saying so when it was translated by machine


class AskSource(BaseModel):
    """One retrieved chunk; a document's chunks share its label."""

    label: str  # "S1": the citation label used in the answer text
    cited: bool
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
    """A figure cited beside the documents: a live count of reports, or an approved amount read from a budget."""

    label: str  # "R1" for a live count, "B1" for a budget figure: the citation label used in the answer text
    cited: bool
    description: str  # what it covers, e.g. "Open reports · Solid waste · Kinka · this month", "Approved budget · 2026"
    value: str  # as it may be shown: "12", "fewer than 5", "none", "GH¢ 124,760,805"
    rows: list[FigureRow]  # a breakdown, if asked for
    counted_at: str | None = None  # when the reports were counted; None for a figure read from a document
    grouped_by: str = "none"  # what the rows break it down by
    source: Literal["reports", "documents"] = "reports"
    document_id: str | None = None  # the budget document it was read from; its PDF is at /api/ledger/{id}/file
    document_title: str | None = None
    year: int | None = None  # the budget year
    coverage: str | None = None  # what the rows read come to as a share of what that document states it details


class ChartValue(BaseModel):
    shown: str  # as the public may see it: "12", "fewer than 5", "none", "7,875.00"
    low: float
    high: float  # low == high for an exact figure; "fewer than 5" is 1 to 4, drawn as a range, never a value


class ChartSeries(BaseModel):
    name: str
    values: list[ChartValue]  # one per category


class AskChart(BaseModel):
    """A chart the question asked for, of the answer's cited figures (ask_charts decides; clients draw)."""

    kind: Literal["bar", "stacked_bar", "line", "pie", "donut"]  # bar: side by side when there are several series
    horizontal: bool  # bars lie flat (long category names)
    title: str
    categories: list[str]  # oldest first when over_time
    series: list[ChartSeries]
    over_time: bool
    source: Literal["reports", "documents"] = "reports"  # live counts, or figures proved against cited passages
    figures: list[str]  # the R labels charted; empty for a chart of document figures
    counted_at: str | None  # when the counts were taken; None for figures read from documents
    axis_max: float  # 0 for a pie or donut
    ticks: list[float]
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
    answer: str  # what the resident reads: their own language where it could be translated safely
    answer_english: str = ""
    language: str = "en"
    translated: bool = False
    status: AnswerStatus
    sources: list[AskSource]
    figures: list[AskFigure]
    chart: AskChart | None = None
    chart_note: str | None = None  # why the chart isn't the kind asked for, or why there is none
    export: ExportView
    speakable: bool = False  # whether it can be read aloud: never an answer about someone's safety


class AskExportRequest(BaseModel):
    view: ExportView
    format: Literal["pdf", "docx", "csv", "xlsx"]


class StageEvent(BaseModel):
    type: Literal["stage"]
    stage: Literal["searching", "counting", "writing", "translating"]  # counting: searching and counting live report data


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
    answer_english: str = ""  # the answer as written and checked; the sources are in English
    language: str = "en"  # the language the answer is written in: "en", "fr" or "tw"
    translated: bool = False  # whether a machine translated it from the English
    status: AnswerStatus
    cited: list[str]
    chart: AskChart | None = None
    chart_note: str | None = None
    export: ExportView | None = None  # what POST /api/ask/export takes back, signed
    speakable: bool = False


class ErrorEvent(BaseModel):
    type: Literal["error"]
    message: str


AnyStreamEvent = Annotated[StageEvent | SourcesEvent | DeltaEvent | DoneEvent | ErrorEvent, Field(discriminator="type")]


class AskStreamEvent(RootModel[AnyStreamEvent]):
    """One line of POST /api/ask/stream's newline-delimited JSON."""


SpeechPart = Annotated[int, Field(ge=0, le=20)]  # which part of the reading, from 0


class SpeechAnswerRequest(BaseModel):
    view: ExportView  # the answer's signed export view, from the done event
    part: SpeechPart = 0


class SpeechReportRequest(BaseModel):
    reference: str = Field(max_length=40)
    kind: Literal["receipt", "status"] = "status"  # the confirmation just after filing, or the status page
    part: SpeechPart = 0
