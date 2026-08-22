# Section 008: Evaluation Spectrum & Observability Subsystem

- **Module**: Evaluation Harness, OpenTelemetry & Telemetry
- **Status**: `PARTIAL`
- **Assigned Subagent**: Quality & Observability Subagent
- **Dependencies**: [`004-section-fastapi-query-service.md`](004-section-fastapi-query-service.md), [`007-section-deployment-and-infrastructure.md`](007-section-deployment-and-infrastructure.md)
- **Target Files**:
  - [`evals/run_eval.py`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/evals/run_eval.py)
  - [`evals/dataset.jsonl`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/evals/dataset.jsonl)
  - `src/personal_rag/telemetry/otel.py` (Pending)
  - `src/personal_rag/evals/golden_set.py` (Pending)

---

## 1. Objectives & Scope
Implement the comprehensive evaluation spectrum (RAG Triad, Recall@K, Faithfulness, Citation Precision, Negative Abstention), OpenTelemetry span instrumentation with OpenInference conventions, Cloud Logging structured logs, and Population Stability Index (PSI) drift detection.

## 2. Checklist & Deliverables
- [x] [DONE] Five-case golden evaluation gate in `evals/run_eval.py` enforcing 100% pass rate.
- [ ] Expand golden evaluation benchmark dataset to 30–50 domain queries covering all source types.
- [ ] Implement OpenTelemetry SDK exporter (`otel.py`) tracing FastAPI requests, hybrid search queries, and Vertex AI completions.
- [ ] Implement synthetic testset generator (Evol-Instruct / Ragas multi-hop).
- [ ] Implement Population Stability Index (PSI) drift detection for query token distributions and retrieval score decay.
- [ ] Create `rag-debug` root-cause triage CLI tool.

## 3. Changes Implemented & Verification
- Evaluation suite passing via `python evals/run_eval.py`.

## 4. Next / Follow-Up Sections
- Continuous release gate integrated into CI/CD workflows.
