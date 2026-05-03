"""analytics retain_forever column + data_access category

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-04-21 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add retain_forever flag and data_access enum value.

    Postgres enum alters cannot run inside a transaction block, so the
    ADD VALUE statement must be committed outside Alembic's default
    transactional wrapper. We use ``op.execute`` with the standard
    autocommit=ON pattern that Alembic documents for Postgres enum
    changes.
    """
    # 1. Extend the event_category enum with DATA_ACCESS.
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE event_category ADD VALUE IF NOT EXISTS 'data_access'"
        )

    # 2. Add the retain_forever column. Defaults to false so existing
    # rows behave like before (eligible for the retention purge).
    op.add_column(
        "analytics_events",
        sa.Column(
            "retain_forever",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Drop the retain_forever column.

    Postgres does not support removing a value from an enum in place, so
    downgrading the enum addition is intentionally a no-op. Rows that
    used the ``data_access`` value would have to be rewritten before any
    destructive downgrade — left to the operator.
    """
    op.drop_column("analytics_events", "retain_forever")
