"""Normalize text and structure, then hash it (specification section 7).

Normalization is deliberately conservative. It removes encoding and whitespace noise that
would otherwise produce a new `content_hash` for unchanged content, and it changes nothing
a reader would notice. Fenced code blocks are left byte-identical because indentation
inside them is content.
"""

import re
import unicodedata

from ..models import (
    DocumentVersion,
    RawDocument,
    SourceDescriptor,
    content_hash,
)

NORMALIZER_VERSION = "normalize/1"

_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})")
_BLANK_RUN = re.compile(r"\n{3,}")

# Diacritics and function words that distinguish Polish legacy material from English.
# Section 8.3 requires the language to be recorded, never silently translated away.
_POLISH_CHARS = set("ąćęłńóśźż")
_POLISH_WORDS = frozenset(
    {"i", "w", "na", "nie", "to", "jest", "się", "że", "do", "z", "oraz", "dla", "jako"}
)
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def normalize_text(text: str) -> str:
    """Return canonical text: NFC, LF endings, no trailing spaces, at most one blank line."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    in_fence = False
    fence_marker = ""
    for line in text.split("\n"):
        fence = _FENCE.match(line)
        if fence and (not in_fence or line.strip().startswith(fence_marker)):
            in_fence = not in_fence
            fence_marker = fence.group(2) if in_fence else ""
            lines.append(line.rstrip())
            continue
        lines.append(line if in_fence else line.rstrip())
    return _BLANK_RUN.sub("\n\n", "\n".join(lines)).strip("\n")


def detect_language(text: str) -> str:
    """Best-effort language tag.

    A frequency heuristic is enough to keep Polish material labelled while the corpus is
    small; replace it with a real detector when a third language appears.
    """
    sample = text.lower()
    if _POLISH_CHARS & set(sample):
        return "pl"
    words = _WORD.findall(sample)[:400]
    if words and sum(word in _POLISH_WORDS for word in words) / len(words) > 0.08:
        return "pl"
    return "en"


def build_document_version(
    raw: RawDocument, descriptor: SourceDescriptor, normalized_text: str
) -> DocumentVersion:
    """Turn one fetched document into the versioned record the index stores."""
    return DocumentVersion(
        document_id=raw.document_id,
        source_id=descriptor.source_id,
        source_uri=raw.item.source_uri,
        title=raw.title,
        media_type=raw.item.media_type,
        language=raw.language or detect_language(normalized_text),
        content_hash=content_hash(normalized_text),
        source_revision=raw.source_revision,
        fetched_at=raw.fetched_at,
        published_at=raw.published_at,
        parser_version=raw.parser_version,
        normalizer_version=NORMALIZER_VERSION,
        visibility=descriptor.visibility,
        rights_policy=descriptor.rights_policy,
        acl_labels=descriptor.acl_labels,
        metadata_json=raw.metadata,
    )
