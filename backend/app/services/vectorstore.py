"""pgvector-backed vector store for RAG document chunks.

Maps langchain-postgres' ``PGVectorStore`` onto the pre-provisioned
``document_chunks`` table in ``nokware_rag`` using 768-dimensional Google
Gemini embeddings (``text-embedding-004``). The table is never created or
altered here — ``PGVectorStore.create_sync`` only introspects it and validates
that the mapped columns exist.

Table schema:
    id                    SERIAL        -> id_column
    appwrite_document_id  TEXT          -> metadata
    chunk_index           INT           -> metadata
    chunk_text            TEXT          -> content_column
    embedding             VECTOR(768)   -> embedding_column
    created_at            TIMESTAMPTZ   -> metadata

There is no JSON metadata column, so ``metadata_json_column`` is ``None``.

Note: ``POSTGRES_URL`` must use the psycopg v3 driver scheme, e.g.
``postgresql+psycopg://user:pass@host:5432/nokware_rag``.
"""

from functools import lru_cache

from langchain_core.vectorstores import VectorStoreRetriever
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGEngine, PGVectorStore

from app.config import get_settings

TABLE_NAME = "document_chunks"
ID_COLUMN = "id"
CONTENT_COLUMN = "chunk_text"
EMBEDDING_COLUMN = "embedding"
METADATA_COLUMNS = ["appwrite_document_id", "chunk_index", "created_at"]
EMBEDDING_MODEL = "models/text-embedding-004"
DEFAULT_K = 5


@lru_cache
def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    settings = get_settings()
    return GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL,
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
