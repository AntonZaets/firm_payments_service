from fastapi.testclient import TestClient

from firm_payments_service.main import app, settings


def test_readiness_with_postgresql() -> None:
    with TestClient(
        app, headers={"X-API-Key": settings.operational_api_key.get_secret_value()}
    ) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
