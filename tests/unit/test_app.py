import json
import logging
from io import StringIO
from logging.config import dictConfig
from typing import NoReturn

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from firm_payments_service.logging_config import logging_config
from firm_payments_service.main import app, engine


def test_liveness_and_metrics() -> None:
    with TestClient(app) as client:
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
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
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
