from fastapi.testclient import TestClient

from firm_payments_service.main import app


def test_readiness_with_postgresql() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
