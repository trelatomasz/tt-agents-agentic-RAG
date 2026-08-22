# Section 001: Core Contracts & Data Models

- **Module**: Data Models & Protocols
- **Status**: `DONE`
- **Assigned Subagent**: `self`
- **Dependencies**: None
- **Target Files**:
  - [`src/personal_rag/models.py`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/src/personal_rag/models.py)
  - [`src/personal_rag/errors.py`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/src/personal_rag/errors.py)
  - [`tests/personal_rag/test_contracts.py`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/tests/personal_rag/test_contracts.py)

---

## 1. Objectives & Scope
Define canonical data structures and error hierarchies for heterogeneous knowledge sources, document versions, structure-aware chunks, citations, and ingestion manifests, completely decoupled from underlying database engines.

## 2. Checklist & Deliverables
- [x] [DONE] Define `RawDocument`, `NormalizedDocument`, `DocumentVersion`, `Chunk`, and `Citation` Pydantic models.
- [x] [DONE] Define structured locator schemas (`heading_path`, `page`, `chapter`, `line_range`, `commit_sha`).
- [x] [DONE] Define typed domain error classes in `errors.py` (`SourceError`, `ChunkingError`, `EmbeddingError`, `AbstentionError`).
- [x] [DONE] Verify serialization/deserialization with comprehensive contract unit tests.

## 3. Changes Implemented & Verification
- Implemented `DocumentVersion` and `Chunk` in `src/personal_rag/models.py`.
- Tested in `tests/personal_rag/test_contracts.py`.
- **Verification**: `pytest tests/personal_rag/test_contracts.py` passes 100%.

## 4. Next / Follow-Up Sections
- Upstream dependency for [`002-section-source-adapters.md`](002-section-source-adapters.md) and [`003-section-database-and-vector-store.md`](003-section-database-and-vector-store.md).
