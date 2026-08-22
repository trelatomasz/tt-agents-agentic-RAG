"""Phase 3: `PostgresIndex` against a real PostgreSQL 16 server with `pgvector`.

Skipped unless `PERSONAL_RAG_TEST_DSN` points at a database this suite may **destroy** --
it truncates every table between tests. Bring one up with:

    docker run --rm -d -p 5433:5432 -e POSTGRES_PASSWORD=rag \\
        --name rag-pg pgvector/pgvector:pg16
    PERSONAL_RAG_TEST_DSN=postgresql://postgres:rag@localhost:5433/postgres \\
        uv run --extra postgres pytest tests/personal_rag/test_postgres_integration.py

These are the assertions a recording double cannot make: that PostgreSQL accepts the DDL
and the queries, that the HNSW and GIN indexes are created, and that the candidate and
activation semantics hold when the storage is real rather than scripted. Where a claim is
also made by `test_memory_index.py`, it is repeated here rather than shared, because the
point is that two independent implementations agree.
"""

import os

import pytest

from personal_rag.db.connection import psycopg_factory
from personal_rag.db.migrate import apply_migrations
from personal_rag.errors import IngestionError
from personal_rag.index.memory import MemoryIndex
from personal_rag.index.postgres import EMBEDDING_DIMENSIONS, PostgresIndex
from personal_rag.models import Principal, SearchRequest, SourceDescriptor
from personal_rag.pipeline.embed import HashingEmbedder
from personal_rag.pipeline.publish import IngestionPipeline
from personal_rag.sources.filesystem import FilesystemAdapter

DSN = os.environ.get("PERSONAL_RAG_TEST_DSN")

pytestmark = pytest.mark.skipif(
    not DSN, reason="set PERSONAL_RAG_TEST_DSN to a disposable PostgreSQL 16 + pgvector database"
)

OWNER = Principal.owner("tomasz")

NOTE = """# Retrieval evaluation

A retrieval evaluation gate decides whether a candidate index becomes the active index.

## Negative cases

Roughly a fifth of the question set should be queries the corpus cannot answer, because a
gate that never sees an abstention rewards a system that always produces something.
"""

SECRET = """# Salary review

The compensation review for the platform team concludes in November with a banded outcome.
"""

TABLES = "sources, ingestion_runs, document_versions, run_document_stagings, chunks"


@pytest.fixture(scope="session")
def connect():
    factory = psycopg_factory(DSN)
    apply_migrations(factory)
    return factory


@pytest.fixture
def clean(connect):
    """Reset the corpus between tests without dropping the schema under test."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
            cursor.execute(
                "UPDATE active_index_pointer SET active_run_id = NULL, active_seq = 0 WHERE id = 1"
            )
            cursor.execute("ALTER SEQUENCE index_activation_seq RESTART")
        connection.commit()
    return connect


@pytest.fixture
def embedder():
    # The schema stores `vector(768)`, so the offline embedder is widened to match.
    return HashingEmbedder(dimensions=EMBEDDING_DIMENSIONS)


@pytest.fixture
def index(clean, embedder):
    return PostgresIndex(clean, embedder)


def descriptor(root, source_id="notes", owner="tomasz", visibility="private") -> SourceDescriptor:
    return SourceDescriptor.model_validate(
        {
            "source_id": source_id,
            "source_type": "filesystem",
            "display_name": source_id,
            "owner": owner,
            "visibility": visibility,
            "rights_policy": "personal_reference",
            "root": str(root),
            "include": ["**/*.md"],
        }
    )


def ingest(index, embedder, tmp_path, name, body, activate=True, **options):
    """Run one file through the real pipeline into `index`."""
    pipe = IngestionPipeline(index, embedder)
    root = tmp_path / options.get("source_id", "notes")
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(body, encoding="utf-8")
    source = descriptor(root, **options)
    run = pipe.run(FilesystemAdapter(source), source)
    if activate:
        pipe.activate(run)
    return run, pipe


def search(index, query, principal=OWNER, **kwargs):
    return index.search(
        SearchRequest(query=query, request_id="req-integration", principal=principal, **kwargs)
    )


# -- schema ------------------------------------------------------------------------


def test_the_expected_indexes_exist(clean):
    with clean() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'chunks'")
        definitions = {name: definition for name, definition in cursor.fetchall()}

    assert "hnsw" in definitions["idx_chunks_dense_vector"]
    assert "vector_cosine_ops" in definitions["idx_chunks_dense_vector"]
    assert "gin" in definitions["idx_chunks_acl_labels"].lower()
    assert "gin" in definitions["idx_chunks_lexical"].lower()


def test_migrations_are_idempotent(clean):
    assert apply_migrations(clean) == []


# -- candidate isolation and activation --------------------------------------------


def test_a_staged_run_is_invisible_until_it_is_activated(index, embedder, tmp_path):
    run, pipe = ingest(index, embedder, tmp_path, "note.md", NOTE, activate=False)

    assert index.active_run_id() is None
    assert search(index, "retrieval evaluation gate") == []

    pipe.activate(run)
    assert index.active_run_id() == run.index_run_id
    assert search(index, "retrieval evaluation gate")


def test_activation_publishes_documents_and_chunks(index, embedder, tmp_path):
    ingest(index, embedder, tmp_path, "note.md", NOTE)

    assert index.document_count() == 1
    assert index.chunk_count() >= 1
    version = index.active_version("notes:note.md")
    assert version is not None
    assert version.title
    assert index.active_documents("notes").keys() == {"notes:note.md"}
    assert index.active_documents("hr") == {}


def test_a_discarded_run_leaves_the_active_index_untouched(index, embedder, tmp_path):
    ingest(index, embedder, tmp_path, "note.md", NOTE)
    before = index.chunk_count()

    candidate = index.open_run("notes")
    index.discard(candidate)

    assert index.chunk_count() == before
    with pytest.raises(IngestionError, match="unknown or already applied"):
        index.stage_tombstone(candidate, "notes:note.md")


# -- retrieval ---------------------------------------------------------------------


def test_hybrid_retrieval_returns_a_supported_result(index, embedder, tmp_path):
    ingest(index, embedder, tmp_path, "note.md", NOTE)

    results = search(index, "retrieval evaluation gate")
    assert results
    top = results[0]
    assert top.supported
    assert top.matched_terms
    assert top.score > 0
    assert top.chunk.text
    assert top.chunk.dense_embedding is not None
    assert len(top.chunk.dense_embedding) == EMBEDDING_DIMENSIONS


def test_a_principal_cannot_read_another_owners_source(index, embedder, tmp_path):
    ingest(index, embedder, tmp_path, "note.md", NOTE)
    ingest(
        index,
        embedder,
        tmp_path,
        "secret.md",
        SECRET,
        source_id="hr",
        owner="someone-else",
    )

    assert index.document_count() == 2
    assert search(index, "compensation review platform team") == []
    assert all(result.chunk.source_id == "notes" for result in search(index, "evaluation gate"))


def test_source_narrowing_never_widens_access(index, embedder, tmp_path):
    ingest(index, embedder, tmp_path, "note.md", NOTE)
    ingest(index, embedder, tmp_path, "secret.md", SECRET, source_id="hr", owner="someone-else")

    assert search(index, "compensation review", source_ids=frozenset({"hr"})) == []
    assert search(index, "evaluation gate", source_ids=frozenset({"notes"}))


def test_it_agrees_with_the_in_memory_index_on_the_same_corpus(index, embedder, tmp_path):
    """Two independent implementations of one protocol should rank the same chunk first."""
    ingest(index, embedder, tmp_path / "pg", "note.md", NOTE)

    reference = MemoryIndex(embedder)
    ingest(reference, embedder, tmp_path / "mem", "note.md", NOTE)

    query = "how does the retrieval evaluation gate decide"
    assert search(index, query)[0].chunk.ordinal == search(reference, query)[0].chunk.ordinal


# -- tombstones and rollback -------------------------------------------------------


def test_an_activated_tombstone_removes_the_document(index, embedder, tmp_path):
    ingest(index, embedder, tmp_path, "note.md", NOTE)

    run = index.open_run("notes")
    index.stage_tombstone(run, "notes:note.md")
    assert index.document_count() == 1, "the tombstone is staged, not applied"

    index.activate(run)
    assert index.document_count() == 0
    assert index.active_version("notes:note.md") is None
    assert search(index, "retrieval evaluation gate") == []


def test_rollback_restores_the_previous_corpus(index, embedder, tmp_path):
    _, pipe = ingest(index, embedder, tmp_path, "note.md", NOTE)
    first = index.active_run_id()

    run = index.open_run("notes")
    index.stage_tombstone(run, "notes:note.md")
    index.activate(run)
    assert index.document_count() == 0

    assert index.rollback() == first
    assert index.document_count() == 1
    assert search(index, "retrieval evaluation gate")

    # Rolling back the original activation empties the index rather than failing.
    assert index.rollback() is None
    assert index.document_count() == 0
    del pipe


def test_a_rolled_back_run_does_not_come_back_after_the_next_activation(index, embedder, tmp_path):
    ingest(index, embedder, tmp_path, "note.md", NOTE)

    tombstone = index.open_run("notes")
    index.stage_tombstone(tombstone, "notes:note.md")
    index.activate(tombstone)
    index.rollback()

    ingest(index, embedder, tmp_path, "second.md", SECRET, source_id="hr", owner="tomasz")

    assert index.active_version("notes:note.md") is not None, "the retired tombstone stayed retired"
    assert index.document_count() == 2


def test_rollback_on_a_never_activated_index_fails(index):
    with pytest.raises(IngestionError, match="no previous index state"):
        index.rollback()
