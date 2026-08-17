import asyncio
import logging
import re
import time
from datetime import UTC, datetime

from .catalog import Catalog
from .generator import AnswerGenerator
from .models import AskResponse, Citation


class CatalogStaleError(RuntimeError):
    pass


class NoEvidenceError(RuntimeError):
    pass


class GroundingError(RuntimeError):
    pass


class DependencyFailedError(RuntimeError):
    pass


logger = logging.getLogger(__name__)
_CITATION = re.compile(r"\[([A-Za-z0-9-]+)\]")


class RagService:
    def __init__(
        self,
        catalog: Catalog,
        generator: AnswerGenerator,
        max_age: int,
        limit: int,
        min_score: float = 2.0,
    ):
        self.catalog, self.generator, self.max_age, self.limit, self.min_score = (
            catalog,
            generator,
            max_age,
            limit,
            min_score,
        )

    async def ask(self, query: str, request_id: str, timeout: float) -> AskResponse:
        started = time.perf_counter()
        age = (datetime.now(UTC) - self.catalog.loaded_at).total_seconds()
        if age > self.max_age:
            raise CatalogStaleError(f"catalog age {age:.0f}s exceeds {self.max_age}s")
        hits = self.catalog.search(query, self.limit, min_score=self.min_score)
        if not hits:
            raise NoEvidenceError("no catalog evidence matched")
        parts = [hit.part for hit in hits]
        try:
            answer = await asyncio.wait_for(self.generator.generate(query, parts), timeout=timeout)
        except TimeoutError:
            raise
        except Exception as exc:
            raise DependencyFailedError("answer generation failed") from exc

        cited_ids = set(_CITATION.findall(answer))
        allowed_ids = {part.part_id for part in parts}
        if not cited_ids or not cited_ids <= allowed_ids:
            raise GroundingError("answer did not contain citations for retrieved evidence")

        citations = [
            Citation(
                source_id=part.source_id,
                catalog_version=part.catalog_version,
                part_id=part.part_id,
                label=f"{part.name} ({part.source_id})",
            )
            for part in parts
            if part.part_id in cited_ids
        ]
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "rag_answer_completed",
            extra={
                "request_id": request_id,
                "catalog_version": self.catalog.version,
                "retrieval_count": len(hits),
                "retrieval_score": max(hit.confidence for hit in hits),
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )
        return AskResponse(
            request_id=request_id,
            answer=answer,
            citations=citations,
            catalog_version=self.catalog.version,
            retrieval_score=max(hit.confidence for hit in hits),
        )
