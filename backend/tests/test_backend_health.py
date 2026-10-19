from app.main import app
from fastapi.testclient import TestClient


def test_backend_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "backend", "status": "ok"}
