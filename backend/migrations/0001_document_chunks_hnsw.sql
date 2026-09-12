-- Replace the IVFFlat index on document_chunks.embedding with HNSW.
--
-- The IVFFlat index was built while the table was empty, so its lists were
-- trained on no data; with lists=100 and the default probes=1 a query would scan
-- roughly 1% of rows. HNSW needs no training, stays accurate as rows are added,
-- and gives better recall at this scale. vector_cosine_ops matches the cosine
-- distance PGVectorStore queries with.
--
-- Apply: psql "$POSTGRES_URL_WITHOUT_+psycopg" -f 0001_document_chunks_hnsw.sql

BEGIN;

DROP INDEX IF EXISTS document_chunks_embedding_idx;

CREATE INDEX document_chunks_embedding_idx
    ON document_chunks USING hnsw (embedding vector_cosine_ops);

COMMIT;
