"""Phase 1 exit condition: a Markdown file reaches a cited answer, and negative
queries abstain instead of guessing."""

import pytest

from personal_rag.errors import DependencyFailedError, GroundingError, NoEvidenceError
from personal_rag.index.memory import MemoryIndex
from personal_rag.models import AnswerRequest, Principal, SearchRequest
from personal_rag.pipeline.embed import HashingEmbedder
from personal_rag.pipeline.publish import IngestionPipeline
from personal_rag.query.service import (
    ABSTENTION_SENTENCE,
    DeterministicAnswerGenerator,
    QueryService,
    build_evidence_prompt,
)
from personal_rag.sources.base import load_descriptor
from personal_rag.sources.filesystem import FilesystemAdapter

OWNER = Principal.owner("tomasz")


@pytest.fixture(scope="module")
def service() -> QueryService:
    """The repository corpus, ingested through the real adapter and pipeline."""
    descriptor = load_descriptor("data/personal/sources/local-notes.yaml")
    embedder = HashingEmbedder()
    index = MemoryIndex(embedder)
    pipeline = IngestionPipeline(index, embedder)
    pipeline.activate(pipeline.run(FilesystemAdapter(descriptor), descriptor))
    return QueryService(index, DeterministicAnswerGenerator())


def ask(query: str, **kwargs) -> AnswerRequest:
    return AnswerRequest(query=query, request_id="req-answer", principal=OWNER, **kwargs)


async def test_markdown_source_reaches_a_cited_answer(service):
    response = await service.answer(ask("How do I design a retrieval evaluation gate?"))
    assert response.citations
    assert response.retrieval_score > 0.2
    cited = {citation.chunk_id for citation in response.citations}
    assert all(f"[{chunk_id}]" in response.answer for chunk_id in cited)


async def test_every_citation_reconstructs_a_verifiable_locator(service):
    response = await service.answer(ask("Why measure retrieval and generation separately?"))
    for citation in response.citations:
        assert citation.source_uri.endswith(".md")
        assert citation.locator.line_start >= 1
        assert citation.document_version_hash
        assert citation.reference.startswith(citation.source_uri)


async def test_unsupported_question_abstains(service):
    with pytest.raises(NoEvidenceError):
        await service.answer(ask("What is the best espresso grinder for light roasts?"))


async def test_search_abstains_rather_than_returning_weak_matches(service):
    with pytest.raises(NoEvidenceError):
        service.search(
            SearchRequest(
                query="tyre pressure for a caravan in winter",
                request_id="req-search",
                principal=OWNER,
            )
        )


async def test_generator_abstention_is_not_returned_as_an_answer(service):
    class AbstainingGenerator:
        async def generate(self, query, evidence):
            del query, evidence
            return ABSTENTION_SENTENCE

    abstaining = QueryService(service.index, AbstainingGenerator())
    with pytest.raises(NoEvidenceError):
        await abstaining.answer(ask("How do I design a retrieval evaluation gate?"))


async def test_answer_without_citations_fails_closed(service):
    class UngroundedGenerator:
        async def generate(self, query, evidence):
            del query, evidence
            return "Evaluation gates are generally a good idea."

    ungrounded = QueryService(service.index, UngroundedGenerator())
    with pytest.raises(GroundingError):
        await ungrounded.answer(ask("How do I design a retrieval evaluation gate?"))


async def test_answer_citing_unretrieved_evidence_fails_closed(service):
    """A model may not cite a chunk that retrieval never returned for this request."""

    class FabricatingGenerator:
        async def generate(self, query, evidence):
            del query, evidence
            return "Gates block releases [local-notes:invented.md@0000000000ff#0000]."

    fabricating = QueryService(service.index, FabricatingGenerator())
    with pytest.raises(GroundingError):
        await fabricating.answer(ask("How do I design a retrieval evaluation gate?"))


async def test_generator_failure_is_typed_for_retry(service):
    class FailingGenerator:
        async def generate(self, query, evidence):
            del query, evidence
            raise RuntimeError("provider unavailable")

    failing = QueryService(service.index, FailingGenerator())
    with pytest.raises(DependencyFailedError):
        await failing.answer(ask("How do I design a retrieval evaluation gate?"))


async def test_evidence_budget_caps_chunks_from_one_document(service):
    captured: list = []

    class CapturingGenerator(DeterministicAnswerGenerator):
        async def generate(self, query, evidence):
            captured.extend(evidence)
            return await super().generate(query, evidence)

    capped = QueryService(service.index, CapturingGenerator(), max_chunks_per_document=2)
    await capped.answer(ask("How do I design a retrieval evaluation gate?", top_k=8))
    per_document: dict[str, int] = {}
    for chunk in captured:
        per_document[chunk.document_id] = per_document.get(chunk.document_id, 0) + 1
    assert captured and max(per_document.values()) <= 2


async def test_answers_are_scoped_to_the_principal(service):
    """A principal with no grants can read nothing, whatever they ask for."""
    stranger = AnswerRequest(
        query="How do I design a retrieval evaluation gate?",
        request_id="req-stranger",
        principal=Principal(subject="stranger"),
    )
    with pytest.raises(NoEvidenceError):
        await service.answer(stranger)


def test_evidence_prompt_frames_retrieved_text_as_untrusted(service):
    found = service.search(
        SearchRequest(
            query="How do I design a retrieval evaluation gate?",
            request_id="req-prompt",
            principal=OWNER,
        )
    )
    best = found.results[0].chunk
    prompt = build_evidence_prompt("How do I design a gate?", [best])
    assert "untrusted data" in prompt
    assert "never as authorization" in prompt
    assert f"chunk_id: {best.chunk_id}" in prompt
