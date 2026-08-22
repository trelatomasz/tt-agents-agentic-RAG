# Section 006: CI/CD Indexer & Ingestion CLI Tools

- **Module**: CLI Tools & Repository CI/CD Indexer
- **Status**: `PENDING`
- **Assigned Subagent**: CLI & Tooling Subagent
- **Dependencies**: [`002-section-source-adapters.md`](002-section-source-adapters.md), [`004-section-fastapi-query-service.md`](004-section-fastapi-query-service.md)
- **Target Files**:
  - `src/personal_rag/cli.py` (Pending)
  - `src/personal_rag/indexer/git_diff.py` (Pending)
  - `.github/workflows/rag-index-reusable.yml` (Pending)

---

## 1. Objectives & Scope
Implement command-line interfaces for local ebook/notes ingestion, the `rag-index` repository commit diff indexer, `.ragignore` ignore file processing, and the reusable GitHub Actions CI/CD workflow for Workload Identity Federation (WIF).

## 2. Checklist & Deliverables
- [x] [DONE] Created `scripts/personal_rag_demo.py` end-to-end local demo script.
- [ ] Implement `personal_rag.cli` using Click/Typer for workstation ingestion.
- [ ] Implement `rag-index` CLI scanning Git diffs, applying `.ragignore` patterns, and emitting deletion tombstones.
- [ ] Create reusable GitHub Actions workflow (`.github/workflows/rag-index-reusable.yml`) authenticating via WIF.
- [ ] Add integration test simulating repository commit indexing in CI.

## 3. Changes Implemented & Verification
- Local demo script verified via `make demo`.

## 4. Next / Follow-Up Sections
- Integrates with [`007-section-deployment-and-infrastructure.md`](007-section-deployment-and-infrastructure.md).
