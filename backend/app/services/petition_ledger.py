"""What The Ledger already holds on a petition's subject, shown beside the petition.

Someone petitioning about drainage should see the Assembly's own flood plans
and budget lines: to strengthen their case, or to find that the commitment
already exists and wasn't kept. The same idea as the publishing record showing
what the Ledger does hold beside a gap.

Found by searching the Ledger, by meaning and by words, for the petition's ask,
its topic and the start of its reasons. The page says so, and that a match
means a document touches the subject, not that it commits to what the petition
asks. Published documents only.
"""

import threading
import time
from dataclasses import dataclass
from typing import Any

from app.services import ledger_documents
from app.services.ledger_documents import LedgerStatus, provenance
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


# Some of the Assembly's PDFs store ligatures and bullets in a font's private characters, which the extracted
# text keeps: "\uf002ooding" for "flooding", "\uf0b7" for a bullet. Mended for reading here; the chunks
# themselves are unchanged.
def passage(text: str) -> str:
    """The matching passage, readable, cut at a word near PASSAGE_MAX."""
    flat = " ".join(mend(text).split())  # chunks stored before mending, and any that slip through
    if len(flat) <= PASSAGE_MAX:
        return flat
    return flat[:PASSAGE_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def describe(document: dict[str, Any]) -> dict[str, Any]:
    """A Ledger document as a petition shows it: title, department, year and how it entered the Ledger."""
    source = provenance(document)
    return {"id": document["$id"], "title": document["title"].strip(),
            "department_name": DEPARTMENT_NAMES.get(document.get("department") or ""),
            "year": year_and_source(document)[0], "provenance": source.value if source else None}


def _match(document: dict[str, Any], text: str) -> LedgerMatch:
    return LedgerMatch(**describe(document), passage=passage(text))


def search(query: str, limit: int = DOCUMENTS_MAX) -> list[LedgerMatch]:
    """The documents best matching the query, one passage each, best first."""
    vector_lists, keyword_lists = ranked_lists([query])
    fused = fuse([*vector_lists, *keyword_lists])
    documents = ledger_documents.get_documents(chunk.document_id for chunk, _ in fused)
    published = [RetrievedChunk(chunk, score, documents[chunk.document_id]) for chunk, score in fused
                 if documents.get(chunk.document_id, {}).get("status") == LedgerStatus.PUBLISHED]
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
    """search(), kept for an hour: a petition's page is read far more often than the Ledger changes."""
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
