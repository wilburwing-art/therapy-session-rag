"""therapist_invites table for multi-clinician practice support

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    role_enum = postgresql.ENUM(
        "therapist",
        "admin",
        name="therapist_invite_role",
    )
    role_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "therapist_invites",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("therapist", "admin", name="therapist_invite_role"),
            nullable=False,
            server_default="therapist",
        ),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(
        "ix_therapist_invites_organization_id",
        "therapist_invites",
        ["organization_id"],
    )
    op.create_index(
        "ix_therapist_invites_token_hash",
        "therapist_invites",
        ["token_hash"],
    )
    op.create_index(
        "ix_therapist_invites_org_accepted",
        "therapist_invites",
        ["organization_id", "accepted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_therapist_invites_org_accepted", table_name="therapist_invites"
    )
    op.drop_index(
        "ix_therapist_invites_token_hash", table_name="therapist_invites"
    )
    op.drop_index(
        "ix_therapist_invites_organization_id", table_name="therapist_invites"
    )
    op.drop_table("therapist_invites")
    sa.Enum(name="therapist_invite_role").drop(op.get_bind(), checkfirst=True)
