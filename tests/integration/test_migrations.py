from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from firm_payments_service.config import Settings
from firm_payments_service.payments.repository import insert_audit


def test_audit_schema_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = create_engine(Settings().database_url, isolation_level="AUTOCOMMIT")
    name = f"migration_tests_{uuid4().hex}"
    engine = create_engine(admin.url.set(database=name))
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        monkeypatch.setenv(
            "DATABASE_URL", engine.url.render_as_string(hide_password=False)
        )
        config = Config("alembic.ini")
        command.upgrade(config, "20261005_01")
        request_id = str(uuid4())
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.firm_payments_audit "
                    "(request_id, raw_request) "
                    "VALUES (:request_id, '{\"existing\": true}')"
                ),
                {"request_id": request_id},
            )
            connection.execute(
                text("GRANT SELECT ON public.firm_payments_audit TO PUBLIC")
            )
            original = connection.execute(
                text("SELECT * FROM public.firm_payments_audit")
            ).one()
            grants = connection.scalar(
                text(
                    "SELECT relacl FROM pg_class WHERE oid="
                    "'public.firm_payments_audit'::regclass"
                )
            )
            connection.execute(text("CREATE TABLE public.firms (id INTEGER)"))
            connection.execute(text("CREATE TABLE public.payments (id INTEGER)"))
            connection.execute(text("CREATE SCHEMA unrelated"))
            connection.execute(text("CREATE TABLE unrelated.other (id INTEGER)"))
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT to_regclass('public.firm_payments_audit')")
                )
                is None
            )
            assert (
                connection.execute(
                    text("SELECT * FROM firm_payments_service.firm_payments_audit")
                ).one()
                == original
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT relacl FROM pg_class WHERE oid="
                        "'firm_payments_service.firm_payments_audit'::regclass"
                    )
                )
                == grants
            )
        with Session(engine) as session:
            insert_audit(session, str(uuid4()), {"new": True})
            session.commit()
        command.downgrade(config, "20261005_01")
        with engine.begin() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM public.firm_payments_audit")
                )
                == 2
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT 1 FROM pg_namespace "
                        "WHERE nspname='firm_payments_service'"
                    )
                )
                is None
            )
            assert (
                connection.scalar(
                    text(
                        "INSERT INTO public.firm_payments_audit "
                        "(request_id, raw_request) "
                        "VALUES (:request_id, '{}') RETURNING id"
                    ),
                    {"request_id": str(uuid4())},
                )
                == 3
            )
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM firm_payments_service.firm_payments_audit"
                    )
                )
                == 3
            )
    finally:
        engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
