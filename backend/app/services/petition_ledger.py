"""What The Ledger already holds on a petition's subject, shown beside the petition.

Someone petitioning about drainage should see the Assembly's own flood plans and budget lines: to strengthen their
case, or to find that the commitment already exists and wasn't kept. A match means a document touches the subject,
not that it commits to what the petition asks, and the page says so.
"""

import threading
import time
from dataclasses import dataclass
from typing import Any

from app.services import ledger_documents
from app.services.ledger_documents import provenance
from app.services.pdf_text import mend
from app.services.publishing_record import year_and_source
from app.services.retrieval import RetrievedChunk, collapse_near_duplicates, fuse, ranked_lists
from app.teams import DEPARTMENT_NAMES

DOCUMENTS_MAX = 5
BODY_IN_QUERY = 400
PASSAGE_MAX = 320
CACHE_SECONDS = 3600


@dataclass(frozen=True)
class LedgerMatch:
    id: str
    title: str
    department_name: str | None
    year: int | None
    provenance: str | None
    passage: str


def query_for(title: str, body: str, topic_label: str) -> str:
    return f"{title}. {topic_label}. {body[:BODY_IN_QUERY]}"


def passage(text: str) -> str:
    # Mended again for chunks stored before ingestion mended ligatures ("\uf002ooding"), and any that slip through.
    flat = " ".join(mend(text).split())
    if len(flat) <= PASSAGE_MAX:
        return flat
    return flat[:PASSAGE_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def describe(document: dict[str, Any]) -> dict[str, Any]:
    source = provenance(document)
    return {"id": document["$id"], "title": document["title"].strip(),
            "department_name": DEPARTMENT_NAMES.get(document.get("department") or ""),
            "year": year_and_source(document)[0], "provenance": source.value if source else None}


def _match(document: dict[str, Any], text: str) -> LedgerMatch:
    return LedgerMatch(**describe(document), passage=passage(text))


def search(query: str, limit: int = DOCUMENTS_MAX) -> list[LedgerMatch]:
    vector_lists, keyword_lists = ranked_lists([query])
    fused = fuse([*vector_lists, *keyword_lists])
    documents = ledger_documents.get_documents(chunk.document_id for chunk, _ in fused)
    published = [RetrievedChunk(chunk, score, documents[chunk.document_id]) for chunk, score in fused
                 if ledger_documents.is_public_document(documents.get(chunk.document_id))]
    found: dict[str, LedgerMatch] = {}
    for hit in collapse_near_duplicates(published):  # best first; the same text in two documents shows once
        if hit.chunk.document_id not in found:
            found[hit.chunk.document_id] = _match(hit.document, hit.chunk.text)
        if len(found) == limit:
            break
    return list(found.values())


_cache: dict[str, tuple[float, list[LedgerMatch]]] = {}
_cache_lock = threading.Lock()


def cached_search(query: str) -> list[LedgerMatch]:
    """Kept for an hour: a petition's page is read far more often than the Ledger changes."""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(query)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    matches = search(query)
    with _cache_lock:
        for stale in [q for q, (at, _) in _cache.items() if now - at >= CACHE_SECONDS]:
            del _cache[stale]
        _cache[query] = (now, matches)
    return matches
