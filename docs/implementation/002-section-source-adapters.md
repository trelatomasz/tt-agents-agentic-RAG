# Section 002: Source Adapters & Normalization Pipeline

- **Module**: Source Adapters & Processing Pipeline
- **Status**: `IN_PROGRESS`
- **Assigned Subagent**: `research` / Ingestion Subagent
- **Dependencies**: [`001-section-contracts-and-models.md`](001-section-contracts-and-models.md)
- **Target Files**:
  - [`src/personal_rag/sources/base.py`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/src/personal_rag/sources/base.py)
  - [`src/personal_rag/sources/filesystem.py`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/src/personal_rag/sources/filesystem.py)
  - `src/personal_rag/sources/web.py` (Pending)
  - `src/personal_rag/sources/git_tree.py` (Pending)
  - [`src/personal_rag/pipeline/`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/src/personal_rag/pipeline/)

---

## 1. Objectives & Scope
Implement concrete source connectors producing standardized `RawDocument` records, and structure-aware normalization/chunking pipelines (Markdown, PDF/EPUB, Git, and Web HTML).

## 2. Checklist & Deliverables
- [x] [DONE] Abstract `SourceAdapter` protocol (`discover`, `fetch`, `fingerprint`).
- [x] [DONE] Implemented `FilesystemAdapter` for local text and Markdown documents with path-traversal security guards.
- [ ] Implement PyMuPDF and `ebooklib` engines for PDF/EPUB books with page and chapter locators.
- [ ] Implement `WebAdapter` with SSRF IP filtering, DNS pinning, `/robots.txt` compliance, and HTML extraction.
- [ ] Implement `GitTreeAdapter` for `tt-root/info` with commit SHA tracking and relative path provenance.
- [ ] Implement structure-aware heading chunker (target 400-800 tokens, 10-15% overlap, no cross-heading merging).

## 3. Changes Implemented & Verification
- Created `SourceAdapter` protocol in `src/personal_rag/sources/base.py`.
- Created `FilesystemAdapter` in `src/personal_rag/sources/filesystem.py`.
- Pipeline stages (`normalize.py`, `chunk.py`, `enrich.py`, `embed.py`, `publish.py`) created.
- **Verification**: `pytest tests/personal_rag/test_pipeline.py` passes.

## 4. Next / Follow-Up Sections
- Feeds output to [`003-section-database-and-vector-store.md`](003-section-database-and-vector-store.md).
