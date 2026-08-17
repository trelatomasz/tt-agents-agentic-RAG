"""Local filesystem adapter, text formats only (specification section 8.1).

Phase 1 needs one Markdown file to reach a cited answer, so this adapter handles Markdown
and plain text. PDF and EPUB parsing arrives in Phase 2 (register entry P-04) as extra
media types here; discovery, revision tracking and the escape guard below are already the
shape that ebook ingestion needs.
"""

import hashlib
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from ..models import DiscoveryRequest, RawDocument, SourceDescriptor, SourceItem
from .base import AdapterError

DEFAULT_INCLUDE = ("**/*.md", "**/*.markdown", "**/*.txt")
MEDIA_TYPES = {".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain"}

_TITLE = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.MULTILINE)


class FilesystemAdapter:
    source_type = "filesystem"
    adapter_version = "filesystem-text/1"
    parser_version = "text-passthrough/1"

    def __init__(self, descriptor: SourceDescriptor):
        configuration = descriptor.configuration
        root = configuration.get("root")
        if not root:
            raise ValueError(f"source {descriptor.source_id!r} needs a 'root' configuration key")
        self.descriptor = descriptor
        self.root = Path(root).expanduser()
        self.include = tuple(configuration.get("include") or DEFAULT_INCLUDE)
        self.exclude = tuple(configuration.get("exclude") or ())

    def discover(self, request: DiscoveryRequest) -> Iterable[SourceItem]:
        """Walk the root, refusing to follow links or junctions that leave it."""
        if not self.root.is_dir():
            raise AdapterError(
                f"root {self.root} is not a directory",
                item_id=self.descriptor.source_id,
                status="unreadable",
            )
        boundary = self.root.resolve()
        excluded = {path for pattern in self.exclude for path in self.root.glob(pattern)}
        included = sorted(
            {
                path
                for pattern in self.include
                for path in self.root.glob(pattern)
                if path.is_file() and path not in excluded
            }
        )

        yielded = 0
        for path in included:
            resolved = path.resolve()
            if not resolved.is_relative_to(boundary):
                continue
            relative = PurePosixPath(path.relative_to(self.root).as_posix())

            # Hashing during discovery keeps `changed_only` exact rather than clock based;
            # a corpus large enough for that to hurt needs the manifest of section 8.1.
            revision = _file_hash(resolved)
            item_id = str(relative)
            if request.changed_only and request.known_revisions.get(item_id) == revision:
                continue
            stat = resolved.stat()
            yield SourceItem(
                item_id=item_id,
                source_id=self.descriptor.source_id,
                source_uri=item_id,
                media_type=MEDIA_TYPES.get(resolved.suffix.lower(), "application/octet-stream"),
                title=relative.stem,
                size_bytes=stat.st_size,
                source_revision=revision,
                metadata={"modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()},
            )
            yielded += 1
            if request.limit is not None and yielded >= request.limit:
                return

    def fetch(self, item: SourceItem) -> RawDocument:
        path = self.root / item.item_id
        suffix = path.suffix.lower()
        if suffix not in MEDIA_TYPES:
            raise AdapterError(
                f"{suffix or 'file'} is not a supported text format",
                item_id=item.item_id,
                status="unsupported",
            )
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise AdapterError(
                f"{item.item_id} is not valid UTF-8", item_id=item.item_id, status="unreadable"
            ) from exc
        except OSError as exc:
            raise AdapterError(
                f"cannot read {item.item_id}", item_id=item.item_id, status="unreadable"
            ) from exc

        heading = _TITLE.search(text)
        return RawDocument(
            item=item,
            text=text,
            title=heading.group(1) if heading else (item.title or item.item_id),
            source_revision=item.source_revision or _file_hash(path),
            parser_version=self.parser_version,
            fetched_at=datetime.now(UTC),
            metadata={**item.metadata, "relative_path": item.item_id},
        )

    def fingerprint(self, document: RawDocument) -> str:
        return hashlib.sha256(document.text.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(131072), b""):
            digest.update(block)
    return digest.hexdigest()
