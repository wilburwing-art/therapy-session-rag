"""Position 1 schema: human auth, subscriptions, recaps, themes, magic links

Revision ID: a1b2c3d4e5f6
Revises: 26cb062ab77b
Create Date: 2026-04-21 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "26cb062ab77b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- users: password-auth fields ----
    op.add_column(
        "users",
        sa.Column("full_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ---- organizations: subscription state ----
    subscription_status_enum = postgresql.ENUM(
        "none",
        "trialing",
        "active",
        "past_due",
        "incomplete",
        "unpaid",
        "canceled",
        name="subscription_status",
    )
    subscription_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "organizations",
        sa.Column("stripe_customer_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_organizations_stripe_customer_id",
        "organizations",
        ["stripe_customer_id"],
        unique=True,
    )
    op.add_column(
        "organizations",
        sa.Column("stripe_subscription_id", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_organizations_stripe_subscription_id",
        "organizations",
        ["stripe_subscription_id"],
    )
    op.add_column(
        "organizations",
        sa.Column(
            "subscription_status",
            sa.Enum(
                "none",
                "trialing",
                "active",
                "past_due",
                "incomplete",
                "unpaid",
                "canceled",
                name="subscription_status",
            ),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
    )

    # ---- session_recaps ----
    op.create_table(
        "session_recaps",
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
            unique=True,
        ),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column(
            "key_topics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("emotional_tone", sa.String(length=255), nullable=True),
        sa.Column(
            "homework_assigned",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "follow_ups",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "risk_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
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
        "ix_session_recaps_session_id",
        "session_recaps",
        ["session_id"],
    )

    # ---- patient_themes ----
    op.create_table(
        "patient_themes",
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
            unique=True,
        ),
        sa.Column(
            "recurring_topics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "emotional_patterns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "coping_strategies",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "progress_indicators",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "ongoing_concerns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "source_session_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
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
        "ix_patient_themes_patient_id",
        "patient_themes",
        ["patient_id"],
    )

    # ---- magic_links ----
    op.create_table(
        "magic_links",
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
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_magic_links_patient_id", "magic_links", ["patient_id"])
    op.create_index("ix_magic_links_token_hash", "magic_links", ["token_hash"])
    op.create_index(
        "ix_magic_links_patient_expires",
        "magic_links",
        ["patient_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_magic_links_patient_expires", table_name="magic_links")
    op.drop_index("ix_magic_links_token_hash", table_name="magic_links")
    op.drop_index("ix_magic_links_patient_id", table_name="magic_links")
    op.drop_table("magic_links")

    op.drop_index("ix_patient_themes_patient_id", table_name="patient_themes")
    op.drop_table("patient_themes")

    op.drop_index("ix_session_recaps_session_id", table_name="session_recaps")
    op.drop_table("session_recaps")

    op.drop_column("organizations", "current_period_end")
    op.drop_column("organizations", "trial_ends_at")
    op.drop_column("organizations", "subscription_status")
    op.drop_constraint(
        "uq_organizations_stripe_subscription_id",
        "organizations",
        type_="unique",
    )
    op.drop_column("organizations", "stripe_subscription_id")
    op.drop_index(
        "ix_organizations_stripe_customer_id", table_name="organizations"
    )
    op.drop_column("organizations", "stripe_customer_id")

    sa.Enum(name="subscription_status").drop(op.get_bind(), checkfirst=True)

    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "full_name")
