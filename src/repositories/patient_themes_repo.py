"""Repository for patient theme operations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.patient_themes import PatientThemes
from src.models.db.session import Session, SessionStatus
from src.models.db.session_recap import SessionRecap


class PatientThemesRepository:
    """Data access for cross-session patient themes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_patient_id(self, patient_id: uuid.UUID) -> PatientThemes | None:
        result = await self.session.execute(
            select(PatientThemes).where(PatientThemes.patient_id == patient_id)
        )
        return result.scalar_one_or_none()

    async def list_recaps_for_patient(
        self,
        patient_id: uuid.UUID,
        limit: int = 25,
    ) -> list[SessionRecap]:
        """Return the most recent session recaps for a patient.

        Joins via sessions so we can scope to the patient. Ordered by
        session_date desc so themes reflect current state.
        """
        stmt = (
            select(SessionRecap)
            .join(Session, Session.id == SessionRecap.session_id)
            .where(
                Session.patient_id == patient_id,
                Session.status == SessionStatus.READY,
            )
            .order_by(Session.session_date.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        patient_id: uuid.UUID,
        recurring_topics: list[dict[str, str | int | None]],
        emotional_patterns: list[dict[str, str | None]],
        coping_strategies: list[dict[str, str | None]],
        progress_indicators: list[str],
        ongoing_concerns: list[str],
        source_session_count: int,
        model_name: str,
    ) -> PatientThemes:
        await self.session.execute(
            delete(PatientThemes).where(PatientThemes.patient_id == patient_id)
        )
        themes = PatientThemes(
            patient_id=patient_id,
            recurring_topics=recurring_topics,
            emotional_patterns=emotional_patterns,
            coping_strategies=coping_strategies,
            progress_indicators=progress_indicators,
            ongoing_concerns=ongoing_concerns,
            source_session_count=source_session_count,
            model_name=model_name,
            generated_at=datetime.now(UTC),
        )
        self.session.add(themes)
        await self.session.flush()
        await self.session.refresh(themes)
        return themes
