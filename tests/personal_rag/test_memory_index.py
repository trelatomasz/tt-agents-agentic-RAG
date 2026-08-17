"""Phase 1: access filtering, hybrid retrieval and the candidate/active index pointer."""

import pytest

from personal_rag.errors import IngestionError
from personal_rag.index.memory import MemoryIndex
from personal_rag.models import Principal, SearchRequest, SourceDescriptor
from personal_rag.pipeline.embed import HashingEmbedder
from personal_rag.pipeline.publish import IngestionPipeline
from personal_rag.sources.filesystem import FilesystemAdapter

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


def build(tmp_path, sources: list[tuple[str, str, dict]]):
    """Ingest and activate one file per source. Each source gets its own root directory."""
    embedder = HashingEmbedder()
    index = MemoryIndex(embedder)
    pipe = IngestionPipeline(index, embedder)
    for name, body, options in sources:
        root = tmp_path / options.get("source_id", "notes")
        root.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(body, encoding="utf-8")
        source = descriptor(root, **options)
        pipe.activate(pipe.run(FilesystemAdapter(source), source))
    return index, pipe


NOTES_SOURCE = ("note.md", NOTE, {})
HR_SOURCE = ("secret.md", SECRET, {"source_id": "hr", "owner": "someone-else"})


def search(index, query, principal=OWNER, **kwargs):
    return index.search(
        SearchRequest(query=query, request_id="req-1", principal=principal, **kwargs)
    )


def test_readable_chunks_are_ranked(tmp_path):
    index, _ = build(tmp_path, [NOTES_SOURCE])
    results = search(index, "what is a retrieval evaluation gate")
    assert results
    assert results[0].score > 0
    assert results[0].chunk.source_id == "notes"


def test_another_owners_private_source_is_filtered_before_ranking(tmp_path):
    """Section 10: access labels are applied before retrieval, not in the prompt."""
    index, _ = build(tmp_path, [NOTES_SOURCE, HR_SOURCE])
    results = search(index, "compensation review for the platform team")
    assert all(result.chunk.source_id != "hr" for result in results)


def test_owner_sees_their_own_second_source(tmp_path):
    index, _ = build(tmp_path, [NOTES_SOURCE, ("secret.md", SECRET, {"source_id": "personal-hr"})])
    results = search(index, "compensation review for the platform team")
    assert any(result.chunk.source_id == "personal-hr" for result in results)


def test_source_ids_narrow_a_search_but_never_grant_access(tmp_path):
    index, _ = build(tmp_path, [NOTES_SOURCE, HR_SOURCE])
    narrowed = search(index, "retrieval evaluation gate", source_ids=frozenset({"notes"}))
    assert {result.chunk.source_id for result in narrowed} == {"notes"}

    requested = search(index, "compensation review", source_ids=frozenset({"hr"}))
    assert requested == []


def test_staged_run_is_invisible_until_activation(tmp_path):
    index, pipe = build(tmp_path, [NOTES_SOURCE])
    root = tmp_path / "notes"
    (root / "second.md").write_text(
        "# Second\n\nA candidate-only note about tombstones.\n", "utf-8"
    )
    source = descriptor(root)

    run = pipe.run(FilesystemAdapter(source), source)
    assert not search(index, "candidate-only note about tombstones")

    pipe.activate(run)
    assert search(index, "candidate-only note about tombstones")


def test_rollback_restores_the_previous_active_index(tmp_path):
    index, pipe = build(tmp_path, [NOTES_SOURCE])
    first_run = index.active_run_id()
    root = tmp_path / "notes"
    (root / "second.md").write_text("# Second\n\nA note about tombstones and rollback.\n", "utf-8")
    source = descriptor(root)
    pipe.activate(pipe.run(FilesystemAdapter(source), source))
    assert index.document_count() == 2

    assert index.rollback() == first_run
    assert index.document_count() == 1
    assert not search(index, "tombstones and rollback")


def test_rollback_without_history_is_refused():
    with pytest.raises(IngestionError):
        MemoryIndex(HashingEmbedder()).rollback()


def test_discarded_run_cannot_be_activated(tmp_path):
    index, _ = build(tmp_path, [NOTES_SOURCE])
    run_id = index.open_run("notes")
    index.discard(run_id)
    with pytest.raises(IngestionError):
        index.activate(run_id)


def test_both_retrieval_signals_contribute(tmp_path):
    """A hybrid index must rank a chunk that only one of the two signals found."""
    index, _ = build(tmp_path, [NOTES_SOURCE])
    results = search(index, "abstention rewards a system that always produces something")
    assert results
    assert any(result.lexical_rank is not None for result in results)
    assert any(result.dense_rank is not None for result in results)


def test_unrelated_query_returns_no_supported_evidence(tmp_path):
    index, _ = build(tmp_path, [NOTES_SOURCE])
    assert not [
        result for result in search(index, "espresso grinder burr alignment") if result.supported
    ]
