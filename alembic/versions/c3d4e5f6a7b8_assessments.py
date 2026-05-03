"""assessments table for PHQ-9 and GAD-7

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-21 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    instrument_enum = postgresql.ENUM(
        "phq9",
        "gad7",
        name="assessment_instrument",
    )
    instrument_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "assessments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "administered_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "instrument",
            sa.Enum("phq9", "gad7", name="assessment_instrument"),
            nullable=False,
        ),
        sa.Column(
            "responses",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("total_score", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.String(length=2048), nullable=True),
        sa.Column("administered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "assessment_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
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
    )
    op.create_index("ix_assessments_patient_id", "assessments", ["patient_id"])
    op.create_index(
        "ix_assessments_patient_instrument_date",
        "assessments",
        ["patient_id", "instrument", "administered_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assessments_patient_instrument_date", table_name="assessments"
    )
    op.drop_index("ix_assessments_patient_id", table_name="assessments")
    op.drop_table("assessments")
    sa.Enum(name="assessment_instrument").drop(op.get_bind(), checkfirst=True)
