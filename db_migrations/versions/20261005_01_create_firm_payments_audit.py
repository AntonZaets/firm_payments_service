"""Create the service-owned payment audit table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "firm_payments_audit",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("raw_request", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("firm_payments_audit")
