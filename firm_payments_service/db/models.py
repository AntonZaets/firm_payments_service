from sqlalchemy import JSON, BigInteger, Column, DateTime, Identity, Table, Uuid, func

from firm_payments_service.db.session import metadata

firm_payments_audit = Table(
    "firm_payments_audit",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),  # pyright: ignore[reportUnknownArgumentType]
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column("request_id", Uuid(as_uuid=True), nullable=False),
    Column("raw_request", JSON, nullable=False),
)
