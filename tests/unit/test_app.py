import json
import logging
from io import StringIO
from logging.config import dictConfig
from typing import NoReturn

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from firm_payments_service.logging_config import logging_config
from firm_payments_service.main import app, engine, settings


def test_liveness_and_metrics() -> None:
    with TestClient(
        app, headers={"X-API-Key": settings.operational_api_key.get_secret_value()}
    ) as client:
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "text/plain" in metrics.headers["content-type"]
        assert "python_info" in metrics.text
        assert (
            'http_requests_total{handler="/health/live",method="GET",status="2xx"}'
            in metrics.text
        )
        assert (
            'http_request_duration_seconds_count{handler="/health/live",method="GET"}'
            in metrics.text
        )
        assert "/metrics" not in client.get("/openapi.json").json()["paths"]


def test_readiness_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fail() -> NoReturn:
        raise OperationalError(None, None, Exception("secret-password"))

    monkeypatch.setattr(engine, "connect", fail)
    with TestClient(
        app, headers={"X-API-Key": settings.operational_api_key.get_secret_value()}
    ) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "unavailable",
            "request_id": response.headers["X-Request-ID"],
        }
        assert "secret-password" not in response.text
        assert "secret-password" not in caplog.text


def test_json_logging() -> None:
    stream = StringIO()
    config = logging_config("INFO")
    config["handlers"]["console"]["stream"] = stream
    previous_handlers = logging.root.handlers[:]
    previous_level = logging.root.level
    try:
        dictConfig(config)
        for name in ["firm_payments_service", "uvicorn.error", "uvicorn.access"]:
            logging.getLogger(name).info("smoke test")
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert len(records) == 3
        assert all(record["message"] == "smoke test" for record in records)
        assert all(record["levelname"] == "INFO" for record in records)
    finally:
        logging.root.handlers = previous_handlers
        logging.root.setLevel(previous_level)


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/metrics"])
@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong-key"}])
def test_operational_endpoints_require_key(path: str, headers: dict[str, str]) -> None:
    with TestClient(app) as client:
        assert client.get(path, headers=headers).status_code == 401


def test_operational_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    from firm_payments_service.settings import Settings

    monkeypatch.setenv("OPERATIONAL_API_KEY", "")
    with pytest.raises(ValidationError):
        Settings()


def test_request_correlation(caplog: pytest.LogCaptureFixture) -> None:
    from uuid import UUID

    with (
        caplog.at_level(logging.INFO),
        TestClient(
            app, headers={"X-API-Key": settings.operational_api_key.get_secret_value()}
        ) as client,
    ):
        response = client.get(
            "/health/live?secret=never-log-me", headers={"X-Request-ID": "client-id"}
        )
        identifier = response.headers["X-Request-ID"]
        assert str(UUID(identifier)) == identifier
        record = next(r for r in caplog.records if r.message == "Request completed")
        assert record.__dict__["route"] == "/health/live"
        assert record.__dict__["status"] == 200
        assert record.__dict__["duration"] >= 0
        assert record.__dict__["outcome"] == "success"
        assert "never-log-me" not in record.message
        denied = client.get("/metrics", headers={"X-API-Key": "bad"})
        assert denied.json()["request_id"] == denied.headers["X-Request-ID"]
        assert denied.headers["X-Request-ID"] != identifier


def test_unexpected_failure_is_correlated(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fail() -> NoReturn:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(engine, "connect", fail)
    with TestClient(
        app, headers={"X-API-Key": settings.operational_api_key.get_secret_value()}
    ) as client:
        response = client.get("/health/ready")
    assert response.status_code == 500
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    record = next(
        r for r in caplog.records if r.message == "Unexpected request failure"
    )
    assert record.exc_info is not None
    assert "unexpected failure" not in response.text
