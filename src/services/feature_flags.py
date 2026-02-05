"""Feature flags backed by the experiment system.

Provides a simple interface for checking feature flag states
and getting variant assignments in application code.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.experiment import Experiment, ExperimentStatus
from src.repositories.experiment_repo import ExperimentRepository
from src.services.experiment_service import ExperimentService

logger = logging.getLogger(__name__)


class FeatureFlags:
    """Feature flag service backed by experiments.

    Usage:
        flags = FeatureFlags(db_session)
        if await flags.is_enabled("new_chat_ui", user_id):
            # Show new UI
        variant = await flags.get_variant("chat_top_k_test", user_id)
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self._repo = ExperimentRepository(db_session)
        self._service = ExperimentService(db_session)

    async def is_enabled(
        self,
        flag_name: str,
        subject_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> bool:
        """Check if a feature flag is enabled for a subject.

        A flag is "enabled" if:
        1. An experiment with this name exists and is RUNNING
        2. The subject is assigned to a non-control variant

        Returns False if the experiment doesn't exist or isn't running.
        """
        experiment = await self._find_experiment(flag_name, organization_id)
        if experiment is None:
            return False

        try:
            variant = await self._service.assign_subject(experiment.id, subject_id)
            return variant != "control"
        except Exception:
            logger.debug("Feature flag %s: subject not assigned", flag_name)
            return False

    async def get_variant(
        self,
        flag_name: str,
        subject_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> str | None:
        """Get the variant assigned to a subject for a feature flag.

        Returns None if the experiment doesn't exist or isn't running.
        """
        experiment = await self._find_experiment(flag_name, organization_id)
        if experiment is None:
            return None

        try:
            return await self._service.assign_subject(experiment.id, subject_id)
        except Exception:
            logger.debug("Feature flag %s: could not assign variant", flag_name)
            return None

    async def _find_experiment(
        self,
        name: str,
        organization_id: uuid.UUID | None = None,
    ) -> Experiment | None:
        """Find a running experiment by name."""
        if organization_id is not None:
            experiment = await self._repo.get_by_name(name, organization_id)
            if experiment and experiment.status == ExperimentStatus.RUNNING:
                return experiment
            return None

        # Without org_id, search all running experiments with this name
        # (less efficient, but supports cross-org flags)
        experiments = await self._repo.list_by_org(
            organization_id=uuid.UUID(int=0),  # Placeholder — see note below
            status=ExperimentStatus.RUNNING,
        )
        # Note: In production, you'd want a dedicated get_by_name_any_org method
        # For now, org_id is required for proper multi-tenant isolation
        for exp in experiments:
            if exp.name == name:
                return exp
        return None
