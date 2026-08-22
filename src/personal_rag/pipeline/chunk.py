"""Structure-aware chunking (specification section 7).

Markdown splits by headings, then by blocks, then by sentences — in that order, so a chunk
never straddles two topics when a heading boundary was available. Code fences and tables
are atomic: section 7 forbids flattening them into prose, and a half table is unusable as
evidence.

The 400-800 token range from section 7 is enforced as a ceiling, not a floor. Because
heading sections are never merged, a document of short sections produces chunks well below
the target — the sample corpus yields 54-166 tokens. That is a deliberate reading of
"split by headings first": merging sibling sections to hit a token count would give a chunk
an ambiguous `heading_path` and a citation that points at two topics. Section 7 asks for
this number to be tuned against retrieval recall rather than adopted blindly, so the
evaluation gate (register entry P-20) is what should decide whether small sections need
merging, and overlap only applies within a section that actually had to split.
"""

import re
from dataclasses import dataclass

from ..models import Chunk, DocumentVersion, Locator, build_chunk_id

CHUNKER_VERSION = "markdown-heading/1"

TARGET_TOKENS = 600
MAX_TOKENS = 800
MIN_TOKENS = 80
OVERLAP_RATIO = 0.12

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_TABLE_ROW = re.compile(r"^\s*\|")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def estimate_tokens(text: str) -> int:
    """Roughly four characters per token.

    The embedding provider owns the real count; this only has to be stable and monotonic
    so chunk sizes stay comparable across runs. Replace it when the tokenizer is pinned.
    """
    return max(1, round(len(text) / 4))


@dataclass(frozen=True)
class Block:
    """One atomic piece of a document, with the source lines it came from."""

    kind: str  # "text", "code" or "table"
    text: str
    line_start: int
    line_end: int
    heading_path: tuple[str, ...]

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)

    @property
    def splittable(self) -> bool:
        return self.kind == "text"


def parse_blocks(text: str) -> list[Block]:
    """Split Markdown into heading-scoped blocks, leaving fenced code untouched."""
    blocks: list[Block] = []
    heading_stack: list[tuple[int, str]] = []
    pending: list[str] = []
    pending_start = 0
    kind = "text"
    fence_marker = ""

    def flush() -> None:
        nonlocal pending, pending_start, kind
        body = "\n".join(pending).strip("\n")
        if body.strip():
            blocks.append(
                Block(
                    kind=kind,
                    text=body,
                    line_start=pending_start,
                    line_end=pending_start + len(pending) - 1,
                    heading_path=tuple(title for _, title in heading_stack),
                )
            )
        pending = []
        kind = "text"

    for number, line in enumerate(text.split("\n"), start=1):
        if fence_marker:
            pending.append(line)
            if line.strip().startswith(fence_marker):
                flush()
                fence_marker = ""
            continue

        fence = _FENCE.match(line)
        if fence:
            flush()
            fence_marker = fence.group(1)
            kind = "code"
            pending, pending_start = [line], number
            continue

        heading = _HEADING.match(line)
        if heading:
            flush()
            level, title = len(heading.group(1)), heading.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            continue

        is_table = bool(_TABLE_ROW.match(line))
        if not line.strip():
            flush()
            continue
        if pending and ((kind == "table") != is_table):
            flush()
        if not pending:
            pending_start = number
            kind = "table" if is_table else "text"
        pending.append(line)

    flush()
    return blocks


def contextual_text(heading_path: tuple[str, ...], text: str) -> str:
    """Text used for retrieval signals.

    Headings carry the topic a chunk body often assumes, so they are indexed with the
    chunk. `Chunk.text` stays verbatim so a citation quotes the source, not a synthesis.
    """
    breadcrumb = " > ".join(heading_path)
    return f"{breadcrumb}\n\n{text}" if breadcrumb else text


def _split_oversized(block: Block, max_tokens: int) -> list[Block]:
    """Break a block that cannot fit, preserving line numbers as closely as possible."""
    if block.tokens <= max_tokens:
        return [block]
    units = _SENTENCE.split(block.text) if block.splittable else block.text.split("\n")
    joiner = " " if block.splittable else "\n"

    pieces: list[Block] = []
    current: list[str] = []
    line_cursor = block.line_start

    def emit() -> None:
        nonlocal current, line_cursor
        if not current:
            return
        body = joiner.join(current)
        span = body.count("\n")
        pieces.append(
            Block(
                block.kind,
                body,
                line_cursor,
                min(line_cursor + span, block.line_end),
                block.heading_path,
            )
        )
        line_cursor = min(line_cursor + span + (0 if block.splittable else 1), block.line_end)
        current = []

    for unit in units:
        if current and estimate_tokens(joiner.join([*current, unit])) > max_tokens:
            emit()
        current.append(unit)
    emit()
    return pieces or [block]


def _pack(blocks: list[Block], target: int, maximum: int) -> list[list[Block]]:
    """Greedily group blocks, flushing at the target and never exceeding the maximum."""
    groups: list[list[Block]] = []
    current: list[Block] = []
    total = 0
    for block in blocks:
        if current and total + block.tokens > maximum:
            groups.append(current)
            current, total = [], 0
        current.append(block)
        total += block.tokens
        if total >= target:
            groups.append(current)
            current, total = [], 0
    if current:
        groups.append(current)

    # A short tail is context, not a chunk; fold it back when the merge still fits.
    if len(groups) > 1:
        tail = sum(block.tokens for block in groups[-1])
        head = sum(block.tokens for block in groups[-2])
        if tail < MIN_TOKENS and head + tail <= maximum:
            groups[-2].extend(groups.pop())
    return groups


def _with_overlap(groups: list[list[Block]], overlap_tokens: int) -> list[list[Block]]:
    """Prepend trailing prose from the previous group so a split idea stays retrievable."""
    if overlap_tokens <= 0:
        return groups
    overlapped = [groups[0]]
    for index in range(1, len(groups)):
        carried: list[Block] = []
        budget = overlap_tokens
        for block in reversed(groups[index - 1]):
            if not block.splittable or block.tokens > budget:
                break
            carried.insert(0, block)
            budget -= block.tokens
        overlapped.append(carried + groups[index])
    return overlapped


def chunk_document(
    version: DocumentVersion,
    text: str,
    *,
    target_tokens: int = TARGET_TOKENS,
    max_tokens: int = MAX_TOKENS,
    overlap_ratio: float = OVERLAP_RATIO,
    locator_template: Locator | None = None,
) -> list[Chunk]:
    """Chunk one normalized document into contiguous, individually citable evidence."""
    blocks = parse_blocks(text)
    if not blocks:
        return []

    sections: list[list[Block]] = []
    for block in blocks:
        if sections and sections[-1][0].heading_path == block.heading_path:
            sections[-1].append(block)
        else:
            sections.append([block])

    groups: list[list[Block]] = []
    for section in sections:
        atoms = [piece for block in section for piece in _split_oversized(block, max_tokens)]
        packed = _pack(atoms, target_tokens, max_tokens)
        groups.extend(_with_overlap(packed, round(target_tokens * overlap_ratio)))

    if locator_template is None:
        is_url = "://" in version.source_uri
        template = Locator(
            path=None if is_url else version.source_uri,
            url=version.source_uri if is_url else None,
            commit=version.metadata_json.get("commit"),
        )
    else:
        template = locator_template
    chunks: list[Chunk] = []
    for ordinal, group in enumerate(groups):
        body = "\n\n".join(block.text for block in group).strip()
        if not body:
            continue
        heading_path = group[-1].heading_path
        locator = template.model_copy(
            update={
                "line_start": min(block.line_start for block in group),
                "line_end": max(block.line_end for block in group),
                "fragment": _fragment(heading_path) or template.fragment,
            }
        )
        locator = _source_locator(version, locator)
        chunks.append(
            Chunk(
                chunk_id=build_chunk_id(version.document_id, version.content_hash, ordinal),
                document_id=version.document_id,
                source_id=version.source_id,
                document_version_hash=version.content_hash,
                ordinal=ordinal,
                text=body,
                token_count=estimate_tokens(body),
                language=version.language,
                chunker_version=CHUNKER_VERSION,
                heading_path=heading_path,
                locator=locator,
                acl_labels=version.acl_labels,
            )
        )
    return chunks


def _fragment(heading_path: tuple[str, ...]) -> str | None:
    if not heading_path:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", heading_path[-1].lower()).strip("-")
    return slug or None


def _source_locator(version: DocumentVersion, locator: Locator) -> Locator:
    """Attach page/chapter provenance emitted by binary source adapters."""
    start = locator.line_start or 1
    end = locator.line_end or start
    pages = version.metadata_json.get("pages", [])
    for page in pages:
        if int(page.get("line_end", 0)) >= start and int(page.get("line_start", 0)) <= end:
            return locator.model_copy(update={"page": int(page["page"])})
    chapters = version.metadata_json.get("chapters", [])
    for chapter in chapters:
        if int(chapter.get("line_end", 0)) >= start and int(chapter.get("line_start", 0)) <= end:
            if locator.fragment:
                return locator
            slug = re.sub(r"[^a-z0-9]+", "-", str(chapter.get("name", "")).lower()).strip("-")
            return locator.model_copy(update={"fragment": slug or locator.fragment})
    return locator
