# Section 003: Database & Vector Store Subsystem

- **Module**: Cloud SQL PostgreSQL Datastore (`pgvector` + FTS)
- **Status**: `PENDING`
- **Assigned Subagent**: Database & Index Subagent
- **Dependencies**: [`001-section-contracts-and-models.md`](001-section-contracts-and-models.md), [`002-section-source-adapters.md`](002-section-source-adapters.md)
- **Target Files**:
  - `src/personal_rag/index/postgres.py` (Pending)
  - `src/personal_rag/db/schema.sql` (Pending)
  - `src/personal_rag/db/migrations/` (Pending)

---

## 1. Objectives & Scope
Implement the transactional database and hybrid search store on Cloud SQL PostgreSQL 16 using `pgvector` for 768-dimensional embeddings, native `tsvector` for lexical FTS, SQL-level ACL filtering, and candidate index activation pointers.

## 2. Checklist & Deliverables
- [x] [DONE] Implemented reference in-memory vector & FTS index (`MemoryIndex`) with RRF fusion for local offline development.
- [ ] Create PostgreSQL DDL schema (`SOURCES`, `DOCUMENT_VERSIONS`, `CHUNKS`, `INGESTION_RUNS`, `ACTIVE_INDEX_POINTER`).
- [ ] Implement `pgvector` HNSW cosine distance index (`vector(768)`).
- [ ] Implement PostgreSQL full-text search `tsvector` with `pg_trgm` and BM25 ranking.
- [ ] Implement parameterized SQL pre-filtering (`WHERE acl_labels && :user_labels`) before distance calculations.
- [ ] Implement `PostgresIndex` matching `BaseIndex` protocol.
- [ ] Implement atomic candidate index pointer swap and $<5$s rollback function.

## 3. Changes Implemented & Verification
- In-memory reference implementation verified in `src/personal_rag/index/memory.py` and `tests/personal_rag/test_memory_index.py`.

## 4. Next / Follow-Up Sections
- Upstream dependency for [`004-section-fastapi-query-service.md`](004-section-fastapi-query-service.md).
