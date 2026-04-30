from fastapi.testclient import TestClient

from egd_parser.api.app import app


def test_healthcheck() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app_env"] == "test"
    assert payload["ocr_engine"] == "mock"
    assert "storage" in payload
    assert "models" in payload
