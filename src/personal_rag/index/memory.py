"""In-process index for local development and tests (register entry P-03).

This is the smallest thing that honors the index contract: candidate runs, an atomic active
pointer, rollback, access filtering before ranking, and sparse plus dense retrieval fused
with Reciprocal Rank Fusion. Building it before Cloud SQL means every later stage is
testable without GCP, and the Phase 3 PostgreSQL implementation has an executable
specification to match rather than a prose one.

Term frequencies are derived here rather than read from `Chunk.lexical_terms`, mirroring
how PostgreSQL builds its own `tsvector` from the stored text.
"""

import math
from collections import Counter
from dataclasses import dataclass, field

from ..errors import IngestionError
from ..models import Chunk, DocumentVersion, SearchRequest, SearchResult
from ..pipeline.chunk import contextual_text
from ..pipeline.embed import Embedder, cosine_similarity
from ..pipeline.enrich import analyze

RRF_K = 60
BM25_K1 = 1.2
BM25_B = 0.75


@dataclass(frozen=True)
class _Posting:
    chunk: Chunk
    terms: Counter[str]
    length: int


@dataclass(frozen=True)
class _Snapshot:
    """An immutable view of the corpus. Activation swaps one of these for another."""

    run_id: str | None = None
    versions: dict[str, DocumentVersion] = field(default_factory=dict)
    postings: dict[str, list[_Posting]] = field(default_factory=dict)

    @property
    def all_postings(self) -> list[_Posting]:
        return [posting for postings in self.postings.values() for posting in postings]


@dataclass
class _CandidateRun:
    run_id: str
    source_id: str
    versions: dict[str, DocumentVersion] = field(default_factory=dict)
    postings: dict[str, list[_Posting]] = field(default_factory=dict)
    tombstones: set[str] = field(default_factory=set)


class MemoryIndex:
    """A `DocumentIndex` that keeps everything in memory."""

    def __init__(self, embedder: Embedder, *, dense_floor: float = 0.15):
        """`dense_floor` is a property of the embedding model, not of this index.

        It is calibrated against `HashingEmbedder`, whose unrelated-text similarity sits
        near zero. Trained embedding models have a much higher baseline, so Phase 3 must
        re-derive this threshold from the corpus rather than inherit 0.15.
        """
        self._embedder = embedder
        self._dense_floor = dense_floor
        self._active = _Snapshot()
        self._history: list[_Snapshot] = []
        self._candidates: dict[str, _CandidateRun] = {}

    # -- write path ----------------------------------------------------------------

    def open_run(self, source_id: str) -> str:
        run_id = f"index-{source_id}-{len(self._candidates) + len(self._history) + 1:04d}"
        self._candidates[run_id] = _CandidateRun(run_id=run_id, source_id=source_id)
        return run_id

    def stage_document(
        self, index_run_id: str, version: DocumentVersion, chunks: list[Chunk]
    ) -> None:
        run = self._candidate(index_run_id)
        stamped = [chunk.model_copy(update={"index_run_id": index_run_id}) for chunk in chunks]
        run.versions[version.document_id] = version
        run.postings[version.document_id] = [self._posting(chunk) for chunk in stamped]
        run.tombstones.discard(version.document_id)

    def stage_tombstone(self, index_run_id: str, document_id: str) -> None:
        run = self._candidate(index_run_id)
        run.tombstones.add(document_id)
        run.versions.pop(document_id, None)
        run.postings.pop(document_id, None)

    def activate(self, index_run_id: str) -> None:
        """Swap the active pointer in one step; a reader sees the old or the new corpus."""
        run = self._candidate(index_run_id)
        versions = dict(self._active.versions)
        postings = dict(self._active.postings)
        for document_id in run.tombstones:
            versions.pop(document_id, None)
            postings.pop(document_id, None)
        versions.update(run.versions)
        postings.update(run.postings)

        self._history.append(self._active)
        self._active = _Snapshot(run_id=index_run_id, versions=versions, postings=postings)
        del self._candidates[index_run_id]

    def discard(self, index_run_id: str) -> None:
        self._candidates.pop(index_run_id, None)

    def rollback(self) -> str | None:
        """Restore the previous active snapshot (register entry P-23)."""
        if not self._history:
            raise IngestionError("no previous index state to roll back to")
        self._active = self._history.pop()
        return self._active.run_id

    # -- read path -----------------------------------------------------------------

    def active_run_id(self) -> str | None:
        return self._active.run_id

    def active_version(self, document_id: str) -> DocumentVersion | None:
        return self._active.versions.get(document_id)

    def active_documents(self, source_id: str) -> dict[str, DocumentVersion]:
        return {
            document_id: version
            for document_id, version in self._active.versions.items()
            if version.source_id == source_id
        }

    def document_count(self) -> int:
        return len(self._active.versions)

    def chunk_count(self) -> int:
        return sum(len(postings) for postings in self._active.postings.values())

    def search(self, request: SearchRequest) -> list[SearchResult]:
        """Filter by access first, then rank. An unreadable chunk never reaches scoring."""
        candidates = [
            posting
            for posting in self._active.all_postings
            if request.principal.may_read(posting.chunk.acl_labels)
            and (not request.source_ids or posting.chunk.source_id in request.source_ids)
        ]
        if not candidates:
            return []

        query_terms = analyze(request.query)
        lexical = self._lexical_ranking(candidates, query_terms)
        dense = self._dense_ranking(candidates, request.query, request.top_k)

        fused: dict[str, float] = {}
        for ranking in (lexical, dense):
            for rank, (chunk_id, _) in enumerate(ranking, start=1):
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)

        lexical_ranks = {chunk_id: rank for rank, (chunk_id, _) in enumerate(lexical, start=1)}
        lexical_scores = dict(lexical)
        dense_ranks = {chunk_id: rank for rank, (chunk_id, _) in enumerate(dense, start=1)}
        dense_scores = dict(dense)
        by_id = {posting.chunk.chunk_id: posting for posting in candidates}
        query_set = set(query_terms)

        results = [
            SearchResult(
                chunk=by_id[chunk_id].chunk,
                score=score,
                lexical_score=lexical_scores.get(chunk_id, 0.0),
                dense_score=dense_scores.get(chunk_id, 0.0),
                lexical_rank=lexical_ranks.get(chunk_id),
                dense_rank=dense_ranks.get(chunk_id),
                matched_terms=tuple(sorted(query_set & set(by_id[chunk_id].terms))),
            )
            for chunk_id, score in fused.items()
        ]
        results.sort(key=lambda result: (-result.score, result.chunk.chunk_id))
        return results[: request.top_k]

    # -- internals -----------------------------------------------------------------

    def _candidate(self, index_run_id: str) -> _CandidateRun:
        run = self._candidates.get(index_run_id)
        if run is None:
            raise IngestionError(f"unknown or already applied index run {index_run_id!r}")
        return run

    def _posting(self, chunk: Chunk) -> _Posting:
        terms = Counter(analyze(contextual_text(chunk.heading_path, chunk.text)))
        return _Posting(chunk=chunk, terms=terms, length=max(1, sum(terms.values())))

    def _lexical_ranking(
        self, candidates: list[_Posting], query_terms: list[str]
    ) -> list[tuple[str, float]]:
        """Okapi BM25 over the readable candidate set."""
        if not query_terms:
            return []
        total = len(candidates)
        average_length = sum(posting.length for posting in candidates) / total
        document_frequency = Counter(
            term for posting in candidates for term in set(query_terms) & set(posting.terms)
        )

        scored: list[tuple[str, float]] = []
        for posting in candidates:
            score = 0.0
            for term in set(query_terms):
                frequency = posting.terms.get(term, 0)
                if not frequency:
                    continue
                df = document_frequency[term]
                idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
                denominator = frequency + BM25_K1 * (
                    1 - BM25_B + BM25_B * posting.length / average_length
                )
                score += idf * frequency * (BM25_K1 + 1) / denominator
            if score > 0:
                scored.append((posting.chunk.chunk_id, score))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored

    def _dense_ranking(
        self, candidates: list[_Posting], query: str, top_k: int
    ) -> list[tuple[str, float]]:
        """Cosine ranking, floored so an unrelated chunk contributes no fusion rank."""
        embedded = [posting for posting in candidates if posting.chunk.dense_embedding]
        if not embedded:
            return []
        query_vector = self._embedder.embed_query(query)
        scored = [
            (posting.chunk.chunk_id, cosine_similarity(query_vector, posting.chunk.dense_embedding))
            for posting in embedded
        ]
        scored = [pair for pair in scored if pair[1] >= self._dense_floor]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[: max(top_k * 5, 25)]
