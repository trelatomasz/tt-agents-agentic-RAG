from fastapi.testclient import TestClient

from gpc_rag.main import app

client = TestClient(app)


def test_typed_answer_contract():
    response = client.post("/v1/answers", json={"query": "Aster Compact brake pads", "request_id": "req-api"})
    assert response.status_code == 200
    assert response.json()["citations"][0]["catalog_version"]


def test_invalid_input_is_rejected():
    assert client.post("/v1/answers", json={"query": "x", "request_id": "req-api"}).status_code == 422
