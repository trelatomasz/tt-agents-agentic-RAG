"""Run one source through the pipeline into a candidate index (specification section 7).

Two safety properties are structural rather than conventional:

* a failed run cannot change the active index, because writes only ever land in a candidate
  run and activation is a separate call;
* an adapter failure is never a deletion, because tombstones come from discovery evidence
  (`SourceItem.status == "deleted"`) or from an explicit full-snapshot `delete_missing`.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ..errors import IngestionError, RightsViolationError
from ..index.base import DocumentIndex
from ..models import (
    DiscoveryRequest,
    DocumentVersion,
    IngestionRun,
    IngestionRunCounters,
    IngestionRunError,
    Locator,
    SourceDescriptor,
    SourceItem,
    new_run_id,
)
from ..sources.base import AdapterError, SourceAdapter
from .chunk import CHUNKER_VERSION, MAX_TOKENS, TARGET_TOKENS, chunk_document
from .embed import Embedder, embed_chunks
from .enrich import enrich_chunks
from .normalize import NORMALIZER_VERSION, build_document_version, normalize_text

logger = logging.getLogger(__name__)

Gate = Callable[[IngestionRun], bool]


@dataclass(frozen=True)
class PipelineLimits:
    """Validation bounds applied before any content is parsed or embedded."""

    max_document_bytes: int = 10_000_000
    max_chunks_per_document: int = 2000


def default_gate(run: IngestionRun) -> bool:
    """Activate only a staged run that has something to apply.

    Retrieval and safety evaluation (register entry P-20) replaces this by passing a
    stricter gate to `activate`; the contract is only that activation is a decision.
    """
    return run.status == "staged" and bool(
        run.counters.documents_indexed or run.counters.tombstoned
    )


class IngestionPipeline:
    """Owns normalization, chunking, embedding and index writes for every source type."""

    def __init__(
        self,
        index: DocumentIndex,
        embedder: Embedder,
        *,
        limits: PipelineLimits | None = None,
        target_tokens: int = TARGET_TOKENS,
        max_tokens: int = MAX_TOKENS,
    ):
        self.index = index
        self.embedder = embedder
        self.limits = limits or PipelineLimits()
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens

    def run(
        self,
        adapter: SourceAdapter,
        descriptor: SourceDescriptor,
        *,
        changed_only: bool = True,
        delete_missing: bool = False,
        dry_run: bool = False,
        force: bool = False,
    ) -> IngestionRun:
        """Stage one source into a candidate index run without activating it."""
        if delete_missing and changed_only:
            raise ValueError("--delete-missing requires a full snapshot; disable changed_only")
        if not (descriptor.allows_storage and descriptor.allows_model_processing):
            raise RightsViolationError(
                f"rights policy {descriptor.rights_policy!r} forbids storing or processing "
                f"source {descriptor.source_id!r}"
            )
        register_source = getattr(self.index, "register_source", None)
        if register_source is not None:
            register_source(descriptor)

        run = IngestionRun(
            run_id=new_run_id("ingest"),
            source_id=descriptor.source_id,
            started_at=datetime.now(UTC),
            dry_run=dry_run,
            adapter_version=adapter.adapter_version,
            normalizer_version=NORMALIZER_VERSION,
            chunker_version=CHUNKER_VERSION,
            embedding_model=self.embedder.model_id,
            counters=IngestionRunCounters(),
        )
        known = self.index.active_documents(descriptor.source_id)
        index_run_id = None if dry_run else self.index.open_run(descriptor.source_id)
        run.index_run_id = index_run_id

        try:
            seen, failed = self._ingest(
                adapter, descriptor, run, known, index_run_id, changed_only, force
            )
            if delete_missing:
                self._tombstone_missing(run, known, index_run_id, seen, failed)
        except Exception as exc:
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.errors.append(
                IngestionRunError(
                    item_id=descriptor.source_id,
                    stage="discover",
                    code="RUN_FAILED",
                    message=str(exc),
                )
            )
            if index_run_id:
                self.index.discard(index_run_id)
            logger.warning(
                "ingestion_run_failed",
                extra={"run_id": run.run_id, "source_id": descriptor.source_id},
            )
            raise IngestionError(f"ingestion run {run.run_id} failed: {exc}") from exc

        run.status = "staged"
        run.finished_at = datetime.now(UTC)
        logger.info(
            "ingestion_run_staged",
            extra={
                "run_id": run.run_id,
                "source_id": descriptor.source_id,
                "index_run_id": index_run_id,
                "documents_indexed": run.counters.documents_indexed,
                "chunks_indexed": run.counters.chunks_indexed,
                "skipped_unchanged": run.counters.skipped_unchanged,
            },
        )
        return run

    def activate(self, run: IngestionRun, gate: Gate = default_gate) -> IngestionRun:
        """Apply the evaluation decision: swap the active pointer, or quarantine the run."""
        if run.dry_run or not run.index_run_id:
            raise IngestionError(f"run {run.run_id} staged nothing to activate")
        if gate(run):
            self.index.activate(run.index_run_id)
            run.status = "succeeded"
        else:
            self.index.discard(run.index_run_id)
            run.status = "quarantined"
        run.finished_at = datetime.now(UTC)
        logger.info(
            "ingestion_run_decided",
            extra={"run_id": run.run_id, "status": run.status, "index_run_id": run.index_run_id},
        )
        return run

    # -- stages --------------------------------------------------------------------

    def _ingest(
        self, adapter, descriptor, run, known, index_run_id, changed_only, force
    ) -> tuple[set[str], set[str]]:
        """Stage every discovered item. Returns the item ids seen and those that failed."""
        seen: set[str] = set()
        failed: set[str] = set()
        request = DiscoveryRequest(
            descriptor=descriptor,
            changed_only=changed_only,
            known_revisions={
                document_id.split(":", 1)[1]: version.source_revision
                for document_id, version in known.items()
            },
        )
        for item in adapter.discover(request):
            run.counters.discovered += 1
            seen.add(item.item_id)

            if item.status == "deleted":
                run.counters.tombstoned += 1
                if index_run_id:
                    self.index.stage_tombstone(index_run_id, item.document_id)
                continue
            if item.status != "available":
                self._reject(
                    run,
                    failed,
                    item.item_id,
                    "discover",
                    item.status.upper(),
                    "adapter reported a non-readable item",
                    "quarantined",
                )
                continue

            try:
                raw = adapter.fetch(item)
            except AdapterError as exc:
                counter = "rejected" if exc.status == "unsupported" else "quarantined"
                self._reject(
                    run, failed, exc.item_id, "fetch", exc.status.upper(), str(exc), counter
                )
                continue
            run.counters.fetched += 1
            run.parser_version = raw.parser_version

            size = len(raw.text.encode("utf-8"))
            if size > self.limits.max_document_bytes:
                self._reject(run, failed, item.item_id, "validate", "TOO_LARGE", f"{size} bytes")
                continue

            normalized = normalize_text(raw.text)
            if not normalized.strip():
                self._reject(
                    run, failed, item.item_id, "validate", "EMPTY", "no content after normalization"
                )
                continue

            version = build_document_version(raw, descriptor, normalized)
            active = known.get(version.document_id)
            if active is not None and active.content_hash == version.content_hash and not force:
                run.counters.skipped_unchanged += 1
                continue

            chunks = chunk_document(
                version,
                normalized,
                target_tokens=self.target_tokens,
                max_tokens=self.max_tokens,
                locator_template=_locator_for(item),
            )
            if not chunks:
                self._reject(
                    run, failed, item.item_id, "chunk", "NO_CHUNKS", "document produced no chunks"
                )
                continue
            if len(chunks) > self.limits.max_chunks_per_document:
                self._reject(
                    run, failed, item.item_id, "chunk", "TOO_MANY_CHUNKS", f"{len(chunks)} chunks"
                )
                continue

            chunks = embed_chunks(enrich_chunks(chunks, version), self.embedder)
            run.counters.documents_indexed += 1
            run.counters.chunks_indexed += len(chunks)
            if index_run_id:
                self.index.stage_document(index_run_id, version, chunks)

        return seen, failed

    def _tombstone_missing(
        self,
        run: IngestionRun,
        known: dict[str, DocumentVersion],
        index_run_id: str | None,
        seen: set[str],
        failed: set[str],
    ) -> None:
        """Delete only what a full snapshot proves is gone.

        An item that failed to fetch or parse is excluded: it was present and unreadable,
        which section 7 distinguishes from absent.
        """
        for document_id in known:
            item_id = document_id.split(":", 1)[1]
            if item_id in seen or item_id in failed:
                continue
            run.counters.tombstoned += 1
            if index_run_id:
                self.index.stage_tombstone(index_run_id, document_id)

    @staticmethod
    def _reject(
        run: IngestionRun,
        failed: set[str],
        item_id: str,
        stage: str,
        code: str,
        message: str,
        counter: str = "rejected",
    ) -> None:
        setattr(run.counters, counter, getattr(run.counters, counter) + 1)
        failed.add(item_id)
        run.errors.append(
            IngestionRunError(item_id=item_id, stage=stage, code=code, message=message)
        )


def _locator_for(item: SourceItem) -> Locator:
    """Seed the chunk locator with whatever identity the source item already proves."""
    is_url = "://" in item.source_uri
    return Locator(
        path=None if is_url else item.source_uri,
        url=item.source_uri if is_url else None,
        commit=item.metadata.get("commit"),
    )
