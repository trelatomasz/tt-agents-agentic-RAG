"""Cloud SQL PostgreSQL implementation of the index contract (specification section 6).

This is the production counterpart to `MemoryIndex`. The two are held to the same
behavioural suite, because the pipeline and the query service are written against the
protocol and must not be able to tell which one they were handed.

Three properties are enforced by the schema rather than by this module, which is why they
survive a crash halfway through a run:

* **Candidate isolation.** Staged rows are keyed by their run and the active views only
  join runs whose status is `activated`, so nothing staged is searchable until the
  pointer moves.
* **Atomic activation.** Activation is one transaction that serializes on the pointer
  row: a reader sees the corpus before or after, never during.
* **Access filtering before ranking.** Both retrieval branches carry
  `acl_labels && :grants` in their own `WHERE` clause, so an unreadable chunk is excluded
  while the index scan is running rather than after a distance has been computed for it.

Two deliberate differences from `MemoryIndex` are documented at their call sites: the
lexical branch ranks with `ts_rank_cd` rather than Okapi BM25, and both branches are
capped at a candidate pool instead of scoring the whole readable corpus.
"""

import json
import logging
from collections.abc import Iterable
from typing import Any

from ..db.connection import ConnectionFactory, transaction
from ..errors import IngestionError
from ..models import (
    Chunk,
    DocumentVersion,
    Locator,
    SearchRequest,
    SearchResult,
    SourceDescriptor,
    new_run_id,
)
from ..pipeline.chunk import contextual_text
from ..pipeline.embed import Embedder
from ..pipeline.enrich import analyze

logger = logging.getLogger(__name__)

RRF_K = 60
EMBEDDING_DIMENSIONS = 768

_VERSION_COLUMNS = (
    "document_id, source_id, source_uri, title, media_type, language, content_hash, "
    "source_revision, fetched_at, published_at, parser_version, normalizer_version, "
    "visibility, rights_policy, status, acl_labels, metadata_json"
)

_CHUNK_COLUMN_NAMES = (
    "chunk_id",
    "document_id",
    "source_id",
    "document_version_hash",
    "ordinal",
    "text",
    "token_count",
    "language",
    "chunker_version",
    "heading_path",
    "locator_json",
    "acl_labels",
    "lexical_terms",
    "lexical_source",
    "dense_embedding",
    "embedding_model",
    "embedding_dimensions",
    "index_run_id",
)

# `fused` also exposes `chunk_id`, so the final projection has to say which side it means.
_CHUNK_COLUMNS = ", ".join(f"c.{name}" for name in _CHUNK_COLUMN_NAMES)

# Access filtering and source narrowing, repeated in each retrieval branch rather than
# shared through a CTE: a CTE referenced twice is materialized by default, which would
# forfeit the GIN and HNSW index scans that make the filter cheap in the first place.
_READABLE_PREDICATE = """
          c.acl_labels && %(grants)s::text[]
      AND (cardinality(%(source_ids)s::text[]) = 0
           OR c.source_id = ANY (%(source_ids)s::text[]))
"""

_SEARCH_SQL = f"""
WITH tsq AS (
    SELECT websearch_to_tsquery('english', %(query_text)s) AS q
),
lexical_fts AS (
    SELECT c.chunk_id, ts_rank_cd(c.lexical_text_vector, tsq.q) AS score
    FROM active_chunks c, tsq
    WHERE {_READABLE_PREDICATE}
      AND c.lexical_text_vector @@ tsq.q
    ORDER BY score DESC, c.chunk_id
    LIMIT %(pool)s
),
-- Trigram recovery: only when the stemmed query matched nothing at all, which is the
-- case a misspelling or an unstemmable identifier produces. `%%` is the pg_trgm
-- similarity operator, so it uses the trigram index rather than scanning.
lexical_trgm AS (
    SELECT c.chunk_id, similarity(c.lexical_source, %(query_text)s) AS score
    FROM active_chunks c
    WHERE %(lexical_fallback)s::boolean
      AND NOT EXISTS (SELECT 1 FROM lexical_fts)
      AND {_READABLE_PREDICATE}
      AND c.lexical_source %% %(query_text)s
    ORDER BY score DESC, c.chunk_id
    LIMIT %(pool)s
),
lexical AS (
    SELECT chunk_id, score,
           ROW_NUMBER() OVER (ORDER BY score DESC, chunk_id) AS rank
    FROM (SELECT * FROM lexical_fts UNION ALL SELECT * FROM lexical_trgm) merged
),
dense AS (
    SELECT chunk_id, score,
           ROW_NUMBER() OVER (ORDER BY score DESC, chunk_id) AS rank
    FROM (
        SELECT c.chunk_id,
               1 - (c.dense_embedding <=> %(query_vector)s::vector) AS score
        FROM active_chunks c
        WHERE {_READABLE_PREDICATE}
          AND c.dense_embedding IS NOT NULL
          AND 1 - (c.dense_embedding <=> %(query_vector)s::vector) >= %(dense_floor)s::double precision
        ORDER BY c.dense_embedding <=> %(query_vector)s::vector, c.chunk_id
        LIMIT %(pool)s
    ) nearest
),
fused AS (
    SELECT COALESCE(l.chunk_id, d.chunk_id) AS chunk_id,
           COALESCE(1.0 / (%(rrf_k)s::int + l.rank), 0.0)
             + COALESCE(1.0 / (%(rrf_k)s::int + d.rank), 0.0) AS score,
           COALESCE(l.score, 0.0) AS lexical_score,
           l.rank AS lexical_rank,
           COALESCE(d.score, 0.0) AS dense_score,
           d.rank AS dense_rank
    FROM lexical l
    FULL OUTER JOIN dense d ON d.chunk_id = l.chunk_id
)
SELECT {_CHUNK_COLUMNS},
       f.score, f.lexical_score, f.lexical_rank, f.dense_score, f.dense_rank
FROM fused f
JOIN active_chunks c ON c.chunk_id = f.chunk_id
ORDER BY f.score DESC, c.chunk_id
LIMIT %(top_k)s
"""

_UPSERT_VERSION_SQL = """
INSERT INTO document_versions (
    document_id, content_hash, source_id, source_uri, title, media_type, language,
    source_revision, fetched_at, published_at, parser_version, normalizer_version,
    visibility, rights_policy, status, acl_labels, metadata_json
) VALUES (
    %(document_id)s, %(content_hash)s, %(source_id)s, %(source_uri)s, %(title)s,
    %(media_type)s, %(language)s, %(source_revision)s, %(fetched_at)s, %(published_at)s,
    %(parser_version)s, %(normalizer_version)s, %(visibility)s, %(rights_policy)s,
    %(status)s, %(acl_labels)s::text[], %(metadata_json)s::jsonb
)
ON CONFLICT (document_id, content_hash) DO UPDATE SET
    source_id = EXCLUDED.source_id,
    source_uri = EXCLUDED.source_uri,
    title = EXCLUDED.title,
    media_type = EXCLUDED.media_type,
    language = EXCLUDED.language,
    source_revision = EXCLUDED.source_revision,
    fetched_at = EXCLUDED.fetched_at,
    published_at = EXCLUDED.published_at,
    parser_version = EXCLUDED.parser_version,
    normalizer_version = EXCLUDED.normalizer_version,
    visibility = EXCLUDED.visibility,
    rights_policy = EXCLUDED.rights_policy,
    status = EXCLUDED.status,
    acl_labels = EXCLUDED.acl_labels,
    metadata_json = EXCLUDED.metadata_json
"""

_INSERT_CHUNK_SQL = """
INSERT INTO chunks (
    index_run_id, chunk_id, document_id, document_version_hash, source_id, ordinal, text,
    token_count, language, chunker_version, heading_path, locator_json, acl_labels,
    lexical_terms, lexical_source, dense_embedding, embedding_model, embedding_dimensions
) VALUES (
    %(index_run_id)s, %(chunk_id)s, %(document_id)s, %(document_version_hash)s,
    %(source_id)s, %(ordinal)s, %(text)s, %(token_count)s, %(language)s,
    %(chunker_version)s, %(heading_path)s::text[], %(locator_json)s::jsonb,
    %(acl_labels)s::text[], %(lexical_terms)s::text[], %(lexical_source)s,
    %(dense_embedding)s::vector, %(embedding_model)s, %(embedding_dimensions)s
)
"""

_UPSERT_SOURCE_SQL = """
INSERT INTO sources (
    source_id, source_type, display_name, owner, visibility, refresh_policy,
    rights_policy, adapter_version, configuration
) VALUES (
    %(source_id)s, %(source_type)s, %(display_name)s, %(owner)s, %(visibility)s,
    %(refresh_policy)s, %(rights_policy)s, %(adapter_version)s, %(configuration)s::jsonb
)
ON CONFLICT (source_id) DO UPDATE SET
    source_type = EXCLUDED.source_type,
    display_name = EXCLUDED.display_name,
    owner = EXCLUDED.owner,
    visibility = EXCLUDED.visibility,
    refresh_policy = EXCLUDED.refresh_policy,
    rights_policy = EXCLUDED.rights_policy,
    adapter_version = EXCLUDED.adapter_version,
    configuration = EXCLUDED.configuration,
    updated_at = NOW()
"""


class PostgresIndex:
    """A `DocumentIndex` backed by Cloud SQL PostgreSQL with `pgvector` and native FTS."""

    def __init__(
        self,
        connect: ConnectionFactory,
        embedder: Embedder,
        *,
        dense_floor: float = 0.15,
        lexical_fallback: bool = True,
        trigram_floor: float = 0.3,
        embedding_dimensions: int = EMBEDDING_DIMENSIONS,
    ):
        """`dense_floor` is a property of the embedding model, not of this index.

        `MemoryIndex` calibrates it against `HashingEmbedder`, whose unrelated-text
        similarity sits near zero. A trained model has a much higher baseline, so the
        deployed value must be re-derived from the corpus rather than inherited.
        """
        self._connect = connect
        self._embedder = embedder
        self._dense_floor = dense_floor
        self._lexical_fallback = lexical_fallback
        self._trigram_floor = trigram_floor
        self._embedding_dimensions = embedding_dimensions
        self._tunable: set[str] | None = None

    # -- registry ------------------------------------------------------------------

    def register_source(self, descriptor: SourceDescriptor) -> None:
        """Record a source descriptor in the registry.

        Not part of the index protocol: retrieval filters on the labels stored with each
        chunk, so this table is a catalogue for operators and the CLI, never an input to
        an access decision.
        """
        with transaction(self._connect) as cursor:
            cursor.execute(
                _UPSERT_SOURCE_SQL,
                {
                    "source_id": descriptor.source_id,
                    "source_type": descriptor.source_type,
                    "display_name": descriptor.display_name,
                    "owner": descriptor.owner,
                    "visibility": descriptor.visibility,
                    "refresh_policy": descriptor.refresh_policy,
                    "rights_policy": descriptor.rights_policy,
                    "adapter_version": descriptor.adapter_version,
                    "configuration": json.dumps(descriptor.configuration),
                },
            )

    # -- write path ----------------------------------------------------------------

    def open_run(self, source_id: str) -> str:
        run_id = new_run_id("index")
        with transaction(self._connect) as cursor:
            cursor.execute(
                "INSERT INTO ingestion_runs (run_id, source_id, status) "
                "VALUES (%(run_id)s, %(source_id)s, 'candidate')",
                {"run_id": run_id, "source_id": source_id},
            )
        return run_id

    def stage_document(
        self, index_run_id: str, version: DocumentVersion, chunks: list[Chunk]
    ) -> None:
        """Stage one document version and its chunks into a candidate run."""
        self._reject_dimension_mismatch(chunks)
        stamped = [chunk.model_copy(update={"index_run_id": index_run_id}) for chunk in chunks]

        with transaction(self._connect) as cursor:
            self._require_candidate(cursor, index_run_id)
            cursor.execute(_UPSERT_VERSION_SQL, _version_params(version))
            # Chunks are removed before the staging row changes: they point at the
            # staging row's content hash, so re-staging a document with new content
            # would otherwise orphan the previous version's chunks inside this run.
            self._clear_staged_document(cursor, index_run_id, version.document_id)
            cursor.execute(
                "INSERT INTO run_document_stagings "
                "(index_run_id, document_id, content_hash, is_tombstone) "
                "VALUES (%(index_run_id)s, %(document_id)s, %(content_hash)s, FALSE) "
                "ON CONFLICT (index_run_id, document_id) DO UPDATE SET "
                "content_hash = EXCLUDED.content_hash, is_tombstone = FALSE, "
                "staged_at = NOW()",
                {
                    "index_run_id": index_run_id,
                    "document_id": version.document_id,
                    "content_hash": version.content_hash,
                },
            )
            if stamped:
                cursor.executemany(
                    _INSERT_CHUNK_SQL, [self._chunk_params(chunk) for chunk in stamped]
                )
            cursor.execute(
                "UPDATE ingestion_runs SET documents_processed = documents_processed + 1, "
                "chunks_created = chunks_created + %(count)s WHERE run_id = %(run_id)s",
                {"count": len(stamped), "run_id": index_run_id},
            )

    def stage_tombstone(self, index_run_id: str, document_id: str) -> None:
        """Stage a deletion. It applies only if the run is activated."""
        with transaction(self._connect) as cursor:
            self._require_candidate(cursor, index_run_id)
            self._clear_staged_document(cursor, index_run_id, document_id)
            cursor.execute(
                "INSERT INTO run_document_stagings "
                "(index_run_id, document_id, content_hash, is_tombstone) "
                "VALUES (%(index_run_id)s, %(document_id)s, NULL, TRUE) "
                "ON CONFLICT (index_run_id, document_id) DO UPDATE SET "
                "content_hash = NULL, is_tombstone = TRUE, staged_at = NOW()",
                {"index_run_id": index_run_id, "document_id": document_id},
            )
            cursor.execute(
                "UPDATE ingestion_runs SET tombstones_created = tombstones_created + 1 "
                "WHERE run_id = %(run_id)s",
                {"run_id": index_run_id},
            )

    def activate(
        self,
        index_run_id: str,
        *,
        activated_by: str = "pipeline",
        reason: str = "evaluation gate passed",
    ) -> None:
        """Atomically swap the active pointer to a candidate run that passed evaluation."""
        with transaction(self._connect) as cursor:
            # Serializes concurrent activations and rollbacks against each other; the
            # pointer row is guaranteed to exist from migration time.
            cursor.execute("SELECT active_seq FROM active_index_pointer WHERE id = 1 FOR UPDATE")
            cursor.execute(
                "UPDATE ingestion_runs SET status = 'activated', "
                "activation_seq = nextval('index_activation_seq'), completed_at = NOW() "
                "WHERE run_id = %(run_id)s AND status = 'candidate' "
                "RETURNING activation_seq",
                {"run_id": index_run_id},
            )
            row = cursor.fetchone()
            if row is None:
                raise IngestionError(f"unknown or already applied index run {index_run_id!r}")
            cursor.execute(
                "UPDATE active_index_pointer SET active_run_id = %(run_id)s, "
                "active_seq = %(seq)s, activated_at = NOW(), activated_by = %(by)s, "
                "reason = %(reason)s WHERE id = 1",
                {
                    "run_id": index_run_id,
                    "seq": row[0],
                    "by": activated_by[:64],
                    "reason": reason[:256],
                },
            )
        logger.info("index_activated", extra={"index_run_id": index_run_id})

    def discard(self, index_run_id: str) -> None:
        """Drop a candidate run without touching the active index."""
        with transaction(self._connect) as cursor:
            cursor.execute(
                "UPDATE ingestion_runs SET status = 'discarded', completed_at = NOW() "
                "WHERE run_id = %(run_id)s AND status = 'candidate' RETURNING run_id",
                {"run_id": index_run_id},
            )
            if cursor.fetchone() is None:
                return
            # Cascades to this run's chunks; the run row itself is kept as evidence.
            cursor.execute(
                "DELETE FROM run_document_stagings WHERE index_run_id = %(run_id)s",
                {"run_id": index_run_id},
            )

    def rollback(self, *, activated_by: str = "operator", reason: str = "rollback") -> str | None:
        """Restore the previous active index, returning the run identifier restored to.

        Retiring the head run is a status update on one row, so the corpus the query
        service serves changes in a single commit rather than by restoring data --
        which is what keeps the register entry P-23 budget of five seconds achievable
        regardless of corpus size.
        """
        with transaction(self._connect) as cursor:
            cursor.execute("SELECT active_seq FROM active_index_pointer WHERE id = 1 FOR UPDATE")
            cursor.execute(
                "UPDATE ingestion_runs SET status = 'rolled_back', activation_seq = NULL "
                "WHERE run_id = (SELECT run_id FROM ingestion_runs WHERE status = 'activated' "
                "ORDER BY activation_seq DESC LIMIT 1) RETURNING run_id",
                {},
            )
            if cursor.fetchone() is None:
                raise IngestionError("no previous index state to roll back to")
            cursor.execute(
                "SELECT run_id, activation_seq FROM ingestion_runs WHERE status = 'activated' "
                "ORDER BY activation_seq DESC LIMIT 1"
            )
            head = cursor.fetchone()
            restored, seq = (head[0], head[1]) if head else (None, 0)
            cursor.execute(
                "UPDATE active_index_pointer SET active_run_id = %(run_id)s, "
                "active_seq = %(seq)s, activated_at = NOW(), activated_by = %(by)s, "
                "reason = %(reason)s WHERE id = 1",
                {
                    "run_id": restored,
                    "seq": seq,
                    "by": activated_by[:64],
                    "reason": reason[:256],
                },
            )
        logger.warning("index_rolled_back", extra={"index_run_id": restored})
        return restored

    # -- read path -----------------------------------------------------------------

    def active_run_id(self) -> str | None:
        with transaction(self._connect) as cursor:
            cursor.execute("SELECT active_run_id FROM active_index_pointer WHERE id = 1")
            row = cursor.fetchone()
            return row[0] if row else None

    def active_version(self, document_id: str) -> DocumentVersion | None:
        with transaction(self._connect) as cursor:
            cursor.execute(
                f"SELECT {_VERSION_COLUMNS} FROM active_document_versions "
                "WHERE document_id = %(document_id)s",
                {"document_id": document_id},
            )
            row = cursor.fetchone()
            return _version_from_row(row) if row else None

    def active_documents(self, source_id: str) -> dict[str, DocumentVersion]:
        with transaction(self._connect) as cursor:
            cursor.execute(
                f"SELECT {_VERSION_COLUMNS} FROM active_document_versions "
                "WHERE source_id = %(source_id)s",
                {"source_id": source_id},
            )
            versions = [_version_from_row(row) for row in cursor.fetchall()]
        return {version.document_id: version for version in versions}

    def document_count(self) -> int:
        with transaction(self._connect) as cursor:
            cursor.execute("SELECT COUNT(*) FROM active_document_versions")
            return int(cursor.fetchone()[0])

    def chunk_count(self) -> int:
        with transaction(self._connect) as cursor:
            cursor.execute("SELECT COUNT(*) FROM active_chunks")
            return int(cursor.fetchone()[0])

    def search(self, request: SearchRequest) -> list[SearchResult]:
        """Rank chunks the principal may read. ACL filtering happens before ranking."""
        grants = sorted(request.principal.grants)
        if not grants:
            return []

        # The dense branch is capped the way `MemoryIndex` caps it; the lexical branch is
        # capped too, which the in-memory reference does not do. Reciprocal rank fusion
        # weights rank 125 at under two percent of rank 1, so a candidate outside the
        # pool could not have reached the result set anyway, and an unbounded lexical
        # scan over the whole readable corpus is exactly the cost this store exists to
        # avoid.
        pool = max(request.top_k * 5, 25)
        params = {
            "query_text": request.query,
            "query_vector": _encode_vector(self._embedder.embed_query(request.query)),
            "grants": grants,
            "source_ids": sorted(request.source_ids),
            "dense_floor": self._dense_floor,
            "lexical_fallback": self._lexical_fallback,
            "rrf_k": RRF_K,
            "pool": pool,
            "top_k": request.top_k,
        }

        with transaction(self._connect) as cursor:
            self._tune(cursor, pool)
            cursor.execute(_SEARCH_SQL, params)
            rows = cursor.fetchall()

        query_terms = set(analyze(request.query))
        return [_result_from_row(row, query_terms) for row in rows]

    # -- internals -----------------------------------------------------------------

    def _tune(self, cursor: Any, pool: int) -> None:
        """Apply per-transaction retrieval settings that this server actually has.

        `hnsw.iterative_scan` only exists on pgvector 0.8 and later. Without it a
        filtered vector scan can return fewer than `pool` rows because the filter is
        applied to a fixed-size candidate list, so recall degrades quietly on an older
        server -- hence probing `pg_settings` rather than assuming, and hence logging
        when the setting is absent.
        """
        settings = {
            "hnsw.ef_search": str(max(40, pool)),
            "hnsw.iterative_scan": "relaxed_order",
            "pg_trgm.similarity_threshold": str(self._trigram_floor),
        }
        if self._tunable is None:
            cursor.execute(
                "SELECT name FROM pg_settings WHERE name = ANY(%(names)s::text[])",
                {"names": sorted(settings)},
            )
            self._tunable = {row[0] for row in cursor.fetchall()}
            missing = sorted(set(settings) - self._tunable)
            if missing:
                logger.info("index_tuning_unavailable", extra={"settings": missing})
        for name, value in settings.items():
            if name in self._tunable:
                cursor.execute(
                    "SELECT set_config(%(name)s, %(value)s, true)",
                    {"name": name, "value": value},
                )

    def _reject_dimension_mismatch(self, chunks: Iterable[Chunk]) -> None:
        """Fail with the dimension in the message rather than a driver level type error."""
        for chunk in chunks:
            if chunk.dense_embedding is None:
                continue
            if len(chunk.dense_embedding) != self._embedding_dimensions:
                raise IngestionError(
                    f"chunk {chunk.chunk_id!r} has a {len(chunk.dense_embedding)}-dimensional "
                    f"embedding but the schema stores vector({self._embedding_dimensions}); "
                    "re-index with a matching embedding model or migrate the column"
                )

    @staticmethod
    def _require_candidate(cursor: Any, index_run_id: str) -> None:
        cursor.execute(
            "SELECT status FROM ingestion_runs WHERE run_id = %(run_id)s FOR UPDATE",
            {"run_id": index_run_id},
        )
        row = cursor.fetchone()
        if row is None or row[0] != "candidate":
            raise IngestionError(f"unknown or already applied index run {index_run_id!r}")

    @staticmethod
    def _clear_staged_document(cursor: Any, index_run_id: str, document_id: str) -> None:
        cursor.execute(
            "DELETE FROM chunks WHERE index_run_id = %(run_id)s AND document_id = %(document_id)s",
            {"run_id": index_run_id, "document_id": document_id},
        )

    def _chunk_params(self, chunk: Chunk) -> dict[str, Any]:
        return {
            "index_run_id": chunk.index_run_id,
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "document_version_hash": chunk.document_version_hash,
            "source_id": chunk.source_id,
            "ordinal": chunk.ordinal,
            "text": chunk.text,
            "token_count": chunk.token_count,
            "language": chunk.language,
            "chunker_version": chunk.chunker_version,
            "heading_path": list(chunk.heading_path),
            "locator_json": chunk.locator.model_dump_json(),
            "acl_labels": list(chunk.acl_labels),
            "lexical_terms": list(chunk.lexical_terms),
            "lexical_source": contextual_text(chunk.heading_path, chunk.text),
            "dense_embedding": _encode_vector(chunk.dense_embedding),
            "embedding_model": chunk.embedding_model,
            "embedding_dimensions": chunk.embedding_dimensions,
        }


# -- row mapping -------------------------------------------------------------------


def _encode_vector(values: tuple[float, ...] | None) -> str | None:
    """pgvector's text input format, so no driver side adapter has to be registered."""
    if values is None:
        return None
    return "[" + ",".join(repr(float(value)) for value in values) + "]"


def _decode_vector(value: Any) -> tuple[float, ...] | None:
    """Accept the text form, and a list if a pgvector adapter is registered."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip().strip("[]")
        return tuple(float(part) for part in stripped.split(",")) if stripped else ()
    return tuple(float(part) for part in value)


def _as_mapping(value: Any) -> dict[str, Any]:
    """`jsonb` arrives as a mapping from psycopg 3 and as text from some drivers."""
    if value is None:
        return {}
    if isinstance(value, str | bytes):
        return json.loads(value)
    return dict(value)


def _version_params(version: DocumentVersion) -> dict[str, Any]:
    params = version.model_dump(mode="python")
    params["acl_labels"] = list(version.acl_labels)
    params["metadata_json"] = json.dumps(version.metadata_json, default=str)
    return params


def _version_from_row(row: tuple[Any, ...]) -> DocumentVersion:
    return DocumentVersion(
        document_id=row[0],
        source_id=row[1],
        source_uri=row[2],
        title=row[3],
        media_type=row[4],
        language=row[5],
        content_hash=row[6],
        source_revision=row[7],
        fetched_at=row[8],
        published_at=row[9],
        parser_version=row[10],
        normalizer_version=row[11],
        visibility=row[12],
        rights_policy=row[13],
        status=row[14],
        acl_labels=tuple(row[15] or ()),
        metadata_json=_as_mapping(row[16]),
    )


def _chunk_from_row(row: tuple[Any, ...]) -> Chunk:
    return Chunk(
        chunk_id=row[0],
        document_id=row[1],
        source_id=row[2],
        document_version_hash=row[3],
        ordinal=row[4],
        text=row[5],
        token_count=row[6],
        language=row[7],
        chunker_version=row[8],
        heading_path=tuple(row[9] or ()),
        locator=Locator(**_as_mapping(row[10])),
        acl_labels=tuple(row[11] or ()),
        lexical_terms=tuple(row[12] or ()),
        # row[13] is `lexical_source`, a storage detail of the lexical index rather than
        # part of the chunk contract; it is read for `matched_terms` and then dropped.
        dense_embedding=_decode_vector(row[14]),
        embedding_model=row[15],
        embedding_dimensions=row[16],
        index_run_id=row[17],
    )


def _result_from_row(row: tuple[Any, ...], query_terms: set[str]) -> SearchResult:
    """Matched terms are derived from the indexed text, as `MemoryIndex` derives them.

    Reading them back from the `tsvector` would report stemmed lexemes instead of the
    terms the caller used, and a citation the caller cannot recognise is not evidence.
    """
    chunk = _chunk_from_row(row)
    indexed_terms = set(analyze(row[13] or ""))
    return SearchResult(
        chunk=chunk,
        score=float(row[18]),
        lexical_score=float(row[19]),
        lexical_rank=row[20],
        dense_score=float(row[21]),
        dense_rank=row[22],
        matched_terms=tuple(sorted(query_terms & indexed_terms)),
    )
