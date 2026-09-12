"""pgvector-backed vector store for RAG document chunks.

Reads go through langchain-postgres' ``PGVectorStore``, mapped onto the
pre-provisioned ``document_chunks`` table in ``nokware_rag``. Embeddings are
Google Gemini ``gemini-embedding-2`` truncated to 768 dimensions to match the
table's ``VECTOR(768)`` column. ``PGVectorStore.create_sync`` only introspects
the table and validates that the mapped columns exist; it never alters it.

Writes bypass PGVectorStore: it inserts random UUID strings as row ids, but
``id`` here is an integer SERIAL. ``replace_document_chunks`` writes rows with
psycopg directly and lets Postgres assign ``id`` and ``created_at``.

Table schema:
    id                    SERIAL        -> id_column
    appwrite_document_id  TEXT          -> metadata
    chunk_index           INT           -> metadata
    chunk_text            TEXT          -> content_column
    embedding             VECTOR(768)   -> embedding_column (HNSW, cosine)
    created_at            TIMESTAMPTZ   -> metadata (defaults to now())

There is no JSON metadata column, so ``metadata_json_column`` is ``None``.

Note: ``POSTGRES_URL`` must use the psycopg v3 driver scheme, e.g.
``postgresql+psycopg://user:pass@host:5432/nokware_rag``.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import numpy as np
import psycopg
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from pgvector.psycopg import register_vector

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
DEFAULT_K = 5

_DELETE_SQL = f'DELETE FROM "{TABLE_NAME}" WHERE "{DOCUMENT_ID_COLUMN}" = %s'
_INSERT_SQL = (
    f'INSERT INTO "{TABLE_NAME}" ("{DOCUMENT_ID_COLUMN}", "{CHUNK_INDEX_COLUMN}", '
    f'"{CONTENT_COLUMN}", "{EMBEDDING_COLUMN}") VALUES (%s, %s, %s, %s)'
)
_COUNT_SQL = f'SELECT count(*) FROM "{TABLE_NAME}" WHERE "{DOCUMENT_ID_COLUMN}" = %s'


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


def get_retriever(k: int = DEFAULT_K) -> VectorStoreRetriever:
    """Return a retriever over the vector store, fetching ``k`` chunks."""
    return get_vectorstore().as_retriever(search_kwargs={"k": k})


@contextmanager
def _connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(libpq_url(get_settings().postgres_url), connect_timeout=10) as conn:
        register_vector(conn)
        yield conn


def replace_document_chunks(document_id: str, chunks: list[str], embeddings: list[list[float]]) -> int:
    """Atomically replace every chunk of one document; returns the number written.

    The delete and inserts run in one transaction, so a retry or re-ingestion
    never duplicates chunks and an interrupted run never leaves a partial set.
    Passing no chunks clears the document's rows.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(f"{len(chunks)} chunks but {len(embeddings)} embeddings")
    rows = [
        (document_id, index, text, np.asarray(vector, dtype=np.float32))
        for index, (text, vector) in enumerate(zip(chunks, embeddings))
    ]
    with _connect() as conn, conn.transaction():
        conn.execute(_DELETE_SQL, (document_id,))
        with conn.cursor() as cursor:
            cursor.executemany(_INSERT_SQL, rows)
    return len(rows)


def count_document_chunks(document_id: str) -> int:
    with _connect() as conn:
        return conn.execute(_COUNT_SQL, (document_id,)).fetchone()[0]
