"""Phase 1: normalize, chunk and publish one Markdown source into a candidate index."""

import pytest

from personal_rag.errors import IngestionError, RightsViolationError
from personal_rag.index.memory import MemoryIndex
from personal_rag.models import SourceDescriptor, content_hash
from personal_rag.pipeline.chunk import chunk_document, estimate_tokens, parse_blocks
from personal_rag.pipeline.embed import HashingEmbedder
from personal_rag.pipeline.normalize import (
    build_document_version,
    detect_language,
    normalize_text,
)
from personal_rag.pipeline.publish import IngestionPipeline
from personal_rag.sources.filesystem import FilesystemAdapter

STRUCTURED = """# Title

Intro paragraph.

## Code section

```python
def keep(value):
    return value
```

## Table section

| Metric | Meaning |
|---|---|
| recall | found at all |
| latency | time to answer |
"""


def descriptor(root, **overrides) -> SourceDescriptor:
    return SourceDescriptor.model_validate(
        {
            "source_id": "local-notes",
            "source_type": "filesystem",
            "display_name": "Notes",
            "owner": "tomasz",
            "rights_policy": "personal_reference",
            "root": str(root),
            "include": ["**/*.md"],
            **overrides,
        }
    )


def pipeline() -> tuple[IngestionPipeline, MemoryIndex]:
    embedder = HashingEmbedder()
    index = MemoryIndex(embedder)
    return IngestionPipeline(index, embedder), index


def write(root, name: str, body: str):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# -- normalize ---------------------------------------------------------------------


def test_cosmetic_edits_do_not_change_the_content_hash():
    """Line endings and trailing whitespace must not produce a new document version."""
    original = "# Title\n\nBody text.\n"
    cosmetic = "# Title   \r\n\r\n\r\nBody text.  \r\n\r\n"
    assert content_hash(normalize_text(original)) == content_hash(normalize_text(cosmetic))


def test_real_edits_do_change_the_content_hash():
    assert content_hash(normalize_text("# A\n\nOne.\n")) != content_hash(
        normalize_text("# A\n\nTwo.\n")
    )


def test_indentation_inside_a_code_fence_is_preserved():
    normalized = normalize_text(STRUCTURED)
    assert "    return value" in normalized


def test_polish_material_keeps_its_language_tag():
    """Section 8.3 forbids silently rewriting Polish legacy notes."""
    assert detect_language("Zwrot kosztów jest częścią umowy oraz zależy od terminu.") == "pl"
    assert detect_language("Retrieval evaluation gates block a release.") == "en"


# -- chunk -------------------------------------------------------------------------


def test_headings_scope_blocks():
    blocks = parse_blocks(normalize_text(STRUCTURED))
    paths = {block.heading_path for block in blocks}
    assert ("Title",) in paths
    assert ("Title", "Code section") in paths
    assert ("Title", "Table section") in paths


def test_code_and_table_blocks_stay_intact():
    """Section 7: tables and code must not be flattened or split into prose."""
    blocks = parse_blocks(normalize_text(STRUCTURED))
    code = next(block for block in blocks if block.kind == "code")
    table = next(block for block in blocks if block.kind == "table")
    assert code.text.startswith("```python") and code.text.rstrip().endswith("```")
    assert table.text.count("\n") == 3


def test_chunks_carry_heading_path_and_line_locators():
    version = _version_for(STRUCTURED)
    chunks = chunk_document(version, normalize_text(STRUCTURED))
    assert chunks
    for chunk in chunks:
        assert chunk.locator.line_start >= 1
        assert chunk.locator.line_end >= chunk.locator.line_start
    assert any(chunk.heading_path == ("Title", "Table section") for chunk in chunks)


def test_oversized_prose_is_split_below_the_maximum():
    body = "# T\n\n" + " ".join(f"Sentence number {index}." for index in range(600))
    version = _version_for(body)
    chunks = chunk_document(version, normalize_text(body), target_tokens=200, max_tokens=300)
    assert len(chunks) > 1
    assert all(estimate_tokens(chunk.text) <= 400 for chunk in chunks)


def test_a_split_section_carries_overlap_into_the_next_chunk():
    """Overlap applies within a section that had to split, so a divided idea stays findable."""
    paragraphs = [
        f"Paragraph {index} discusses evaluation gates and retrieval recall in some detail."
        for index in range(8)
    ]
    body = "# Title\n\n## One long section\n\n" + "\n\n".join(paragraphs) + "\n"
    version = _version_for(body)
    chunks = chunk_document(
        version, normalize_text(body), target_tokens=60, max_tokens=100, overlap_ratio=0.4
    )
    assert len(chunks) > 1
    shared = set(chunks[0].text.split("\n\n")) & set(chunks[1].text.split("\n\n"))
    assert shared, "consecutive chunks of one section must share trailing context"
    assert chunks[1].locator.line_start <= chunks[0].locator.line_end


def test_a_section_that_fits_is_not_split():
    """Heading sections are atomic when they fit; small sections stay whole, not padded."""
    body = "# Title\n\n## A\n\nShort body A.\n\n## B\n\nShort body B.\n"
    version = _version_for(body)
    chunks = chunk_document(version, normalize_text(body))
    assert [chunk.heading_path for chunk in chunks] == [("Title", "A"), ("Title", "B")]


def test_chunk_ordinals_are_contiguous():
    version = _version_for(STRUCTURED)
    chunks = chunk_document(version, normalize_text(STRUCTURED))
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


# -- publish -----------------------------------------------------------------------


def test_markdown_file_reaches_the_index(tmp_path):
    write(tmp_path, "notes.md", STRUCTURED)
    pipe, index = pipeline()
    source = descriptor(tmp_path)

    run = pipe.run(FilesystemAdapter(source), source)
    assert run.status == "staged"
    assert run.counters.documents_indexed == 1
    assert index.chunk_count() == 0, "a staged run must not be searchable"

    pipe.activate(run)
    assert run.status == "succeeded"
    assert index.document_count() == 1
    assert index.chunk_count() > 0


def test_reingesting_unchanged_content_costs_nothing(tmp_path):
    write(tmp_path, "notes.md", STRUCTURED)
    pipe, index = pipeline()
    source = descriptor(tmp_path)
    adapter = FilesystemAdapter(source)
    pipe.activate(pipe.run(adapter, source))
    chunks_after_first = index.chunk_count()

    second = pipe.run(adapter, source)
    assert second.counters.discovered == 0, "an unchanged revision is not rediscovered"
    assert second.counters.documents_indexed == 0
    assert index.chunk_count() == chunks_after_first


def test_cosmetic_rewrite_is_skipped_but_a_real_edit_creates_a_version(tmp_path):
    path = write(tmp_path, "notes.md", "# Title\n\nBody text.\n")
    pipe, index = pipeline()
    source = descriptor(tmp_path)
    adapter = FilesystemAdapter(source)
    pipe.activate(pipe.run(adapter, source))
    first_hash = index.active_version("local-notes:notes.md").content_hash

    path.write_text("# Title\r\n\r\nBody text.   \r\n", encoding="utf-8")
    cosmetic = pipe.run(adapter, source)
    assert cosmetic.counters.skipped_unchanged == 1
    assert cosmetic.counters.documents_indexed == 0

    path.write_text("# Title\n\nBody text, revised.\n", encoding="utf-8")
    real = pipe.run(adapter, source)
    pipe.activate(real)
    assert real.counters.documents_indexed == 1
    assert index.active_version("local-notes:notes.md").content_hash != first_hash


def test_restricted_rights_policy_blocks_ingestion(tmp_path):
    write(tmp_path, "notes.md", STRUCTURED)
    pipe, _ = pipeline()
    source = descriptor(tmp_path, rights_policy="restricted")
    with pytest.raises(RightsViolationError):
        pipe.run(FilesystemAdapter(source), source)


def test_unreadable_file_is_recorded_without_deleting_anything(tmp_path):
    write(tmp_path, "good.md", STRUCTURED)
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe not utf-8 \xff")
    pipe, index = pipeline()
    source = descriptor(tmp_path)

    run = pipe.run(FilesystemAdapter(source), source)
    pipe.activate(run)
    assert run.counters.quarantined == 1
    assert run.counters.tombstoned == 0
    assert [error.code for error in run.errors] == ["UNREADABLE"]
    assert index.document_count() == 1


def test_delete_missing_requires_a_full_snapshot(tmp_path):
    write(tmp_path, "notes.md", STRUCTURED)
    pipe, _ = pipeline()
    source = descriptor(tmp_path)
    with pytest.raises(ValueError):
        pipe.run(FilesystemAdapter(source), source, delete_missing=True, changed_only=True)


def test_full_snapshot_tombstones_a_removed_file(tmp_path):
    write(tmp_path, "keep.md", STRUCTURED)
    removed = write(tmp_path, "drop.md", "# Drop\n\nTemporary note.\n")
    pipe, index = pipeline()
    source = descriptor(tmp_path)
    adapter = FilesystemAdapter(source)
    pipe.activate(pipe.run(adapter, source))
    assert index.document_count() == 2

    removed.unlink()
    run = pipe.run(adapter, source, changed_only=False, delete_missing=True)
    pipe.activate(run)
    assert run.counters.tombstoned == 1
    assert index.active_version("local-notes:drop.md") is None
    assert index.active_version("local-notes:keep.md") is not None


def test_unreadable_file_is_not_tombstoned_by_a_full_snapshot(tmp_path):
    """An adapter failure means present-and-unreadable, never absent."""
    write(tmp_path, "keep.md", STRUCTURED)
    broken = write(tmp_path, "flaky.md", "# Flaky\n\nStill here.\n")
    pipe, index = pipeline()
    source = descriptor(tmp_path)
    adapter = FilesystemAdapter(source)
    pipe.activate(pipe.run(adapter, source))

    broken.write_bytes(b"\xff\xfe broken now \xff")
    run = pipe.run(adapter, source, changed_only=False, delete_missing=True)
    pipe.activate(run)
    assert run.counters.tombstoned == 0
    assert index.active_version("local-notes:flaky.md") is not None


def test_failed_run_leaves_the_active_index_untouched(tmp_path):
    write(tmp_path, "notes.md", STRUCTURED)
    pipe, index = pipeline()
    source = descriptor(tmp_path)
    pipe.activate(pipe.run(FilesystemAdapter(source), source))
    active_before = index.active_run_id()

    class ExplodingAdapter(FilesystemAdapter):
        def discover(self, request):
            raise RuntimeError("source unavailable")

    with pytest.raises(IngestionError):
        pipe.run(ExplodingAdapter(source), source)
    assert index.active_run_id() == active_before
    assert index.document_count() == 1


def test_dry_run_stages_nothing(tmp_path):
    write(tmp_path, "notes.md", STRUCTURED)
    pipe, index = pipeline()
    source = descriptor(tmp_path)

    run = pipe.run(FilesystemAdapter(source), source, dry_run=True)
    assert run.counters.documents_indexed == 1
    assert run.index_run_id is None
    assert index.document_count() == 0
    with pytest.raises(IngestionError):
        pipe.activate(run)


def test_run_records_the_versions_that_produced_it(tmp_path):
    write(tmp_path, "notes.md", STRUCTURED)
    pipe, _ = pipeline()
    source = descriptor(tmp_path)
    run = pipe.run(FilesystemAdapter(source), source)
    assert run.adapter_version == "filesystem-text/1"
    assert run.parser_version == "text-passthrough/1"
    assert run.chunker_version and run.normalizer_version and run.embedding_model


def _version_for(body: str):
    from datetime import UTC, datetime

    from personal_rag.models import RawDocument, SourceItem

    item = SourceItem(
        item_id="notes.md",
        source_id="local-notes",
        source_uri="notes.md",
        media_type="text/markdown",
    )
    raw = RawDocument(
        item=item,
        text=body,
        title="Title",
        source_revision="rev",
        parser_version="text-passthrough/1",
        fetched_at=datetime.now(UTC),
    )
    return build_document_version(raw, descriptor("unused"), normalize_text(body))
