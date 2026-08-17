"""The index contract (specification sections 3 and 7).

Indexes are rebuildable artifacts: writes land in a *candidate* run, evaluation decides,
and only then does the active pointer move. Cloud SQL implements the same protocol in
Phase 3, so the pipeline and query service never change when persistence arrives.
"""

from typing import Protocol, runtime_checkable

from ..models import Chunk, DocumentVersion, SearchRequest, SearchResult


@runtime_checkable
class DocumentIndex(Protocol):
    def open_run(self, source_id: str) -> str:
        """Start a candidate run. Nothing staged in it is searchable until activation."""
        ...

    def stage_document(
        self, index_run_id: str, version: DocumentVersion, chunks: list[Chunk]
    ) -> None:
        """Stage one document version and its chunks into a candidate run."""
        ...

    def stage_tombstone(self, index_run_id: str, document_id: str) -> None:
        """Stage a deletion. It applies only if the run is activated."""
        ...

    def activate(self, index_run_id: str) -> None:
        """Atomically swap the active pointer to a candidate run that passed evaluation."""
        ...

    def discard(self, index_run_id: str) -> None:
        """Drop a candidate run without touching the active index."""
        ...

    def rollback(self) -> str | None:
        """Restore the previous active index, returning the run identifier restored to."""
        ...

    def active_run_id(self) -> str | None: ...

    def active_version(self, document_id: str) -> DocumentVersion | None:
        """The currently active version, used for idempotency and freshness checks."""
        ...

    def active_documents(self, source_id: str) -> dict[str, DocumentVersion]:
        """Active versions for one source, keyed by document id.

        Incremental runs need it to skip unchanged content, and a full snapshot run needs
        it to prove which documents disappeared.
        """
        ...

    def search(self, request: SearchRequest) -> list[SearchResult]:
        """Rank chunks the principal may read. ACL filtering happens before ranking."""
        ...
