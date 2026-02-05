"""Experiment service for A/B testing lifecycle management."""

from __future__ import annotations

import hashlib
import logging
import math
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.experiment import (
    Experiment,
    ExperimentAssignment,
    ExperimentMetric,
    ExperimentStatus,
)
from src.models.domain.experiment import (
    ExperimentCreate,
    ExperimentRead,
    ExperimentResults,
    ExperimentUpdate,
    VariantStats,
)
from src.repositories.experiment_repo import ExperimentRepository

logger = logging.getLogger(__name__)


class ExperimentServiceError(Exception):
    """Error in experiment service."""


class ExperimentService:
    """Manages experiment lifecycle: create, assign, record, analyze."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._repo = ExperimentRepository(db_session)

    async def create_experiment(
        self,
        data: ExperimentCreate,
        organization_id: uuid.UUID,
    ) -> ExperimentRead:
        """Create a new experiment."""
        if not data.variants or len(data.variants) < 2:
            raise ExperimentServiceError("Experiment must have at least 2 variants")

        existing = await self._repo.get_by_name(data.name, organization_id)
        if existing:
            raise ExperimentServiceError(f"Experiment '{data.name}' already exists")

        experiment = Experiment(
            name=data.name,
            description=data.description,
            status=ExperimentStatus.DRAFT,
            organization_id=organization_id,
            variants=data.variants,
            targeting_rules=data.targeting_rules,
            traffic_percentage=data.traffic_percentage,
        )
        created = await self._repo.create(experiment)
        return ExperimentRead.model_validate(created)

    async def get_experiment(self, experiment_id: uuid.UUID) -> ExperimentRead | None:
        """Get experiment by ID."""
        experiment = await self._repo.get_by_id(experiment_id)
        if experiment is None:
            return None
        return ExperimentRead.model_validate(experiment)

    async def list_experiments(
        self,
        organization_id: uuid.UUID,
        status: ExperimentStatus | None = None,
    ) -> list[ExperimentRead]:
        """List experiments for an organization."""
        experiments = await self._repo.list_by_org(organization_id, status=status)
        return [ExperimentRead.model_validate(e) for e in experiments]

    async def update_experiment(
        self,
        experiment_id: uuid.UUID,
        data: ExperimentUpdate,
    ) -> ExperimentRead:
        """Update experiment settings (only DRAFT experiments)."""
        experiment = await self._repo.get_by_id(experiment_id)
        if experiment is None:
            raise ExperimentServiceError("Experiment not found")
        if experiment.status != ExperimentStatus.DRAFT:
            raise ExperimentServiceError("Can only update DRAFT experiments")

        if data.description is not None:
            experiment.description = data.description
        if data.variants is not None:
            experiment.variants = data.variants
        if data.targeting_rules is not None:
            experiment.targeting_rules = data.targeting_rules
        if data.traffic_percentage is not None:
            experiment.traffic_percentage = data.traffic_percentage

        return ExperimentRead.model_validate(experiment)

    async def start_experiment(self, experiment_id: uuid.UUID) -> ExperimentRead:
        """Start a DRAFT experiment."""
        experiment = await self._repo.get_by_id(experiment_id)
        if experiment is None:
            raise ExperimentServiceError("Experiment not found")
        if experiment.status != ExperimentStatus.DRAFT:
            raise ExperimentServiceError("Can only start DRAFT experiments")

        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.now(UTC)
        return ExperimentRead.model_validate(experiment)

    async def stop_experiment(self, experiment_id: uuid.UUID) -> ExperimentRead:
        """Stop a RUNNING experiment."""
        experiment = await self._repo.get_by_id(experiment_id)
        if experiment is None:
            raise ExperimentServiceError("Experiment not found")
        if experiment.status != ExperimentStatus.RUNNING:
            raise ExperimentServiceError("Can only stop RUNNING experiments")

        experiment.status = ExperimentStatus.COMPLETED
        experiment.ended_at = datetime.now(UTC)
        return ExperimentRead.model_validate(experiment)

    async def assign_subject(
        self,
        experiment_id: uuid.UUID,
        subject_id: uuid.UUID,
    ) -> str:
        """Assign a subject to a variant.

        Uses deterministic hashing for consistent assignment.
        Returns the assigned variant name.
        """
        experiment = await self._repo.get_by_id(experiment_id)
        if experiment is None:
            raise ExperimentServiceError("Experiment not found")
        if experiment.status != ExperimentStatus.RUNNING:
            raise ExperimentServiceError("Experiment is not running")

        # Check existing assignment
        existing = await self._repo.get_assignment(experiment_id, subject_id)
        if existing:
            return existing.variant

        # Check traffic percentage
        if not self._is_in_traffic(experiment_id, subject_id, experiment.traffic_percentage):
            raise ExperimentServiceError("Subject not in experiment traffic")

        # Deterministic variant assignment
        variant_names = sorted(experiment.variants.keys())
        variant = self._hash_assign(experiment_id, subject_id, variant_names)

        assignment = ExperimentAssignment(
            experiment_id=experiment_id,
            subject_id=subject_id,
            variant=variant,
        )
        await self._repo.create_assignment(assignment)
        return variant

    async def record_metric(
        self,
        experiment_id: uuid.UUID,
        subject_id: uuid.UUID,
        metric_name: str,
        metric_value: float,
    ) -> None:
        """Record a metric observation for a subject."""
        metric = ExperimentMetric(
            experiment_id=experiment_id,
            subject_id=subject_id,
            metric_name=metric_name,
            metric_value=metric_value,
        )
        await self._repo.record_metric(metric)

    async def get_results(
        self,
        experiment_id: uuid.UUID,
        metric_name: str,
        confidence_level: float = 0.95,
    ) -> ExperimentResults:
        """Compute experiment results with statistical significance.

        Uses Welch's t-test for comparing variant means.
        """
        experiment = await self._repo.get_by_id(experiment_id)
        if experiment is None:
            raise ExperimentServiceError("Experiment not found")

        stats = await self._repo.get_metric_stats(experiment_id, metric_name)

        variant_stats: dict[str, VariantStats] = {}
        for variant_name, count, mean, stddev, min_val, max_val in stats:
            variant_stats[variant_name] = VariantStats(
                variant_name=variant_name,
                subject_count=count,
                metric_mean=round(mean, 4),
                metric_std=round(stddev, 4),
                metric_min=round(min_val, 4),
                metric_max=round(max_val, 4),
            )

        # Compute significance if we have exactly 2 variants with data
        p_value: float | None = None
        is_significant = False

        variant_list = list(variant_stats.values())
        if len(variant_list) == 2:
            a, b = variant_list[0], variant_list[1]
            if a.subject_count >= 2 and b.subject_count >= 2:
                p_value = self._welch_t_test(
                    a.metric_mean, a.metric_std, a.subject_count,
                    b.metric_mean, b.metric_std, b.subject_count,
                )
                is_significant = p_value < (1 - confidence_level)

        return ExperimentResults(
            experiment_id=experiment_id,
            experiment_name=experiment.name,
            status=ExperimentRead.model_validate(experiment).status,
            variant_stats=variant_stats,
            is_significant=is_significant,
            p_value=round(p_value, 6) if p_value is not None else None,
            confidence_level=confidence_level,
        )

    @staticmethod
    def _hash_assign(
        experiment_id: uuid.UUID,
        subject_id: uuid.UUID,
        variant_names: list[str],
    ) -> str:
        """Deterministically assign a subject to a variant using hashing."""
        key = f"{experiment_id}:{subject_id}"
        hash_val = int(hashlib.sha256(key.encode()).hexdigest(), 16)
        index = hash_val % len(variant_names)
        return variant_names[index]

    @staticmethod
    def _is_in_traffic(
        experiment_id: uuid.UUID,
        subject_id: uuid.UUID,
        traffic_percentage: int,
    ) -> bool:
        """Check if subject falls within the traffic percentage."""
        if traffic_percentage >= 100:
            return True
        key = f"traffic:{experiment_id}:{subject_id}"
        hash_val = int(hashlib.md5(key.encode()).hexdigest(), 16)  # noqa: S324
        bucket = hash_val % 100
        return bucket < traffic_percentage

    @staticmethod
    def _welch_t_test(
        mean_a: float, std_a: float, n_a: int,
        mean_b: float, std_b: float, n_b: int,
    ) -> float:
        """Welch's t-test for unequal variances.

        Returns approximate p-value using normal approximation
        (sufficient for large samples).
        """
        if std_a == 0 and std_b == 0:
            return 1.0 if mean_a == mean_b else 0.0

        se = math.sqrt((std_a ** 2 / n_a) + (std_b ** 2 / n_b))
        if se == 0:
            return 1.0

        t_stat = abs(mean_a - mean_b) / se

        # Approximate p-value using normal CDF (valid for df > 30)
        # For smaller samples this is approximate but avoids scipy dependency
        p_value = 2 * (1 - _normal_cdf(t_stat))
        return max(p_value, 1e-10)


def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF using Abramowitz and Stegun formula."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
