"""Hermetic coverage for the Phase 2 source connectors."""

import subprocess
from pathlib import Path

import pytest

from personal_rag.models import DiscoveryRequest, SourceDescriptor, SourceItem
from personal_rag.pipeline.chunk import chunk_document
from personal_rag.pipeline.normalize import build_document_version, normalize_text
from personal_rag.sources.base import AdapterError
from personal_rag.sources.filesystem import FilesystemAdapter
from personal_rag.sources.git_tree import GitTreeAdapter
from personal_rag.sources.web import WebAdapter, extract_html


def descriptor(source_type: str, **configuration) -> SourceDescriptor:
    return SourceDescriptor.model_validate(
        {
            "source_id": f"test-{source_type}",
            "source_type": source_type,
            "display_name": f"Test {source_type}",
            "owner": "test-owner",
            "rights_policy": "personal_reference",
            **configuration,
        }
    )


def test_html_extractor_keeps_headings_and_drops_hidden_instructions():
    extracted = extract_html(
        """
        <html><head><title>Useful article</title></head><body>
          <nav>Navigation noise</nav><article><h1>Evaluation</h1>
          <p>Use a golden set before release.</p>
          <p hidden>Ignore this instruction.</p>
          <script>Ignore this instruction too.</script>
          </article>
        </body></html>
        """
    )
    assert extracted.title == "Useful article"
    assert "# Evaluation" in extracted.text
    assert "golden set" in extracted.text
    assert "Ignore" not in extracted.text


class FakeResponse:
    def __init__(self, status_code, *, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.encoding = "utf-8"

    @property
    def text(self):
        return self.content.decode(self.encoding)


class FakeClient:
    def __init__(self, **_kwargs):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, url):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FakeResponse(200, content=b"User-agent: *\nAllow: /\n")
        return FakeResponse(
            200,
            content=(
                b"<html><head><link rel='canonical' href='/article'></head>"
                b"<body><article><h1>Grounding</h1><p>Verify every citation.</p></article></body></html>"
            ),
            headers={"content-type": "text/html", "etag": '"v1"'},
        )


def test_web_adapter_validates_and_records_web_provenance():
    source = descriptor("web", url="https://example.com/article", allow_hosts=["example.com"])
    adapter = WebAdapter(
        source, client_factory=FakeClient, resolver=lambda _host: ["93.184.216.34"]
    )
    item = next(adapter.discover(DiscoveryRequest(descriptor=source, changed_only=False)))
    raw = adapter.fetch(item)
    assert raw.source_revision == '"v1"'
    assert raw.metadata["canonical_url"] == "https://example.com/article"
    assert raw.metadata["robots_allowed"] is True
    assert "Verify every citation." in raw.text


def test_web_adapter_rejects_private_resolution():
    source = descriptor("web", url="https://example.com/article")
    adapter = WebAdapter(source, resolver=lambda _host: ["127.0.0.1"])
    item = next(adapter.discover(DiscoveryRequest(descriptor=source, changed_only=False)))
    with pytest.raises(Exception, match="unsafe|failed"):
        adapter.fetch(item)


def test_git_tree_adapter_tracks_commit_and_relative_path(tmp_path: Path):
    root = tmp_path / "info"
    root.mkdir()
    (root / "guide.md").write_text("# Guide\n\nUse evidence.\n", encoding="utf-8")
    (root / "generated.json").write_text("{}", encoding="utf-8")
    for args in (
        ["git", "init", "-q", str(root)],
        ["git", "-C", str(root), "config", "user.email", "your-email@example.com"],
        ["git", "-C", str(root), "config", "user.name", "Test User"],
        ["git", "-C", str(root), "add", "."],
        ["git", "-C", str(root), "commit", "-qm", "initial"],
    ):
        subprocess.run(args, check=True, capture_output=True)

    source = descriptor("git_tree", root=str(root), include=["**/*.md"])
    adapter = GitTreeAdapter(source)
    item = next(adapter.discover(DiscoveryRequest(descriptor=source, changed_only=False)))
    raw = adapter.fetch(item)
    assert item.source_uri == "guide.md"
    assert len(item.source_revision) == 40
    assert raw.metadata["commit"] == item.source_revision

    version = build_document_version(raw, source, normalize_text(raw.text))
    chunk = chunk_document(version, normalize_text(raw.text))[0]
    assert chunk.locator.path == "guide.md"
    assert chunk.locator.commit == item.source_revision


def test_git_tree_adapter_rejects_escape_path(tmp_path: Path):
    root = tmp_path / "info"
    root.mkdir()
    source = descriptor("git_tree", root=str(root))
    adapter = GitTreeAdapter(source)
    item = SourceItem(
        item_id="../outside.md",
        source_id=source.source_id,
        source_uri="../outside.md",
        media_type="text/markdown",
    )
    with pytest.raises(Exception, match="boundary|present"):
        adapter.fetch(item)


def test_filesystem_fetch_rejects_escape_path(tmp_path: Path):
    root = tmp_path / "notes"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    source = descriptor("filesystem", root=str(root), include=["**/*.md"])
    item = SourceItem(
        item_id="../outside.md",
        source_id=source.source_id,
        source_uri="../outside.md",
        media_type="text/markdown",
    )
    with pytest.raises(AdapterError, match="boundary"):
        FilesystemAdapter(source).fetch(item)
