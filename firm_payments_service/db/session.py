from sqlalchemy import Engine, MetaData, create_engine

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
