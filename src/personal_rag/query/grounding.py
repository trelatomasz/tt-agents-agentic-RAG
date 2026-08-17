"""Citation validation (specification section 9, step 8).

An answer is accepted only when every identifier it cites was actually retrieved for this
request. That makes an ungrounded answer a typed failure rather than a plausible paragraph,
and it is the control that stops a model from inventing a source or citing a chunk the
principal was never allowed to see.
"""

import re

from ..errors import GroundingError
from ..models import Chunk, Citation, DocumentVersion

_CITATION = re.compile(r"\[([A-Za-z0-9._:@#/-]+)\]")


def extract_citations(answer: str) -> set[str]:
    """Every bracketed identifier the answer claims as evidence."""
    return set(_CITATION.findall(answer))


def validate_citations(answer: str, allowed_chunk_ids: set[str]) -> set[str]:
    """Return the cited identifiers, or raise when the answer is not grounded."""
    cited = extract_citations(answer)
    if not cited:
        raise GroundingError("answer cited no evidence")
    unknown = cited - allowed_chunk_ids
    if unknown:
        raise GroundingError(f"answer cited evidence that was not retrieved: {sorted(unknown)}")
    return cited


def build_citations(
    chunks: list[Chunk], versions: dict[str, DocumentVersion], cited_chunk_ids: set[str]
) -> list[Citation]:
    """Turn cited chunks into verifiable citations, preserving evidence order."""
    citations: list[Citation] = []
    for chunk in chunks:
        if chunk.chunk_id not in cited_chunk_ids:
            continue
        version = versions.get(chunk.document_id)
        if version is None:
            raise GroundingError(f"no active version backs cited chunk {chunk.chunk_id!r}")
        citations.append(Citation.from_chunk(chunk, version))
    return citations
