"""Request and response models for Ask: POST /api/ask and POST /api/ask/stream."""

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


class AskResponse(BaseModel):
    answer: str
    status: AnswerStatus
    sources: list[AskSource]


class StageEvent(BaseModel):
    type: Literal["stage"]
    stage: Literal["searching", "writing"]


class SourcesEvent(BaseModel):
    """Every source retrieved, before the answer is written; none is marked cited yet."""

    type: Literal["sources"]
    sources: list[AskSource]


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


class ErrorEvent(BaseModel):
    type: Literal["error"]
    message: str


AnyStreamEvent = Annotated[StageEvent | SourcesEvent | DeltaEvent | DoneEvent | ErrorEvent, Field(discriminator="type")]


class AskStreamEvent(RootModel[AnyStreamEvent]):
    """One line of POST /api/ask/stream's newline-delimited JSON."""
