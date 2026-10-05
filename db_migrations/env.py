from alembic import context

import firm_payments_service.db.models
from firm_payments_service.config import Settings
from firm_payments_service.db.session import make_engine, metadata

settings = Settings()
_ = firm_payments_service.db.models

if context.is_offline_mode():
    context.configure(
        url=settings.database_url,
        target_metadata=metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
