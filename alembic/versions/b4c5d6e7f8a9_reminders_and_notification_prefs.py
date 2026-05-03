"""reminders_sent table and user notification preferences

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-04-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4c5d6e7f8a9"
down_revision: str | Sequence[str] | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- users: per-user notification preferences ----
    op.add_column(
        "users",
        sa.Column(
            "notification_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # ---- enums for reminders_sent ----
    reminder_kind_enum = postgresql.ENUM(
        "homework_due",
        "session_upcoming",
        "intake_pending",
        "assessment_due",
        name="reminder_kind",
    )
    reminder_kind_enum.create(op.get_bind(), checkfirst=True)

    reminder_channel_enum = postgresql.ENUM(
        "sms",
        "email",
        "in_app",
        name="reminder_channel",
    )
    reminder_channel_enum.create(op.get_bind(), checkfirst=True)

    reminder_status_enum = postgresql.ENUM(
        "queued",
        "sent",
        "failed",
        "skipped",
        name="reminder_status",
    )
    reminder_status_enum.create(op.get_bind(), checkfirst=True)

    # ---- reminders_sent ----
    op.create_table(
        "reminders_sent",
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
            "kind",
            sa.Enum(
                "homework_due",
                "session_upcoming",
                "intake_pending",
                "assessment_due",
                name="reminder_kind",
            ),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.Enum(
                "sms",
                "email",
                "in_app",
                name="reminder_channel",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "sent",
                "failed",
                "skipped",
                name="reminder_status",
            ),
            nullable=False,
        ),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("error", sa.String(length=1024), nullable=True),
        sa.Column(
            "reminder_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_reminders_sent_patient_id",
        "reminders_sent",
        ["patient_id"],
    )
    op.create_index(
        "ix_reminders_sent_dedupe",
        "reminders_sent",
        ["patient_id", "kind", "dedupe_key"],
        unique=True,
    )
    op.create_index(
        "ix_reminders_sent_patient_kind_created",
        "reminders_sent",
        ["patient_id", "kind", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reminders_sent_patient_kind_created", table_name="reminders_sent"
    )
    op.drop_index("ix_reminders_sent_dedupe", table_name="reminders_sent")
    op.drop_index("ix_reminders_sent_patient_id", table_name="reminders_sent")
    op.drop_table("reminders_sent")

    sa.Enum(name="reminder_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reminder_channel").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reminder_kind").drop(op.get_bind(), checkfirst=True)

    op.drop_column("users", "notification_preferences")
