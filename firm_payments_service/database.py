from sqlalchemy import Engine, MetaData, create_engine

from firm_payments_service.settings import Settings

metadata = MetaData()


def make_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 3},
    )
