from contextlib import nullcontext

import pytest
from sqlalchemy import create_engine, text

from firm_payments_service.db import session as db_session


@pytest.mark.parametrize("fail", [False, True])
def test_make_session_commits_or_rolls_back(
    monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db_session, "engine", engine)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE entries (id INTEGER)"))
        with pytest.raises(RuntimeError, match="abort") if fail else nullcontext():
            with db_session.make_session(isolation_level="SERIALIZABLE") as session:
                session.execute(text("INSERT INTO entries VALUES (1)"))
                if fail:
                    raise RuntimeError("abort")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM entries")) == (
                0 if fail else 1
            )
    finally:
        engine.dispose()
