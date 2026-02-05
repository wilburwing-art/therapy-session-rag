"""Experiment database models for A/B testing and feature flags."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.db.base import Base, TimestampMixin


class ExperimentStatus(enum.StrEnum):
    """Status of an experiment."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class Experiment(Base, TimestampMixin):
    """A/B test experiment definition.

    Tracks experiment configuration, variants, and targeting rules.
    """

    __tablename__ = "experiments"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[ExperimentStatus] = mapped_column(
        Enum(ExperimentStatus, name="experiment_status"),
        nullable=False,
        default=ExperimentStatus.DRAFT,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    variants: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    targeting_rules: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    traffic_percentage: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_experiments_org_status", "organization_id", "status"),
    )


class ExperimentAssignment(Base, TimestampMixin):
    """Tracks which variant a subject is assigned to.

    Ensures consistent assignment — once assigned, a subject always
    sees the same variant for a given experiment.
    """

    __tablename__ = "experiment_assignments"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    variant: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_assignments_experiment_subject",
            "experiment_id",
            "subject_id",
            unique=True,
        ),
        Index("ix_assignments_subject", "subject_id"),
    )


class ExperimentMetric(Base):
    """Recorded metric observation for an experiment.

    Stores metric values per subject per experiment for statistical analysis.
    """

    __tablename__ = "experiment_metrics"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    metric_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    metric_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_metrics_experiment_metric", "experiment_id", "metric_name"),
        Index("ix_metrics_experiment_subject", "experiment_id", "subject_id"),
    )
