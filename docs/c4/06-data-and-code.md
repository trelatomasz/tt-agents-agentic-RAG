# C4 Level 4: Data & Code Models

This document specifies the **Data Architecture (Level 4)** of the Personal Agentic RAG Platform, defining the PostgreSQL relational and vector schemas, JSON contracts, locator models, and entity lifecycle state machines.

---

## 1. Entity-Relationship Diagram (ERD)

```plantuml
@startuml "06-data-and-code-erd"
!theme plain
skinparam linetype ortho

title Relational & Vector Data Model (Level 4: ERD)

entity "SOURCES" as sources {
    * source_id : varchar(64) [PK]
    --
    source_type : varchar(32)
    display_name : varchar(128)
    visibility : varchar(32)
    owner : varchar(64)
    refresh_policy : varchar(32)
    rights_policy : varchar(64)
    configuration : jsonb
    adapter_version : varchar(32)
    created_at : timestamptz
    updated_at : timestamptz
}

entity "DOCUMENT_VERSIONS" as doc_versions {
    * document_id : varchar(128) [PK]
    --
    * source_id : varchar(64) [FK]
    source_uri : text
    title : varchar(256)
    media_type : varchar(64)
    language : varchar(16)
    content_hash : char(64)
    source_revision : varchar(64)
    fetched_at : timestamptz
    published_at : timestamptz
    parser_version : varchar(32)
    metadata_json : jsonb
    visibility : varchar(32)
    rights_policy : varchar(64)
    status : varchar(32)
}

entity "CHUNKS" as chunks {
    * chunk_id : varchar(160) [PK]
    --
    * document_id : varchar(128) [FK]
    document_version_hash : char(64)
    ordinal : integer
    text : text
    token_count : integer
    heading_path : jsonb
    locator_json : jsonb
    language : varchar(16)
    acl_labels : text[]
    embedding_model : varchar(64)
    embedding : vector(768)
    tsv_content : tsvector
    indexed_at : timestamptz
}

entity "INGESTION_RUNS" as ingestion_runs {
    * run_id : varchar(64) [PK]
    --
    run_type : varchar(32)
    started_at : timestamptz
    completed_at : timestamptz
    status : varchar(32)
    documents_scanned : integer
    chunks_indexed : integer
    index_version : varchar(64)
    manifest_uri : text
    metrics_json : jsonb
}

entity "ACTIVE_INDEX_POINTER" as active_pointer {
    * pointer_key : varchar(32) [PK]
    --
    * active_run_id : varchar(64) [FK]
    index_version : varchar(64)
    swapped_at : timestamptz
    swapped_by : varchar(64)
    previous_run_id : varchar(64)
}

entity "EVAL_REPORTS" as eval_reports {
    * report_id : varchar(64) [PK]
    --
    * run_id : varchar(64) [FK]
    eval_suite : varchar(64)
    faithfulness_score : float
    answer_relevancy_score : float
    context_precision_score : float
    passed_gate : boolean
    created_at : timestamptz
}

sources ||--o{ doc_versions : "owns"
doc_versions ||--o{ chunks : "contains"
ingestion_runs ||--o{ chunks : "indexes"
ingestion_runs ||--o{ eval_reports : "evaluates"
active_pointer }|--|| ingestion_runs : "points to"

@enduml
```

---

## 2. PostgreSQL Schema & Index Specifications

### 2.1 Database Tables DDL
```sql
-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Sources Registry
CREATE TABLE sources (
    source_id VARCHAR(64) PRIMARY KEY,
    source_type VARCHAR(32) NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    visibility VARCHAR(32) NOT NULL DEFAULT 'private',
    owner VARCHAR(64) NOT NULL,
    refresh_policy VARCHAR(32) NOT NULL,
    rights_policy VARCHAR(64) NOT NULL,
    configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
    adapter_version VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Document Versions Table
CREATE TABLE document_versions (
    document_id VARCHAR(128) NOT NULL,
    source_id VARCHAR(64) NOT NULL REFERENCES sources(source_id),
    source_uri TEXT NOT NULL,
    title VARCHAR(256) NOT NULL,
    media_type VARCHAR(64) NOT NULL,
    language VARCHAR(16) NOT NULL DEFAULT 'en',
    content_hash CHAR(64) NOT NULL,
    source_revision VARCHAR(64) NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    parser_version VARCHAR(32) NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    visibility VARCHAR(32) NOT NULL DEFAULT 'private',
    rights_policy VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    PRIMARY KEY (document_id, content_hash)
);

-- Ingestion Runs Table
CREATE TABLE ingestion_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    source_id VARCHAR(64) NOT NULL REFERENCES sources(source_id),
    trigger_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'candidate',
    documents_processed INTEGER NOT NULL DEFAULT 0,
    chunks_created INTEGER NOT NULL DEFAULT 0,
    tombstones_created INTEGER NOT NULL DEFAULT 0,
    cost_estimate_usd NUMERIC(10, 4) DEFAULT 0.0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Chunks Table with Full-Text and Vector Indexes
CREATE TABLE chunks (
    chunk_id VARCHAR(160) PRIMARY KEY,
    document_id VARCHAR(128) NOT NULL,
    document_version_hash CHAR(64) NOT NULL,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    heading_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    locator_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    language VARCHAR(16) NOT NULL DEFAULT 'en',
    acl_labels TEXT[] NOT NULL DEFAULT '{}',
    embedding_model VARCHAR(64) NOT NULL,
    embedding_dimensions INTEGER NOT NULL,
    chunker_version VARCHAR(32) NOT NULL,
    lexical_text_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    dense_embedding VECTOR(768),
    index_run_id VARCHAR(64) NOT NULL REFERENCES ingestion_runs(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Active Index Pointer Table (Single-row table)
CREATE TABLE active_index_pointers (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    active_run_id VARCHAR(64) NOT NULL REFERENCES ingestion_runs(run_id),
    activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_by VARCHAR(64) NOT NULL,
    reason VARCHAR(256) NOT NULL
);
```

### 2.2 Performance Indexing Strategy
```sql
-- Fast ACL and Source filtering
CREATE INDEX idx_chunks_acl_labels ON chunks USING GIN(acl_labels);
CREATE INDEX idx_chunks_run_id ON chunks (index_run_id);

-- Full-Text Lexical Search Index (GIN)
CREATE INDEX idx_chunks_lexical ON chunks USING GIN(lexical_text_vector);

-- Dense Vector Search Index (HNSW for high recall and low query latency)
CREATE INDEX idx_chunks_dense_vector ON chunks 
USING hnsw (dense_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

---

## 3. Provenance Locator Schemas

Every chunk stores a structured `locator_json` object enabling human-verifiable citations:

| Source Type | Locator JSON Schema | Example Payload |
|---|---|---|
| **Ebook (PDF)** | `{"page": int, "total_pages": int}` | `{"page": 42, "total_pages": 380}` |
| **Ebook (EPUB)** | `{"chapter": str, "section": str}` | `{"chapter": "Chapter 3: Vector Indexing", "section": "3.2 HNSW vs IVFFlat"}` |
| **Web Article** | `{"canonical_url": str, "fragment": str, "fetched_at": str}` | `{"canonical_url": "https://cloud.google.com/sql/docs/postgres/ai-overview", "fragment": "using-pgvector", "fetched_at": "2026-08-19T08:00:00Z"}` |
| **`tt-root/info`** | `{"git_commit": str, "path": str, "heading": str}` | `{"git_commit": "c4d5e6f7", "path": "knowledge-base/part-3-ai-engineering/12-rag-pipelines.md", "heading": "Retrieval Evaluation Gate"}` |
| **Project Repo** | `{"repo": str, "commit": str, "path": str, "lines": [int, int]}` | `{"repo": "org/repo-service", "commit": "8f9e0a1b", "path": "src/service.py", "lines": [45, 82]}` |

---

## 4. Entity Lifecycle State Machines

### 4.1 Document Version Lifecycle (`DocumentStatus`)

```plantuml
@startuml "06-document-lifecycle"

title Document Version Lifecycle (DocumentStatus)

[*] --> ACTIVE : Ingested & Indexed
ACTIVE --> TOMBSTONED : Source Modified (New Version Created)
ACTIVE --> DELETED : File Deleted at Source (Explicit Tombstone)
ACTIVE --> QUARANTINED : Parser/Rights Violation Detected
QUARANTINED --> ACTIVE : Manually Approved
TOMBSTONED --> [*] : Purged per Retention Policy
DELETED --> [*] : Purged

@enduml
```

### 4.2 Ingestion Run Lifecycle (`IngestionRunStatus`)

```plantuml
@startuml "06-ingestion-lifecycle"

title Ingestion Run Lifecycle (IngestionRunStatus)

[*] --> CANDIDATE : Chunks Staged in Batch
CANDIDATE --> EVALUATING : Running Golden & Negative Sets
EVALUATING --> ACTIVE : Evaluation Passed & Pointer Swapped
EVALUATING --> QUARANTINED : Evaluation Failed (Regression Detected)
ACTIVE --> ROLLED_BACK : Emergency Reversion to Prior Run
QUARANTINED --> [*] : Diagnostic Inspect & Purge
ROLLED_BACK --> [*] : Historical Retention

@enduml
```
