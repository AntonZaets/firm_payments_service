import time
from collections import defaultdict
from typing import Any

from sqlalchemy.exc import DBAPIError, NoResultFound
from sqlalchemy.orm import Session

from firm_payments_service.api.schemas import (
    BulkPayment,
    Error,
    InvalidRequest,
)
from firm_payments_service.config import Settings
from firm_payments_service.db.session import make_session
from firm_payments_service.payments import repository


class SerializationExhausted(Exception):
    pass


def _resolve_firm_ids(session: Session, request: BulkPayment) -> dict[str, int]:
    uuids = {
        request.payer_firm_uuid,
        *(payment.payee_firm_uuid for payment in request.payments),
    }
    rows = repository.find_firms(session, uuids)
    firm_ids = {str(row.uuid).lower(): row.id for row in rows}
    if len(rows) != len(firm_ids) or firm_ids.keys() != uuids:
        raise InvalidRequest(
            [
                Error(
                    "UNKNOWN_FIRM",
                    "A firm UUID does not resolve to exactly one firm.",
                )
            ]
        )
    return firm_ids


def _update_balances(session: Session, changes: dict[int, int]) -> None:
    try:
        repository.update_balances(session, changes.items())
    except NoResultFound as error:
        raise InvalidRequest(
            [
                Error(
                    "INSUFFICIENT_FUNDS",
                    "Payer balance is below the payment total.",
                )
            ]
        ) from error
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) != "22003":
            raise
        raise InvalidRequest(
            [
                Error(
                    "INVALID_AMOUNT",
                    "A resulting balance exceeds the supported range.",
                )
            ]
        ) from error


def _attempt(
    request: BulkPayment,
    raw_request: dict[str, Any],
    request_id: str,
    settings: Settings,
) -> None:
    with make_session(
        isolation_level="SERIALIZABLE",
        statement_timeout_ms=settings.statement_timeout_ms,
        lock_timeout_ms=settings.lock_timeout_ms,
    ) as session:
        firm_ids = _resolve_firm_ids(session, request)
        payer_id = firm_ids[request.payer_firm_uuid]
        total = sum(payment.amount_cents for payment in request.payments)
        balance_changes: dict[int, int] = defaultdict(int, {payer_id: -total})
        for payment in request.payments:
            balance_changes[firm_ids[payment.payee_firm_uuid]] += payment.amount_cents
        _update_balances(session, balance_changes)
        repository.insert_payments(session, payer_id, firm_ids, request.payments)
        repository.insert_audit(session, request_id, raw_request)


def transfer(
    request: BulkPayment,
    raw_request: dict[str, Any],
    request_id: str,
    settings: Settings,
) -> None:
    for attempt in range(settings.serialization_attempts):
        try:
            _attempt(request, raw_request, request_id, settings)
            return
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) != "40001":
                raise
            if attempt + 1 == settings.serialization_attempts:
                raise SerializationExhausted from error
            time.sleep(settings.serialization_retry_delay_ms / 1_000)
