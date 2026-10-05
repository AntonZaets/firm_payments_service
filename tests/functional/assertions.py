from typing import Any
from uuid import UUID

from httpx2 import Response
from sqlalchemy import Engine, text

from .factories import Firm, Payload


def assert_success(
    response: Response,
    engine: Engine,
    firms: list[Firm],
    payload: Payload,
    balances: list[int],
    cents: list[int],
    *,
    submissions: int = 1,
) -> None:
    assert response.status_code == 201, response.text
    request_id = response.json()["request_id"]
    assert str(UUID(request_id)) == request_id
    assert response.headers["X-Request-ID"] == request_id
    ids = {firm.uuid: firm.id for firm in firms}
    with engine.connect() as connection:
        actual = dict(
            connection.execute(text("SELECT id, balance_cents FROM firms"))
            .tuples()
            .all()
        )
        assert actual == dict(zip([firm.id for firm in firms], balances, strict=True))
        assert sum(actual.values()) == sum(firm.balance_cents for firm in firms)
        rows = (
            connection.execute(
                text(
                    "SELECT payer_firm_id, payee_firm_id, amount_cents, "
                    "description FROM payments"
                )
            )
            .tuples()
            .all()
        )
        expected = [
            (
                ids[payload["payer_firm_uuid"]],
                ids[payment["payee_firm_uuid"]],
                amount,
                payment["description"],
            )
            for payment, amount in zip(payload["payments"], cents, strict=True)
        ] * submissions
        assert sorted(rows) == sorted(expected)
        audits = (
            connection.execute(
                text(
                    "SELECT request_id, raw_request, created_at "
                    "FROM firm_payments_audit"
                )
            )
            .tuples()
            .all()
        )
        assert len(audits) == submissions
        assert len({row[0] for row in audits}) == submissions
        assert request_id in {str(row[0]) for row in audits}
        assert all(row[1] == payload and row[2] is not None for row in audits)


def assert_rejected(
    response: Response,
    before: dict[str, list[tuple[Any, ...]]],
    after: dict[str, list[tuple[Any, ...]]],
    code: str | None,
) -> None:
    assert response.status_code == 422, response.text
    body = response.json()
    assert str(UUID(body["request_id"])) == body["request_id"]
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["errors"]
    assert all(error["code"] and error["details"] for error in body["errors"])
    if code:
        assert code in {error["code"] for error in body["errors"]}
    assert after == before
