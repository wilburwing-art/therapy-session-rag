"""homework_items table for patient between-session task tracking

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-04-21 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3b4c5d6e7f8"
down_revision: str | Sequence[str] | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "homework_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("task_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "session_id",
            "task_hash",
            name="uq_homework_items_session_task",
        ),
    )
    op.create_index(
        "ix_homework_items_session_id",
        "homework_items",
        ["session_id"],
    )
    op.create_index(
        "ix_homework_items_patient_id",
        "homework_items",
        ["patient_id"],
    )
    op.create_index(
        "ix_homework_items_organization_id",
        "homework_items",
        ["organization_id"],
    )
    op.create_index(
        "ix_homework_items_patient_completed",
        "homework_items",
        ["patient_id", "completed"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_homework_items_patient_completed", table_name="homework_items"
    )
    op.drop_index(
        "ix_homework_items_organization_id", table_name="homework_items"
    )
    op.drop_index("ix_homework_items_patient_id", table_name="homework_items")
    op.drop_index("ix_homework_items_session_id", table_name="homework_items")
    op.drop_table("homework_items")
