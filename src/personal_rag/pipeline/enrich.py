"""Attach the metadata retrieval and access control depend on (specification section 7).

Access labels are copied from the document version, which took them from the source
descriptor. They are never read from document content: section 10 requires the principal
and the source policy to come from server context, and retrieved text is untrusted data.
"""

import re

from ..models import Chunk, DocumentVersion
from .chunk import contextual_text

ENRICHER_VERSION = "enrich/1"

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#._-]*")
STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "not",
        "of",
        "on",
        "or",
        "that",
        "the",
        "then",
        "there",
        "these",
        "this",
        "to",
        "was",
        "what",
        "when",
        "which",
        "why",
        "will",
        "with",
        "you",
        "your",
    }
)


def analyze(text: str) -> list[str]:
    """Tokenize for retrieval. Shared by lexical scoring and the embedder so a term that
    survives analysis is visible to both signals."""
    return [
        token
        for token in TOKEN_PATTERN.findall(text.lower())
        if token not in STOP_WORDS and len(token) > 1
    ]


def lexical_terms(text: str) -> tuple[str, ...]:
    """Terms for sparse retrieval, kept sorted so a rebuild is byte-comparable."""
    return tuple(sorted(set(analyze(text))))


def enrich_chunks(chunks: list[Chunk], version: DocumentVersion) -> list[Chunk]:
    """Fill language, access labels and lexical terms from the owning document version."""
    return [
        chunk.model_copy(
            update={
                "language": chunk.language or version.language,
                "acl_labels": version.acl_labels,
                "lexical_terms": lexical_terms(contextual_text(chunk.heading_path, chunk.text)),
            }
        )
        for chunk in chunks
    ]
