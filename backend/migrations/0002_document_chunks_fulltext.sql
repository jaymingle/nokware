-- Full-text search on document_chunks, for hybrid (keyword + vector) retrieval.
--
-- Vector search alone misses exact-figure questions ("How much revenue did AMA
-- collect in 2023?") whose answer chunk shares specific terms but not overall
-- meaning with the question. A keyword arm over this column catches those, and
-- retrieval fuses both rankings.
--
-- STORED is required: on Postgres 18 a generated column defaults to VIRTUAL,
-- which cannot be indexed. Being generated, the column fills itself for
-- existing rows now and for every row ingestion inserts later.
--
-- The index is built serially: a parallel GIN build needs a dynamic shared
-- memory segment larger than the database container's /dev/shm (Docker's
-- 64 MB default), and fails with "could not resize shared memory segment".
--
-- Apply: psql "$POSTGRES_URL_WITHOUT_+psycopg" -f 0002_document_chunks_fulltext.sql

BEGIN;

SET LOCAL max_parallel_maintenance_workers = 0;

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS chunk_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED;

CREATE INDEX IF NOT EXISTS document_chunks_chunk_tsv_idx
    ON document_chunks USING gin (chunk_tsv);

COMMIT;
