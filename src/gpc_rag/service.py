import asyncio
from datetime import UTC, datetime

from .catalog import Catalog
from .generator import AnswerGenerator
from .models import AskResponse, Citation


class CatalogStaleError(RuntimeError): pass
class NoEvidenceError(RuntimeError): pass


class RagService:
    def __init__(self, catalog: Catalog, generator: AnswerGenerator, max_age: int, limit: int):
        self.catalog, self.generator, self.max_age, self.limit = catalog, generator, max_age, limit

    async def ask(self, query: str, request_id: str, timeout: float) -> AskResponse:
        age = (datetime.now(UTC) - self.catalog.loaded_at).total_seconds()
        if age > self.max_age:
            raise CatalogStaleError(f"catalog age {age:.0f}s exceeds {self.max_age}s")
        parts = self.catalog.search(query, self.limit)
        if not parts:
            raise NoEvidenceError("no catalog evidence matched")
        answer = await asyncio.wait_for(self.generator.generate(query, parts), timeout=timeout)
        citations = [Citation(source_id=p.source_id, catalog_version=p.catalog_version, part_id=p.part_id, label=f"{p.name} ({p.source_id})") for p in parts]
        return AskResponse(request_id=request_id, answer=answer, citations=citations, catalog_version=self.catalog.version)
