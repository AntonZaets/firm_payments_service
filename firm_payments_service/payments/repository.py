import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import Row, bindparam, text
from sqlalchemy.orm import Session

from firm_payments_service.api.schemas import Payment


def find_firms(session: Session, uuids: set[str]) -> list[Row[Any]]:
    return list(
        session.execute(
            text(
                "SELECT id, uuid, balance_cents FROM firms WHERE lower(uuid) IN :uuids"
            ).bindparams(bindparam("uuids", expanding=True)),
            {"uuids": tuple(uuids)},
        )
    )


def update_balances(session: Session, balances: Iterable[tuple[int, int]]) -> None:
    for firm_id, balance in sorted(balances):
        session.execute(
            text("UPDATE firms SET balance_cents=:balance WHERE id=:id"),
            {"id": firm_id, "balance": balance},
        )


def insert_payments(
    session: Session, payer_id: int, ids: dict[str, int], payments: list[Payment]
) -> None:
    session.execute(
        text(
            "INSERT INTO payments "
            "(payer_firm_id, payee_firm_id, amount_cents, description) "
            "VALUES (:payer, :payee, :amount, :description)"
        ),
        [
            {
                "payer": payer_id,
                "payee": ids[payment.payee_firm_uuid],
                "amount": payment.amount_cents,
                "description": payment.description,
            }
            for payment in payments
        ],
    )


def insert_audit(
    session: Session, request_id: str, raw_request: dict[str, Any]
) -> None:
    session.execute(
        text(
            "INSERT INTO firm_payments_audit (request_id, raw_request) "
            "VALUES (:request_id, CAST(:raw_request AS JSON))"
        ),
        {
            "request_id": request_id,
            "raw_request": json.dumps(raw_request),
        },
    )
