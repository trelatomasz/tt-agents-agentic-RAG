from fastapi.testclient import TestClient

from gpc_rag import main
from gpc_rag.catalog import Catalog
from gpc_rag.main import app
from gpc_rag.service import RagService

client = TestClient(app)


def test_typed_answer_contract():
    response = client.post(
        "/v1/answers", json={"query": "Aster Compact brake pads", "request_id": "req-api"}
    )
    assert response.status_code == 200
    assert response.json()["citations"][0]["catalog_version"]


def test_invalid_input_is_rejected():
    assert (
        client.post("/v1/answers", json={"query": "x", "request_id": "req-api"}).status_code == 422
    )


def test_dependency_failure_has_retry_contract(monkeypatch):
    class FailingGenerator:
        async def generate(self, query, parts):
            del query, parts
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        main,
        "service",
        RagService(Catalog.load("data/catalog.json"), FailingGenerator(), 3600, 4),
    )
    response = client.post(
        "/v1/answers", json={"query": "Aster Compact brake pads", "request_id": "req-api-fail"}
    )
    assert response.status_code == 502
    assert response.json()["error"] == {
        "code": "DEPENDENCY_FAILED",
        "message": "answer generation failed",
        "retryable": True,
        "fallback": "RETRY",
    }
