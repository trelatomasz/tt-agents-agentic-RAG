# RAG problem evidence

This pilot treats correctness as the release constraint. Each row names an important
Retrieval-Augmented Generation (RAG) failure mode, the control implemented here and the
executable evidence that proves the control for the current structured parts catalog.

| Problem | Control | Evidence | Current limitation |
|---|---|---|---|
| Partial lexical matches return the wrong part | Fitment-aware retrieval requires overlap with the requested vehicle and ranks product plus fitment terms | `src/gpc_rag/catalog.py`; `tests/test_service.py::test_wrong_vehicle_for_explicit_part_abstains`; `evals/dataset.jsonl` `wrong-vehicle` | This is deterministic lexical retrieval, not semantic or hybrid retrieval |
| An unsupported model year looks plausible | Requested years must fall inside a catalog fitment range | `tests/test_service.py::test_unsupported_model_year_abstains`; evaluation case `unsupported-year` | Range parsing currently expects four-digit years in the catalog text |
| Weak one-token matches produce confident answers | Retrieval has a configurable minimum score and exposes normalized retrieval confidence | `src/gpc_rag/config.py`; `tests/test_service.py::test_low_confidence_product_match_abstains` | The threshold needs calibration against 30–50 representative queries |
| The model answers without evidence | The answer must contain at least one citation for an allowed retrieved part; unknown citations fail closed | `src/gpc_rag/service.py`; `tests/test_service.py::test_generator_without_allowed_citation_fails_closed` | Citation presence does not yet prove every claim is entailed by the cited text |
| Stale or withdrawn catalog data is used | Catalog age is checked before retrieval; source and catalog version travel with every citation | `tests/test_service.py::test_stale_catalog_fails_closed`; `src/gpc_rag/catalog.py` | Ingestion quarantine and the immutable current-pointer update are deployment responsibilities |
| Provider timeout or failure becomes an untyped 500 | Generation timeout and dependency failures have explicit retry/fallback contracts | `src/gpc_rag/service.py`; `src/gpc_rag/main.py`; `src/gpc_rag/models.py` | Provider-specific retry budgets and circuit breaking are not implemented yet |
| Streaming hides failure semantics | Server-Sent Events emit the same typed failure codes as the HTTP endpoint | `src/gpc_rag/main.py`; `docs/QUESTION_EVIDENCE.md` Q19 | Stream backpressure and reconnect/resume semantics still need load testing |
| Prompt injection in retrieved data changes authority | Vertex prompt treats evidence as untrusted data and the pilot exposes no tools or authorization path | `src/gpc_rag/generator.py`; `docs/threat-model.md` | Add a malicious-catalog fixture and a model-backed adversarial evaluation before launch |
| A regression passes because the test set is too small | The evaluation gate covers known answers, unknown vehicle, wrong vehicle and unsupported year | `evals/dataset.jsonl`; `evals/run_eval.py`; `make eval` | Expand to 30–50 real, slice-labeled queries before a production decision |
| Latency and retrieval behavior cannot be diagnosed | Structured completion logs include request ID, catalog version, retrieval count, score and elapsed time | `src/gpc_rag/service.py`; `docs/slo-runbook.md` | Metrics export, trace correlation and cost/token telemetry remain to be connected |

## Verification command

```powershell
& '.venv\Scripts\python.exe' -m pytest -q
$env:PYTHONPATH = 'src'
& '.venv\Scripts\python.exe' evals/run_eval.py
& '.venv\Scripts\python.exe' -m ruff check src tests evals
```

The current local evidence is eleven passing tests and a five-case evaluation gate at
100%. It is a pilot result, not production-quality recall or groundedness evidence.
