"""Phase 0 exit condition: the contracts hold before any adapter depends on them."""

import pytest
from pydantic import ValidationError

from personal_rag.models import (
    Chunk,
    DocumentVersion,
    Locator,
    Principal,
    SearchRequest,
    SourceDescriptor,
    SourceItem,
    build_chunk_id,
    content_hash,
)
from personal_rag.sources.base import AdapterError, SourceAdapter, load_descriptor
from personal_rag.sources.filesystem import FilesystemAdapter

DESCRIPTOR = {
    "source_id": "tt-root-info",
    "source_type": "git_tree",
    "display_name": "tt-root canonical information",
    "owner": "tomasz",
    "rights_policy": "personal_reference",
    "root": r"D:\src\tt-root.git\info",
    "include": ["**/*.md"],
}


def test_specification_descriptor_example_loads():
    descriptor = load_descriptor("data/personal/sources/tt-root-info.yaml")
    assert descriptor.source_id == "tt-root-info"
    assert descriptor.refresh_policy == "on_commit"
    assert descriptor.configuration["root"] == r"D:\src\tt-root.git\info"


def test_adapter_specific_keys_fold_into_configuration():
    descriptor = SourceDescriptor.model_validate(DESCRIPTOR)
    assert descriptor.configuration["include"] == ["**/*.md"]
    assert not hasattr(descriptor, "root")


def test_visibility_defaults_to_private():
    assert SourceDescriptor.model_validate(DESCRIPTOR).visibility == "private"


def test_restricted_rights_policy_forbids_storage_and_processing():
    descriptor = SourceDescriptor.model_validate({**DESCRIPTOR, "rights_policy": "restricted"})
    assert not descriptor.allows_storage
    assert not descriptor.allows_model_processing


def test_rights_policy_is_required():
    payload = {key: value for key, value in DESCRIPTOR.items() if key != "rights_policy"}
    with pytest.raises(ValidationError):
        SourceDescriptor.model_validate(payload)


def test_owner_principal_reads_own_private_source_but_not_another_owners():
    descriptor = SourceDescriptor.model_validate(DESCRIPTOR)
    assert Principal.owner("tomasz").may_read(descriptor.acl_labels)
    assert not Principal.owner("someone-else").may_read(descriptor.acl_labels)


def test_public_source_is_readable_by_any_principal():
    descriptor = SourceDescriptor.model_validate({**DESCRIPTOR, "visibility": "public"})
    assert Principal.owner("someone-else").may_read(descriptor.acl_labels)


def test_document_id_is_stable_across_content_changes():
    item = SourceItem(
        item_id="notes/a.md", source_id="local", source_uri="notes/a.md", media_type="text/markdown"
    )
    assert item.document_id == "local:notes/a.md"
    assert content_hash("one") != content_hash("two")


def test_chunk_id_is_stable_per_version_and_ordinal():
    first = build_chunk_id("local:a.md", content_hash("body"), 0)
    assert first == build_chunk_id("local:a.md", content_hash("body"), 0)
    assert first != build_chunk_id("local:a.md", content_hash("body"), 1)
    assert first != build_chunk_id("local:a.md", content_hash("other"), 0)


def test_locator_reconstructs_a_human_reference():
    locator = Locator(path="notes/a.md", line_start=12, line_end=40)
    assert locator.human_reference(("Retrieval", "Gates")) == "notes/a.md:12-40 § Retrieval > Gates"


def test_adapter_error_cannot_claim_a_deletion():
    """Section 7: an adapter failure must never be interpreted as a delete."""
    with pytest.raises(ValueError):
        AdapterError("gone", item_id="a.md", status="deleted")
    assert AdapterError("bad bytes", item_id="a.md", status="unreadable").status == "unreadable"


def test_filesystem_adapter_satisfies_the_source_contract():
    adapter = FilesystemAdapter(
        SourceDescriptor.model_validate({**DESCRIPTOR, "root": "data/personal/notes"})
    )
    assert isinstance(adapter, SourceAdapter)


def test_search_request_rejects_a_client_supplied_principal_grant_escalation():
    """`source_ids` narrows a search; the grant set comes from the principal alone."""
    request = SearchRequest(
        query="retrieval gate",
        request_id="req-1",
        principal=Principal.owner("tomasz"),
        source_ids=frozenset({"secret-source"}),
    )
    assert "secret-source" not in request.principal.grants


def test_contract_records_are_immutable():
    version = DocumentVersion(
        document_id="local:a.md",
        source_id="local",
        source_uri="a.md",
        title="A",
        media_type="text/markdown",
        language="en",
        content_hash=content_hash("body"),
        source_revision="rev",
        fetched_at="2026-08-17T00:00:00Z",
        parser_version="p/1",
        normalizer_version="n/1",
        visibility="private",
        rights_policy="personal_reference",
    )
    with pytest.raises(ValidationError):
        version.content_hash = "tampered"

    chunk = Chunk(
        chunk_id="c",
        document_id="local:a.md",
        source_id="local",
        document_version_hash="h",
        ordinal=0,
        text="body",
        token_count=1,
        language="en",
        chunker_version="c/1",
    )
    with pytest.raises(ValidationError):
        chunk.acl_labels = ("public",)
