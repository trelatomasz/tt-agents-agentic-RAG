# Interview question evidence map

| Q | Evidence | Verification |
|---:|---|---|
| 1 | `docs/knowledge-evidence/portfolio-evidence.md` § First five days | Review baseline, scope and gate |
| 2 | Git history and deployed vertical slice | Commit, deployment and evaluation result |
| 3 | `docs/knowledge-evidence/portfolio-evidence.md` § Agent-driven development | Review adoption controls |
| 4 | `docs/architecture.md`, `deployment/gcp/` | `tofu validate` and resource graph |
| 5 | `docs/slo-runbook.md` | Recalculate capacity and inspect fallback |
| 6 | `docs/overview.md` § Autonomy boundary, `docs/architecture.md` | Review removal trigger |
| 7 | `evals/` | `make eval` |
| 8 | `Makefile`, `Dockerfile`, `docs/release.md` | `make lint test eval image plan` |
| 9 | `src/gpc_rag/service.py`, `src/gpc_rag/models.py` | `make test` |
| 10 | `docs/knowledge-evidence/portfolio-evidence.md` § Launch recommendation | Review decision date and thresholds |
| 11 | `docs/knowledge-evidence/portfolio-evidence.md` § GPC context | Review hypotheses and questions |
| 12 | `docs/knowledge-evidence/portfolio-evidence.md` § Temporary priority | Review decision rights |
| 13 | `docs/knowledge-evidence/portfolio-evidence.md` § Failed RAG story | Replace measurement TODOs |
| 14 | `docs/threat-model.md`, `deployment/gcp/iam.tf` | Inspect trust boundaries and plan |
| 15 | `docs/slo-runbook.md` | Recalculate QPS and concurrency |
| 16 | `src/gpc_rag/catalog.py`, bucket versioning, stale test | Run test and inspect versions |
| 17 | `docs/slo-runbook.md` | Run model-regression drill |
| 18 | Typed boundary and tests | Run failure-path tests |
| 19 | `/v1/answers:stream`, `src/gpc_rag/models.py` | Inspect events and cancellation |
| 20 | `docs/overview.md` § Decision experiment, `docs/architecture.md` | Review evidence and owner |
| RAG reliability | `docs/knowledge-evidence/rag-problem-evidence.md` | Run the tests and evaluation; inspect each control and stated limitation |
