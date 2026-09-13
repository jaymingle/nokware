"""Request and response models for POST /api/ask."""

from typing import Annotated

from pydantic import BaseModel, StringConstraints

MAX_QUESTION_LENGTH = 1000

Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH)
]


class AskRequest(BaseModel):
    question: Question


class AskSource(BaseModel):
    label: str  # "S1": the citation label used in the answer text
    cited: bool  # whether the answer cites this source's label
    document_id: str
    title: str | None
    chunk_text: str
    department: str | None
    source_type: str | None
    published_at: str | None
    document_year: int | None


class AskResponse(BaseModel):
    answer: str
    sources: list[AskSource]
