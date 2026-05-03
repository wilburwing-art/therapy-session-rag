"""webhook_endpoints + webhook_deliveries for customer outbound events

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-04-21 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a3b4c5d6e7"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
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
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("secret", sa.String(length=128), nullable=False),
        sa.Column(
            "event_types",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "last_rotated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_webhook_endpoints_organization_id",
        "webhook_endpoints",
        ["organization_id"],
    )
    op.create_index(
        "ix_webhook_endpoints_org_active",
        "webhook_endpoints",
        ["organization_id", "is_active"],
    )

    delivery_status_enum = postgresql.ENUM(
        "pending",
        "in_flight",
        "delivered",
        "failed",
        name="webhook_delivery_status",
    )
    delivery_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "webhook_deliveries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "endpoint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "event_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "in_flight",
                "delivered",
                "failed",
                name="webhook_delivery_status",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body_snippet", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_attempt_at", sa.DateTime(timezone=True), nullable=True
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
        "ix_webhook_deliveries_endpoint_id",
        "webhook_deliveries",
        ["endpoint_id"],
    )
    op.create_index(
        "ix_webhook_deliveries_organization_id",
        "webhook_deliveries",
        ["organization_id"],
    )
    op.create_index(
        "ix_webhook_deliveries_status_next",
        "webhook_deliveries",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_webhook_deliveries_status_next", table_name="webhook_deliveries"
    )
    op.drop_index(
        "ix_webhook_deliveries_organization_id",
        table_name="webhook_deliveries",
    )
    op.drop_index(
        "ix_webhook_deliveries_endpoint_id", table_name="webhook_deliveries"
    )
    op.drop_table("webhook_deliveries")
    sa.Enum(name="webhook_delivery_status").drop(op.get_bind(), checkfirst=True)

    op.drop_index(
        "ix_webhook_endpoints_org_active", table_name="webhook_endpoints"
    )
    op.drop_index(
        "ix_webhook_endpoints_organization_id", table_name="webhook_endpoints"
    )
    op.drop_table("webhook_endpoints")
