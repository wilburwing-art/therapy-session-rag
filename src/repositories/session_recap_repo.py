"""Repository for session recap operations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.session_recap import SessionRecap


class SessionRecapRepository:
    """Data access for LLM-generated session recaps."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_session_id(self, session_id: uuid.UUID) -> SessionRecap | None:
        result = await self.session.execute(
            select(SessionRecap).where(SessionRecap.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        session_id: uuid.UUID,
        brief: str,
        key_topics: list[str],
        emotional_tone: str | None,
        homework_assigned: list[dict[str, str | None]],
        follow_ups: list[str],
        risk_flags: list[str],
        model_name: str,
    ) -> SessionRecap:
        """Create or replace the recap for a session.

        Recaps are re-generable; we delete any prior recap for the
        same session and insert a fresh one so timestamps reflect the
        latest generation.
        """
        await self.session.execute(
            delete(SessionRecap).where(SessionRecap.session_id == session_id)
        )
        recap = SessionRecap(
            session_id=session_id,
            brief=brief,
            key_topics=key_topics,
            emotional_tone=emotional_tone,
            homework_assigned=homework_assigned,
            follow_ups=follow_ups,
            risk_flags=risk_flags,
            model_name=model_name,
            generated_at=datetime.now(UTC),
        )
        self.session.add(recap)
        await self.session.flush()
        await self.session.refresh(recap)
        return recap

    async def delete_by_session_id(self, session_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(SessionRecap).where(SessionRecap.session_id == session_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)
