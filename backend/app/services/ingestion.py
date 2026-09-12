"""Turn a published ledger document into searchable chunks.

ingest_document() is the single entry point for every publish path: agency
upload, department accept, MCE overrule, the held-document timer, and the AMA
bulk import. It downloads the PDF from MinIO, extracts its text, splits it into
overlapping chunks, embeds them with gemini-embedding-2 (768 dims) and
atomically replaces the document's rows in document_chunks. Re-running it for
the same document is safe: chunks are replaced, never duplicated.

Image-only PDFs (scanned pages without a text layer) stay published but are
marked not searchable: chunkCount=0 with an ingestionError saying why.
"""

import io
import logging
import time
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.services import ledger_documents
from app.services.ledger_documents import LedgerStatus
from app.services.storage import download_ledger_file
from app.services.vectorstore import get_embeddings, replace_document_chunks

logger = logging.getLogger(__name__)
logging.getLogger("pypdf").setLevel(logging.ERROR)  # malformed-PDF warnings are noise

CHUNK_SIZE = 1200  # characters, roughly 300 tokens
CHUNK_OVERLAP = 200
MIN_CHARS_PER_PAGE = 100  # below this on average, the PDF is treated as image-only
EMBED_BATCH_SIZE = 100
EMBED_MAX_ATTEMPTS = 5
NO_TEXT_NOTE = "Not searchable: no extractable text (image-only PDF). OCR is not supported yet."
_TRANSIENT_MARKERS = ("429", "RESOURCE_EXHAUSTED", "500", "503", "UNAVAILABLE", "DEADLINE_EXCEEDED")


class IngestionRefused(Exception):
    """The document is not in a state that may be ingested."""


@dataclass(frozen=True)
class IngestionResult:
    document_id: str
    chunk_count: int
    searchable: bool


def extract_pdf_pages(pdf_bytes: bytes) -> list[str]:
    """Return the stripped text of each page (empty string for image-only pages)."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [(page.extract_text() or "").strip() for page in reader.pages]


def split_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]


def _is_transient(exc: Exception) -> bool:
    return any(marker in str(exc) for marker in _TRANSIENT_MARKERS)


def _embed_batch(batch: list[str], title: str) -> list[list[float]]:
    """Embed one batch in document mode, backing off on rate limits and 5xx errors."""
    for attempt in range(1, EMBED_MAX_ATTEMPTS + 1):
        try:
            return get_embeddings().embed_documents(batch, batch_size=EMBED_BATCH_SIZE, titles=[title] * len(batch))
        except Exception as exc:
            if attempt == EMBED_MAX_ATTEMPTS or not _is_transient(exc):
                raise
            delay = 2**attempt
            logger.warning("Embedding attempt %d failed (%s); retrying in %ds", attempt, exc, delay)
            time.sleep(delay)
    raise AssertionError("unreachable")


def embed_chunks(chunks: list[str], title: str) -> list[list[float]]:
    """Embed chunks batch by batch, so a retry only repeats the failed batch."""
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        vectors.extend(_embed_batch(chunks[start : start + EMBED_BATCH_SIZE], title))
    return vectors


def _ingest(document_id: str, document: dict) -> IngestionResult:
    pages = extract_pdf_pages(download_ledger_file(document["fileId"]))
    if sum(len(page) for page in pages) < MIN_CHARS_PER_PAGE * max(len(pages), 1):
        replace_document_chunks(document_id, [], [])  # clear any stale chunks
        ledger_documents.mark_ingested(document_id, 0, NO_TEXT_NOTE)
        return IngestionResult(document_id, 0, searchable=False)
    chunks = split_text("\n\n".join(page for page in pages if page))
    vectors = embed_chunks(chunks, document["title"])
    count = replace_document_chunks(document_id, chunks, vectors)
    ledger_documents.mark_ingested(document_id, count)
    return IngestionResult(document_id, count, searchable=True)


def ingest_document(document_id: str) -> IngestionResult:
    """Chunk, embed and store one published document. Safe to call repeatedly.

    Raises IngestionRefused unless the document is published. Any other failure
    is recorded on the document (ingestionError, ingestedAt cleared) and re-raised.
    """
    document = ledger_documents.get_document(document_id)
    if document.get("status") != LedgerStatus.PUBLISHED:
        raise IngestionRefused(f"{document_id} is {document.get('status')!r}; only published documents are ingested")
    try:
        return _ingest(document_id, document)
    except Exception as exc:
        ledger_documents.mark_ingestion_failed(document_id, f"{type(exc).__name__}: {exc}")
        raise
