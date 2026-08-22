"""Read-only Git-tree adapter for the canonical information boundary."""

import fnmatch
import hashlib
import re
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from ..models import DiscoveryRequest, RawDocument, SourceDescriptor, SourceItem
from .base import AdapterError

DEFAULT_INCLUDE = ("**/*.md", "**/*.markdown", "**/*.txt", "**/*.yaml", "**/*.yml")
DEFAULT_EXCLUDE = (".git/**", "atlas/**", "learning/**", "compass/**")
MEDIA_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
}
_TITLE = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.MULTILINE)


class GitTreeAdapter:
    source_type = "git_tree"
    adapter_version = "git-tree/1"
    parser_version = "git-text/1"

    def __init__(self, descriptor: SourceDescriptor) -> None:
        self.descriptor = descriptor
        root = descriptor.configuration.get("root")
        if not root:
            raise ValueError(f"source {descriptor.source_id!r} needs a 'root' configuration key")
        self.root = Path(root).expanduser()
        self.include = tuple(descriptor.configuration.get("include") or DEFAULT_INCLUDE)
        self.exclude = tuple(descriptor.configuration.get("exclude") or DEFAULT_EXCLUDE)

    def discover(self, request: DiscoveryRequest) -> Iterable[SourceItem]:
        commit = self._commit()
        tracked = self._tracked_files()
        yielded = 0
        for relative in tracked:
            if not self._matches(relative):
                continue
            path = self.root / Path(*relative.parts)
            if not self._inside_root(path) or not path.is_file():
                continue
            item_id = relative.as_posix()
            if request.changed_only and request.known_revisions.get(item_id) == commit:
                continue
            stat = path.stat()
            yield SourceItem(
                item_id=item_id,
                source_id=self.descriptor.source_id,
                source_uri=item_id,
                media_type=MEDIA_TYPES.get(path.suffix.lower(), "text/plain"),
                title=path.stem,
                size_bytes=stat.st_size,
                source_revision=commit,
                metadata={"commit": commit, "relative_path": item_id},
            )
            yielded += 1
            if request.limit is not None and yielded >= request.limit:
                return

    def fetch(self, item: SourceItem) -> RawDocument:
        relative = PurePosixPath(item.item_id)
        if relative.is_absolute() or ".." in relative.parts:
            raise AdapterError(
                "path escapes the Git source boundary", item_id=item.item_id, status="quarantined"
            )
        path = self.root.joinpath(*relative.parts)
        if not self._inside_root(path) or not path.is_file():
            raise AdapterError("Git item is not present in the source tree", item_id=item.item_id)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise AdapterError("Git item is not valid UTF-8", item_id=item.item_id) from exc
        except OSError as exc:
            raise AdapterError("cannot read Git item", item_id=item.item_id) from exc
        commit = item.metadata.get("commit") or self._commit()
        heading = _TITLE.search(text)
        return RawDocument(
            item=item,
            text=text,
            title=heading.group(1) if heading else (item.title or item.item_id),
            source_revision=str(commit),
            parser_version=self.parser_version,
            fetched_at=datetime.now(UTC),
            metadata={
                **item.metadata,
                "commit": str(commit),
                "relative_path": item.item_id,
                "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            },
        )

    def fingerprint(self, document: RawDocument) -> str:
        return hashlib.sha256(document.text.encode("utf-8")).hexdigest()

    def _commit(self) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AdapterError(
                "cannot determine the Git source revision", item_id=str(self.root)
            ) from exc
        return result.stdout.strip()

    def _tracked_files(self) -> list[PurePosixPath]:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), "ls-files", "-z"],
                check=True,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AdapterError(
                "cannot enumerate the Git source tree", item_id=str(self.root)
            ) from exc
        return [PurePosixPath(raw.decode("utf-8")) for raw in result.stdout.split(b"\0") if raw]

    def _matches(self, relative: PurePosixPath) -> bool:
        value = relative.as_posix()
        included = any(
            relative.match(pattern)
            or fnmatch.fnmatch(value, pattern)
            or fnmatch.fnmatch(value, pattern.removeprefix("**/"))
            for pattern in self.include
        )
        excluded = any(
            relative.match(pattern)
            or fnmatch.fnmatch(value, pattern)
            or value.startswith(pattern.removesuffix("/**"))
            for pattern in self.exclude
        )
        return included and not excluded

    def _inside_root(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(self.root.resolve())
        except OSError:
            return False
