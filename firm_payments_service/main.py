import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from firm_payments_service.api.health import router as health_router
from firm_payments_service.db.session import engine
from firm_payments_service.observability.logging import log_request
from firm_payments_service.observability.metrics import register_metrics

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("Application started")
    try:
        yield
    finally:
        engine.dispose()
        logger.info("Application stopped")


app = FastAPI(title="Firm Payments Service", lifespan=lifespan)
app.middleware("http")(log_request)
app.include_router(health_router)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        {"request_id": request.state.request_id, "detail": exc.detail},
        status_code=exc.status_code,
        headers=exc.headers,
    )


register_metrics(app)
