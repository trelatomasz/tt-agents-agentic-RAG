"""Versioned embedding (specification section 7).

Phase 1 runs entirely offline, so the default embedder is a deterministic hashing model
rather than a network call. It mirrors the `DeterministicGenerator` pattern already used by
the parts pilot: evaluation stays hermetic and a release gate cannot flake on a provider.
The Vertex embedder replaces it in Phase 3 (register entry P-11) behind this same protocol.
"""

import hashlib
import math
from collections import Counter
from typing import Protocol, runtime_checkable

from ..models import Chunk
from .chunk import contextual_text
from .enrich import analyze


@runtime_checkable
class Embedder(Protocol):
    model_id: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...


class HashingEmbedder:
    """Signed feature hashing with sublinear term frequency, L2 normalized.

    Deterministic across processes and machines: Python's built-in `hash` is salted per
    process, so token buckets come from BLAKE2b instead. Quality is adequate for contract
    and pipeline tests; it is not a substitute for a trained embedding model.
    """

    def __init__(self, dimensions: int = 256, model_id: str = "hashing/1"):
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8")
        self.dimensions = dimensions
        self.model_id = model_id

    def _vector(self, text: str) -> tuple[float, ...]:
        counts = Counter(analyze(text))
        values = [0.0] * self.dimensions
        for token, count in counts.items():
            digest = int.from_bytes(
                hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big"
            )
            bucket = digest % self.dimensions
            sign = 1.0 if digest & (1 << 63) else -1.0
            values[bucket] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(value * value for value in values))
        return tuple(value / norm for value in values) if norm else tuple(values)

    def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._vector(text)


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Both operands are already L2 normalized, so the dot product is the similarity."""
    if len(left) != len(right):
        raise ValueError(f"dimension mismatch: {len(left)} != {len(right)}")
    return sum(a * b for a, b in zip(left, right, strict=True))


def embed_chunks(chunks: list[Chunk], embedder: Embedder) -> list[Chunk]:
    """Embed chunks with their heading context and record the model that produced them."""
    if not chunks:
        return []
    vectors = embedder.embed_documents(
        [contextual_text(chunk.heading_path, chunk.text) for chunk in chunks]
    )
    return [
        chunk.model_copy(
            update={
                "dense_embedding": vector,
                "embedding_model": embedder.model_id,
                "embedding_dimensions": embedder.dimensions,
            }
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
