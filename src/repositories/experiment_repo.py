"""Repository for experiment operations."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.experiment import (
    Experiment,
    ExperimentAssignment,
    ExperimentMetric,
    ExperimentStatus,
)


class ExperimentRepository:
    """Database operations for experiments, assignments, and metrics."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Experiments ---

    async def create(self, experiment: Experiment) -> Experiment:
        """Create a new experiment."""
        self.session.add(experiment)
        await self.session.flush()
        return experiment

    async def get_by_id(self, experiment_id: uuid.UUID) -> Experiment | None:
        """Get experiment by ID."""
        result = await self.session.execute(
            select(Experiment).where(Experiment.id == experiment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(
        self, name: str, organization_id: uuid.UUID
    ) -> Experiment | None:
        """Get experiment by name within an organization."""
        result = await self.session.execute(
            select(Experiment).where(
                and_(
                    Experiment.name == name,
                    Experiment.organization_id == organization_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_org(
        self,
        organization_id: uuid.UUID,
        status: ExperimentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Experiment]:
        """List experiments for an organization."""
        conditions: list[Any] = [Experiment.organization_id == organization_id]
        if status is not None:
            conditions.append(Experiment.status == status)

        stmt = (
            select(Experiment)
            .where(and_(*conditions))
            .order_by(Experiment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # --- Assignments ---

    async def get_assignment(
        self, experiment_id: uuid.UUID, subject_id: uuid.UUID
    ) -> ExperimentAssignment | None:
        """Get existing assignment for a subject in an experiment."""
        result = await self.session.execute(
            select(ExperimentAssignment).where(
                and_(
                    ExperimentAssignment.experiment_id == experiment_id,
                    ExperimentAssignment.subject_id == subject_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def create_assignment(
        self, assignment: ExperimentAssignment
    ) -> ExperimentAssignment:
        """Create a new assignment."""
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def count_assignments_by_variant(
        self, experiment_id: uuid.UUID
    ) -> list[tuple[str, int]]:
        """Count assignments per variant for an experiment."""
        stmt = (
            select(
                ExperimentAssignment.variant,
                func.count().label("count"),
            )
            .where(ExperimentAssignment.experiment_id == experiment_id)
            .group_by(ExperimentAssignment.variant)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    # --- Metrics ---

    async def record_metric(self, metric: ExperimentMetric) -> ExperimentMetric:
        """Record a metric observation."""
        self.session.add(metric)
        await self.session.flush()
        return metric

    async def get_metric_stats(
        self, experiment_id: uuid.UUID, metric_name: str
    ) -> list[tuple[str, int, float, float, float, float]]:
        """Get metric statistics grouped by variant.

        Returns: list of (variant, count, mean, stddev, min, max) tuples.
        """
        stmt = (
            select(
                ExperimentAssignment.variant,
                func.count(ExperimentMetric.id).label("count"),
                func.avg(ExperimentMetric.metric_value).label("mean"),
                func.coalesce(func.stddev(ExperimentMetric.metric_value), 0.0).label("stddev"),
                func.min(ExperimentMetric.metric_value).label("min_val"),
                func.max(ExperimentMetric.metric_value).label("max_val"),
            )
            .join(
                ExperimentAssignment,
                and_(
                    ExperimentAssignment.experiment_id == ExperimentMetric.experiment_id,
                    ExperimentAssignment.subject_id == ExperimentMetric.subject_id,
                ),
            )
            .where(
                and_(
                    ExperimentMetric.experiment_id == experiment_id,
                    ExperimentMetric.metric_name == metric_name,
                )
            )
            .group_by(ExperimentAssignment.variant)
        )
        result = await self.session.execute(stmt)
        return [
            (row[0], row[1], float(row[2]), float(row[3]), float(row[4]), float(row[5]))
            for row in result.all()
        ]
