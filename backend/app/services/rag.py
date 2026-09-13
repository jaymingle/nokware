"""Ask: answer a question from the Ledger with verifiable citations.

Retrieval (hybrid, edition-aware, de-duplicated) supplies up to eight chunks.
Each document is shown to gemini-2.5-flash under a short label ([S1], [S2], ...)
with its title, year, department and source type; raw document ids never appear
in the prompt. The model cites labels, and sanitize_citations() drops any label
that does not map to a retrieved document. The answer and its labelled sources
are returned together, so every citation resolves to a real document.

Years come from ``documentYear`` (the year of the document itself), never
``publishedAt``, which is when the document was added to the Ledger.

answer_question() returns the whole answer at once; stream_answer() yields the
same pipeline's progress as events (searching, the sources found, the answer
text as it is written, then the checked answer), so a reader sees it working.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.services.citations import make_label, sanitize_citations
from app.services.ledger_documents import Provenance, provenance
from app.services.llm import get_chat_model
from app.services.retrieval import RetrievedChunk, retrieve
from app.teams import DEPARTMENT_NAMES

ANSWER_TEMPERATURE = 0.2
# Capped rather than off: halves answer latency versus unlimited thinking with no
# loss in completeness, while thinking=0 started citing other years' editions for
# single-document questions.
ANSWER_THINKING_BUDGET = 1024
NO_INFO_ANSWER = "I don't have information on that in the Ledger."
UNKNOWN_YEAR = "unknown"
# Fixed wording so readers, and the UI, can reliably spot conflicting sources.
DISAGREEMENT_LEAD = "The sources disagree"

_SYSTEM_PROMPT = (
    "You are the Nokware Ledger assistant. Answer the resident's question using ONLY "
    "the sources below: excerpts from official Accra Metropolitan Assembly documents. "
    "Each source starts with a header line: its label in square brackets (e.g. [S1]), "
    "then the document's title, year, department and source type.\n\n"
    "How to answer:\n"
    "- Be complete. Use every relevant detail in the sources (figures, dates, names, "
    "steps, conditions, fees, deadlines), not just the first fact you find. Organise "
    "the answer as short paragraphs or bullet points.\n"
    "- Cite once per point, at the end of the point, with the label(s) it comes from, "
    "e.g. [S2] or [S1][S3]. Do not cite every sentence. Cite only labels listed below.\n"
    "- When a year matters, take it from the source header. If the header year is "
    f"{UNKNOWN_YEAR}, do not state or guess one.\n"
    "- If sources disagree (different figures, dates or facts for the same thing), "
    "never pick one, merge them or average them. Start that point with the exact words "
    f'"{DISAGREEMENT_LEAD}" and give each version with the document it comes from, '
    f'named by title, e.g. "{DISAGREEMENT_LEAD} on 2023 revenue: the 2023 Monitoring and '
    'Evaluation Report gives X [S1]; the AMA Biweekly Newsletter gives Y [S2]."\n'
    f'- If the sources do not contain the answer, reply exactly: "{NO_INFO_ANSWER}"'
)

_PROMPT = ChatPromptTemplate.from_messages(
    [("system", _SYSTEM_PROMPT), ("human", "Sources:\n\n{context}\n\nQuestion: {question}")]
)


AnswerStatus = Literal["answered", "no_information"]


class Source(TypedDict):
    label: str
    cited: bool
    document_id: str
    title: str | None
    chunk_text: str
    department: str | None
    department_name: str | None
    source_type: str | None
    provenance: Provenance | None
    source_url: str | None
    published_at: str | None
    document_year: int | None


class RagAnswer(TypedDict):
    answer: str
    status: AnswerStatus
    sources: list[Source]
    search_queries: list[str]


@dataclass(frozen=True)
class Prepared:
    """A question with its retrieved chunks, each document under its citation label."""

    question: str
    chunks: list[RetrievedChunk]
    labels: dict[str, str]  # {document_id: "S1", ...}
    queries: list[str]


def _assign_labels(chunks: list[RetrievedChunk]) -> dict[str, str]:
    """One label per document, numbered in retrieval order: {document_id: "S1", ...}."""
    labels: dict[str, str] = {}
    for retrieved in chunks:
        labels.setdefault(retrieved.chunk.document_id, make_label(len(labels) + 1))
    return labels


def _format_context(chunks: list[RetrievedChunk], labels: dict[str, str]) -> str:
    blocks = []
    for document_id, label in labels.items():
        document_chunks = [c for c in chunks if c.chunk.document_id == document_id]
        document = document_chunks[0].document
        header = (
            f"[{label}] {document.get('title') or 'Untitled'} | "
            f"year: {document.get('documentYear') or UNKNOWN_YEAR} | "
            f"department: {document.get('department')} | source: {document.get('sourceType')}"
        )
        excerpts = "\n[...]\n".join(c.chunk.text for c in document_chunks)
        blocks.append(f"{header}\n{excerpts}")
    return "\n\n".join(blocks)


def _source(retrieved: RetrievedChunk, label: str, cited: bool) -> Source:
    document: dict[str, Any] = retrieved.document
    department = document.get("department")
    return Source(
        label=label,
        cited=cited,
        document_id=retrieved.chunk.document_id,
        title=document.get("title"),
        chunk_text=retrieved.chunk.text,
        department=department,
        department_name=DEPARTMENT_NAMES.get(department) if department else None,
        source_type=document.get("sourceType"),
        provenance=provenance(document),
        source_url=document.get("sourceUrl"),
        published_at=document.get("publishedAt"),
        document_year=document.get("documentYear"),
    )


def _to_sources(chunks: list[RetrievedChunk], labels: dict[str, str], cited: set[str]) -> list[Source]:
    order = {document_id: position for position, document_id in enumerate(labels)}
    ordered = sorted(chunks, key=lambda c: order[c.chunk.document_id])  # stable: rank order within a document
    return [_source(c, labels[c.chunk.document_id], labels[c.chunk.document_id] in cited) for c in ordered]


def answer_status(answer: str) -> AnswerStatus:
    """Whether the Ledger answered, from the fixed no-information reply the model is told to give."""
    return "no_information" if answer.strip().startswith(NO_INFO_ANSWER) else "answered"


def prepare(question: str) -> Prepared:
    retrieval = retrieve(question)
    return Prepared(question, retrieval.chunks, _assign_labels(retrieval.chunks), retrieval.queries)


def _answer_chain() -> Runnable[dict[str, str], str]:
    return _PROMPT | get_chat_model(ANSWER_TEMPERATURE, thinking_budget=ANSWER_THINKING_BUDGET) | StrOutputParser()


def _prompt_input(prepared: Prepared) -> dict[str, str]:
    return {"context": _format_context(prepared.chunks, prepared.labels), "question": prepared.question}


def finish(prepared: Prepared, raw_answer: str) -> RagAnswer:
    """The checked answer: only real citations kept, sources marked cited or not."""
    if not prepared.chunks:
        return RagAnswer(answer=NO_INFO_ANSWER, status="no_information", sources=[], search_queries=prepared.queries)
    answer, cited = sanitize_citations(raw_answer, set(prepared.labels.values()))
    return RagAnswer(
        answer=answer,
        status=answer_status(answer),
        sources=_to_sources(prepared.chunks, prepared.labels, cited),
        search_queries=prepared.queries,
    )


def answer_question(question: str) -> RagAnswer:
    """Answer from the Ledger. Every [S#] left in the answer maps to a returned source."""
    prepared = prepare(question)
    if not prepared.chunks:
        return finish(prepared, NO_INFO_ANSWER)
    return finish(prepared, _answer_chain().invoke(_prompt_input(prepared)))


def stream_answer(question: str) -> Iterator[dict[str, Any]]:
    """The answer as events: stage, sources, deltas of raw text, then the checked answer.

    Deltas are the model's raw text, shown while it writes; the final "done"
    event carries the sanitized answer that replaces them, so a citation the
    checker removes never survives.
    """
    yield {"type": "stage", "stage": "searching"}
    prepared = prepare(question)
    yield {"type": "sources", "sources": _to_sources(prepared.chunks, prepared.labels, set())}
    parts: list[str] = []
    if prepared.chunks:
        yield {"type": "stage", "stage": "writing"}
        for piece in _answer_chain().stream(_prompt_input(prepared)):
            parts.append(piece)
            yield {"type": "delta", "text": piece}
    result = finish(prepared, "".join(parts))
    cited = sorted({source["label"] for source in result["sources"] if source["cited"]})
    yield {"type": "done", "answer": result["answer"], "status": result["status"], "cited": cited}
