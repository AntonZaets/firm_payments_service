from alembic import context
from alembic.runtime.environment import NameFilterParentNames

import firm_payments_service.db.models
from firm_payments_service.config import Settings
from firm_payments_service.db.session import make_engine, metadata

settings = Settings()
_ = firm_payments_service.db.models


def include_name(
    name: str | None, type_: str, parent_names: NameFilterParentNames
) -> bool:
    if type_ == "schema":
        return name == "firm_payments_service"
    if type_ == "table":
        return parent_names["schema_qualified_table_name"] in metadata.tables
    return True


if context.is_offline_mode():
    context.configure(
        url=settings.database_url,
        target_metadata=metadata,
        literal_binds=True,
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=metadata,
                include_schemas=True,
                include_name=include_name,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
