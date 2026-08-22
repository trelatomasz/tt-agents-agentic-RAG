"""Local filesystem adapter for text and Windows ebook formats (specification section 8.1).

The adapter keeps discovery, hashing and boundary checks common to every file type. Parser
engines are imported lazily so descriptor validation and text-only callers do not need to
initialize either native PDF or EPUB support.
"""

import hashlib
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from ..models import DiscoveryRequest, RawDocument, SourceDescriptor, SourceItem
from .base import AdapterError

DEFAULT_INCLUDE = ("**/*.md", "**/*.markdown", "**/*.txt", "**/*.pdf", "**/*.epub")
MEDIA_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
}

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
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(self.root.resolve()):
                raise AdapterError(
                    "path escapes the filesystem source boundary",
                    item_id=item.item_id,
                    status="quarantined",
                )
            path = resolved
        except AdapterError:
            raise
        except OSError as exc:
            raise AdapterError(
                "filesystem item is not present", item_id=item.item_id, status="unreadable"
            ) from exc
        suffix = path.suffix.lower()
        if suffix not in MEDIA_TYPES:
            raise AdapterError(
                f"{suffix or 'file'} is not a supported text format",
                item_id=item.item_id,
                status="unsupported",
            )
        try:
            if suffix == ".pdf":
                text, metadata = _read_pdf(path, item.item_id)
            elif suffix == ".epub":
                text, metadata = _read_epub(path, item.item_id)
            else:
                text = path.read_text(encoding="utf-8")
                metadata = {}
        except (UnicodeDecodeError, OSError) as exc:
            raise AdapterError(
                f"cannot read {item.item_id}", item_id=item.item_id, status="unreadable"
            ) from exc
        except _ParserFailure as exc:
            raise AdapterError(str(exc), item_id=item.item_id, status="unreadable") from exc

        heading = _TITLE.search(text)
        return RawDocument(
            item=item,
            text=text,
            title=heading.group(1) if heading else (item.title or item.item_id),
            source_revision=item.source_revision or _file_hash(path),
            parser_version=metadata.pop("parser_version", self.parser_version),
            fetched_at=datetime.now(UTC),
            metadata={**item.metadata, "relative_path": item.item_id, **metadata},
        )

    def fingerprint(self, document: RawDocument) -> str:
        return hashlib.sha256(document.text.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(131072), b""):
            digest.update(block)
    return digest.hexdigest()


class _ParserFailure(RuntimeError):
    """An installed parser could not decode one ebook."""


def _read_pdf(path: Path, item_id: str) -> tuple[str, dict]:
    try:
        import pymupdf
    except ImportError as exc:
        raise _ParserFailure("PDF support requires the PyMuPDF dependency") from exc

    try:
        pages: list[str] = []
        page_metadata: list[dict[str, int]] = []
        line_cursor = 1
        with pymupdf.open(path) as document:
            for page_number, page in enumerate(document, start=1):
                page_text = page.get_text("text").replace("\r\n", "\n").replace("\r", "\n").strip()
                if not page_text:
                    continue
                pages.append(page_text)
                line_count = max(1, page_text.count("\n") + 1)
                page_metadata.append(
                    {
                        "page": page_number,
                        "line_start": line_cursor,
                        "line_end": line_cursor + line_count - 1,
                    }
                )
                line_cursor += line_count + 2
        if not pages:
            raise _ParserFailure(f"{item_id} contains no extractable PDF text")
        return "\n\n".join(pages), {
            "pages": page_metadata,
            "parser_version": "pymupdf/1",
        }
    except _ParserFailure:
        raise
    except Exception as exc:  # parser-specific exceptions vary between PyMuPDF releases
        raise _ParserFailure(f"cannot parse PDF {item_id}") from exc


def _read_epub(path: Path, item_id: str) -> tuple[str, dict]:
    try:
        from ebooklib import ITEM_DOCUMENT, epub
    except ImportError as exc:
        raise _ParserFailure("EPUB support requires the ebooklib dependency") from exc

    try:
        book = epub.read_epub(str(path), options={"ignore_ncx": True})
        sections: list[str] = []
        chapters: list[dict[str, str | int]] = []
        for chapter_number, item in enumerate(book.get_items_of_type(ITEM_DOCUMENT), start=1):
            body = _html_to_markdown(item.get_content().decode("utf-8", errors="replace"))
            if not body.strip():
                continue
            title = item.get_name() or f"chapter-{chapter_number}"
            sections.append(body)
            line_start = sum(section.count("\n") + 3 for section in sections[:-1]) + 1
            chapters.append(
                {
                    "chapter": chapter_number,
                    "name": title,
                    "line_start": line_start,
                    "line_end": line_start + body.count("\n"),
                }
            )
        if not sections:
            raise _ParserFailure(f"{item_id} contains no extractable EPUB text")
        return "\n\n".join(sections), {
            "chapters": chapters,
            "parser_version": "ebooklib/1",
        }
    except _ParserFailure:
        raise
    except Exception as exc:
        raise _ParserFailure(f"cannot parse EPUB {item_id}") from exc


def _html_to_markdown(html: str) -> str:
    """Use the shared small HTML reader without making ebook parsing depend on a browser."""
    from .web import extract_html

    return extract_html(html).text
