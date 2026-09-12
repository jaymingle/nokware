"""RAG chain over the Ledger's document chunks.

Retrieves the top-k chunks from the pgvector store, enriches each with its
parent document's metadata from Appwrite's ``ledger_documents`` collection,
asks Gemini (``gemini-2.5-flash``) to answer strictly from that context while
citing each source's document id and document year, and returns the answer
alongside structured source metadata.

Citations use ``documentYear`` (the year of the document itself), never
``publishedAt``, which is when the document was added to the Ledger; for the
imported AMA archive that is the import date.
"""

import logging
from collections.abc import Iterable
from functools import lru_cache
from typing import TypedDict

from appwrite.exception import AppwriteException
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import get_settings
from app.services import ledger_documents
from app.services.vectorstore import DEFAULT_K, DOCUMENT_ID_COLUMN, get_retriever

logger = logging.getLogger(__name__)

# Must honour temperature: low temperature keeps answers grounded in the
# retrieved chunks, so fixed-sampling models (e.g. gemini-3.6-flash) are out.
LLM_MODEL = "gemini-2.5-flash"
LLM_TEMPERATURE = 0.2
NO_INFO_ANSWER = "I don't have information on that in the Ledger."
UNKNOWN_YEAR = "unknown"

_SYSTEM_PROMPT = (
    "You are the Nokware Ledger assistant. Answer the question using ONLY the "
    "context below, which contains excerpts from official municipal documents. "
    "Each excerpt starts with a metadata header in square brackets giving its "
    "document_id, document_year, department and source_type. For every fact you "
    "state, cite the document_id and document_year from that excerpt's header, "
    "e.g. (source: <document_id>, <document_year>). If document_year is "
    f"{UNKNOWN_YEAR}, cite the document_id and say the document's date is not "
    "recorded. Never take the citation id or year from the excerpt text itself, "
    "and never cite the date a document was added to the Ledger. "
    f'If the context does not contain the answer, reply exactly: "{NO_INFO_ANSWER}"'
)

_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM_PROMPT),
        ("human", "Context:\n{context}\n\nQuestion: {question}"),
    ]
)


class LedgerMeta(TypedDict):
    department: str | None
    source_type: str | None
    published_at: str | None
    document_year: int | None


class Source(TypedDict):
    document_id: str | None
    chunk_text: str
    department: str | None
    source_type: str | None
    published_at: str | None
    document_year: int | None


class RagAnswer(TypedDict):
    answer: str
    sources: list[Source]


@lru_cache
def get_llm() -> ChatGoogleGenerativeAI:
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        google_api_key=settings.gemini_api_key,
    )


def _empty_meta() -> LedgerMeta:
    return LedgerMeta(department=None, source_type=None, published_at=None, document_year=None)


def _fetch_ledger_meta(document_id: str) -> LedgerMeta:
    """Fetch one ledger document's metadata; nulls if it is missing or fails."""
    try:
        data = ledger_documents.get_document(document_id)
    except AppwriteException as exc:
        logger.warning("Ledger lookup failed for %s: %s", document_id, exc)
        return _empty_meta()
    return LedgerMeta(
        department=data.get("department"),
        source_type=data.get("sourceType"),
        published_at=data.get("publishedAt"),
        document_year=data.get("documentYear"),
    )


def _lookup_ledger_meta(document_ids: Iterable[str | None]) -> dict[str, LedgerMeta]:
    """One Appwrite call per unique, non-empty document id."""
    unique_ids = dict.fromkeys(doc_id for doc_id in document_ids if doc_id)
    return {doc_id: _fetch_ledger_meta(doc_id) for doc_id in unique_ids}


def _chunk_document_id(doc: Document) -> str | None:
    return (doc.metadata or {}).get(DOCUMENT_ID_COLUMN)


def _to_source(doc: Document, ledger: dict[str, LedgerMeta]) -> Source:
    document_id = _chunk_document_id(doc)
    meta = ledger.get(document_id, _empty_meta()) if document_id else _empty_meta()
    return Source(document_id=document_id, chunk_text=doc.page_content, **meta)


def _format_context(sources: list[Source]) -> str:
    blocks = []
    for source in sources:
        header = (
            f"[document_id={source['document_id']}, "
            f"document_year={source['document_year'] or UNKNOWN_YEAR}, "
            f"department={source['department']}, "
            f"source_type={source['source_type']}]"
        )
        blocks.append(f"{header}\n{source['chunk_text']}")
    return "\n\n".join(blocks)


def answer_question(question: str) -> RagAnswer:
    """Answer a question from the Ledger, returning the answer and sources."""
    docs: list[Document] = get_retriever(k=DEFAULT_K).invoke(question)
    if not docs:
        return RagAnswer(answer=NO_INFO_ANSWER, sources=[])
    ledger = _lookup_ledger_meta(_chunk_document_id(doc) for doc in docs)
    sources = [_to_source(doc, ledger) for doc in docs]
    chain = _PROMPT | get_llm() | StrOutputParser()
    answer = chain.invoke({"context": _format_context(sources), "question": question})
    return RagAnswer(answer=answer, sources=sources)
