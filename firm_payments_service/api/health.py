import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from firm_payments_service.auth import require_operational_key
from firm_payments_service.db.session import engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health/live", dependencies=[Depends(require_operational_key)])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", dependencies=[Depends(require_operational_key)])
def readiness(request: Request, response: Response) -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("Database readiness check failed")
        response.status_code = 503
        return {"status": "unavailable", "request_id": request.state.request_id}
    return {"status": "ok"}
