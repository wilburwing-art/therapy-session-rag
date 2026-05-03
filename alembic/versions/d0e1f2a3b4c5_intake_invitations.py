"""intake_invitations — patient intake forms, invitations, and responses

Adds three tables that power a pre-first-session intake flow:

- ``intake_forms``: per-organization questionnaire templates. Questions
  live in a JSONB column so practices can customise without schema
  migrations.
- ``intake_invitations``: one-time tokenised invites sent to prospective
  patients. Tokens are stored hashed.
- ``intake_responses``: a patient's submitted answers for an invitation.
  One response per invitation (enforced by UNIQUE on ``invitation_id``).

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-04-21 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d0e1f2a3b4c5"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    form_status_enum = postgresql.ENUM(
        "draft",
        "active",
        "archived",
        name="intake_form_status",
    )
    form_status_enum.create(op.get_bind(), checkfirst=True)

    invitation_status_enum = postgresql.ENUM(
        "pending",
        "submitted",
        "expired",
        "revoked",
        name="intake_invitation_status",
    )
    invitation_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "intake_forms",
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
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "archived", name="intake_form_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "questions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
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
    op.create_index(
        "ix_intake_forms_organization_id",
        "intake_forms",
        ["organization_id"],
    )
    op.create_index(
        "ix_intake_forms_org_status",
        "intake_forms",
        ["organization_id", "status"],
    )

    op.create_table(
        "intake_invitations",
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
            "form_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("intake_forms.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("patient_email", sa.String(length=255), nullable=False),
        sa.Column("patient_name", sa.String(length=255), nullable=True),
        sa.Column(
            "token_hash",
            sa.String(length=128),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "submitted",
                "expired",
                "revoked",
                name="intake_invitation_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_intake_invitations_organization_id",
        "intake_invitations",
        ["organization_id"],
    )
    op.create_index(
        "ix_intake_invitations_token_hash",
        "intake_invitations",
        ["token_hash"],
    )
    op.create_index(
        "ix_intake_invitations_org_status",
        "intake_invitations",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_intake_invitations_org_email",
        "intake_invitations",
        ["organization_id", "patient_email"],
    )

    op.create_table(
        "intake_responses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "invitation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("intake_invitations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "form_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("intake_forms.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "answers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("submitted_ip", sa.String(length=64), nullable=True),
        sa.Column("submitted_user_agent", sa.String(length=512), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
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
        "ix_intake_responses_invitation_id",
        "intake_responses",
        ["invitation_id"],
    )
    op.create_index(
        "ix_intake_responses_organization_id",
        "intake_responses",
        ["organization_id"],
    )
    op.create_index(
        "ix_intake_responses_org_submitted",
        "intake_responses",
        ["organization_id", "submitted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intake_responses_org_submitted", table_name="intake_responses"
    )
    op.drop_index(
        "ix_intake_responses_organization_id", table_name="intake_responses"
    )
    op.drop_index(
        "ix_intake_responses_invitation_id", table_name="intake_responses"
    )
    op.drop_table("intake_responses")

    op.drop_index(
        "ix_intake_invitations_org_email", table_name="intake_invitations"
    )
    op.drop_index(
        "ix_intake_invitations_org_status", table_name="intake_invitations"
    )
    op.drop_index(
        "ix_intake_invitations_token_hash", table_name="intake_invitations"
    )
    op.drop_index(
        "ix_intake_invitations_organization_id", table_name="intake_invitations"
    )
    op.drop_table("intake_invitations")

    op.drop_index("ix_intake_forms_org_status", table_name="intake_forms")
    op.drop_index(
        "ix_intake_forms_organization_id", table_name="intake_forms"
    )
    op.drop_table("intake_forms")

    sa.Enum(name="intake_invitation_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="intake_form_status").drop(op.get_bind(), checkfirst=True)
