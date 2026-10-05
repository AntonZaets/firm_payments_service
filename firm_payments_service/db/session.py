from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, MetaData, create_engine, text
from sqlalchemy.orm import Session

from firm_payments_service.config import Settings

metadata = MetaData()


def make_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 3},
    )


engine = make_engine(Settings())


@contextmanager
def make_session(
    *,
    isolation_level: str | None = None,
    statement_timeout_ms: int | None = None,
    lock_timeout_ms: int | None = None,
) -> Generator[Session]:
    with Session(engine) as session, session.begin():
        if isolation_level is not None:
            session.connection(execution_options={"isolation_level": isolation_level})
        for name, timeout_ms in (
            ("statement_timeout", statement_timeout_ms),
            ("lock_timeout", lock_timeout_ms),
        ):
            if timeout_ms is not None:
                session.execute(
                    text("SELECT set_config(:name, :timeout, true)"),
                    {"name": name, "timeout": f"{timeout_ms}ms"},
                )
        yield session
