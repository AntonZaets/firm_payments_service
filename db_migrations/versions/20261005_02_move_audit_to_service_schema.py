"""Move the audit table into the service-owned PostgreSQL schema."""

from collections.abc import Sequence

from alembic import op

revision: str = "20261005_02"
down_revision: str | Sequence[str] | None = "20261005_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA firm_payments_service")
    op.execute(
        "ALTER TABLE public.firm_payments_audit SET SCHEMA firm_payments_service"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE firm_payments_service.firm_payments_audit SET SCHEMA public"
    )
    op.execute("DROP SCHEMA firm_payments_service")
