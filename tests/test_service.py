from datetime import UTC, datetime, timedelta

import pytest

from gpc_rag.catalog import Catalog
from gpc_rag.generator import DeterministicGenerator
from gpc_rag.service import CatalogStaleError, NoEvidenceError, RagService


def catalog() -> Catalog:
    return Catalog.load("data/catalog.json")


@pytest.mark.asyncio
async def test_answer_contains_versioned_citations():
    result = await RagService(catalog(), DeterministicGenerator(), 3600, 4).ask("brake pad for Aster Compact", "req-1", 1)
    assert result.citations[0].part_id == "BRK-100"
    assert result.citations[0].catalog_version == result.catalog_version


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
