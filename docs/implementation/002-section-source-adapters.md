# Section 002: Source Adapters & Normalization Pipeline

- **Module**: Source Adapters & Processing Pipeline
- **Status**: `DONE`
- **Assigned Subagent**: `research` / Ingestion Subagent
- **Dependencies**: [`001-section-contracts-and-models.md`](001-section-contracts-and-models.md)
- **Target Files**:
  - [`src/personal_rag/sources/base.py`](../../src/personal_rag/sources/base.py)
  - [`src/personal_rag/sources/filesystem.py`](../../src/personal_rag/sources/filesystem.py)
  - `src/personal_rag/sources/web.py` (Pending)
  - `src/personal_rag/sources/git_tree.py` (Pending)
  - [`src/personal_rag/pipeline/`](../../src/personal_rag/pipeline/)

---

## 1. Objectives & Scope
Implement concrete source connectors producing standardized `RawDocument` records, and structure-aware normalization/chunking pipelines (Markdown, PDF/EPUB, Git, and Web HTML).

## 2. Checklist & Deliverables
- [x] [DONE] Abstract `SourceAdapter` protocol (`discover`, `fetch`, `fingerprint`).
- [x] [DONE] Implemented `FilesystemAdapter` for local text and Markdown documents with path-traversal security guards.
- [x] [DONE] Implement PyMuPDF and `ebooklib` engines for PDF/EPUB books with page and chapter locators.
- [x] [DONE] Implement `WebAdapter` with SSRF IP filtering, DNS pinning, `/robots.txt` compliance, and HTML extraction.
- [x] [DONE] Implement `GitTreeAdapter` for `tt-root/info` with commit SHA tracking and relative path provenance.
- [x] [DONE] Implement structure-aware heading chunker (target 400-800 tokens, 10-15% overlap, no cross-heading merging).

## 3. Changes Implemented & Verification
- Created `SourceAdapter` protocol in `src/personal_rag/sources/base.py`.
- Created `FilesystemAdapter` in `src/personal_rag/sources/filesystem.py`.
- Pipeline stages (`normalize.py`, `chunk.py`, `enrich.py`, `embed.py`, `publish.py`) created.
- Added PDF/EPUB parsing to `FilesystemAdapter`, including page/chapter metadata and parser-failure quarantine.
- Added HTTPS-only `WebAdapter` with destination validation before every request, redirect checks, robots policy, size/content-type limits, canonical metadata, and visible HTML extraction.
- Added read-only `GitTreeAdapter` with tracked-file filtering, commit provenance, include/exclude boundaries, and relative path locators.
- Added commit propagation to chunk locators for Git-backed citations.
- **Verification**: `pytest tests/personal_rag/test_pipeline.py tests/personal_rag/test_source_adapters.py` and `ruff check src tests` pass.

## 4. Next / Follow-Up Sections
- Feeds output to [`003-section-database-and-vector-store.md`](003-section-database-and-vector-store.md).
