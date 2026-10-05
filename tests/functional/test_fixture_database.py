import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from .conftest import Failure, SeedFirm, Snapshot


@pytest.mark.parametrize("table", ["payments", "firm_payments_audit"])
def test_fixture_isolation_and_failure_trigger(
    db_engine: Engine,
    firm_factory: SeedFirm,
    database_snapshot: Snapshot,
    database_failure: Failure,
    table: str,
) -> None:
    # Both parameter cases must start empty despite committed data in the first.
    assert all(not rows for rows in database_snapshot().values())
    firm_factory()
    firm_factory()
    before = database_snapshot()
    database_failure(table)
    with pytest.raises(DBAPIError, match="private database failure"):
        with db_engine.begin() as connection:
            connection.execute(text("UPDATE firms SET balance_cents=0 WHERE id=1"))
            connection.execute(
                text(
                    "INSERT INTO payments (payer_firm_id, payee_firm_id, "
                    "amount_cents, "
                    "description) VALUES (1, 2, 100, 'first')"
                )
            )
            if table == "payments":
                connection.execute(
                    text(
                        "INSERT INTO payments (payer_firm_id, payee_firm_id, "
                        "amount_cents, "
                        "description) VALUES (1, 2, 100, 'reject-this-payment')"
                    )
                )
            else:
                connection.execute(
                    text(
                        "INSERT INTO firm_payments_audit (request_id, raw_request) "
                        "VALUES ('00000000-0000-0000-0000-000000000001', '{}'::json)"
                    )
                )
    assert database_snapshot() == before
