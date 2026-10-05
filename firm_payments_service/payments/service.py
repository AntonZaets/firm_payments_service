import time
from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from firm_payments_service.api.schemas import (
    INTEGER_MAX,
    BulkPayment,
    Error,
    InvalidRequest,
)
from firm_payments_service.config import Settings
from firm_payments_service.db.session import make_session
from firm_payments_service.payments import repository


class SerializationExhausted(Exception):
    pass


def _is_serialization_failure(error: DBAPIError) -> bool:
    return getattr(error.orig, "sqlstate", None) == "40001"


def _attempt(
    request: BulkPayment,
    raw_request: dict[str, Any],
    request_id: str,
    settings: Settings,
) -> None:
    with make_session() as session:
        try:
            session.connection(execution_options={"isolation_level": "SERIALIZABLE"})
            session.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": f"{settings.statement_timeout_ms}ms"},
            )
            session.execute(
                text("SELECT set_config('lock_timeout', :timeout, true)"),
                {"timeout": f"{settings.lock_timeout_ms}ms"},
            )
            rows = repository.find_firms(
                session,
                {
                    request.payer_firm_uuid,
                    *(payment.payee_firm_uuid for payment in request.payments),
                },
            )
            resolved: dict[str, list[tuple[int, int]]] = defaultdict(list)
            for row in rows:
                resolved[str(row.uuid).lower()].append((row.id, row.balance_cents))
            if any(
                len(resolved[uuid]) != 1
                for uuid in {
                    request.payer_firm_uuid,
                    *(p.payee_firm_uuid for p in request.payments),
                }
            ):
                raise InvalidRequest(
                    [
                        Error(
                            "UNKNOWN_FIRM",
                            "A firm UUID does not resolve to exactly one firm.",
                        )
                    ]
                )
            ids = {uuid: values[0][0] for uuid, values in resolved.items()}
            balances = {values[0][0]: values[0][1] for values in resolved.values()}
            payer_id = ids[request.payer_firm_uuid]
            total = sum(payment.amount_cents for payment in request.payments)
            if balances[payer_id] < total:
                raise InvalidRequest(
                    [
                        Error(
                            "INSUFFICIENT_FUNDS",
                            "Payer balance is below the payment total.",
                        )
                    ]
                )
            changes: dict[int, int] = defaultdict(int, {payer_id: -total})
            for payment in request.payments:
                changes[ids[payment.payee_firm_uuid]] += payment.amount_cents
            updated = [
                (firm_id, balances[firm_id] + change)
                for firm_id, change in changes.items()
            ]
            if any(
                not -INTEGER_MAX - 1 <= balance <= INTEGER_MAX for _, balance in updated
            ):
                raise InvalidRequest(
                    [
                        Error(
                            "INVALID_AMOUNT",
                            "A resulting balance exceeds the supported range.",
                        )
                    ]
                )
            repository.update_balances(session, updated)
            repository.insert_payments(session, payer_id, ids, request.payments)
            repository.insert_audit(session, request_id, raw_request)
            session.commit()
        except Exception:
            session.rollback()
            raise


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
            if not _is_serialization_failure(error):
                raise
            if attempt + 1 == settings.serialization_attempts:
                raise SerializationExhausted from error
            time.sleep(settings.serialization_retry_delay_ms / 1_000)
