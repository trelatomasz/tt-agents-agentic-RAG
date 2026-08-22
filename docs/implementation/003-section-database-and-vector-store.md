# Section 003: Database & Vector Store Subsystem

- **Module**: Cloud SQL PostgreSQL Datastore (`pgvector` + FTS)
- **Status**: `DONE` (integration suite written but not yet executed — see §3.5)
- **Assigned Subagent**: Database & Index Subagent
- **Dependencies**: [`001-section-contracts-and-models.md`](001-section-contracts-and-models.md), [`002-section-source-adapters.md`](002-section-source-adapters.md)
- **Target Files**:
  - `src/personal_rag/index/postgres.py` (Done)
  - `src/personal_rag/db/schema.sql` (Done — generated from the migrations)
  - `src/personal_rag/db/migrations/0001_initial_schema.sql` (Done)
  - `src/personal_rag/db/migrate.py`, `src/personal_rag/db/connection.py` (Done)

---

## 1. Objectives & Scope
Implement the transactional database and hybrid search store on Cloud SQL PostgreSQL 16 using `pgvector` for 768-dimensional embeddings, native `tsvector` for lexical FTS, SQL-level ACL filtering, and candidate index activation pointers.

## 2. Checklist & Deliverables
- [x] [DONE] Implemented reference in-memory vector & FTS index (`MemoryIndex`) with RRF fusion for local offline development.
- [x] [DONE] Create PostgreSQL DDL schema (`SOURCES`, `DOCUMENT_VERSIONS`, `CHUNKS`, `INGESTION_RUNS`, `ACTIVE_INDEX_POINTER`).
- [x] [DONE] Implement `pgvector` HNSW cosine distance index (`vector(768)`).
- [x] [DONE] Implement PostgreSQL full-text search `tsvector` with `pg_trgm`. *Lexical ranking uses `ts_rank_cd`, not Okapi BM25 — see §3.4.*
- [x] [DONE] Implement parameterized SQL pre-filtering (`WHERE acl_labels && :user_labels`) before distance calculations.
- [x] [DONE] Implement `PostgresIndex` matching the `DocumentIndex` protocol.
- [x] [DONE] Implement atomic candidate index pointer swap and $<5$s rollback function.

## 3. Changes Implemented & Verification

### 3.1 The structural idea: an index is a fold over activated runs

The active corpus is not a mutable table. Each run records one *staging event* per document
in `run_document_stagings` — a new version, or a tombstone. Activation stamps the run with a
monotonic `activation_seq`. The `active_document_versions` view derives the corpus: for each
document the newest staging event from an `activated` run wins, and the document is absent if
that event was a tombstone.

Three properties then fall out of the schema rather than out of application discipline, which
is why they survive a crash halfway through a run:

| Property | Mechanism |
|---|---|
| **Candidate isolation** | Chunks are keyed `(index_run_id, chunk_id)` and the active views join only `activated` runs, so a candidate run cannot overwrite rows the active index is serving. |
| **Atomic activation** | One transaction that serializes on `SELECT … FOR UPDATE` against the single `active_index_pointer` row. A reader sees the corpus before or after, never during. |
| **Rollback in $O(1)$** | Retiring the head run is a status update on one row (`activated` → `rolled_back`, `activation_seq` → `NULL`). No data is restored, so the five-second budget (register entry P-23) holds regardless of corpus size. |

A rolled-back run stays retired: because the fold keys off `status = 'activated'`, a later
activation cannot resurrect it.

### 3.2 Access filtering before ranking

`acl_labels && %(grants)s::text[]` is repeated inside **each** retrieval branch (lexical,
trigram recovery, dense) rather than shared through a CTE — a CTE referenced more than once is
materialized by default, which would forfeit the GIN and HNSW index scans that make the filter
cheap. Grants come from `Principal.grants` (server context, never the request body) and are
always bound parameters; a test asserts the grant strings never appear in the SQL text.

`pgvector`'s `hnsw.iterative_scan` is enabled per transaction so a filtered vector scan keeps
pulling candidates until enough pass the ACL filter, instead of filtering a fixed-size
candidate list and quietly losing recall. It exists only on pgvector ≥ 0.8, so
`PostgresIndex._tune` probes `pg_settings` and logs `index_tuning_unavailable` rather than
assuming.

### 3.3 Deliberate deviations from the C4 DDL in `../c4/06-data-and-code.md`

| Deviation | Reason |
|---|---|
| No FK from `ingestion_runs`/`document_versions` to `sources` | The descriptor is owned by configuration (section 5). A FK would force the index to fabricate a registry row — inventing an `owner` and a `rights_policy` it was never told — and a fabricated rights policy is the one value that must never be guessed. Filtering reads labels stored on each chunk, so it never depends on this table. `register_source()` populates the registry from a real descriptor. |
| `chunks` PK is `(index_run_id, chunk_id)`, not `chunk_id` | `chunk_id` is stable across re-ingestion of identical content, so a single-column PK would let a candidate run overwrite live rows. |
| `heading_path` is `TEXT[]`, not `JSONB` | Better type match for a string tuple. |
| Added `lexical_source TEXT`; the tsvector is generated from it, not from `text` | `MemoryIndex` indexes heading path **plus** body (`contextual_text`). Generating from `text` alone would make the two implementations rank differently. A generated column may only call immutable functions and `array_to_string` is merely *stable*, so the string is written by the application. |
| Added `chunks.source_id` | Lets `source_ids` narrowing filter without a join. |
| Added `chunks.lexical_terms TEXT[]` | Keeps the `Chunk` contract field round-tripping exactly; the tsvector stores stemmed lexemes and cannot reproduce it. |
| Added `run_document_stagings` | Carries the per-run staging events the fold in §3.1 needs. |

### 3.4 Known limitation: lexical ranking is `ts_rank_cd`, not BM25

The checklist asked for BM25. `MemoryIndex` computes Okapi BM25 with IDF derived from the
**ACL-filtered candidate set**. Reproducing that in PostgreSQL needs a document-frequency pass
over the readable subset on every query — a full pass over exactly the rows the GIN index
exists to avoid touching. `ts_rank_cd` is used instead.

Reciprocal Rank Fusion consumes *ranks*, not scores, so the absolute scale of the lexical
ranker never reaches the fused result; but the ordering *within* the lexical branch does
differ from the in-memory reference, and that divergence is not yet measured. Carried as
[`009-section-bm25-lexical-ranking.md`](009-section-bm25-lexical-ranking.md), which starts by
measuring whether the gap justifies the machinery.

A second, smaller deviation: both branches are capped at a candidate pool of
`max(top_k * 5, 25)`, where `MemoryIndex` scores the whole readable corpus lexically. RRF
weights rank 125 at under two percent of rank 1, so a candidate outside the pool could not
have reached the result set anyway.

### 3.5 Verification

**Offline suite — run and passing:**

```bash
uv run ruff check src tests evals && uv run ruff format --check src tests evals && uv run pytest -q
```

```
All checks passed!
39 files already formatted
93 passed, 13 skipped in 5.30s
```

```
release_gate_pass_rate  value 1.0  threshold 1.0     (evals/run_eval.py)
```

`tests/personal_rag/test_postgres_index.py` (25 tests, passing) covers what a live server
cannot: the ACL filter is present in all three retrieval branches and always parameterized,
rows decode back into the same contract objects the pipeline staged, chunks are deleted before
a staging row moves, an embedding of the wrong width is rejected before any write, activation
locks the pointer before moving it, and `schema.sql` still matches the migrations.

**Integration suite — written, not yet executed.** The 13 tests are the 13 skips above.

`tests/personal_rag/test_postgres_integration.py` exercises DDL acceptance, HNSW/GIN index
creation, candidate isolation, tombstones, rollback, ACL filtering, and agreement with
`MemoryIndex` on the same corpus. It skips unless `PERSONAL_RAG_TEST_DSN` is set, because it
truncates every table. It has **not been run against a live server yet** — the local Docker
engine did not start — so the DDL and the retrieval SQL are reviewed but not executed. Treat
that as the outstanding risk on this section.

```bash
docker run --rm -d -p 5433:5432 -e POSTGRES_PASSWORD=rag --name rag-pg pgvector/pgvector:pg16
```

```bash
PERSONAL_RAG_TEST_DSN=postgresql://postgres:rag@localhost:5433/postgres uv run --extra postgres pytest tests/personal_rag/test_postgres_integration.py -v
```

CI installs the `postgres` extra (`uv sync --all-extras`) but starts no server, so the suite
skips there too. Wiring a service container into the CI job is
[`010-section-integration-test-services.md`](010-section-integration-test-services.md), and it
should land before this section is relied on in deployment.

### 3.6 Dependency

`psycopg` is an **optional** extra (`uv sync --extra postgres`), imported lazily by
`db.connection.psycopg_factory`. Phase 1 and the offline evaluation gate run entirely without
a database, and `PostgresIndex` itself takes a connection factory rather than a driver, so the
SQL is unit testable against a recording double.

## 4. Next / Follow-Up Sections
- Upstream dependency for [`004-section-fastapi-query-service.md`](004-section-fastapi-query-service.md), which can now be pointed at `PostgresIndex` without changing a line of the query service.
- New: [`009-section-bm25-lexical-ranking.md`](009-section-bm25-lexical-ranking.md) — true BM25 over maintained corpus statistics.
- New: [`010-section-integration-test-services.md`](010-section-integration-test-services.md) — run the PostgreSQL integration suite in CI.
