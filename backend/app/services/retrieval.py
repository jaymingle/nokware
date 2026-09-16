"""Hybrid retrieval for Ask.

1. Query expansion: gemini-2.5-flash rewrites the question into a few search
   queries in the wording official documents use ("revenue realised" rather
   than "money collected"). The original question is always searched too.
2. Two ranked lists per query: vector similarity (PGVectorStore over the HNSW
   index) and BM25 keyword ranking over the chunk_tsv full-text column. Vector
   search alone misses a fact buried in a multi-topic chunk; keyword search
   alone misses paraphrases. Together they catch both.
3. Reciprocal rank fusion merges every list into one ranking. Each keyword
   search's top hit is pinned into the final set, so a precise match cannot be
   crowded out by a document that merely appears in more lists.
4. Selection: only published documents. Where a document comes in annual
   editions, the newest is preferred, unless the question names a year, in
   which case that year's edition is (so history stays retrievable). Near-
   duplicate chunks, e.g. the same paragraph in several editions, collapse to
   the preferred one so they cannot crowd out other content.
"""

import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.services import ledger_documents
from app.services.ledger_documents import year_from_title
from app.services.llm import get_chat_model
from app.services.vectorstore import (
    CHUNK_INDEX_COLUMN,
    CONTENT_COLUMN,
    DOCUMENT_ID_COLUMN,
    FULLTEXT_COLUMN,
    ID_COLUMN,
    TABLE_NAME,
    connect,
    get_embeddings,
    get_vectorstore,
)

logger = logging.getLogger(__name__)

EXPANSION_ENABLED = True  # set False to search the question alone
QUERY_EXPANSIONS = 3  # rewrites per question, in addition to the question itself
LIST_LIMIT = 30  # chunks per ranked list (per query, per arm)
RRF_K = 60  # standard reciprocal-rank-fusion constant
CANDIDATE_POOL = 40  # fused chunks considered for selection
FINAL_K = 8  # chunks passed to the answering model, plus any pinned keyword hits
OLDER_EDITION_WEIGHT = 0.5  # score multiplier for a non-preferred edition
MATCHING_YEAR_WEIGHT = 1.5  # score multiplier for the edition the question asks about
NEAR_DUPLICATE_SIMILARITY = 0.8  # Jaccard similarity of word 3-grams
_BM25_K1, _BM25_B = 1.2, 0.75
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_SERIES_NOISE = {"final", "draft", "revised", "copy"}

_EXPANSION_PROMPT = ChatPromptTemplate.from_template(
    "Turn a resident's question into search queries for an archive of Accra "
    "Metropolitan Assembly (AMA) documents: budgets and fee-fixing resolutions, "
    "annual and quarterly reports, press releases, newsletters, bye-laws and manuals.\n"
    "Write {count} short search queries that use the wording such official documents "
    'are likely to use, for example "revenue realised" or "IGF" for money collected, '
    '"fatalities" for deaths, "desilting" for drain cleaning. Keep every year, place, '
    "name and number from the question.\n"
    "Output only the queries, one per line, with no numbering and no other text.\n\n"
    "Question: {question}"
)

# BM25 over chunk_tsv. Document frequencies come from GIN-indexed counts per query
# term, so the ranking weighs rare terms above common ones ("realis" above "ama").
# Only chunk ids and term counts flow through the join; chunk text is fetched for
# the final rows alone (carrying it through the join made it spill to disk). Ties,
# common when editions repeat a paragraph, are broken by id so results are stable.
_BM25_SQL = f"""
WITH terms AS (
    SELECT DISTINCT lexeme FROM unnest(to_tsvector('english', %(query)s))
), corpus AS (
    SELECT count(*)::float8 AS n, avg(length({FULLTEXT_COLUMN}))::float8 AS avglen FROM {TABLE_NAME}
), weights AS (
    SELECT t.lexeme, ln((corpus.n - df.df + 0.5) / (df.df + 0.5) + 1) AS idf
    FROM terms t CROSS JOIN corpus
    CROSS JOIN LATERAL (
        SELECT count(*)::float8 AS df FROM {TABLE_NAME}
        WHERE {FULLTEXT_COLUMN} @@ to_tsquery('simple', quote_literal(t.lexeme))
    ) df
), q AS (
    SELECT to_tsquery('simple', string_agg(quote_literal(lexeme), ' | ')) AS query,
           array_agg(lexeme) AS lexemes
    FROM terms
), term_counts AS (
    SELECT c.{ID_COLUMN} AS id, length(c.{FULLTEXT_COLUMN}) AS len, u.lexeme,
           array_length(u.positions, 1) AS tf
    FROM {TABLE_NAME} c CROSS JOIN q
    CROSS JOIN LATERAL unnest(c.{FULLTEXT_COLUMN}) u
    WHERE c.{FULLTEXT_COLUMN} @@ q.query AND u.lexeme = ANY (q.lexemes)
), ranked AS (
    SELECT tc.id,
           sum(w.idf * tc.tf * {_BM25_K1 + 1}
               / (tc.tf + {_BM25_K1} * (1 - {_BM25_B} + {_BM25_B} * tc.len / corpus.avglen))) AS score
    FROM term_counts tc JOIN weights w ON w.lexeme = tc.lexeme CROSS JOIN corpus
    GROUP BY tc.id
    ORDER BY score DESC, tc.id
    LIMIT %(limit)s
)
SELECT c.{ID_COLUMN}, c.{DOCUMENT_ID_COLUMN}, c.{CHUNK_INDEX_COLUMN}, c.{CONTENT_COLUMN}
FROM ranked JOIN {TABLE_NAME} c ON c.{ID_COLUMN} = ranked.id
ORDER BY ranked.score DESC, ranked.id
"""


@dataclass(frozen=True)
class Chunk:
    chunk_id: int
    document_id: str
    chunk_index: int
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    document: dict[str, Any]  # the chunk's ledger_documents attributes


@dataclass(frozen=True)
class Retrieval:
    queries: list[str]
    chunks: list[RetrievedChunk]


def _clean_query_line(line: str) -> str:
    return re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip().strip('"').strip()


def expand_query(question: str) -> list[str]:
    """The question plus up to QUERY_EXPANSIONS rewrites; just the question on failure."""
    if not EXPANSION_ENABLED:
        return [question]
    chain = _EXPANSION_PROMPT | get_chat_model(0.0, thinking_budget=0) | StrOutputParser()
    try:
        reply = chain.invoke({"question": question, "count": QUERY_EXPANSIONS})
    except Exception as exc:  # retrieval must still work if expansion is unavailable
        logger.warning("Query expansion failed (%s); searching the question only", exc)
        return [question]
    rewrites = [query for query in map(_clean_query_line, reply.splitlines()) if query]
    return list(dict.fromkeys([question, *rewrites]))[: QUERY_EXPANSIONS + 1]


def vector_search(vector: list[float]) -> list[Chunk]:
    hits = get_vectorstore().similarity_search_with_score_by_vector(vector, k=LIST_LIMIT)
    return [
        Chunk(int(doc.id), doc.metadata[DOCUMENT_ID_COLUMN], doc.metadata[CHUNK_INDEX_COLUMN], doc.page_content)
        for doc, _distance in hits
    ]


def keyword_search(query: str) -> list[Chunk]:
    with connect() as conn:
        rows = conn.execute(_BM25_SQL, {"query": query, "limit": LIST_LIMIT}).fetchall()
    return [Chunk(row[0], row[1], row[2], row[3]) for row in rows]


def ranked_lists(queries: list[str]) -> tuple[list[list[Chunk]], list[list[Chunk]]]:
    """(vector lists, keyword lists): one of each per query, built in parallel."""
    vectors = get_embeddings().embed_documents(queries, task_type="RETRIEVAL_QUERY")
    with ThreadPoolExecutor(max_workers=2 * len(queries)) as pool:
        vector_lists = pool.map(vector_search, vectors)
        keyword_lists = pool.map(keyword_search, queries)
        return list(vector_lists), list(keyword_lists)


def fuse(ranked_lists: Iterable[list[Chunk]]) -> list[tuple[Chunk, float]]:
    """Reciprocal rank fusion: each list adds 1 / (RRF_K + rank) to a chunk's score."""
    scores: dict[int, float] = defaultdict(float)
    chunks: dict[int, Chunk] = {}
    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, 1):
            scores[chunk.chunk_id] += 1 / (RRF_K + rank)
            chunks[chunk.chunk_id] = chunk
    return sorted(((chunks[i], score) for i, score in scores.items()), key=lambda pair: pair[1], reverse=True)


def question_years(question: str) -> set[int]:
    return {int(year) for year in _YEAR.findall(question)}


def series_key(title: str) -> str:
    """Titles of one document's editions, reduced to what they share.

    "RIGHT TO INFORMATION MANUAL 2024" and "Right to Information Manual" both
    give "right to information manual".
    """
    words = re.findall(r"[a-z]+", _YEAR.sub(" ", title.lower()))
    return " ".join(word for word in words if word not in _SERIES_NOISE)


def edition_year(document: dict[str, Any]) -> int | None:
    return document.get("documentYear") or year_from_title(document.get("title") or "")


def _edition_weight(year: int | None, known_years: set[int], asked_years: set[int]) -> float:
    matching = known_years & asked_years
    if matching:  # the question names an edition's year: prefer it, history stays retrievable
        return MATCHING_YEAR_WEIGHT if year in matching else OLDER_EDITION_WEIGHT
    return 1.0 if year == max(known_years) else OLDER_EDITION_WEIGHT


def apply_edition_preference(candidates: list[RetrievedChunk], asked_years: set[int]) -> list[RetrievedChunk]:
    """Re-weight chunks from documents that come in several yearly editions."""
    editions: dict[str, dict[str, int | None]] = defaultdict(dict)
    for candidate in candidates:
        key = series_key(candidate.document.get("title") or "")
        editions[key][candidate.chunk.document_id] = edition_year(candidate.document)
    weighted = []
    for candidate in candidates:
        series = editions[series_key(candidate.document.get("title") or "")]
        known_years = {year for year in series.values() if year}
        weight = 1.0
        if len(series) > 1 and known_years:
            weight = _edition_weight(series[candidate.chunk.document_id], known_years, asked_years)
        weighted.append(replace(candidate, score=candidate.score * weight))
    return sorted(weighted, key=lambda candidate: candidate.score, reverse=True)


def _shingles(text: str) -> frozenset[tuple[str, ...]]:
    words = re.findall(r"[a-z]+", text.lower())  # letters only: editions differ mostly in numbers
    return frozenset(zip(words, words[1:], words[2:]))


def _similarity(a: frozenset[tuple[str, ...]], b: frozenset[tuple[str, ...]]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def collapse_near_duplicates(candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Keep the best-scored chunk of each group of near-identical chunks."""
    kept: list[tuple[RetrievedChunk, frozenset[tuple[str, ...]]]] = []
    for candidate in candidates:
        shingles = _shingles(candidate.chunk.text)
        if all(_similarity(shingles, other) < NEAR_DUPLICATE_SIMILARITY for _, other in kept):
            kept.append((candidate, shingles))
    return [candidate for candidate, _ in kept]


def select_final(ranked: list[RetrievedChunk], pinned_ids: set[int]) -> list[RetrievedChunk]:
    """The top FINAL_K chunks plus any pinned chunk outside them, in ranking order.

    Pinned chunks are each keyword search's top hit. A precise keyword match can
    lose the fused ranking to a document that appears in many lists; pinning it
    keeps a second source (for example one whose figures disagree) in view. Pins
    are added on top of the top FINAL_K rather than displacing them, so the
    best-supported chunks are never traded away (at most one extra per query).
    """
    chosen = {c.chunk.chunk_id for c in ranked[:FINAL_K]} | pinned_ids
    return [c for c in ranked if c.chunk.chunk_id in chosen]


def retrieve(question: str) -> Retrieval:
    queries = expand_query(question)
    vector_lists, keyword_lists = ranked_lists(queries)
    fused = fuse([*vector_lists, *keyword_lists])
    pinned_ids = {ranked[0].chunk_id for ranked in keyword_lists if ranked}
    pool = fused[:CANDIDATE_POOL] + [pair for pair in fused[CANDIDATE_POOL:] if pair[0].chunk_id in pinned_ids]
    documents = ledger_documents.get_documents(chunk.document_id for chunk, _ in pool)
    candidates = [
        RetrievedChunk(chunk, score, documents[chunk.document_id])
        for chunk, score in pool
        if ledger_documents.is_public_document(documents.get(chunk.document_id))
    ]
    ranked = collapse_near_duplicates(apply_edition_preference(candidates, question_years(question)))
    return Retrieval(queries=queries, chunks=select_final(ranked, pinned_ids))
