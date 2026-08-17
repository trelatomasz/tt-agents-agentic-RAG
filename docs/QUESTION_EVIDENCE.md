# Interview question evidence map

| Q | Evidence | Verification |
|---:|---|---|
| 1 | `docs/portfolio-evidence.md` § First five days | Review baseline, scope and gate |
| 2 | Git history and deployed vertical slice | Commit, deployment and evaluation result |
| 3 | `docs/portfolio-evidence.md` § Agent-driven development | Review adoption controls |
| 4 | `docs/architecture.md`, `deployment/gcp/` | `tofu validate` and resource graph |
| 5 | `docs/slo-runbook.md` | Recalculate capacity and inspect fallback |
| 6 | `docs/architecture.md` § Autonomy boundary | Review removal trigger |
| 7 | `evals/` | `make eval` |
| 8 | `Makefile`, `Dockerfile`, `docs/release.md` | `make lint test eval image plan` |
| 9 | `service.py`, `models.py` | `make test` |
| 10 | `docs/portfolio-evidence.md` § Launch recommendation | Review decision date and thresholds |
| 11 | `docs/portfolio-evidence.md` § GPC context | Review hypotheses and questions |
| 12 | `docs/portfolio-evidence.md` § Temporary priority | Review decision rights |
| 13 | `docs/portfolio-evidence.md` § Failed RAG story | Replace measurement TODOs |
| 14 | `docs/threat-model.md`, Terraform IAM | Inspect trust boundaries and plan |
| 15 | `docs/slo-runbook.md` | Recalculate QPS and concurrency |
| 16 | `catalog.py`, bucket versioning, stale test | Run test and inspect versions |
| 17 | `docs/slo-runbook.md` | Run model-regression drill |
| 18 | Typed boundary and tests | Run failure-path tests |
| 19 | `/v1/answers:stream`, `models.py` | Inspect events and cancellation |
| 20 | `docs/architecture.md` § Decision experiment | Review evidence and owner |
| RAG reliability | `docs/rag-problem-evidence.md` | Run the tests and evaluation; inspect each control and stated limitation |
