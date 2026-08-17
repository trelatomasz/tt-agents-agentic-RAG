from datetime import UTC, datetime, timedelta

import pytest

from gpc_rag.catalog import Catalog
from gpc_rag.generator import DeterministicGenerator
from gpc_rag.service import (
    CatalogStaleError,
    DependencyFailedError,
    GroundingError,
    NoEvidenceError,
    RagService,
)


def catalog() -> Catalog:
    return Catalog.load("data/catalog.json")


@pytest.mark.asyncio
async def test_answer_contains_versioned_citations():
    result = await RagService(catalog(), DeterministicGenerator(), 3600, 4).ask("brake pad for Aster Compact", "req-1", 1)
    assert result.citations[0].part_id == "BRK-100"
    assert result.citations[0].catalog_version == result.catalog_version
    assert result.retrieval_score > 0.5


@pytest.mark.asyncio
async def test_unknown_query_abstains():
    with pytest.raises(NoEvidenceError):
        await RagService(catalog(), DeterministicGenerator(), 3600, 4).ask("windscreen wiper", "req-2", 1)


@pytest.mark.asyncio
async def test_stale_catalog_fails_closed():
    stale = catalog()
    stale.loaded_at = datetime.now(UTC) - timedelta(hours=2)
    with pytest.raises(CatalogStaleError):
        await RagService(stale, DeterministicGenerator(), 60, 4).ask("brake pad", "req-3", 1)


@pytest.mark.asyncio
async def test_unsupported_model_year_abstains():
    with pytest.raises(NoEvidenceError):
        await RagService(catalog(), DeterministicGenerator(), 3600, 4).ask(
            "brake pads for Aster Compact 2024", "req-4", 1
        )


@pytest.mark.asyncio
async def test_wrong_vehicle_for_explicit_part_abstains():
    with pytest.raises(NoEvidenceError):
        await RagService(catalog(), DeterministicGenerator(), 3600, 4).ask(
            "Does BRK-100 fit Boreal Sedan 2021?", "req-5", 1
        )


@pytest.mark.asyncio
async def test_generator_without_allowed_citation_fails_closed():
    class UngroundedGenerator:
        async def generate(self, query, parts):
            del query, parts
            return "Every part is compatible."

    with pytest.raises(GroundingError):
        await RagService(catalog(), UngroundedGenerator(), 3600, 4).ask(
            "brake pad for Aster Compact", "req-6", 1
        )


@pytest.mark.asyncio
async def test_low_confidence_product_match_abstains():
    with pytest.raises(NoEvidenceError):
        await RagService(catalog(), DeterministicGenerator(), 3600, 4).ask(
            "engine", "req-7", 1
        )


@pytest.mark.asyncio
async def test_generator_failure_is_typed_for_retry():
    class FailingGenerator:
        async def generate(self, query, parts):
            del query, parts
            raise RuntimeError("provider unavailable")

    with pytest.raises(DependencyFailedError):
        await RagService(catalog(), FailingGenerator(), 3600, 4).ask(
            "brake pad for Aster Compact", "req-8", 1
        )
