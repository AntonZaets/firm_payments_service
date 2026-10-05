import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.security import APIKeyHeader
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from firm_payments_service.database import make_engine
from firm_payments_service.settings import Settings

settings = Settings()
engine = make_engine(settings)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("Application started")
    try:
        yield
    finally:
        engine.dispose()
        logger.info("Application stopped")


def require_operational_key(
    key: Annotated[
        str | None, Depends(APIKeyHeader(name="X-API-Key", auto_error=False))
    ],
) -> None:
    if key is None or not compare_digest(
        key.encode(), settings.operational_api_key.get_secret_value().encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")


app = FastAPI(title="Firm Payments Service", lifespan=lifespan)
Instrumentator().instrument(app).expose(
    app, include_in_schema=False, dependencies=[Depends(require_operational_key)]
)


@app.get("/health/live", dependencies=[Depends(require_operational_key)])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", dependencies=[Depends(require_operational_key)])
def readiness(response: Response) -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("Database readiness check failed")
        response.status_code = 503
        return {"status": "unavailable"}
    return {"status": "ok"}
