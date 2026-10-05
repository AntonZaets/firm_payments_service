import logging
from json import JSONDecodeError
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from firm_payments_service.api.schemas import Error, InvalidRequest, validate_request
from firm_payments_service.config import Settings
from firm_payments_service.observability.metrics import (
    record_payment_batch,
    record_payment_transaction_failure,
)
from firm_payments_service.payments.service import SerializationExhausted, transfer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/payments")
settings = Settings()


async def payment_body(request: Request) -> tuple[Any, dict[str, Any] | None]:
    try:
        body = await request.json()
    except JSONDecodeError:
        return None, None
    return body, cast(dict[str, Any], body) if isinstance(body, dict) else None


def _errors(request_id: str, errors: list[Error]) -> JSONResponse:
    record_payment_batch("rejected")
    return JSONResponse(
        {"request_id": request_id, "errors": [error.__dict__ for error in errors]},
        status_code=422,
    )


@router.post("/bulk", status_code=201)
def bulk_payment(
    request: Request, body: tuple[Any, dict[str, Any] | None] = Depends(payment_body)
) -> JSONResponse:
    value, raw = body
    if raw is None and value is None:
        return _errors(
            request.state.request_id, [Error("INVALID_JSON", "Body is not valid JSON.")]
        )
    try:
        payment = validate_request(value, settings)
        if raw is None:
            raise RuntimeError("validated request body is not an object")
        transfer(payment, raw, request.state.request_id, settings)
    except InvalidRequest as error:
        return _errors(request.state.request_id, error.errors)
    except SerializationExhausted:
        record_payment_batch("unavailable")
        record_payment_transaction_failure("serialization")
        logger.warning("Payment serialization retries exhausted")
        return JSONResponse(
            {"request_id": request.state.request_id, "detail": "Service unavailable"},
            status_code=503,
            headers={"Retry-After": str(settings.retry_after_seconds)},
        )
    except SQLAlchemyError:
        record_payment_batch("failed")
        record_payment_transaction_failure("database")
        logger.exception("Payment database failure")
        return JSONResponse(
            {"request_id": request.state.request_id, "detail": "Internal server error"},
            status_code=500,
        )
    record_payment_batch("accepted")
    logger.info(
        "Payment request committed", extra={"payment_count": len(payment.payments)}
    )
    return JSONResponse({"request_id": request.state.request_id}, status_code=201)
