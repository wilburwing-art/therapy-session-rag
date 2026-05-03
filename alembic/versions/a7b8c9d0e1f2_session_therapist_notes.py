"""session_therapist_notes

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-21 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add therapist_notes column to sessions."""
    op.add_column(
        "sessions",
        sa.Column("therapist_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop therapist_notes column from sessions."""
    op.drop_column("sessions", "therapist_notes")
