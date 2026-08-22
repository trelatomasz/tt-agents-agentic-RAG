-- 0001_initial_schema.sql
--
-- Cloud SQL PostgreSQL 16 datastore for the personal RAG platform (specification
-- sections 6 and 7, C4 document `06-data-and-code`).
--
-- The one structural idea worth reading before the tables: an index is a *fold over
-- activated runs*, not a mutable corpus. Writes land in a candidate run, activation
-- stamps that run with a monotonic `activation_seq`, and the active corpus is derived
-- by replaying every activated run in sequence order. Rollback retires the newest
-- activated run instead of rewriting data, which is why it is O(1) rather than a
-- restore. Nothing staged in a candidate run is reachable from the active views.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Registry of configured sources (specification section 5).
--
-- Deliberately not referenced by a foreign key from the run and document tables: the
-- descriptor is owned by configuration (YAML) and synchronized by the CLI, while the
-- index is handed documents. A foreign key here would force the index to fabricate
-- registry rows -- inventing an `owner` and a `rights_policy` it was never told -- and
-- a fabricated rights policy is exactly the value that must never be guessed. The
-- access labels retrieval actually enforces are stored on each document version and
-- copied onto each chunk, so filtering never depends on this table.
CREATE TABLE IF NOT EXISTS sources (
    source_id       VARCHAR(100) PRIMARY KEY,
    source_type     VARCHAR(32)  NOT NULL,
    display_name    VARCHAR(128) NOT NULL,
    owner           VARCHAR(64)  NOT NULL,
    visibility      VARCHAR(32)  NOT NULL DEFAULT 'private',
    refresh_policy  VARCHAR(32)  NOT NULL DEFAULT 'manual',
    rights_policy   VARCHAR(64)  NOT NULL,
    adapter_version VARCHAR(32)  NOT NULL DEFAULT 'unversioned',
    configuration   JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Candidate index runs. `run_id` is the *index* run identifier returned by
-- `DocumentIndex.open_run`; the pipeline's own `IngestionRun.run_id` is recorded in
-- `summary_json` so a database row can be traced back to a pipeline run record.
CREATE SEQUENCE IF NOT EXISTS index_activation_seq AS BIGINT START 1;

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id              VARCHAR(64) PRIMARY KEY,
    source_id           VARCHAR(100) NOT NULL,
    trigger_type        VARCHAR(32)  NOT NULL DEFAULT 'manual',
    status              VARCHAR(32)  NOT NULL DEFAULT 'candidate',
    -- NULL while the run is a candidate, set from `index_activation_seq` on activation
    -- and cleared again when a rollback retires the run. "Activated" is therefore
    -- exactly "status = 'activated'", and the check constraint keeps the two in step.
    activation_seq      BIGINT UNIQUE,
    documents_processed INTEGER      NOT NULL DEFAULT 0,
    chunks_created      INTEGER      NOT NULL DEFAULT 0,
    tombstones_created  INTEGER      NOT NULL DEFAULT 0,
    cost_estimate_usd   NUMERIC(10, 4) NOT NULL DEFAULT 0.0,
    started_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    summary_json        JSONB        NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ingestion_runs_status_check
        CHECK (status IN ('candidate', 'activated', 'discarded', 'rolled_back')),
    CONSTRAINT ingestion_runs_activation_seq_check
        CHECK ((status = 'activated') = (activation_seq IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_source ON ingestion_runs (source_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_activation
    ON ingestion_runs (activation_seq DESC) WHERE activation_seq IS NOT NULL;

-- Document versions are content addressed: `content_hash` identifies this particular
-- version of a document, so the same version staged by two runs is one row.
CREATE TABLE IF NOT EXISTS document_versions (
    document_id        VARCHAR(128) NOT NULL,
    content_hash       CHAR(64)     NOT NULL,
    source_id          VARCHAR(100) NOT NULL,
    source_uri         TEXT         NOT NULL,
    title              TEXT         NOT NULL,
    media_type         VARCHAR(64)  NOT NULL,
    language           VARCHAR(16)  NOT NULL DEFAULT 'en',
    source_revision    VARCHAR(128) NOT NULL,
    fetched_at         TIMESTAMPTZ  NOT NULL,
    published_at       TIMESTAMPTZ,
    parser_version     VARCHAR(32)  NOT NULL,
    normalizer_version VARCHAR(32)  NOT NULL,
    visibility         VARCHAR(32)  NOT NULL DEFAULT 'private',
    rights_policy      VARCHAR(64)  NOT NULL,
    status             VARCHAR(32)  NOT NULL DEFAULT 'active',
    acl_labels         TEXT[]       NOT NULL DEFAULT '{}',
    metadata_json      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (document_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_document_versions_source ON document_versions (source_id);
CREATE INDEX IF NOT EXISTS idx_document_versions_title_trgm
    ON document_versions USING GIN (title gin_trgm_ops);

-- One row per (run, document): the staging event that a run recorded for a document.
-- A tombstone is the same event with no content, so "this run deleted D" and "this run
-- replaced D" are the same shape and the fold needs only one ordering rule.
CREATE TABLE IF NOT EXISTS run_document_stagings (
    index_run_id VARCHAR(64)  NOT NULL REFERENCES ingestion_runs (run_id) ON DELETE CASCADE,
    document_id  VARCHAR(128) NOT NULL,
    content_hash CHAR(64),
    is_tombstone BOOLEAN      NOT NULL DEFAULT FALSE,
    staged_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (index_run_id, document_id),
    UNIQUE (index_run_id, document_id, content_hash),
    CONSTRAINT run_document_stagings_tombstone_check
        CHECK (is_tombstone = (content_hash IS NULL)),
    FOREIGN KEY (document_id, content_hash)
        REFERENCES document_versions (document_id, content_hash) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_run_document_stagings_document
    ON run_document_stagings (document_id);

-- Chunks are keyed by the run that staged them, not by `chunk_id` alone. Chunk
-- identifiers are stable across re-ingestion of identical content, so a shared primary
-- key would let a candidate run overwrite rows the active index is currently serving --
-- the one thing candidate isolation exists to prevent.
CREATE TABLE IF NOT EXISTS chunks (
    index_run_id          VARCHAR(64)  NOT NULL,
    chunk_id              VARCHAR(160) NOT NULL,
    document_id           VARCHAR(128) NOT NULL,
    document_version_hash CHAR(64)     NOT NULL,
    source_id             VARCHAR(100) NOT NULL,
    ordinal               INTEGER      NOT NULL,
    text                  TEXT         NOT NULL,
    token_count           INTEGER      NOT NULL,
    language              VARCHAR(16)  NOT NULL DEFAULT 'en',
    chunker_version       VARCHAR(32)  NOT NULL,
    heading_path          TEXT[]       NOT NULL DEFAULT '{}',
    locator_json          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    acl_labels            TEXT[]       NOT NULL DEFAULT '{}',
    lexical_terms         TEXT[]       NOT NULL DEFAULT '{}',
    -- The exact string the lexical index is built from: heading path plus body, written
    -- by `pipeline.chunk.contextual_text`. It is stored rather than derived because a
    -- generated column may only call immutable functions (`array_to_string` is merely
    -- stable), and storing it keeps the PostgreSQL lexical signal identical to the
    -- in-memory reference implementation.
    lexical_source        TEXT         NOT NULL,
    lexical_text_vector   TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', lexical_source)) STORED,
    dense_embedding       VECTOR(768),
    embedding_model       VARCHAR(64),
    embedding_dimensions  INTEGER,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (index_run_id, chunk_id),
    -- Cascades from the staging row, so discarding a run or replacing a document's
    -- staging event cannot leave chunks behind that the fold would still join to.
    FOREIGN KEY (index_run_id, document_id, document_version_hash)
        REFERENCES run_document_stagings (index_run_id, document_id, content_hash)
        ON DELETE CASCADE
);

-- Access filtering runs before ranking, so the GIN index on `acl_labels` is the one
-- that has to be fast; `&&` (array overlap) is the operator it supports.
CREATE INDEX IF NOT EXISTS idx_chunks_acl_labels ON chunks USING GIN (acl_labels);
CREATE INDEX IF NOT EXISTS idx_chunks_lexical ON chunks USING GIN (lexical_text_vector);
CREATE INDEX IF NOT EXISTS idx_chunks_lexical_trgm
    ON chunks USING GIN (lexical_source gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_document
    ON chunks (document_id, document_version_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks (source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_dense_vector
    ON chunks USING hnsw (dense_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- The activation pointer. A single row exists from migration time so that activation
-- and rollback can serialize on `SELECT ... FOR UPDATE` against a row that is always
-- there; `active_run_id` is NULL only while the index has never been activated.
CREATE TABLE IF NOT EXISTS active_index_pointer (
    id             INTEGER      PRIMARY KEY DEFAULT 1,
    active_run_id  VARCHAR(64)  REFERENCES ingestion_runs (run_id),
    active_seq     BIGINT       NOT NULL DEFAULT 0,
    activated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    activated_by   VARCHAR(64)  NOT NULL DEFAULT 'system',
    reason         VARCHAR(256) NOT NULL DEFAULT 'initial empty index',
    CONSTRAINT active_index_pointer_single_row CHECK (id = 1)
);

INSERT INTO active_index_pointer (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- The fold. For each document, the newest activated staging event wins; if that event
-- is a tombstone the document is absent from the active corpus.
CREATE OR REPLACE VIEW active_document_versions AS
WITH latest AS (
    SELECT DISTINCT ON (s.document_id)
           s.document_id,
           s.content_hash,
           s.index_run_id,
           s.is_tombstone
    FROM run_document_stagings s
    JOIN ingestion_runs r ON r.run_id = s.index_run_id
    WHERE r.status = 'activated'
    ORDER BY s.document_id, r.activation_seq DESC
)
SELECT latest.index_run_id, dv.*
FROM latest
JOIN document_versions dv
  ON dv.document_id = latest.document_id
 AND dv.content_hash = latest.content_hash
WHERE NOT latest.is_tombstone;

CREATE OR REPLACE VIEW active_chunks AS
SELECT c.*
FROM chunks c
JOIN active_document_versions adv
  ON adv.document_id = c.document_id
 AND adv.content_hash = c.document_version_hash
 AND adv.index_run_id = c.index_run_id;
