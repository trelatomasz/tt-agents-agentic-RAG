"""Phase 1 exit evidence: one Markdown source from disk to a cited answer.

Runs the whole local baseline with no GCP resources and no model provider — normalize,
chunk, index, search, answer — and asserts the two behaviours the phase is judged on: a
supported question is answered with verifiable citations, and an unsupported one abstains.
Exits non-zero if either fails, so `make demo` is a check rather than a printout.

    PYTHONPATH=src python scripts/personal_rag_demo.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from personal_rag.errors import NoEvidenceError
from personal_rag.index.memory import MemoryIndex
from personal_rag.models import AnswerRequest, Principal
from personal_rag.pipeline.embed import HashingEmbedder
from personal_rag.pipeline.publish import IngestionPipeline
from personal_rag.query.service import DeterministicAnswerGenerator, QueryService
from personal_rag.sources.base import load_descriptor
from personal_rag.sources.filesystem import FilesystemAdapter

DESCRIPTOR_PATH = "data/personal/sources/local-notes.yaml"
SUPPORTED_QUERY = "How do I design a retrieval evaluation gate?"
UNSUPPORTED_QUERY = "What is the best espresso grinder for light roasts?"


async def main() -> int:
    descriptor = load_descriptor(DESCRIPTOR_PATH)
    embedder = HashingEmbedder()
    index = MemoryIndex(embedder)
    pipeline = IngestionPipeline(index, embedder)

    run = pipeline.run(FilesystemAdapter(descriptor), descriptor)
    pipeline.activate(run)
    print(
        json.dumps(
            {
                "stage": "ingest",
                "run_id": run.run_id,
                "status": run.status,
                "index_run_id": run.index_run_id,
                "chunker_version": run.chunker_version,
                "embedding_model": run.embedding_model,
                **run.counters.model_dump(),
            }
        )
    )

    service = QueryService(index, DeterministicAnswerGenerator())
    principal = Principal.owner(descriptor.owner)
    failures: list[str] = []

    try:
        answer = await service.answer(
            AnswerRequest(query=SUPPORTED_QUERY, request_id="demo-1", principal=principal)
        )
        print(
            json.dumps(
                {
                    "stage": "answer",
                    "query": SUPPORTED_QUERY,
                    "retrieval_score": round(answer.retrieval_score, 3),
                    "citations": [
                        {"chunk_id": citation.chunk_id, "reference": citation.reference}
                        for citation in answer.citations
                    ],
                },
                indent=2,
            )
        )
        if not answer.citations:
            failures.append("supported query returned no citations")
    except NoEvidenceError as exc:
        failures.append(f"supported query abstained: {exc}")

    try:
        await service.answer(
            AnswerRequest(query=UNSUPPORTED_QUERY, request_id="demo-2", principal=principal)
        )
        failures.append("unsupported query produced an answer instead of abstaining")
    except NoEvidenceError:
        print(json.dumps({"stage": "abstain", "query": UNSUPPORTED_QUERY, "abstained": True}))

    print(
        json.dumps(
            {
                "metric": "phase_1_local_baseline",
                "passed": not failures,
                "failures": failures,
            }
        )
    )
    return 1 if failures else 0


raise SystemExit(asyncio.run(main()))
