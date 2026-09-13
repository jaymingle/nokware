"""Ask: answer a question from the Ledger with verifiable citations.

Retrieval (hybrid, edition-aware, de-duplicated) supplies up to eight chunks.
Each document is shown to gemini-2.5-flash under a short label ([S1], [S2], ...)
with its title, year, department and source type; raw document ids never appear
in the prompt. The model cites labels, and sanitize_citations() drops any label
that does not map to a retrieved document. The answer and its labelled sources
are returned together, so every citation resolves to a real document.

Years come from ``documentYear`` (the year of the document itself), never
``publishedAt``, which is when the document was added to the Ledger.
"""

from typing import TypedDict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.services.citations import make_label, sanitize_citations
from app.services.llm import get_chat_model
from app.services.retrieval import RetrievedChunk, retrieve

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


class Source(TypedDict):
    label: str
    cited: bool
    document_id: str
    title: str | None
    chunk_text: str
    department: str | None
    source_type: str | None
    published_at: str | None
    document_year: int | None


class RagAnswer(TypedDict):
    answer: str
    sources: list[Source]
    search_queries: list[str]


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


def _to_sources(chunks: list[RetrievedChunk], labels: dict[str, str], cited: set[str]) -> list[Source]:
    order = {document_id: position for position, document_id in enumerate(labels)}
    ordered = sorted(chunks, key=lambda c: order[c.chunk.document_id])  # stable: rank order within a document
    return [
        Source(
            label=labels[c.chunk.document_id],
            cited=labels[c.chunk.document_id] in cited,
            document_id=c.chunk.document_id,
            title=c.document.get("title"),
            chunk_text=c.chunk.text,
            department=c.document.get("department"),
            source_type=c.document.get("sourceType"),
            published_at=c.document.get("publishedAt"),
            document_year=c.document.get("documentYear"),
        )
        for c in ordered
    ]


def answer_question(question: str) -> RagAnswer:
    """Answer from the Ledger. Every [S#] left in the answer maps to a returned source."""
    retrieval = retrieve(question)
    if not retrieval.chunks:
        return RagAnswer(answer=NO_INFO_ANSWER, sources=[], search_queries=retrieval.queries)
    labels = _assign_labels(retrieval.chunks)
    chain = _PROMPT | get_chat_model(ANSWER_TEMPERATURE, thinking_budget=ANSWER_THINKING_BUDGET) | StrOutputParser()
    raw_answer = chain.invoke({"context": _format_context(retrieval.chunks, labels), "question": question})
    answer, cited = sanitize_citations(raw_answer, set(labels.values()))
    return RagAnswer(
        answer=answer,
        sources=_to_sources(retrieval.chunks, labels, cited),
        search_queries=retrieval.queries,
    )
