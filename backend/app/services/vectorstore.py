"""pgvector-backed vector store for RAG document chunks.

``PGVectorStore.create_sync`` only introspects the pre-provisioned table; it never alters it.

Writes bypass PGVectorStore: it inserts random UUID strings as row ids, but ``id`` here is an integer SERIAL.

Table schema:
    id                    SERIAL        -> id_column
    appwrite_document_id  TEXT          -> metadata
    chunk_index           INT           -> metadata
    chunk_text            TEXT          -> content_column
    embedding             VECTOR(768)   -> embedding_column (HNSW, cosine)
    created_at            TIMESTAMPTZ   -> metadata (defaults to now())
    chunk_tsv             TSVECTOR      -> generated from chunk_text; keyword search (GIN)

Note: ``POSTGRES_URL`` must use the psycopg v3 driver scheme, e.g.
``postgresql+psycopg://user:pass@host:5432/nokware_rag``.
"""

import atexit
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import numpy as np
import psycopg
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from app.config import get_settings

TABLE_NAME = "document_chunks"
ID_COLUMN = "id"
DOCUMENT_ID_COLUMN = "appwrite_document_id"
CHUNK_INDEX_COLUMN = "chunk_index"
CONTENT_COLUMN = "chunk_text"
EMBEDDING_COLUMN = "embedding"
CREATED_AT_COLUMN = "created_at"
METADATA_COLUMNS = [DOCUMENT_ID_COLUMN, CHUNK_INDEX_COLUMN, CREATED_AT_COLUMN]
EMBEDDING_MODEL = "models/gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768  # must equal the VECTOR(n) size of the embedding column
FULLTEXT_COLUMN = "chunk_tsv"  # generated tsvector over chunk_text (migration 0002)
POOL_MAX_SIZE = 8  # enough for retrieval's parallel keyword queries
POOL_CONNECT_SECONDS = 10
# What a caller waits is the pool's checkout timeout, not connect_timeout: its 30s default retried until the page
# had already given up at 30s, so an unreachable index reached the reader as a generic timeout instead of our 503.
# One connect attempt plus a second's grace surfaces the first failure rather than a retry loop.
POOL_CHECKOUT_SECONDS = POOL_CONNECT_SECONDS + 1

_DELETE_SQL = f'DELETE FROM "{TABLE_NAME}" WHERE "{DOCUMENT_ID_COLUMN}" = %s'
_INSERT_SQL = (
    f'INSERT INTO "{TABLE_NAME}" ("{DOCUMENT_ID_COLUMN}", "{CHUNK_INDEX_COLUMN}", '
    f'"{CONTENT_COLUMN}", "{EMBEDDING_COLUMN}") VALUES (%s, %s, %s, %s)'
)


def libpq_url(url: str) -> str:
    """psycopg wants a plain libpq URL, so drop any SQLAlchemy driver suffix."""
    scheme, sep, rest = url.partition("://")
    return f"{scheme.split('+')[0]}{sep}{rest}"


@lru_cache
def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    settings = get_settings()
    return GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL,
        output_dimensionality=EMBEDDING_DIMENSIONS,
        google_api_key=settings.gemini_api_key,
    )


@lru_cache
def get_engine() -> PGEngine:
    return PGEngine.from_connection_string(url=get_settings().postgres_url)


@lru_cache
def get_vectorstore() -> PGVectorStore:
    return PGVectorStore.create_sync(
        engine=get_engine(),
        table_name=TABLE_NAME,
        embedding_service=get_embeddings(),
        id_column=ID_COLUMN,
        content_column=CONTENT_COLUMN,
        embedding_column=EMBEDDING_COLUMN,
        metadata_columns=METADATA_COLUMNS,
        metadata_json_column=None,
    )


@lru_cache
def get_pool() -> ConnectionPool:
    """Shared connection pool: each new connection through the SSH tunnel costs
    several ~120 ms round trips, and retrieval runs its queries in parallel.
    Connections are checked on checkout, so one dropped by the tunnel is
    replaced rather than surfacing as an error."""
    pool = ConnectionPool(
        libpq_url(get_settings().postgres_url),
        min_size=1,
        max_size=POOL_MAX_SIZE,
        timeout=POOL_CHECKOUT_SECONDS,
        kwargs={"connect_timeout": POOL_CONNECT_SECONDS},
        configure=register_vector,
        check=ConnectionPool.check_connection,
        open=True,
    )
    atexit.register(pool.close)
    return pool


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Commits on normal exit, rolls back on an exception."""
    with get_pool().connection() as conn:
        yield conn


def replace_document_chunks(document_id: str, chunks: list[str], embeddings: list[list[float]]) -> int:
    """One transaction, so a retry or re-ingestion never duplicates chunks and an interrupted run never leaves a
    partial set."""
    if len(chunks) != len(embeddings):
        raise ValueError(f"{len(chunks)} chunks but {len(embeddings)} embeddings")
    rows = [
        (document_id, index, text, np.asarray(vector, dtype=np.float32))
        for index, (text, vector) in enumerate(zip(chunks, embeddings))
    ]
    with connect() as conn, conn.transaction():
        conn.execute(_DELETE_SQL, (document_id,))
        with conn.cursor() as cursor:
            cursor.executemany(_INSERT_SQL, rows)
    return len(rows)


def first_chunks() -> dict[str, str]:
    """A document's first chunk is roughly its first page: enough to check what the document is."""
    with connect() as conn:
        rows = conn.execute(f'SELECT "{DOCUMENT_ID_COLUMN}", "{CONTENT_COLUMN}" FROM "{TABLE_NAME}" WHERE "{CHUNK_INDEX_COLUMN}" = 0').fetchall()
    return {document_id: text for document_id, text in rows}
