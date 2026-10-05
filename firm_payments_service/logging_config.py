import logging
from contextvars import ContextVar
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import Request, Response
from pythonjsonlogger.json import JsonFormatter
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger(__name__)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


async def log_request(request: Request, call_next: RequestResponseEndpoint) -> Response:
    identifier = str(uuid4())
    request.state.request_id = identifier
    token = request_id.set(identifier)
    started = perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unexpected request failure")
            response = JSONResponse(
                {"request_id": identifier, "detail": "Internal server error"},
                status_code=500,
            )
        response.headers["X-Request-ID"] = identifier
        route = request.scope.get("route")
        logger.info(
            "Request completed",
            extra={
                "route": getattr(route, "path", "<unmatched>"),
                "status": response.status_code,
                "duration": perf_counter() - started,
                "outcome": "success" if response.status_code < 400 else "failure",
            },
        )
        return response
    finally:
        request_id.reset(token)


def logging_config(level: str) -> dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": JsonFormatter,
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            }
        },
        "filters": {"request_id": {"()": RequestIdFilter}},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "filters": ["request_id"],
                "stream": "ext://sys.stdout",
            }
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            "uvicorn": {"handlers": [], "propagate": True, "level": level},
            "uvicorn.error": {"handlers": [], "propagate": True, "level": level},
            "uvicorn.access": {"handlers": [], "propagate": True, "level": level},
        },
    }
