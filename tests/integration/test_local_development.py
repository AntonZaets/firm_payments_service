import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from firm_payments_service.api.schemas import validate_request
from firm_payments_service.config import Settings
from firm_payments_service.db import session
from firm_payments_service.payments.service import transfer


def test_local_example_and_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = create_engine(Settings().database_url, isolation_level="AUTOCOMMIT")
    name = f"local_tests_{uuid4().hex}"
    engine = create_engine(admin.url.set(database=name))
    created = False
    bootstrap = Path("local/bootstrap.sql").read_text()
    payload = json.loads(Path("local/payment.json").read_text())
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        monkeypatch.setenv(
            "DATABASE_URL", engine.url.render_as_string(hide_password=False)
        )
        monkeypatch.setattr(session, "engine", engine)
        with engine.connect() as connection:
            connection.exec_driver_sql(bootstrap)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert [
                tuple(row)
                for row in connection.execute(
                    text("SELECT id, name, balance_cents, uuid FROM firms ORDER BY id")
                )
            ] == [
                (
                    1,
                    "Pinecrest CPA Group",
                    5_000_000,
                    "3f1c9a2e-7b4d-4c1e-9a55-2d8e6f0b7c41",
                ),
                (
                    2,
                    "Lopez Bookkeeping",
                    50_000,
                    "8b2e4c71-0d3a-4f6e-b1c9-5a7d2e9f4c10",
                ),
                (
                    3,
                    "Nair Tax Services",
                    200_000,
                    "e5f18b3c-2a9d-4c07-8e6b-1d4a7f9c3b25",
                ),
            ]
        request_id = str(uuid4())
        settings = Settings()
        transfer(validate_request(payload, settings), payload, request_id, settings)
        with engine.begin() as connection:
            assert (
                connection.scalar(
                    text(
                        "INSERT INTO firms (name, balance_cents, uuid) "
                        "VALUES ('Extra firm', 0, :uuid) RETURNING id"
                    ),
                    {"uuid": str(uuid4())},
                )
                == 4
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM payments WHERE id IN (1, 2, 3)")
                )
                == 3
            )
        with engine.connect() as connection:
            connection.exec_driver_sql(bootstrap)
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert list(
                connection.execute(
                    text("SELECT balance_cents FROM firms ORDER BY id")
                ).scalars()
            ) == [3_674_875, 170_075, 1_405_050, 0]
            assert [
                tuple(row)
                for row in connection.execute(
                    text(
                        "SELECT payer_firm_id, payee_firm_id, "
                        "amount_cents, description "
                        "FROM payments ORDER BY id"
                    )
                )
            ] == [
                (1, 3, 625_000, "Overflow returns, August 2026"),
                (1, 3, 580_050, "Amended returns, August 2026"),
                (1, 2, 120_075, "Bookkeeping cleanup, 3 clients"),
            ]
            audit = connection.execute(
                text(
                    "SELECT request_id, raw_request "
                    "FROM firm_payments_service.firm_payments_audit"
                )
            ).one()
            assert str(audit.request_id) == request_id
            assert audit.raw_request == payload
    finally:
        engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
