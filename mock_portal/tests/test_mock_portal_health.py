from app.main import app
from fastapi.testclient import TestClient


def test_mock_portal_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "mock_portal", "status": "ok"}
