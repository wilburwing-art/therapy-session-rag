"""Service layer for between-session homework tasks.

Two entry points:

1. ``materialize_from_recap`` — called from the summarization service
   after a recap is persisted. Writes one row per ``homework_assigned``
   entry, idempotently.
2. Patient / therapist list/mutation endpoints call this service to
   read and flip completion state.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.models.db.homework_item import HomeworkItem
from src.models.domain.homework import HomeworkItemRead
from src.repositories.homework_repo import HomeworkRepository

logger = logging.getLogger(__name__)


class HomeworkService:
    """Read/write access to the homework_items table."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.repo = HomeworkRepository(db_session)

    async def materialize_from_recap(
        self,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
        homework_assigned: list[dict[str, str | None]],
    ) -> int:
        """Persist the recap's homework_assigned list as homework_items.

        Idempotent on ``(session_id, task_hash)`` — re-running is safe.
        Returns the count of newly created rows (existing rows that
        collided are left unchanged so patient-edited completion state
        survives recap regeneration).
        """
        if not homework_assigned:
            return 0
        created = await self.repo.upsert_many_for_session(
            session_id=session_id,
            patient_id=patient_id,
            organization_id=organization_id,
            items=homework_assigned,
        )
        logger.info(
            "Materialized %d homework item(s) for session %s (patient=%s)",
            created,
            session_id,
            patient_id,
        )
        return created

    async def list_for_patient(
        self,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        completed: bool | None = None,
        limit: int = 100,
    ) -> list[HomeworkItemRead]:
        rows = await self.repo.list_for_patient(
            patient_id=patient_id,
            organization_id=organization_id,
            completed=completed,
            limit=limit,
        )
        return [self._to_read(row) for row in rows]

    async def toggle_completion(
        self,
        homework_id: uuid.UUID,
        patient_id: uuid.UUID,
        completed: bool,
    ) -> HomeworkItemRead:
        row = await self.repo.set_completed(
            homework_id=homework_id,
            patient_id=patient_id,
            completed=completed,
        )
        if row is None:
            raise NotFoundError(
                resource="HomeworkItem",
                resource_id=str(homework_id),
            )
        return self._to_read(row)

    @staticmethod
    def _to_read(row: HomeworkItem) -> HomeworkItemRead:
        return HomeworkItemRead(
            id=row.id,
            session_id=row.session_id,
            patient_id=row.patient_id,
            task=row.task,
            notes=row.notes,
            completed=row.completed,
            completed_at=row.completed_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
