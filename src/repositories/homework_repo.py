"""Repository for homework item operations."""

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.homework_item import HomeworkItem
from src.models.db.session import Session


class HomeworkRepository:
    """Data access for between-session homework tasks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def hash_task(task: str) -> str:
        """Produce a stable 64-char hex hash of the normalized task.

        Used as the idempotency key for (session_id, task_hash).
        """
        normalized = " ".join(task.strip().lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    async def upsert_many_for_session(
        self,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
        items: list[dict[str, str | None]],
    ) -> int:
        """Insert homework rows for ``session_id`` if they don't already exist.

        Each item dict must have ``task`` (str) and optional ``notes`` (str | None).
        Rows that collide with the ``(session_id, task_hash)`` unique index
        are left untouched — we intentionally do *not* overwrite notes or
        reset completion, because patients may have already ticked them
        off. Returns the number of rows newly inserted.
        """
        if not items:
            return 0

        rows: list[dict[str, str | None | uuid.UUID]] = []
        seen_hashes: set[str] = set()
        for item in items:
            task = item.get("task")
            if not isinstance(task, str) or not task.strip():
                continue
            task_hash = self.hash_task(task)
            if task_hash in seen_hashes:
                continue
            seen_hashes.add(task_hash)
            notes = item.get("notes")
            rows.append(
                {
                    "session_id": session_id,
                    "patient_id": patient_id,
                    "organization_id": organization_id,
                    "task": task.strip(),
                    "notes": notes if isinstance(notes, str) else None,
                    "task_hash": task_hash,
                }
            )

        if not rows:
            return 0

        stmt = (
            pg_insert(HomeworkItem)
            .values(rows)
            .on_conflict_do_nothing(
                constraint="uq_homework_items_session_task",
            )
        )
        result = await self.session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def list_for_patient(
        self,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        completed: bool | None = None,
        limit: int = 100,
    ) -> list[HomeworkItem]:
        """List a patient's homework, newest session first.

        ``organization_id`` scopes the query for therapist access.
        Patient-facing callers pass ``None`` (auth comes from the user's
        patient token, which is already tied to the patient_id).
        """
        stmt = (
            select(HomeworkItem)
            .join(Session, Session.id == HomeworkItem.session_id)
            .where(HomeworkItem.patient_id == patient_id)
        )
        if organization_id is not None:
            stmt = stmt.where(HomeworkItem.organization_id == organization_id)
        if completed is not None:
            stmt = stmt.where(HomeworkItem.completed == completed)
        stmt = stmt.order_by(Session.session_date.desc(), HomeworkItem.created_at.asc())
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_patient(
        self,
        homework_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> HomeworkItem | None:
        """Fetch a single row, scoped to the patient that owns it."""
        result = await self.session.execute(
            select(HomeworkItem).where(
                HomeworkItem.id == homework_id,
                HomeworkItem.patient_id == patient_id,
            )
        )
        return result.scalar_one_or_none()

    async def set_completed(
        self,
        homework_id: uuid.UUID,
        patient_id: uuid.UUID,
        completed: bool,
    ) -> HomeworkItem | None:
        """Flip completion state. Returns the updated row or None if missing."""
        row = await self.get_for_patient(homework_id, patient_id)
        if row is None:
            return None
        row.completed = completed
        row.completed_at = datetime.now(UTC) if completed else None
        await self.session.flush()
        await self.session.refresh(row)
        return row
