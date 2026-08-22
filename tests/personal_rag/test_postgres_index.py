"""Phase 3: the SQL the PostgreSQL index sends, and how it maps rows back to contracts.

These tests run without a database. They cover the parts a live server cannot check for
us -- that access labels are always parameters rather than interpolated text, that the
filter appears in every retrieval branch, and that a row decodes back into the same
contract objects the pipeline staged. Whether PostgreSQL accepts the statements is
covered by `test_postgres_integration.py`, which needs a real server.
"""

from datetime import UTC, datetime

import pytest
from fake_db import FakeConnection, factory

from personal_rag.db import migrate
from personal_rag.errors import IngestionError
from personal_rag.index.base import DocumentIndex
from personal_rag.index.postgres import (
    _SEARCH_SQL,
    EMBEDDING_DIMENSIONS,
    PostgresIndex,
    _decode_vector,
    _encode_vector,
)
from personal_rag.models import (
    Chunk,
    DocumentVersion,
    Locator,
    Principal,
    SearchRequest,
    SourceDescriptor,
    build_chunk_id,
)
from personal_rag.pipeline.embed import HashingEmbedder

OWNER = Principal.owner("tomasz")
CANDIDATE = [("SELECT status FROM ingestion_runs", [("candidate",)])]

embedder = HashingEmbedder(dimensions=EMBEDDING_DIMENSIONS)


def build_index(responses=None) -> tuple[PostgresIndex, FakeConnection]:
    connection = FakeConnection(list(responses or []))
    return PostgresIndex(factory(connection), embedder), connection


def version(document_id: str = "notes:note.md") -> DocumentVersion:
    return DocumentVersion(
        document_id=document_id,
        source_id="notes",
        source_uri="/notes/note.md",
        title="Note",
        media_type="text/markdown",
        language="en",
        content_hash="a" * 64,
        source_revision="rev-1",
        fetched_at=datetime(2026, 8, 22, tzinfo=UTC),
        parser_version="markdown/1",
        normalizer_version="normalize/1",
        visibility="private",
        rights_policy="personal_reference",
        acl_labels=("source:notes", "owner:tomasz"),
    )


def chunk(dimensions: int = EMBEDDING_DIMENSIONS) -> Chunk:
    return Chunk(
        chunk_id=build_chunk_id("notes:note.md", "a" * 64, 0),
        document_id="notes:note.md",
        source_id="notes",
        document_version_hash="a" * 64,
        ordinal=0,
        text="A retrieval evaluation gate decides whether a candidate index becomes active.",
        token_count=14,
        language="en",
        chunker_version="markdown-heading/1",
        heading_path=("Retrieval evaluation",),
        locator=Locator(path="/notes/note.md", line_start=1, line_end=3),
        acl_labels=("source:notes", "owner:tomasz"),
        lexical_terms=("candidate", "evaluation", "retrieval"),
        dense_embedding=tuple(0.001 * (i % 7) for i in range(dimensions)),
        embedding_model="hashing/1",
        embedding_dimensions=dimensions,
    )


def search_row(score: float = 0.03) -> tuple:
    staged = chunk()
    return (
        staged.chunk_id,
        staged.document_id,
        staged.source_id,
        staged.document_version_hash,
        staged.ordinal,
        staged.text,
        staged.token_count,
        staged.language,
        staged.chunker_version,
        list(staged.heading_path),
        staged.locator.model_dump_json(),
        list(staged.acl_labels),
        list(staged.lexical_terms),
        f"{' > '.join(staged.heading_path)}\n\n{staged.text}",
        _encode_vector(staged.dense_embedding),
        staged.embedding_model,
        staged.embedding_dimensions,
        "index-20260822T000000-abcd1234",
        score,
        0.42,
        1,
        0.81,
        2,
    )


# -- contract ----------------------------------------------------------------------


def test_satisfies_the_index_protocol():
    index, _ = build_index()
    assert isinstance(index, DocumentIndex)


# -- access filtering --------------------------------------------------------------


def test_every_retrieval_branch_filters_on_access_labels():
    """Lexical, trigram recovery and dense each carry the filter; none inherits it."""
    assert _SEARCH_SQL.count("c.acl_labels && %(grants)s::text[]") == 3


def test_search_passes_grants_and_query_as_parameters():
    index, connection = build_index([("FROM fused f", [search_row()])])
    index.search(SearchRequest(query="retrieval gate", request_id="req-1", principal=OWNER))

    sql, params = next(
        (sql, params) for sql, params in connection.statements if "FROM fused f" in sql
    )
    assert "retrieval gate" not in sql
    assert "owner:tomasz" not in sql
    assert params["grants"] == ["owner:tomasz", "public"]
    assert params["query_text"] == "retrieval gate"


def test_search_without_grants_never_reaches_the_database():
    index, connection = build_index()
    request = SearchRequest(
        query="anything at all",
        request_id="req-2",
        principal=Principal(subject="stranger", grants=frozenset()),
    )
    assert index.search(request) == []
    assert connection.statements == []


def test_source_narrowing_is_a_parameter_not_a_grant():
    index, connection = build_index([("FROM fused f", [])])
    index.search(
        SearchRequest(
            query="retrieval gate",
            request_id="req-3",
            principal=OWNER,
            source_ids=frozenset({"hr", "notes"}),
        )
    )
    params = connection.parameters_for("FROM fused f")
    assert params["source_ids"] == ["hr", "notes"]
    assert params["grants"] == ["owner:tomasz", "public"]


# -- row mapping -------------------------------------------------------------------


def test_search_row_decodes_into_the_staged_chunk():
    index, _ = build_index([("FROM fused f", [search_row()])])
    results = index.search(
        SearchRequest(query="retrieval evaluation gate", request_id="req-4", principal=OWNER)
    )

    assert len(results) == 1
    result = results[0]
    staged = chunk()
    assert result.chunk.chunk_id == staged.chunk_id
    assert result.chunk.heading_path == staged.heading_path
    assert result.chunk.locator == staged.locator
    assert result.chunk.acl_labels == staged.acl_labels
    assert result.chunk.lexical_terms == staged.lexical_terms
    assert result.chunk.dense_embedding == pytest.approx(staged.dense_embedding)
    assert result.lexical_rank == 1
    assert result.dense_rank == 2
    assert result.supported


def test_matched_terms_report_the_callers_words_not_stemmed_lexemes():
    index, _ = build_index([("FROM fused f", [search_row()])])
    results = index.search(
        SearchRequest(query="retrieval evaluation gate", request_id="req-5", principal=OWNER)
    )
    # "evaluation" survives verbatim rather than arriving as the lexeme "evalu".
    assert results[0].matched_terms == ("evaluation", "gate", "retrieval")


def test_vector_round_trips_through_the_text_encoding():
    values = (0.5, -0.25, 0.125)
    assert _encode_vector(values) == "[0.5,-0.25,0.125]"
    assert _decode_vector("[0.5,-0.25,0.125]") == values
    assert _decode_vector([0.5, -0.25, 0.125]) == values
    assert _encode_vector(None) is None
    assert _decode_vector(None) is None


# -- write path --------------------------------------------------------------------


def test_stage_document_writes_the_version_the_staging_row_and_the_chunks():
    index, connection = build_index(CANDIDATE)
    index.stage_document("run-1", version(), [chunk()])

    executed = " | ".join(connection.executed())
    assert "INSERT INTO document_versions" in executed
    assert "INSERT INTO run_document_stagings" in executed
    assert connection.batches, "chunks are inserted as one batch"
    batch_sql, rows = connection.batches[0]
    assert "INSERT INTO chunks" in batch_sql
    assert rows[0]["index_run_id"] == "run-1"
    # The lexical index is built from heading plus body, as the in-memory index is.
    assert rows[0]["lexical_source"].startswith("Retrieval evaluation\n\n")
    assert connection.commits == 1


def test_chunks_are_deleted_before_the_staging_row_moves_to_a_new_version():
    """Chunks reference the staging row's content hash, so order is not cosmetic."""
    index, connection = build_index(CANDIDATE)
    index.stage_document("run-1", version(), [chunk()])

    order = connection.executed()
    delete = next(i for i, sql in enumerate(order) if "DELETE FROM chunks" in sql)
    stage = next(i for i, sql in enumerate(order) if "INSERT INTO run_document_stagings" in sql)
    assert delete < stage


def test_staging_into_an_unknown_run_fails_and_rolls_back():
    index, connection = build_index([("SELECT status FROM ingestion_runs", [])])
    with pytest.raises(IngestionError, match="unknown or already applied"):
        index.stage_document("run-missing", version(), [chunk()])
    assert connection.rollbacks == 1
    assert connection.commits == 0


def test_staging_into_an_activated_run_fails():
    index, _ = build_index([("SELECT status FROM ingestion_runs", [("activated",)])])
    with pytest.raises(IngestionError, match="unknown or already applied"):
        index.stage_tombstone("run-1", "notes:note.md")


def test_an_embedding_of_the_wrong_width_is_rejected_before_any_write():
    index, connection = build_index(CANDIDATE)
    with pytest.raises(IngestionError, match="256-dimensional"):
        index.stage_document("run-1", version(), [chunk(dimensions=256)])
    assert connection.statements == []


def test_tombstone_clears_the_runs_chunks_for_that_document():
    index, connection = build_index(CANDIDATE)
    index.stage_tombstone("run-1", "notes:note.md")

    executed = " | ".join(connection.executed())
    assert "DELETE FROM chunks" in executed
    assert "is_tombstone = TRUE" in executed


# -- activation and rollback -------------------------------------------------------


def test_activation_locks_the_pointer_before_moving_it():
    index, connection = build_index([("UPDATE ingestion_runs SET status = 'activated'", [(7,)])])
    index.activate("run-1", activated_by="ci", reason="gate passed")

    order = connection.executed()
    assert "FOR UPDATE" in order[0], "the pointer row is locked first"
    assert "UPDATE active_index_pointer" in order[-1]
    assert connection.parameters_for("UPDATE active_index_pointer")["seq"] == 7
    assert connection.commits == 1


def test_activating_an_already_applied_run_fails_without_touching_the_pointer():
    index, connection = build_index()
    with pytest.raises(IngestionError, match="unknown or already applied"):
        index.activate("run-1")
    assert not any("UPDATE active_index_pointer" in sql for sql in connection.executed())
    assert connection.rollbacks == 1


def test_rollback_retires_the_head_run_and_returns_the_restored_one():
    index, connection = build_index(
        [
            ("SET status = 'rolled_back'", [("run-2",)]),
            ("SELECT run_id, activation_seq", [("run-1", 4)]),
        ]
    )
    assert index.rollback(activated_by="operator", reason="bad eval") == "run-1"
    assert connection.parameters_for("UPDATE active_index_pointer")["run_id"] == "run-1"


def test_rollback_to_an_empty_index_reports_no_active_run():
    index, connection = build_index([("SET status = 'rolled_back'", [("run-1",)])])
    assert index.rollback() is None
    params = connection.parameters_for("UPDATE active_index_pointer")
    assert params["run_id"] is None
    assert params["seq"] == 0


def test_rollback_without_an_activated_run_fails():
    index, connection = build_index()
    with pytest.raises(IngestionError, match="no previous index state"):
        index.rollback()
    assert connection.rollbacks == 1


def test_discard_leaves_the_run_record_as_evidence():
    index, connection = build_index([("SET status = 'discarded'", [("run-1",)])])
    index.discard("run-1")

    executed = " | ".join(connection.executed())
    assert "DELETE FROM run_document_stagings" in executed
    assert "DELETE FROM ingestion_runs" not in executed


def test_discarding_an_unknown_run_is_a_no_op():
    index, connection = build_index()
    index.discard("run-missing")
    assert not any("DELETE FROM" in sql for sql in connection.executed())


# -- registry ----------------------------------------------------------------------


def test_register_source_stores_the_descriptor_configuration_as_json():
    index, connection = build_index()
    index.register_source(
        SourceDescriptor.model_validate(
            {
                "source_id": "notes",
                "source_type": "filesystem",
                "display_name": "Notes",
                "owner": "tomasz",
                "rights_policy": "personal_reference",
                "root": "/notes",
            }
        )
    )
    params = connection.parameters_for("INSERT INTO sources")
    assert params["configuration"] == '{"root": "/notes"}'
    assert params["rights_policy"] == "personal_reference"


# -- migrations --------------------------------------------------------------------


def test_schema_file_matches_the_migrations():
    """A stale `schema.sql` would bootstrap a database the migrations never produce."""
    assert migrate.SCHEMA_FILE.read_text(encoding="utf-8") == migrate.render_schema()


def test_migrations_are_applied_in_filename_order_and_recorded():
    connection = FakeConnection()
    applied = migrate.apply_migrations(factory(connection))

    assert applied == [path.stem for path in migrate.migration_files()]
    executed = " | ".join(connection.executed())
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in executed
    assert "CREATE EXTENSION IF NOT EXISTS vector" in executed
    assert connection.parameters_for("INSERT INTO schema_migrations") == {
        "version": "0001_initial_schema"
    }


def test_already_applied_migrations_are_skipped():
    connection = FakeConnection(
        [("SELECT version FROM schema_migrations", [("0001_initial_schema",)])]
    )
    assert migrate.apply_migrations(factory(connection)) == []
    assert not any("CREATE EXTENSION" in sql for sql in connection.executed())
