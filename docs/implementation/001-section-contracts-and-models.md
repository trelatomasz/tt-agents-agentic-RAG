# Section 001: Core Contracts & Data Models

- **Module**: Data Models & Protocols
- **Status**: `DONE`
- **Assigned Subagent**: `self`
- **Dependencies**: None
- **Target Files**:
  - `src/personal_rag/models.py`
  - `src/personal_rag/errors.py`
  - `tests/personal_rag/test_contracts.py`

---

## 1. Objectives & Scope
Define canonical data structures and error hierarchies for heterogeneous knowledge sources, document versions, structure-aware chunks, citations, and ingestion manifests, completely decoupled from underlying database engines.

## 2. Checklist & Deliverables
- [x] [DONE] Define `RawDocument`, `NormalizedDocument`, `DocumentVersion`, `Chunk`, and `Citation` Pydantic models.
- [x] [DONE] Define structured locator schemas (`heading_path`, `page`, `chapter`, `line_range`, `commit_sha`).
- [x] [DONE] Define typed domain error classes in `errors.py` (`SourceError`, `ChunkingError`, `EmbeddingError`, `AbstentionError`).
- [x] [DONE] Verify serialization/deserialization with comprehensive contract unit tests.

## 3. Changes Implemented & Verification
- Implemented `RawDocument`, `NormalizedDocument`, `DocumentVersion`, `Chunk`, `Citation`, `SourceDescriptor`, `Principal`, `Locator`, and `IngestionRun` Pydantic models in `src/personal_rag/models.py`.
- Implemented typed domain failure hierarchy in `src/personal_rag/errors.py`: `SourceError`, `ChunkingError`, `EmbeddingError`, `AbstentionError`, `NoEvidenceError`, `GroundingError`, `DependencyFailedError`, `RightsViolationError`, `AccessDeniedError`, and `IngestionError`.
- Added comprehensive unit tests in `tests/personal_rag/test_contracts.py` validating immutability, serialization/deserialization, locator references, ACL checks, and domain error sub-classing.
- **Verification**: Executed pytest (`70 passed`) and ruff checks (`All checks passed!`).

## 4. Next / Follow-Up Sections
- Upstream dependency for [`002-section-source-adapters.md`](002-section-source-adapters.md) and [`003-section-database-and-vector-store.md`](003-section-database-and-vector-store.md).
